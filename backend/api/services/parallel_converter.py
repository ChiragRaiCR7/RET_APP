
"""
Parallel XML to CSV/XLSX converter optimized for high-volume processing.

Features:
- Multiprocessing worker pool with configurable size (default 32 workers)
- Memory-efficient streaming for huge XML files
- Rolling in-flight task submission for 100,000+ files with low memory usage
- Progress logging and optional callback
- Automatic error recovery and retry logic
- Windows-safe worker clamping (prevents max_workers > Windows limit)

REFINEMENTS (per requirement):
- Output filenames are derived from "real names" (logical_path) when provided.
- Output filenames are always UPPERCASE.
- Collision handling is deterministic using __SHA8 suffix (NO random _1, _2).
- Backwards compatible: path_to_logical is optional.
"""

import csv
import logging
import os
import re
import sys
import time
import hashlib
from pathlib import Path
from typing import List, Dict, Optional, Set, Tuple, Any, Callable, Iterator
from dataclasses import dataclass, field
from concurrent.futures import ProcessPoolExecutor, as_completed, Future

from api.services.xml_processing_service import (
    xml_to_rows,
    xml_to_rows_streaming,
    infer_group,
    STREAMING_THRESHOLD_MB,
)
from api.services.xlsx_service import csv_to_xlsx_bytes
from api.core.config import settings

logger = logging.getLogger(__name__)

# Configuration from settings with fallbacks
DEFAULT_WORKERS = int(getattr(settings, "CONVERSION_DEFAULT_WORKERS", 32))
MAX_WORKERS = int(getattr(settings, "CONVERSION_MAX_WORKERS", 64))

# Note: "BATCH_SIZE" retained for compatibility, but rolling in-flight is used instead.
BATCH_SIZE = int(getattr(settings, "CONVERSION_BATCH_SIZE", 1000))

PROGRESS_LOG_INTERVAL = int(getattr(settings, "CONVERSION_PROGRESS_LOG_INTERVAL", 100))

MEMORY_EFFICIENT_THRESHOLD_MB = float(
    getattr(settings, "CONVERSION_STREAMING_THRESHOLD_MB", STREAMING_THRESHOLD_MB)
)

# Retry behavior
MAX_RETRIES = int(getattr(settings, "CONVERSION_MAX_RETRIES", 1))  # 0/1/2...
RETRY_BACKOFF_SEC = float(getattr(settings, "CONVERSION_RETRY_BACKOFF_SEC", 0.05))


# ---------------------------------------------------------------------
# Output naming helpers (REAL NAME + UPPERCASE + deterministic collisions)
# ---------------------------------------------------------------------

_INVALID_CHARS = re.compile(r'[^A-Za-z0-9._\- ]+')
_MULTI_SPACE = re.compile(r"\s+")
_MAX_STEM_LEN = 160  # keep safe for most filesystems


def _sha8(s: str) -> str:
    return hashlib.sha1(s.encode("utf-8")).hexdigest()[:8].upper()


def _safe_stem_from_logical(logical_path: str) -> str:
    """
    Extract stem from logical_path base name and sanitize:
    - take base name (drop directories)
    - remove extension
    - replace invalid chars
    - collapse spaces
    - trim length
    """
    lp = (logical_path or "").replace("\\", "/")
    base = Path(lp).name or "FILE"
    stem = Path(base).stem or "FILE"

    # sanitize
    stem = _INVALID_CHARS.sub("_", stem)
    stem = _MULTI_SPACE.sub(" ", stem).strip()
    if not stem:
        stem = "FILE"

    # enforce length
    if len(stem) > _MAX_STEM_LEN:
        stem = stem[:_MAX_STEM_LEN].rstrip("_ ").strip()

    return stem


def _unique_output_name_from_logical(
    logical_path: str,
    out_ext: str,
    used_names: Set[str],
) -> str:
    """
    Deterministic output name:
    - primary: <STEM><ext> in UPPERCASE
    - collision: <STEM>__<SHA8><ext> in UPPERCASE
    No random counters.
    """
    stem = _safe_stem_from_logical(logical_path)
    candidate = f"{stem}{out_ext}".upper()

    if candidate not in used_names:
        used_names.add(candidate)
        return candidate

    # deterministic collision suffix
    suffix = _sha8(logical_path or candidate)
    candidate2 = f"{stem}__{suffix}{out_ext}".upper()
    used_names.add(candidate2)
    return candidate2


# ---------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------

@dataclass(frozen=True)
class ConversionTask:
    """Single file conversion task"""
    xml_path: Path
    output_dir: Path
    group: str
    output_format: str = "csv"
    csv_name: str = ""            # output CSV name (already UPPERCASE)
    logical_path: str = ""        # "real name" source (zip chain + member path etc.)


@dataclass
class ConversionResult:
    """Result of a single file conversion"""
    success: bool
    filename: str
    group: str
    rows: int = 0
    columns: int = 0
    format: str = "csv"
    file_type: str = "csv"
    logical_path: str = ""
    error: str = ""
    processing_time: float = 0.0


@dataclass
class ConversionStats:
    """Overall conversion statistics"""
    total_files: int = 0
    success: int = 0
    failed: int = 0
    skipped: int = 0
    total_rows: int = 0
    total_duration: float = 0.0
    group_stats: Dict[str, int] = field(default_factory=dict)

    @property
    def average_time_per_file(self) -> float:
        if self.success > 0:
            return self.total_duration / self.success
        return 0.0


# ---------------------------------------------------------------------
# Worker count clamping (Windows-safe)
# ---------------------------------------------------------------------

def _windows_max_workers_limit() -> int:
    """
    On Windows, ProcessPoolExecutor has a hard upper limit (commonly 61).
    In Python 3.13 this is enforced internally, raising ValueError if exceeded.
    We attempt to read the internal constant; fallback to 61.
    """
    if sys.platform != "win32":
        return 10**9
    try:
        from concurrent.futures.process import _MAX_WINDOWS_WORKERS  # type: ignore
        return int(_MAX_WINDOWS_WORKERS)
    except Exception:
        return 61


def _clamp_worker_count(requested: Optional[int], *, large_file_ratio: float = 0.0) -> int:
    """
    Effective workers:
    - If requested is None -> choose MAX_WORKERS bounded by platform.
    - Clamp by:
        1) settings MAX_WORKERS
        2) Windows hard limit
        3) >= 1
        4) cpu-based soft cap (adjusted for workload)

    When many files are large (streaming), reduce concurrency to avoid
    memory pressure.  ``large_file_ratio`` is the fraction of files above
    the streaming threshold (0.0 – 1.0).
    """
    platform_cap = _windows_max_workers_limit()
    cpu = os.cpu_count() or 1

    workers = MAX_WORKERS if requested is None else int(requested)
    workers = max(1, workers)

    # CPU-aware soft cap: I/O-heavy small files benefit from more workers,
    # but CPU/memory-heavy large files should use fewer.
    if large_file_ratio > 0.5:
        soft_cap = max(2, cpu * 2)
    elif large_file_ratio > 0.2:
        soft_cap = max(4, cpu * 4)
    else:
        soft_cap = max(4, cpu * 8)

    workers = min(workers, MAX_WORKERS, platform_cap, soft_cap)

    return workers


# ---------------------------------------------------------------------
# Worker function
# ---------------------------------------------------------------------

def _convert_single_file(task: ConversionTask) -> ConversionResult:
    """
    Worker function to convert a single XML file to CSV/XLSX.
    Runs in a separate process.
    Uses streaming for large files to minimize memory usage.
    """
    start_time = time.time()

    try:
        file_size_mb = task.xml_path.stat().st_size / (1024 * 1024)
        use_streaming = file_size_mb > MEMORY_EFFICIENT_THRESHOLD_MB

        csv_path = task.output_dir / task.csv_name
        total_rows = 0
        total_columns = 0
        tag_used = ""

        if use_streaming:
            headers_written = False
            writer = None

            with open(csv_path, "w", newline="", encoding="utf-8") as csv_file:
                for rows_chunk, headers, tag_used in xml_to_rows_streaming(
                    task.xml_path,
                    record_tag=None,
                    auto_detect=True,
                    path_sep=".",
                    include_root=False,
                    max_field_len=300,
                    chunk_size=10000,
                ):
                    if not headers_written:
                        writer = csv.DictWriter(csv_file, fieldnames=headers)
                        writer.writeheader()
                        headers_written = True
                        total_columns = len(headers)

                    if writer and rows_chunk:
                        for r in rows_chunk:
                            writer.writerow({h: r.get(h, "") for h in headers})
                            total_rows += 1

            if total_rows == 0:
                return ConversionResult(
                    success=False,
                    filename=task.csv_name,
                    group=task.group,
                    format="csv",
                    file_type="csv",
                    logical_path=task.logical_path,
                    error="No records found in XML (streaming)",
                    processing_time=time.time() - start_time,
                )

        else:
            with open(task.xml_path, "rb") as f:
                xml_bytes = f.read()

            rows, headers, tag_used = xml_to_rows(
                xml_bytes,
                record_tag=None,
                auto_detect=True,
                path_sep=".",
                include_root=False,
                max_field_len=300,
            )

            if not rows:
                return ConversionResult(
                    success=False,
                    filename=task.csv_name,
                    group=task.group,
                    format="csv",
                    file_type="csv",
                    logical_path=task.logical_path,
                    error="No records found in XML",
                    processing_time=time.time() - start_time,
                )

            with open(csv_path, "w", newline="", encoding="utf-8") as outf:
                writer = csv.DictWriter(outf, fieldnames=headers)
                writer.writeheader()
                for r in rows:
                    writer.writerow({h: r.get(h, "") for h in headers})

            total_rows = len(rows)
            total_columns = len(headers)

        result_filename = task.csv_name
        result_format = "csv"
        result_file_type = "csv"

        # Convert to XLSX if requested
        if task.output_format == "xlsx":
            try:
                xlsx_name = task.csv_name.replace(".CSV", ".XLSX")
                xlsx_path = task.output_dir / xlsx_name

                # For large files, limit XLSX conversion for safety
                max_rows = None
                if file_size_mb > MEMORY_EFFICIENT_THRESHOLD_MB:
                    max_rows = 50000

                xlsx_bytes = csv_to_xlsx_bytes(str(csv_path), max_rows=max_rows)
                with open(xlsx_path, "wb") as f:
                    f.write(xlsx_bytes)

                result_filename = xlsx_name
                result_format = "xlsx"
                result_file_type = "xlsx"
            except Exception as xlsx_err:
                logger.debug(f"XLSX conversion failed for {task.csv_name}: {xlsx_err}")
                # Keep CSV if XLSX fails

        return ConversionResult(
            success=True,
            filename=result_filename,
            group=task.group,
            rows=total_rows,
            columns=total_columns,
            format=result_format,
            file_type=result_file_type,
            logical_path=task.logical_path,
            processing_time=time.time() - start_time,
        )

    except Exception as e:
        logger.exception(f"Failed to convert {task.xml_path.name}: {e}")
        return ConversionResult(
            success=False,
            filename=task.csv_name,
            group=task.group,
            format="csv",
            file_type="csv",
            logical_path=task.logical_path,
            error=str(e),
            processing_time=time.time() - start_time,
        )


# ---------------------------------------------------------------------
# Main parallel conversion entry point
# ---------------------------------------------------------------------

def convert_parallel(
    session_id: str,
    extract_dir: Path,
    output_dir: Path,
    xml_files: List[Path],
    path_to_group: Dict[str, str],
    groups_filter: Optional[List[str]] = None,
    output_format: str = "csv",
    num_workers: Optional[int] = None,
    progress_callback: Optional[Callable[[int, int, ConversionStats], None]] = None,

    # ✅ NEW (optional): abs XML path -> logical_path (real name)
    path_to_logical: Optional[Dict[str, str]] = None,
) -> Tuple[ConversionStats, List[Dict], List[Dict]]:
    """
    Convert multiple XML files to CSV/XLSX in parallel using multiprocessing.

    Windows-safe: clamps worker count to platform limit.
    Memory-safe for huge volume: rolling submission of tasks.
    Includes retry logic for failed conversions.

    NEW:
    - If path_to_logical is supplied, output filenames are derived from logical_path
      and are UPPERCASE, deterministic, collision-safe (no random _1 suffixes).
    - Results include logical_path + file_type.
    """
    from api.utils.metrics import timed_block

    conversion_start = time.time()

    stats = ConversionStats(total_files=len(xml_files))
    converted_files: List[Dict] = []
    errors: List[Dict] = []

    used_output_names: Set[str] = set()

    groups_filter_set = set(groups_filter) if groups_filter else None
    logical_map = path_to_logical or {}

    # Build tasks and collect file sizes for workload classification
    tasks: List[ConversionTask] = []
    task_sizes: List[int] = []           # parallel list, bytes per task
    streaming_threshold = int(MEMORY_EFFICIENT_THRESHOLD_MB * 1024 * 1024)

    for xml_file in xml_files:
        abs_path_str = str(xml_file)
        relative_path = str(xml_file.relative_to(extract_dir)).replace("\\", "/")

        # group (prefer provided mapping)
        if abs_path_str in path_to_group:
            group = path_to_group[abs_path_str]
        else:
            group = infer_group(relative_path, xml_file.name)

        if groups_filter_set and group not in groups_filter_set:
            stats.skipped += 1
            continue

        # logical path (prefer provided mapping; fallback to relative path)
        logical_path = logical_map.get(abs_path_str) or relative_path

        # output name derived from logical (real) name
        csv_name = _unique_output_name_from_logical(logical_path, ".CSV", used_output_names)

        try:
            fsize = xml_file.stat().st_size
        except OSError:
            fsize = 0

        tasks.append(
            ConversionTask(
                xml_path=xml_file,
                output_dir=output_dir,
                group=group,
                output_format=output_format,
                csv_name=csv_name,
                logical_path=logical_path,
            )
        )
        task_sizes.append(fsize)

    if not tasks:
        logger.warning(f"  No files to convert after filtering (skipped: {stats.skipped})")
        stats.total_duration = time.time() - conversion_start
        return stats, converted_files, errors

    # -- Workload classification --
    large_count = sum(1 for sz in task_sizes if sz >= streaming_threshold)
    large_file_ratio = large_count / len(tasks) if tasks else 0.0

    # Sort tasks: large files first so they start early and don't create tail latency
    if len(tasks) > 1:
        paired = list(zip(task_sizes, tasks))
        paired.sort(key=lambda p: p[0], reverse=True)
        task_sizes = [p[0] for p in paired]
        tasks = [p[1] for p in paired]

    # Adaptive worker count using workload profile
    effective_workers = _clamp_worker_count(num_workers, large_file_ratio=large_file_ratio)

    # Adaptive in-flight cap: fewer in-flight for large/streaming files
    if large_file_ratio > 0.5:
        max_in_flight = max(1, effective_workers * 2)
    else:
        max_in_flight = max(1, effective_workers * 4)

    logger.info("========== Starting Parallel Conversion ==========")
    logger.info(f"  Session: {session_id}")
    logger.info(f"  Total XML files discovered: {len(xml_files)}")
    logger.info(f"  Requested workers: {num_workers if num_workers is not None else 'AUTO(MAX)'}")
    logger.info(f"  Effective workers: {effective_workers}")
    logger.info(f"  Output format: {output_format}")
    logger.info(f"  Groups filter: {groups_filter or 'ALL'}")
    logger.info(f"  Logical naming: {'ENABLED' if path_to_logical else 'FALLBACK(relative-path)'}")
    logger.info(f"  Large files (>{MEMORY_EFFICIENT_THRESHOLD_MB:.0f}MB): {large_count}/{len(tasks)} ({large_file_ratio:.0%})")
    logger.info(f"  Max in-flight: {max_in_flight}")
    logger.info(f"  Files to process: {len(tasks)}")
    logger.info(f"  Files skipped by filter: {stats.skipped}")

    processed_count = 0
    last_log_time = time.time()

    retries: Dict[str, int] = {}

    def task_key(t: ConversionTask) -> str:
        return f"{str(t.xml_path)}::{t.csv_name}"

    def submit_next(
        executor: ProcessPoolExecutor,
        it: Iterator[ConversionTask],
        future_map: Dict[Future, ConversionTask],
    ) -> bool:
        nxt = next(it, None)
        if nxt is None:
            return False
        fut = executor.submit(_convert_single_file, nxt)
        future_map[fut] = nxt
        return True

    with ProcessPoolExecutor(max_workers=effective_workers) as executor:
        it = iter(tasks)
        future_to_task: Dict[Future, ConversionTask] = {}

        # prime
        for _ in range(min(max_in_flight, len(tasks))):
            if not submit_next(executor, it, future_to_task):
                break

        while future_to_task:
            for future in as_completed(list(future_to_task.keys())):
                task = future_to_task.pop(future)
                processed_count += 1

                try:
                    result: ConversionResult = future.result()

                    if result.success:
                        stats.success += 1
                        stats.total_rows += result.rows
                        stats.group_stats[result.group] = stats.group_stats.get(result.group, 0) + 1

                        converted_files.append(
                            {
                                "filename": (result.filename or "").upper(),
                                "group": result.group,
                                "rows": result.rows,
                                "columns": result.columns,
                                "format": result.format,
                                "file_type": result.file_type,
                                "logical_path": result.logical_path,
                            }
                        )
                    else:
                        key = task_key(task)
                        attempt = retries.get(key, 0)
                        if attempt < MAX_RETRIES:
                            retries[key] = attempt + 1
                            if RETRY_BACKOFF_SEC:
                                time.sleep(RETRY_BACKOFF_SEC)
                            fut = executor.submit(_convert_single_file, task)
                            future_to_task[fut] = task
                        else:
                            stats.failed += 1
                            errors.append({"file": (result.filename or task.csv_name).upper(), "error": result.error})

                except Exception as e:
                    key = task_key(task)
                    attempt = retries.get(key, 0)
                    if attempt < MAX_RETRIES:
                        retries[key] = attempt + 1
                        if RETRY_BACKOFF_SEC:
                            time.sleep(RETRY_BACKOFF_SEC)
                        fut = executor.submit(_convert_single_file, task)
                        future_to_task[fut] = task
                    else:
                        stats.failed += 1
                        logger.exception(f"Task execution failed for {task.xml_path.name}: {e}")
                        errors.append({"file": task.csv_name.upper(), "error": f"Task execution failed: {str(e)}"})

                # refill pipeline
                while len(future_to_task) < max_in_flight:
                    if not submit_next(executor, it, future_to_task):
                        break

                # progress logs + callback
                current_time = time.time()
                if processed_count % PROGRESS_LOG_INTERVAL == 0 or (current_time - last_log_time) > 30:
                    elapsed = current_time - conversion_start
                    rate = processed_count / elapsed if elapsed > 0 else 0
                    remaining = max(0, len(tasks) - processed_count)
                    eta = remaining / rate if rate > 0 else 0
                    percent = (processed_count / len(tasks)) * 100

                    logger.info(
                        f"  Progress: {processed_count}/{len(tasks)} ({percent:.1f}%) | "
                        f"Success: {stats.success} | Failed: {stats.failed} | Skipped: {stats.skipped} | "
                        f"Rate: {rate:.1f} files/s | ETA: {eta:.0f}s"
                    )
                    last_log_time = current_time

                    if progress_callback:
                        try:
                            progress_callback(processed_count, len(tasks), stats)
                        except Exception as cb_err:
                            logger.debug(f"Progress callback error: {cb_err}")

                # break to refresh as_completed list
                break

    stats.total_duration = time.time() - conversion_start

    # Emit structured perf metric
    try:
        from api.utils.metrics import timed_block
        import logging as _logging
        _perf_logger = _logging.getLogger("ret.metrics")
        _perf_logger.info(
            "perf_metric: convert_parallel %.1fms",
            stats.total_duration * 1000,
            extra={"extra_fields": {
                "op": "convert_parallel",
                "elapsed_ms": round(stats.total_duration * 1000, 2),
                "items": len(tasks),
                "items_per_sec": round(len(tasks) / max(stats.total_duration, 0.001), 1),
                "success": stats.success,
                "failed": stats.failed,
                "workers": effective_workers,
            }},
        )
    except Exception:
        pass

    logger.info("========== Parallel Conversion Complete ==========")
    logger.info(f"  Duration: {stats.total_duration:.2f}s")
    logger.info(f"  Processed: {len(tasks)} files")
    logger.info(f"  Success: {stats.success}")
    logger.info(f"  Failed: {stats.failed}")
    logger.info(f"  Skipped: {stats.skipped}")
    logger.info(f"  Total rows: {stats.total_rows:,}")
    logger.info(f"  Average: {stats.average_time_per_file:.3f}s per file")
    logger.info(f"  Throughput: {len(tasks) / stats.total_duration:.1f} files/s")

    if stats.group_stats:
        logger.info("  Files by group:")
        for grp, count in sorted(stats.group_stats.items()):
            logger.info(f"    {grp}: {count} files")

    return stats, converted_files, errors


def estimate_conversion_time(num_files: int, avg_file_size_mb: float, num_workers: int = DEFAULT_WORKERS) -> float:
    """
    Estimate conversion time based on file count and size.
    Returns estimated time in seconds.
    """
    if avg_file_size_mb < 1:
        time_per_file = 0.1
    elif avg_file_size_mb < 10:
        time_per_file = 0.5
    else:
        time_per_file = 2.0

    effective_workers = max(1, min(int(num_workers), MAX_WORKERS, _windows_max_workers_limit()))
    estimated_time = (num_files * time_per_file) / effective_workers
    return estimated_time * 1.2
