"""
Sidecar cache: pre-chunked text written during conversion so
the auto-embedder can skip CSV re-parsing.

Format: one ``.chunks.jsonl`` file per CSV in the output directory.
Each line is a JSON object with keys: text, group, filename,
row_start, row_end, chunk_index.
"""

import csv
import json
import logging
from pathlib import Path
from typing import Dict, Iterator, List, Optional

from api.core.config import settings

logger = logging.getLogger(__name__)

# Re-use the same defaults the embedding chunker uses.
_CHUNK_TARGET = getattr(settings, "RAG_CHUNK_SIZE", 1500)
_CHUNK_OVERLAP = getattr(settings, "RAG_CHUNK_OVERLAP", 200)
_CHUNK_MAX_COLS = getattr(settings, "RAG_CHUNK_MAX_COLS", 120)
_CELL_MAX = getattr(settings, "RAG_CELL_MAX_CHARS", 250)

SIDECAR_SUFFIX = ".chunks.jsonl"


# ------------------------------------------------------------------
# Write
# ------------------------------------------------------------------

def _normalize_cell(val: str) -> str:
    s = val.strip()
    if len(s) > _CELL_MAX:
        s = s[:_CELL_MAX]
    return " ".join(s.split())


def generate_sidecar(
    csv_path: Path,
    group: str,
    *,
    chunk_target: int = _CHUNK_TARGET,
    chunk_overlap: int = _CHUNK_OVERLAP,
) -> Optional[Path]:
    """Generate a ``.chunks.jsonl`` sidecar next to *csv_path*.

    Returns the sidecar path on success, ``None`` on failure.
    """
    sidecar_path = csv_path.with_suffix(csv_path.suffix + SIDECAR_SUFFIX)
    try:
        chunks = list(_chunk_csv(csv_path, group, chunk_target, chunk_overlap))
        with open(sidecar_path, "w", encoding="utf-8") as out:
            for chunk in chunks:
                out.write(json.dumps(chunk, ensure_ascii=False))
                out.write("\n")
        return sidecar_path
    except Exception as exc:
        logger.debug("Sidecar generation failed for %s: %s", csv_path.name, exc)
        return None


def generate_sidecars_for_dir(
    output_dir: Path,
    file_groups: Dict[str, str],
) -> int:
    """Generate sidecars for all CSVs in *output_dir*.

    *file_groups* maps uppercase filename → group name.
    Returns the number of sidecars written.
    """
    count = 0
    for csv_path in sorted(output_dir.glob("*.CSV")):
        group = file_groups.get(csv_path.name, "EXTRAS")
        if generate_sidecar(csv_path, group):
            count += 1
    # Also try lowercase extension
    for csv_path in sorted(output_dir.glob("*.csv")):
        if csv_path.name.upper() in {p.name for p in output_dir.glob("*.CSV")}:
            continue  # already handled above
        group = file_groups.get(csv_path.name.upper(), file_groups.get(csv_path.name, "EXTRAS"))
        if generate_sidecar(csv_path, group):
            count += 1
    return count


# ------------------------------------------------------------------
# Read
# ------------------------------------------------------------------

def read_sidecar(sidecar_path: Path) -> List[Dict]:
    """Read a sidecar JSONL file and return list of chunk dicts."""
    chunks: List[Dict] = []
    try:
        with open(sidecar_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    chunks.append(json.loads(line))
    except Exception as exc:
        logger.debug("Failed to read sidecar %s: %s", sidecar_path.name, exc)
    return chunks


def find_sidecar(csv_path: Path) -> Optional[Path]:
    """Return the sidecar path if it exists and is newer than the CSV."""
    sidecar = csv_path.with_suffix(csv_path.suffix + SIDECAR_SUFFIX)
    if not sidecar.exists():
        return None
    # Stale check: sidecar must be at least as new as the CSV
    try:
        if sidecar.stat().st_mtime < csv_path.stat().st_mtime:
            return None
    except OSError:
        return None
    return sidecar


# ------------------------------------------------------------------
# Chunking (mirrors _chunk_csv_iter from advanced_ai_service)
# ------------------------------------------------------------------

def _chunk_csv(
    csv_path: Path,
    group: str,
    target_chars: int,
    overlap_chars: int,
) -> Iterator[Dict]:
    """Yield chunk dicts from a CSV file."""
    filename = csv_path.name
    with open(csv_path, "r", encoding="utf-8", errors="replace") as f:
        reader = csv.reader(f)
        try:
            headers = next(reader)
        except StopIteration:
            return

        headers = headers[:_CHUNK_MAX_COLS]
        header_line = "COLUMNS: " + ", ".join(headers)
        preamble = f"TYPE: CSV_DATA_CHUNK | FILE: {filename} | GROUP: {group}\n{header_line}\nROWS:\n"

        buf_lines: List[str] = []
        buf_chars = len(preamble)
        row_start = 1
        chunk_idx = 0
        row_num = 0

        overlap_lines: List[str] = []

        for raw_row in reader:
            row_num += 1
            cells = [_normalize_cell(c) for c in raw_row[:_CHUNK_MAX_COLS]]
            line = " | ".join(cells)

            if buf_chars + len(line) + 1 > target_chars and buf_lines:
                text = preamble + "\n".join(buf_lines)
                yield {
                    "text": text,
                    "group": group,
                    "filename": filename,
                    "row_start": row_start,
                    "row_end": row_start + len(buf_lines) - 1,
                    "chunk_index": chunk_idx,
                }
                chunk_idx += 1

                # Overlap: carry the last N characters of lines
                overlap_lines = []
                overlap_size = 0
                for prev_line in reversed(buf_lines):
                    if overlap_size + len(prev_line) > overlap_chars:
                        break
                    overlap_lines.insert(0, prev_line)
                    overlap_size += len(prev_line)

                row_start = row_num - len(overlap_lines)
                buf_lines = list(overlap_lines)
                buf_chars = len(preamble) + sum(len(l) for l in buf_lines)

            buf_lines.append(line)
            buf_chars += len(line) + 1

        if buf_lines:
            text = preamble + "\n".join(buf_lines)
            yield {
                "text": text,
                "group": group,
                "filename": filename,
                "row_start": row_start,
                "row_end": row_start + len(buf_lines) - 1,
                "chunk_index": chunk_idx,
            }
