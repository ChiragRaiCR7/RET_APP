"""
ZIP Scanning Service for RET App
Handles ZIP file extraction with nested ZIP support,
safety limits, and progress tracking.
"""
import zipfile
import time
from pathlib import Path
from typing import List, Dict, Optional, Tuple, Any, Callable
from dataclasses import dataclass, field
from collections import Counter
import logging

from api.services.rag_service import XmlEntry, infer_group, sha_short

logger = logging.getLogger(__name__)


# ============================================================
# Configuration
# ============================================================
DEFAULT_MAX_DEPTH = 50
DEFAULT_MAX_FILES = 10000
DEFAULT_MAX_TOTAL_MB = 10000
DEFAULT_MAX_PER_FILE_MB = 1000
DEFAULT_MAX_COMPRESSION_RATIO = 200
DEFAULT_NESTED_ZIP_MB = 256
DEFAULT_TOTAL_COPY_MB = 512


@dataclass
class ZipPlan:
    """Plan for ZIP extraction."""
    total_compressed_bytes: int
    total_entries: int
    zips: List[Tuple[Path, str, int]]  # (path, prefix, depth)


@dataclass
class ScanResult:
    """Result from ZIP scanning."""
    xml_entries: List[XmlEntry]
    group_counts: Dict[str, int]
    total_extracted_bytes: int
    total_entries: int
    elapsed_seconds: float
    errors: List[str] = field(default_factory=list)


# ============================================================
# Utility Functions
# ============================================================
def _zip_entry_ratio(zi: zipfile.ZipInfo) -> float:
    """Calculate compression ratio of a ZIP entry."""
    comp = getattr(zi, "compress_size", 0) or 0
    uncomp = getattr(zi, "file_size", 0) or 0
    if comp <= 0:
        return float("inf") if uncomp > 0 else 1.0
    return uncomp / comp


def safe_display(text: str, max_len: int = 100) -> str:
    """Safely display text by sanitizing special characters."""
    if not text:
        return ""
    safe = text.replace("\x00", "").replace("\n", " ").replace("\r", "")
    return (safe[:max_len] + "…") if len(safe) > max_len else safe


# ============================================================
# ZIP Planning
# ============================================================
def plan_zip_work(
    zip_path: Path,
    temp_dir: Path,
    max_depth: int = DEFAULT_MAX_DEPTH,
    max_ratio: int = DEFAULT_MAX_COMPRESSION_RATIO,
    plan_max_total_copy_mb: Optional[int] = None,
    plan_max_nested_zip_mb: Optional[int] = None,
) -> ZipPlan:
    """
    Plan ZIP extraction work by scanning all ZIPs including nested ones.
    
    Args:
        zip_path: Path to the main ZIP file
        temp_dir: Directory for extracting nested ZIPs
        max_depth: Maximum nesting depth
        max_ratio: Maximum compression ratio allowed
        plan_max_total_copy_mb: Maximum total MB to copy during planning
        plan_max_nested_zip_mb: Maximum MB per nested ZIP
    
    Returns:
        ZipPlan with all ZIPs to process
    """
    nested_root = temp_dir / "nested_zips_plan"
    nested_root.mkdir(parents=True, exist_ok=True)
    
    total_cap = (plan_max_total_copy_mb or DEFAULT_TOTAL_COPY_MB) * 1024 * 1024
    per_nested_cap = (plan_max_nested_zip_mb or DEFAULT_NESTED_ZIP_MB) * 1024 * 1024
    
    stack: List[Tuple[Path, str, int]] = [(zip_path, "", 0)]
    all_zips: List[Tuple[Path, str, int]] = []
    total_comp = 0
    total_entries = 0
    total_copied = 0
    CHUNK = 1024 * 1024
    
    while stack:
        zpath, base_prefix, depth = stack.pop()
        all_zips.append((zpath, base_prefix, depth))
        
        try:
            with zipfile.ZipFile(str(zpath)) as z:
                infos = z.infolist()
                total_entries += len(infos)
                total_comp += sum((getattr(i, "compress_size", 0) or 0) for i in infos)
                
                for zi in infos:
                    if zi.is_dir():
                        continue
                    if depth >= max_depth:
                        continue
                    
                    lower = zi.filename.lower()
                    if not lower.endswith(".zip"):
                        continue
                    
                    # Check compression ratio
                    try:
                        ratio = _zip_entry_ratio(zi)
                        if ratio > max_ratio and (zi.file_size or 0) > 50_000:
                            continue
                    except Exception:
                        pass
                    
                    nested_uncomp = int(zi.file_size or 0)
                    if nested_uncomp > per_nested_cap:
                        continue
                    if total_copied + nested_uncomp > total_cap:
                        continue
                    
                    logical_path = f"{base_prefix}/{zi.filename}" if base_prefix else zi.filename
                    nested_stub = f"nestedplan__{sha_short(logical_path, 16)}"
                    nested_file = nested_root / f"{nested_stub}.zip"
                    
                    if not nested_file.exists():
                        written = 0
                        try:
                            with z.open(zi) as src, open(nested_file, "wb") as dst:
                                while True:
                                    buf = src.read(CHUNK)
                                    if not buf:
                                        break
                                    written += len(buf)
                                    if written > per_nested_cap:
                                        raise ValueError("Nested zip exceeded per-plan cap")
                                    if total_copied + written > total_cap:
                                        raise ValueError("Plan phase exceeded total copy cap")
                                    dst.write(buf)
                            total_copied += written
                        except Exception:
                            try:
                                if nested_file.exists():
                                    nested_file.unlink()
                            except Exception:
                                pass
                            continue
                    
                    stack.append((nested_file, logical_path, depth + 1))
        
        except zipfile.BadZipFile:
            continue
        except Exception as e:
            logger.error(f"Error planning ZIP {zpath}: {e}")
            continue
    
    return ZipPlan(
        total_compressed_bytes=total_comp,
        total_entries=total_entries,
        zips=all_zips
    )


# ============================================================
# XML Collection from ZIP
# ============================================================
def collect_xml_from_zip(
    zip_path: Path,
    temp_dir: Path,
    max_depth: int = DEFAULT_MAX_DEPTH,
    max_files: int = DEFAULT_MAX_FILES,
    max_total_bytes: int = None,
    max_per_file_bytes: int = None,
    max_ratio: int = DEFAULT_MAX_COMPRESSION_RATIO,
    plan: Optional[ZipPlan] = None,
    custom_prefixes: Optional[set] = None,
    progress_cb: Optional[Callable[[float, str, Dict[str, Any]], None]] = None,
) -> ScanResult:
    """
    Collect XML files from a ZIP (including nested ZIPs).
    
    Args:
        zip_path: Path to the ZIP file
        temp_dir: Directory for temporary extraction
        max_depth: Maximum nesting depth
        max_files: Maximum number of XML files to extract
        max_total_bytes: Maximum total bytes to extract
        max_per_file_bytes: Maximum bytes per file
        max_ratio: Maximum compression ratio
        plan: Optional pre-computed plan
        custom_prefixes: Custom group prefixes
        progress_cb: Progress callback (progress, label, stats)
    
    Returns:
        ScanResult with XML entries and statistics
    """
    max_total_bytes = max_total_bytes or (DEFAULT_MAX_TOTAL_MB * 1024 * 1024)
    max_per_file_bytes = max_per_file_bytes or (DEFAULT_MAX_PER_FILE_MB * 1024 * 1024)
    per_nested_cap = DEFAULT_NESTED_ZIP_MB * 1024 * 1024
    custom_prefixes = custom_prefixes or set()
    
    results: List[XmlEntry] = []
    errors: List[str] = []
    stack: List[Tuple[Path, str, int]] = [(zip_path, "", 0)]
    total_extracted = 0
    CHUNK = 1024 * 1024
    
    xml_root = temp_dir / "xml_inputs"
    xml_root.mkdir(parents=True, exist_ok=True)
    nested_root = temp_dir / "nested_zips"
    nested_root.mkdir(parents=True, exist_ok=True)
    
    # Progress tracking
    work_total = int(plan.total_compressed_bytes) if plan else 0
    entries_total = int(plan.total_entries) if plan else 0
    work_done = 0
    entries_done = 0
    xml_found = 0
    
    group_counts: Counter = Counter()
    t0 = time.time()
    last_emit = 0.0
    
    def emit_progress(label: str):
        nonlocal last_emit
        if not progress_cb:
            return
        now = time.time()
        if (now - last_emit) < 0.10 and label != "__final__":
            return
        last_emit = now
        
        progress = float(work_done) / float(max(work_total, 1)) if work_total else 0.0
        elapsed = max(now - t0, 1e-6)
        stats = {
            "elapsed_s": elapsed,
            "entries_done": entries_done,
            "entries_total": entries_total,
            "xml_found": xml_found,
            "extracted_mb": total_extracted / (1024 * 1024),
            "files_per_sec": entries_done / elapsed,
            "mb_per_sec": (total_extracted / (1024 * 1024)) / elapsed,
            "group_counts_top": dict(group_counts.most_common(10)),
            "compressed_done": work_done,
            "compressed_total": work_total,
        }
        progress_cb(min(max(progress, 0.0), 1.0), safe_display(label), stats)
    
    while stack:
        zpath, base_prefix, depth = stack.pop()
        
        try:
            with zipfile.ZipFile(str(zpath)) as z:
                infos = z.infolist()
                if not plan:
                    work_total += sum((getattr(i, "compress_size", 0) or 0) for i in infos)
                    entries_total += len(infos)
                
                for zi in infos:
                    entries_done += 1
                    inner_name = zi.filename
                    lower = inner_name.lower()
                    is_xml = lower.endswith(".xml")
                    is_zip = lower.endswith(".zip")
                    logical_path = f"{base_prefix}/{inner_name}" if base_prefix else inner_name
                    
                    if zi.is_dir():
                        continue
                    
                    work_done += (getattr(zi, "compress_size", 0) or 0)
                    emit_progress(logical_path)
                    
                    # Check compression ratio
                    try:
                        ratio = _zip_entry_ratio(zi)
                        if ratio > max_ratio and (zi.file_size or 0) > 50_000:
                            errors.append(f"High compression ratio ({ratio:.1f}): {logical_path}")
                            continue
                    except Exception:
                        pass
                    
                    # Check size limits
                    if total_extracted + (zi.file_size or 0) > max_total_bytes:
                        raise ValueError("ZIP exceeds total extracted size safety limit.")
                    
                    if is_xml and (zi.file_size or 0) > max_per_file_bytes:
                        errors.append(f"XML exceeds per-file limit: {logical_path}")
                        continue
                    
                    # Extract XML
                    if is_xml:
                        safe_leaf = Path(inner_name).name
                        stub = f"{Path(safe_leaf).stem}__{sha_short(logical_path, 16)}"
                        out_file = xml_root / f"{stub}.xml"
                        
                        written = 0
                        with z.open(zi) as src, open(out_file, "wb") as dst:
                            while True:
                                buf = src.read(CHUNK)
                                if not buf:
                                    break
                                written += len(buf)
                                if written > max_per_file_bytes:
                                    raise ValueError(f"XML exceeds per-file limit: {logical_path}")
                                dst.write(buf)
                                total_extracted += len(buf)
                                if total_extracted > max_total_bytes:
                                    raise ValueError("ZIP exceeds total size safety limit.")
                        
                        results.append(XmlEntry(
                            logical_path=logical_path,
                            filename=Path(inner_name).name,
                            xml_path=str(out_file),
                            xml_size=int(written),
                            stub=stub,
                        ))
                        xml_found += 1
                        
                        try:
                            grp = infer_group(logical_path, Path(inner_name).name, custom_prefixes)
                            group_counts[grp] += 1
                        except Exception:
                            pass
                        
                        if len(results) >= max_files:
                            raise ValueError(f"Too many XML files (≥{max_files}) found.")
                    
                    # Handle nested ZIP
                    elif is_zip and depth < max_depth:
                        nested_uncomp = int(zi.file_size or 0)
                        if nested_uncomp > per_nested_cap:
                            errors.append(f"Nested ZIP too large: {logical_path}")
                            continue
                        
                        nested_stub = f"nested__{sha_short(logical_path, 16)}"
                        nested_file = nested_root / f"{nested_stub}.zip"
                        
                        written = 0
                        with z.open(zi) as src, open(nested_file, "wb") as dst:
                            while True:
                                buf = src.read(CHUNK)
                                if not buf:
                                    break
                                written += len(buf)
                                if written > per_nested_cap:
                                    raise ValueError("Nested ZIP exceeded per-nested cap")
                                dst.write(buf)
                                total_extracted += len(buf)
                                if total_extracted > max_total_bytes:
                                    raise ValueError("ZIP exceeds total size limit.")
                        
                        # Validate nested ZIP
                        try:
                            with zipfile.ZipFile(str(nested_file)) as nz:
                                _ = nz.infolist()[:5]
                        except zipfile.BadZipFile:
                            try:
                                nested_file.unlink()
                            except Exception:
                                pass
                            errors.append(f"Invalid nested ZIP: {logical_path}")
                            continue
                        
                        stack.append((nested_file, logical_path, depth + 1))
        
        except zipfile.BadZipFile as e:
            errors.append(f"Bad ZIP file: {zpath}")
            continue
        except ValueError as e:
            errors.append(str(e))
            break
        except Exception as e:
            errors.append(f"Error processing {zpath}: {str(e)}")
            continue
    
    emit_progress("__final__")
    elapsed = time.time() - t0
    
    return ScanResult(
        xml_entries=results,
        group_counts=dict(group_counts),
        total_extracted_bytes=total_extracted,
        total_entries=entries_done,
        elapsed_seconds=elapsed,
        errors=errors
    )


# ============================================================
# High-Level Scan Function
# ============================================================
def scan_zip_file(
    zip_path: Path,
    session_dir: Path,
    custom_prefixes: Optional[set] = None,
    max_depth: int = DEFAULT_MAX_DEPTH,
    max_files: int = DEFAULT_MAX_FILES,
    max_total_mb: int = DEFAULT_MAX_TOTAL_MB,
    max_per_file_mb: int = DEFAULT_MAX_PER_FILE_MB,
    progress_cb: Optional[Callable[[float, str, Dict[str, Any]], None]] = None,
) -> ScanResult:
    """
    Scan a ZIP file and extract XML entries.
    
    Args:
        zip_path: Path to the ZIP file
        session_dir: Session directory for extracted files
        custom_prefixes: Custom group prefixes
        max_depth: Maximum nesting depth
        max_files: Maximum XML files to extract
        max_total_mb: Maximum total MB to extract
        max_per_file_mb: Maximum MB per file
        progress_cb: Progress callback
    
    Returns:
        ScanResult with XML entries and statistics
    """
    temp_dir = session_dir / "temp"
    temp_dir.mkdir(parents=True, exist_ok=True)
    
    # Plan the work first
    plan = plan_zip_work(
        zip_path,
        temp_dir,
        max_depth=max_depth,
        max_ratio=DEFAULT_MAX_COMPRESSION_RATIO
    )
    
    # Collect XMLs
    result = collect_xml_from_zip(
        zip_path,
        temp_dir,
        max_depth=max_depth,
        max_files=max_files,
        max_total_bytes=max_total_mb * 1024 * 1024,
        max_per_file_bytes=max_per_file_mb * 1024 * 1024,
        max_ratio=DEFAULT_MAX_COMPRESSION_RATIO,
        plan=plan,
        custom_prefixes=custom_prefixes,
        progress_cb=progress_cb,
    )
    
    return result


def get_detected_groups(xml_entries: List[XmlEntry], custom_prefixes: Optional[set] = None) -> List[str]:
    """Get sorted list of detected groups from XML entries."""
    custom_prefixes = custom_prefixes or set()
    groups = set()
    for entry in xml_entries:
        try:
            g = infer_group(entry.logical_path, entry.filename, custom_prefixes)
            groups.add(g)
        except Exception:
            pass
    return sorted(groups)
