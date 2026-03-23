
from __future__ import annotations

"""
Comparison Service - Enhanced ZIP/XML/CSV Comparison (Refactored)

Features:
- ZIP-to-ZIP comparison with extraction + XML-to-CSV conversion
- Uses canonical scan_zip_for_files for nested ZIP scanning
- Detects .xml and .xml.gz files and converts them to CSV for comparisons
  - Handles true gzip AND mislabeled .xml.gz that is actually plain XML (common export behavior)
- Copies-through scanned .csv into working output for consistent processing
- Group + filename matching with cosine similarity
- Drilldown: row/column diff (GitHub-style) with cell indicators
- Record/Row-focused summary for /comparison/run:
  - added_rows / removed_rows / modified_rows per file
- Ignore columns support (WHO columns by default)
"""

import csv
import difflib
import gzip
import hashlib
import logging
import math
import re
import shutil
import tempfile
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from api.services.storage_service import get_session_dir
from api.services.xml_processing_service import (
    infer_group as _infer_group_canonical,
    scan_zip_for_files,
    xml_to_rows as _xml_to_rows_canonical,
)
from api.utils.oracle_catalog import enrich_group as _oracle_enrich_cmp

logger = logging.getLogger(__name__)

# ============================================================
# Constants / Settings
# ============================================================
COS_DIM = 1 << 18
_TOKEN_RE = re.compile(r"[A-Za-z0-9_./\-]{2,64}")

DEFAULT_IGNORE_COLUMNS = {
    "created by",
    "last updated by",
    "creation date",
    "last update date",
    "last update login",
}

# Scan limits (match conversion_service defaults)
SCAN_MAX_DEPTH = 10
SCAN_MAX_FILES = 20000
SCAN_MAX_UNZIPPED_BYTES = 300 * 1024 * 1024

# Keep only N active comparison dirs for drilldown (avoid disk bloat)
MAX_ACTIVE_DIRS = 10

# Limit noisy per-file warnings
MAX_PROCESSING_WARNINGS = 25


# ============================================================
# Enums
# ============================================================
class ChangeType(str, Enum):
    ADDED = "ADDED"
    REMOVED = "REMOVED"
    MODIFIED = "MODIFIED"
    SAME = "SAME"


# ============================================================
# Data classes
# ============================================================
@dataclass
class CsvArtifact:
    """
    Represents a processed CSV file with metadata used for matching.
    """
    logical_path: str
    filename: str
    group: str
    stub: str
    csv_path: str
    csv_sha256: str
    rows: int = 0
    cols: int = 0
    tag_used: str = ""
    status: str = "OK"
    err_msg: str = ""
    vec: Optional[Dict[int, float]] = None
    vec_norm: Optional[float] = None  # type: ignore[valid-type]

    def get(self, key: str, default=None):
        return getattr(self, key, default)


@dataclass
class DeltaRow:
    """
    Represents a row-level change for drilldown diff.
    """
    kind: str  # "MODIFIED"|"ADDED"|"REMOVED"
    rowA: Optional[int]
    rowB: Optional[int]
    changed_cols: List[int] = field(default_factory=list)
    old_vals: Dict[int, str] = field(default_factory=dict)
    new_vals: Dict[int, str] = field(default_factory=dict)


# ============================================================
# Session directory registry for drilldown
# ============================================================
_active_comparison_dirs: Dict[str, Path] = {}


def get_comparison_dir(prefix: str) -> Optional[Path]:
    return _active_comparison_dirs.get(prefix)


def cleanup_comparison_dir(prefix: str) -> None:
    work_dir = _active_comparison_dirs.pop(prefix, None)
    if not work_dir:
        return
    try:
        shutil.rmtree(work_dir, ignore_errors=True)
    except Exception:
        pass


def _register_comparison_dir(work_dir: Path) -> str:
    """
    Keep only the last MAX_ACTIVE_DIRS temp dirs.
    """
    if len(_active_comparison_dirs) >= MAX_ACTIVE_DIRS:
        # dict preserves insertion order, so first key is oldest
        oldest = next(iter(_active_comparison_dirs.keys()))
        cleanup_comparison_dir(oldest)

    dir_id = work_dir.name
    _active_comparison_dirs[dir_id] = work_dir
    return dir_id


# ============================================================
# Ignore columns helpers
# ============================================================
def _norm_colname(name: str) -> str:
    return re.sub(r"\s+", " ", str(name or "").strip().lower())


def _parse_ignore_columns(ignore_columns: Optional[str]) -> Set[str]:
    """
    Parse comma-separated ignore columns. Always includes DEFAULT_IGNORE_COLUMNS.
    """
    base = set(DEFAULT_IGNORE_COLUMNS)
    if not ignore_columns:
        return base
    parts = [p.strip() for p in ignore_columns.split(",") if p.strip()]
    return base | {_norm_colname(p) for p in parts}


# ============================================================
# Utility
# ============================================================
def sha_short(s: str, n: int = 16) -> str:
    return hashlib.sha1(s.encode("utf-8")).hexdigest()[:n]


def _hash_token(token: str, dim: int = COS_DIM) -> int:
    return int(hashlib.blake2b(token.encode("utf-8"), digest_size=8).hexdigest(), 16) % dim


def _norm_cell(v: Any, *, ignore_case: bool = False, trim_ws: bool = True) -> str:
    if v is None:
        s = ""
    else:
        s = str(v).replace("\x00", "")
    if trim_ws:
        s = s.strip()
        s = re.sub(r"\s+", " ", s)
    if ignore_case:
        s = s.lower()
    return s


def _row_hash(s: str) -> str:
    return hashlib.sha1(s.encode("utf-8")).hexdigest()


def _token_set(s: str) -> Set[str]:
    return set(_TOKEN_RE.findall((s or "").lower()))


def _jaccard(a: Set[str], b: Set[str]) -> float:
    if not a or not b:
        return 0.0
    inter = len(a & b)
    uni = len(a | b)
    return float(inter / max(uni, 1))


def cosine_sparse(a: Dict[int, float], an: float, b: Dict[int, float], bn: float) -> float:
    if not a or not b or an <= 0.0 or bn <= 0.0:
        return 0.0
    # iterate smaller map for speed
    if len(a) > len(b):
        a, b = b, a
        an, bn = bn, an
    dot = 0.0
    for k, av in a.items():
        bv = b.get(k)
        if bv is not None:
            dot += av * bv
    return float(dot / (an * bn))


# ============================================================
# CSV I/O helpers
# ============================================================
def _open_text_fallback(path: str):
    encodings = ["utf-8-sig", "utf-8", "latin-1", "cp1252"]
    for enc in encodings:
        try:
            return open(path, "r", encoding=enc, newline="", errors="replace")
        except UnicodeDecodeError:
            continue
    return open(path, "r", encoding="utf-8", errors="replace", newline="")


def _read_csv_matrix(path: str, *, max_rows: int = 60000, max_cols: int = 240) -> Tuple[List[str], List[List[str]]]:
    header: List[str] = []
    rows: List[List[str]] = []
    try:
        with _open_text_fallback(path) as f:
            reader = csv.reader(f)
            header = next(reader, [])
            header = header[:max_cols]
            for i, row in enumerate(reader):
                if i >= max_rows:
                    break
                row = (row + [""] * len(header))[:len(header)]
                row = row[:max_cols]
                rows.append(row)
    except Exception as e:
        logger.warning("Error reading CSV %s: %s", path, e)
    return header, rows


def stream_hash_and_vector(path: str, dim: int = COS_DIM) -> Tuple[str, Dict[int, float], float]:
    """
    Compute SHA256 and sparse token vector for cosine similarity.
    """
    import codecs

    h = hashlib.sha256()
    vec: Dict[int, float] = defaultdict(float)
    decoder = codecs.getincrementaldecoder("utf-8")(errors="ignore")
    carry = ""

    try:
        with open(path, "rb") as f:
            while True:
                b = f.read(1024 * 1024)
                if not b:
                    break
                h.update(b)
                text = decoder.decode(b)
                text = carry + text
                carry = text[-200:]
                body = text[:-200] if len(text) > 200 else ""
                for t in _TOKEN_RE.findall(body.lower()):
                    vec[_hash_token(t, dim)] += 1.0

        if carry:
            for t in _TOKEN_RE.findall(carry.lower()):
                vec[_hash_token(t, dim)] += 1.0

        norm = math.sqrt(sum(v * v for v in vec.values())) or 0.0
        return h.hexdigest(), dict(vec), float(norm)
    except Exception as e:
        logger.warning("Error computing hash/vector for %s: %s", path, e)
        return "", {}, 0.0


# ============================================================
# Diff / Delta (GitHub-style)
# ============================================================
def compute_keyless_csv_delta(
    a_csv: str,
    b_csv: str,
    *,
    ignore_case: bool = False,
    trim_ws: bool = True,
    similarity_pairing: bool = True,
    sim_threshold: float = 0.65,
    ignore_columns: Optional[Set[str]] = None,
    return_rows: bool = True,
    max_rows: int = 60000,
    max_cols: int = 240,
    max_output_changes: int = 5000,
) -> Dict[str, Any]:
    """
    Compare two CSV files and compute row-level deltas.

    - ignore_columns excludes those columns from comparison (WHO etc.)
    - return_rows=False is stats-only mode for faster summary comparisons
    """
    hdrA, rowsA = _read_csv_matrix(a_csv, max_rows=max_rows, max_cols=max_cols)
    hdrB, rowsB = _read_csv_matrix(b_csv, max_rows=max_rows, max_cols=max_cols)

    header = hdrA if len(hdrA) >= len(hdrB) else hdrB
    width = min(max(len(hdrA), len(hdrB)), max_cols)
    header = (header + [f"COL_{i}" for i in range(len(header), width)])[:width]

    ignore_columns = ignore_columns or set()
    ignore_idx: Set[int] = set()
    for i, h in enumerate(header[:width]):
        if _norm_colname(h) in ignore_columns:
            ignore_idx.add(i)
    non_ignored_idx = [i for i in range(width) if i not in ignore_idx]

    def _row_norm_join(row: List[str]) -> str:
        if not non_ignored_idx:
            return ""
        return "\x1f".join(
            _norm_cell(row[i] if i < len(row) else "", ignore_case=ignore_case, trim_ws=trim_ws)
            for i in non_ignored_idx
        )

    normA = [_row_norm_join(r[:width]) for r in rowsA]
    normB = [_row_norm_join(r[:width]) for r in rowsB]
    hA = [_row_hash(s) for s in normA]
    hB = [_row_hash(s) for s in normB]

    sm = difflib.SequenceMatcher(a=hA, b=hB, autojunk=False)
    opcodes = sm.get_opcodes()

    deltas: List[DeltaRow] = []
    stats = {"modified": 0, "added": 0, "removed": 0, "equal": 0}
    truncated = False

    def add_delta(dr: DeltaRow) -> None:
        nonlocal truncated
        if not return_rows:
            return
        if len(deltas) >= max_output_changes:
            truncated = True
            return
        deltas.append(dr)

    def changed_cols(a_row: List[str], b_row: List[str]) -> Tuple[List[int], Dict[int, str], Dict[int, str]]:
        ch: List[int] = []
        old: Dict[int, str] = {}
        new: Dict[int, str] = {}
        for i in non_ignored_idx:
            av = _norm_cell(a_row[i] if i < len(a_row) else "", ignore_case=ignore_case, trim_ws=trim_ws)
            bv = _norm_cell(b_row[i] if i < len(b_row) else "", ignore_case=ignore_case, trim_ws=trim_ws)
            if av != bv:
                ch.append(i)
                old[i] = av
                new[i] = bv
        return ch, old, new

    for tag, i1, i2, j1, j2 in opcodes:
        if truncated:
            break

        if tag == "equal":
            stats["equal"] += (i2 - i1)
            continue

        if tag == "delete":
            for ai in range(i1, i2):
                stats["removed"] += 1
                add_delta(DeltaRow(
                    kind="REMOVED",
                    rowA=ai,
                    rowB=None,
                    changed_cols=list(non_ignored_idx),
                    old_vals={k: _norm_cell(rowsA[ai][k] if k < len(rowsA[ai]) else "",
                                            ignore_case=ignore_case, trim_ws=trim_ws)
                              for k in non_ignored_idx},
                    new_vals={}
                ))
            continue

        if tag == "insert":
            for bj in range(j1, j2):
                stats["added"] += 1
                add_delta(DeltaRow(
                    kind="ADDED",
                    rowA=None,
                    rowB=bj,
                    changed_cols=list(non_ignored_idx),
                    old_vals={},
                    new_vals={k: _norm_cell(rowsB[bj][k] if k < len(rowsB[bj]) else "",
                                            ignore_case=ignore_case, trim_ws=trim_ws)
                              for k in non_ignored_idx}
                ))
            continue

        if tag == "replace":
            blockA = list(range(i1, i2))
            blockB = list(range(j1, j2))

            # no similarity pairing => positional replace
            if (not similarity_pairing) or (not blockA) or (not blockB):
                m = min(len(blockA), len(blockB))
                for k in range(m):
                    ai = blockA[k]
                    bj = blockB[k]
                    ch, old, new = changed_cols(rowsA[ai], rowsB[bj])
                    if ch:
                        stats["modified"] += 1
                        add_delta(DeltaRow(kind="MODIFIED", rowA=ai, rowB=bj, changed_cols=ch, old_vals=old, new_vals=new))

                for ai in blockA[m:]:
                    stats["removed"] += 1
                    add_delta(DeltaRow(
                        kind="REMOVED",
                        rowA=ai,
                        rowB=None,
                        changed_cols=list(non_ignored_idx),
                        old_vals={k: _norm_cell(rowsA[ai][k] if k < len(rowsA[ai]) else "",
                                                ignore_case=ignore_case, trim_ws=trim_ws)
                                  for k in non_ignored_idx},
                        new_vals={}
                    ))

                for bj in blockB[m:]:
                    stats["added"] += 1
                    add_delta(DeltaRow(
                        kind="ADDED",
                        rowA=None,
                        rowB=bj,
                        changed_cols=list(non_ignored_idx),
                        old_vals={},
                        new_vals={k: _norm_cell(rowsB[bj][k] if k < len(rowsB[bj]) else "",
                                                ignore_case=ignore_case, trim_ws=trim_ws)
                                  for k in non_ignored_idx}
                    ))
                continue

            # similarity pairing => greedy jaccard on tokens
            tokA = [_token_set(normA[ai]) for ai in blockA]
            tokB = [_token_set(normB[bj]) for bj in blockB]
            pairs: List[Tuple[float, int, int]] = []
            for ia in range(len(blockA)):
                for jb in range(len(blockB)):
                    sim = _jaccard(tokA[ia], tokB[jb])
                    if sim >= sim_threshold:
                        pairs.append((sim, ia, jb))
            pairs.sort(reverse=True, key=lambda x: x[0])

            usedA: Set[int] = set()
            usedB: Set[int] = set()
            matched: List[Tuple[int, int]] = []
            for _sim, ia, jb in pairs:
                if ia in usedA or jb in usedB:
                    continue
                usedA.add(ia)
                usedB.add(jb)
                matched.append((blockA[ia], blockB[jb]))

            for ai, bj in matched:
                ch, old, new = changed_cols(rowsA[ai], rowsB[bj])
                if ch:
                    stats["modified"] += 1
                    add_delta(DeltaRow(kind="MODIFIED", rowA=ai, rowB=bj, changed_cols=ch, old_vals=old, new_vals=new))

            for idx, ai in enumerate(blockA):
                if idx not in usedA:
                    stats["removed"] += 1
                    add_delta(DeltaRow(
                        kind="REMOVED",
                        rowA=ai,
                        rowB=None,
                        changed_cols=list(non_ignored_idx),
                        old_vals={k: _norm_cell(rowsA[ai][k] if k < len(rowsA[ai]) else "",
                                                ignore_case=ignore_case, trim_ws=trim_ws)
                                  for k in non_ignored_idx},
                        new_vals={}
                    ))

            for idx, bj in enumerate(blockB):
                if idx not in usedB:
                    stats["added"] += 1
                    add_delta(DeltaRow(
                        kind="ADDED",
                        rowA=None,
                        rowB=bj,
                        changed_cols=list(non_ignored_idx),
                        old_vals={},
                        new_vals={k: _norm_cell(rowsB[bj][k] if k < len(rowsB[bj]) else "",
                                                ignore_case=ignore_case, trim_ws=trim_ws)
                                  for k in non_ignored_idx}
                    ))

    if not return_rows:
        return {
            "header": header,
            "stats": stats,
            "truncated": truncated,
            "row_count_A": len(rowsA),
            "row_count_B": len(rowsB),
            "col_count": width,
        }

    # Build side-by-side delta frames
    MAX_ADDED_REMOVED_COLS = 30

    def build_side_rows(which: str) -> List[Dict[str, Any]]:
        rows_out: List[Dict[str, Any]] = []
        for d in deltas:
            if which == "A" and d.kind == "ADDED":
                continue
            if which == "B" and d.kind == "REMOVED":
                continue

            rec: Dict[str, Any] = {
                "_kind_": d.kind,
                "_rowA_": d.rowA if d.rowA is not None else "",
                "_rowB_": d.rowB if d.rowB is not None else "",
                "_changed_cols_": d.changed_cols,
            }

            if which == "A" and d.rowA is not None:
                src_row = rowsA[d.rowA]
            elif which == "B" and d.rowB is not None:
                src_row = rowsB[d.rowB]
            else:
                src_row = None

            if src_row is not None:
                for ci in range(width):
                    col_name = header[ci] if ci < len(header) else f"COL_{ci}"
                    rec[col_name] = src_row[ci] if ci < len(src_row) else ""
            else:
                if d.kind == "MODIFIED":
                    vals = d.old_vals if which == "A" else d.new_vals
                    for ci in d.changed_cols:
                        col_name = header[ci] if ci < len(header) else f"COL_{ci}"
                        rec[col_name] = vals.get(ci, "")
                elif d.kind == "REMOVED" and which == "A":
                    non_empty = [ci for ci in non_ignored_idx if (d.old_vals.get(ci, "") or "").strip()]
                    for ci in non_empty[:MAX_ADDED_REMOVED_COLS]:
                        col_name = header[ci] if ci < len(header) else f"COL_{ci}"
                        rec[col_name] = d.old_vals.get(ci, "")
                elif d.kind == "ADDED" and which == "B":
                    non_empty = [ci for ci in non_ignored_idx if (d.new_vals.get(ci, "") or "").strip()]
                    for ci in non_empty[:MAX_ADDED_REMOVED_COLS]:
                        col_name = header[ci] if ci < len(header) else f"COL_{ci}"
                        rec[col_name] = d.new_vals.get(ci, "")

            rows_out.append(rec)
        return rows_out

    deltaA_rows = build_side_rows("A")
    deltaB_rows = build_side_rows("B")

    def get_delta_headers(rows: List[Dict[str, Any]]) -> List[str]:
        base = ["_kind_", "_rowA_", "_rowB_"]
        all_cols = set()
        for r in rows:
            all_cols.update(k for k in r.keys() if not k.startswith("_"))
        rest_sorted = [c for c in header if c in all_cols] + [c for c in all_cols if c not in header]
        return base + rest_sorted

    return {
        "header": header,
        "stats": stats,
        "truncated": truncated,
        "deltaA": {"headers": get_delta_headers(deltaA_rows), "rows": deltaA_rows},
        "deltaB": {"headers": get_delta_headers(deltaB_rows), "rows": deltaB_rows},
        "row_count_A": len(rowsA),
        "row_count_B": len(rowsB),
        "col_count": width,
    }


# ============================================================
# Group inference (delegated)
# ============================================================
def infer_group(logical_path: str, filename: str, custom_prefixes: Optional[Set[str]] = None) -> str:
    return _infer_group_canonical(logical_path, filename, custom_prefixes)


# ============================================================
# Artifact building
# ============================================================
def _artifact_from_csv_file(
    csv_path: Path,
    logical_path: str,
    filename: str,
    custom_prefixes: Optional[Set[str]] = None,
) -> CsvArtifact:
    custom_prefixes = custom_prefixes or set()
    group = infer_group(logical_path, filename, custom_prefixes)
    stub = f"{Path(filename).stem}__{sha_short(logical_path, 16)}"
    sha, vec, vec_norm = stream_hash_and_vector(str(csv_path), dim=COS_DIM)

    rows_count = 0
    cols_count = 0
    try:
        with _open_text_fallback(str(csv_path)) as f:
            reader = csv.reader(f)
            header = next(reader, [])
            cols_count = len(header)
            rows_count = sum(1 for _ in reader)
    except Exception:
        pass

    return CsvArtifact(
        logical_path=logical_path,
        filename=filename,
        group=group,
        stub=stub,
        csv_path=str(csv_path),
        csv_sha256=sha,
        rows=rows_count,
        cols=cols_count,
        status="OK",
        err_msg="",
        vec=vec,
        vec_norm=vec_norm,
    )


# ============================================================
# Structure analysis
# ============================================================
def folder_counts(arts: List[CsvArtifact]) -> Counter:
    c: Counter = Counter()
    for x in arts:
        lp = x.logical_path or ""
        folder = str(Path(lp).parent) if lp else ""
        c[folder] += 1
    return c


def group_counts(arts: List[CsvArtifact]) -> Counter:
    c: Counter = Counter()
    for x in arts:
        if x.status == "OK":
            c[x.group or ""] += 1
    return c


def compute_structure_changes(artsA: List[CsvArtifact], artsB: List[CsvArtifact]) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    foldersA = folder_counts(artsA)
    foldersB = folder_counts(artsB)
    folder_changes: List[Dict[str, Any]] = []
    for f in sorted(set(foldersA) | set(foldersB)):
        a = foldersA.get(f, 0)
        b = foldersB.get(f, 0)
        if a != b:
            folder_changes.append({"folder": f, "count_a": a, "count_b": b, "delta": b - a})

    groupsA = group_counts(artsA)
    groupsB = group_counts(artsB)
    group_changes: List[Dict[str, Any]] = []
    for g in sorted(set(groupsA) | set(groupsB)):
        a = groupsA.get(g, 0)
        b = groupsB.get(g, 0)
        if a != b:
            group_changes.append({"group": g, "count_a": a, "count_b": b, "delta": b - a})

    return folder_changes, group_changes


# ============================================================
# ZIP/XML scanning + conversion (uses scan_zip_for_files)
# ============================================================
def _infer_type_from_name(name: str) -> str:
    n = (name or "").lower().strip()
    if n.endswith(".xml") or n.endswith(".xml.gz"):
        return "xml"
    if n.endswith(".csv"):
        return "csv"
    if n.endswith(".zip"):
        return "zip"
    return "file"


def _looks_like_xml(data: bytes) -> bool:
    if not data:
        return False
    head = data.lstrip()[:64].lower()
    return head.startswith(b"<?xml") or head.startswith(b"<")


def _looks_like_gzip(data: bytes) -> bool:
    return len(data) >= 2 and data[0] == 0x1F and data[1] == 0x8B


def _read_xml_bytes_from_path(path: Path, logical_name: str) -> bytes:
    """
    Reads XML bytes from disk.

    Supports:
    - True gzip XML (.xml.gz with gzip header)
    - Mislabeled .xml.gz that is actually plain XML (starts with "<?xml" or "<")
    """
    b = path.read_bytes()
    ln = (logical_name or "").lower()

    # ✅ If it already looks like XML, return as-is even if filename says .gz
    if _looks_like_xml(b):
        return b

    # ✅ If it's gzip by header, decompress
    if _looks_like_gzip(b):
        return gzip.decompress(b)

    # If name claims .gz but not gzip and not XML, fail clearly
    if ln.endswith(".xml.gz"):
        raise OSError("File endswith .xml.gz but content is neither gzip nor XML")

    return b


def _rows_headers_from_xml_bytes(xml_bytes: bytes) -> Tuple[List[Dict[str, Any]], List[str], str]:
    rows, headers, tag = _xml_to_rows_canonical(xml_bytes)

    # Derive headers if missing but rows exist
    if (not headers) and rows:
        keys: List[str] = []
        seen: Set[str] = set()
        for r in rows:
            for k in r.keys():
                if k not in seen:
                    seen.add(k)
                    keys.append(k)
        headers = keys

    return rows or [], headers or [], tag or ""


def _write_rows_to_csv(rows: List[Dict[str, Any]], headers: List[str], csv_path: Path) -> None:
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=headers)
        w.writeheader()
        for r in rows:
            w.writerow({h: r.get(h, "") for h in headers})


def _artifact_name_for(logical_path: str, preferred_stem: str) -> str:
    stem = (preferred_stem or "file").strip() or "file"
    return f"{stem}__{sha_short(logical_path or stem, 8)}.csv"


def _scan_zip_and_convert(zip_path: Path, output_dir: Path) -> List[CsvArtifact]:
    """
    Scan ZIP (including nested ZIPs) using scan_zip_for_files.
    Convert all XML/XML.GZ -> CSV and copy-through CSV files.
    """
    artifacts: List[CsvArtifact] = []

    scanned_files, _groups, _total_size = scan_zip_for_files(
        zip_path,
        temp_dir=output_dir.parent,
        max_depth=SCAN_MAX_DEPTH,
        max_files=SCAN_MAX_FILES,
        max_unzipped_bytes=SCAN_MAX_UNZIPPED_BYTES,
        include_extensions={".xml", ".xml.gz", ".csv"},
        custom_prefixes=None,
        group_prefix_len=None,
    )

    warn_count = 0

    for entry in scanned_files or []:
        logical_path = entry.get("logical_path") or entry.get("path") or entry.get("filename") or ""
        abs_path = entry.get("abs_path") or ""
        src = Path(abs_path) if abs_path else None
        if not src or not src.exists():
            continue

        # Some scanners may set file_type="xml" for both .xml and .xml.gz
        ftype = (entry.get("file_type") or "").lower().strip() or _infer_type_from_name(logical_path)
        filename = Path(logical_path).name or src.name

        try:
            if ftype == "csv" or filename.lower().endswith(".csv"):
                out_name = _artifact_name_for(logical_path, Path(filename).stem)
                dst = output_dir / out_name
                dst.write_bytes(src.read_bytes())
                artifacts.append(_artifact_from_csv_file(dst, logical_path, filename))

            elif ftype == "xml" or filename.lower().endswith(".xml") or filename.lower().endswith(".xml.gz"):
                xml_bytes = _read_xml_bytes_from_path(src, logical_path)
                rows, headers, _tag = _rows_headers_from_xml_bytes(xml_bytes)
                if not rows or not headers:
                    continue

                out_name = _artifact_name_for(logical_path, Path(filename).stem)
                csv_path = output_dir / out_name
                _write_rows_to_csv(rows, headers, csv_path)
                artifacts.append(_artifact_from_csv_file(csv_path, logical_path, filename))

        except Exception as e:
            warn_count += 1
            if warn_count <= MAX_PROCESSING_WARNINGS:
                logger.warning("Failed processing %s (%s): %s", logical_path, ftype, e)
            elif warn_count == MAX_PROCESSING_WARNINGS + 1:
                logger.warning("Too many processing errors; suppressing further warnings...")

    return artifacts


def _scan_single_file_and_convert(file_path: Path, output_dir: Path, logical_name: str) -> List[CsvArtifact]:
    """
    Handle a single file input: CSV/XML/XML.GZ.
    Converts XML/XML.GZ -> CSV artifact and copies CSV through.
    """
    artifacts: List[CsvArtifact] = []
    logical = logical_name or file_path.name
    ftype = _infer_type_from_name(logical)

    try:
        if ftype == "csv":
            out_name = _artifact_name_for(logical, file_path.stem)
            dst = output_dir / out_name
            dst.write_bytes(file_path.read_bytes())
            artifacts.append(_artifact_from_csv_file(dst, logical, Path(logical).name))
            return artifacts

        if ftype == "xml":
            xml_bytes = _read_xml_bytes_from_path(file_path, logical)
            rows, headers, _tag = _rows_headers_from_xml_bytes(xml_bytes)
            if rows and headers:
                out_name = _artifact_name_for(logical, Path(logical).stem)
                csv_path = output_dir / out_name
                _write_rows_to_csv(rows, headers, csv_path)
                artifacts.append(_artifact_from_csv_file(csv_path, logical, Path(logical).name))
            return artifacts

        # fallback: treat unknown as CSV-like
        out_name = _artifact_name_for(logical, file_path.stem)
        dst = output_dir / out_name
        dst.write_bytes(file_path.read_bytes())
        artifacts.append(_artifact_from_csv_file(dst, logical, Path(logical).name))
        return artifacts

    except Exception as e:
        logger.warning("Failed processing single file %s: %s", logical, e)
        return artifacts


# ============================================================
# Compare by group + filename
# ============================================================
def _key_group_filename(x: CsvArtifact) -> Tuple[str, str]:
    return (str(x.group or ""), str(x.filename or ""))


def compare_by_group_filename(
    A: List[CsvArtifact],
    B: List[CsvArtifact],
    *,
    ignore_case: bool = False,
    trim_whitespace: bool = True,
    similarity_pairing: bool = True,
    sim_threshold: float = 0.65,
    ignore_columns: Optional[Set[str]] = None,
) -> Dict[str, Any]:
    """
    Compare two sets of artifacts by (group + filename).

    - Exact SHA match => SAME
    - Else cosine pairing => compare and compute row delta stats
    - If deltas are zero after ignore_columns => SAME
    """
    ignore_columns = ignore_columns or set(DEFAULT_IGNORE_COLUMNS)

    Aok = [x for x in A if x.status == "OK" and x.csv_path]
    Bok = [x for x in B if x.status == "OK" and x.csv_path]

    mapA: Dict[Tuple[str, str], List[CsvArtifact]] = defaultdict(list)
    mapB: Dict[Tuple[str, str], List[CsvArtifact]] = defaultdict(list)
    for x in Aok:
        mapA[_key_group_filename(x)].append(x)
    for x in Bok:
        mapB[_key_group_filename(x)].append(x)

    keys = set(mapA.keys()) | set(mapB.keys())
    out_rows: List[Dict[str, Any]] = []

    def greedy_pair_cos(a_list: List[CsvArtifact], b_list: List[CsvArtifact]) -> List[Tuple[int, int, float]]:
        pairs: List[Tuple[float, int, int]] = []
        for i, a in enumerate(a_list):
            avec = a.vec or {}
            an = float(a.vec_norm or 0.0)
            for j, b in enumerate(b_list):
                bvec = b.vec or {}
                bn = float(b.vec_norm or 0.0)
                sim = cosine_sparse(avec, an, bvec, bn)
                pairs.append((sim, i, j))
        pairs.sort(reverse=True, key=lambda x: x[0])

        usedA, usedB = set(), set()
        out: List[Tuple[int, int, float]] = []
        for sim, i, j in pairs:
            if i in usedA or j in usedB:
                continue
            usedA.add(i)
            usedB.add(j)
            out.append((i, j, float(sim)))
        return out

    def _row_deltas_stats(a_csv: str, b_csv: str) -> Dict[str, int]:
        try:
            delta = compute_keyless_csv_delta(
                a_csv,
                b_csv,
                ignore_case=ignore_case,
                trim_ws=trim_whitespace,
                similarity_pairing=similarity_pairing,
                sim_threshold=sim_threshold,
                ignore_columns=ignore_columns,
                return_rows=False,
                max_output_changes=0,
            )
            stats = delta.get("stats", {}) or {}
            return {
                "added_rows": int(stats.get("added", 0)),
                "removed_rows": int(stats.get("removed", 0)),
                "modified_rows": int(stats.get("modified", 0)),
            }
        except Exception:
            return {"added_rows": 0, "removed_rows": 0, "modified_rows": 0}

    for k in sorted(keys):
        a_list = mapA.get(k, [])
        b_list = mapB.get(k, [])

        used_a: Set[int] = set()
        used_b: Set[int] = set()

        # Fast SHA matches
        sha_to_b: Dict[str, List[int]] = defaultdict(list)
        for j, b in enumerate(b_list):
            if b.csv_sha256:
                sha_to_b[b.csv_sha256].append(j)

        for i, a in enumerate(a_list):
            sha = a.csv_sha256 or ""
            if not sha:
                continue
            for j in sha_to_b.get(sha, []):
                if j in used_b:
                    continue
                used_a.add(i)
                used_b.add(j)
                bb = b_list[j]
                out_rows.append({
                    "group": k[0],
                    "filename": k[1],
                    "status": "SAME",
                    "similarity": 1.0,
                    "rows_a": int(a.rows or 0),
                    "rows_b": int(bb.rows or 0),
                    "cols_a": int(a.cols or 0),
                    "cols_b": int(bb.cols or 0),
                    "added_rows": 0,
                    "removed_rows": 0,
                    "modified_rows": 0,
                    "sha_a": sha,
                    "sha_b": sha,
                    "message": "✅ Content identical (SHA256 match).",
                    "path_a": a.logical_path or "",
                    "path_b": bb.logical_path or "",
                    "csv_path_a": a.csv_path or "",
                    "csv_path_b": bb.csv_path or "",
                })
                break

        rem_a = [a_list[i] for i in range(len(a_list)) if i not in used_a]
        rem_b = [b_list[j] for j in range(len(b_list)) if j not in used_b]

        paired = greedy_pair_cos(rem_a, rem_b)
        usedA: Set[int] = set()
        usedB: Set[int] = set()

        for ia, ib, sim in paired:
            a = rem_a[ia]
            b = rem_b[ib]
            usedA.add(ia)
            usedB.add(ib)

            same_hash = bool(a.csv_sha256 and a.csv_sha256 == b.csv_sha256)
            deltas = {"added_rows": 0, "removed_rows": 0, "modified_rows": 0}

            if same_hash:
                status = "SAME"
                msg = "✅ Content identical (SHA256 match)."
                sim = 1.0
            else:
                deltas = _row_deltas_stats(a.csv_path, b.csv_path)
                total_delta = deltas["added_rows"] + deltas["removed_rows"] + deltas["modified_rows"]
                if total_delta == 0:
                    status = "SAME"
                    msg = "✅ Content identical after ignoring configured columns."
                    sim = 1.0
                else:
                    status = "MODIFIED"
                    msg = "🔴 Content differs (record changes detected)."

            out_rows.append({
                "group": k[0],
                "filename": k[1],
                "status": status,
                "similarity": float(max(0.0, min(1.0, sim))),
                "rows_a": int(a.rows or 0),
                "rows_b": int(b.rows or 0),
                "cols_a": int(a.cols or 0),
                "cols_b": int(b.cols or 0),
                "added_rows": int(deltas.get("added_rows", 0)),
                "removed_rows": int(deltas.get("removed_rows", 0)),
                "modified_rows": int(deltas.get("modified_rows", 0)),
                "sha_a": a.csv_sha256 or "",
                "sha_b": b.csv_sha256 or "",
                "message": msg,
                "path_a": a.logical_path or "",
                "path_b": b.logical_path or "",
                "csv_path_a": a.csv_path or "",
                "csv_path_b": b.csv_path or "",
            })

        # leftovers
        for i, a in enumerate(rem_a):
            if i not in usedA:
                out_rows.append({
                    "group": k[0],
                    "filename": k[1],
                    "status": "REMOVED",
                    "similarity": 0.0,
                    "rows_a": int(a.rows or 0),
                    "rows_b": 0,
                    "cols_a": int(a.cols or 0),
                    "cols_b": 0,
                    "added_rows": 0,
                    "removed_rows": int(a.rows or 0),
                    "modified_rows": 0,
                    "sha_a": a.csv_sha256 or "",
                    "sha_b": "",
                    "message": "🗑️ Present in Side A only.",
                    "path_a": a.logical_path or "",
                    "path_b": "",
                    "csv_path_a": a.csv_path or "",
                    "csv_path_b": "",
                })

        for j, b in enumerate(rem_b):
            if j not in usedB:
                out_rows.append({
                    "group": k[0],
                    "filename": k[1],
                    "status": "ADDED",
                    "similarity": 0.0,
                    "rows_a": 0,
                    "rows_b": int(b.rows or 0),
                    "cols_a": 0,
                    "cols_b": int(b.cols or 0),
                    "added_rows": int(b.rows or 0),
                    "removed_rows": 0,
                    "modified_rows": 0,
                    "sha_a": "",
                    "sha_b": b.csv_sha256 or "",
                    "message": "➕ Present in Side B only.",
                    "path_a": "",
                    "path_b": b.logical_path or "",
                    "csv_path_a": "",
                    "csv_path_b": b.csv_path or "",
                })

    same = sum(1 for r in out_rows if r.get("status") == "SAME")
    modified = sum(1 for r in out_rows if r.get("status") == "MODIFIED")
    added = sum(1 for r in out_rows if r.get("status") == "ADDED")
    removed = sum(1 for r in out_rows if r.get("status") == "REMOVED")
    overall_proxy = (same / max(len(out_rows), 1)) * 100 if out_rows else 0.0

    # Oracle EBS enrichment — add module name + domain to every file row
    domain_counts: Dict[str, int] = defaultdict(int)
    for row in out_rows:
        meta = _oracle_enrich_cmp(row.get("group", ""))
        row["oracle_module_name"] = meta.get("oracle_module_name")
        row["oracle_business_domain"] = meta.get("oracle_business_domain")
        domain = meta.get("oracle_business_domain") or "Unknown"
        domain_counts[domain] += 1

    return {
        "rows": out_rows,
        "summary": {
            "same": same,
            "modified": modified,
            "added": added,
            "removed": removed,
            "total_files": len(out_rows),
            "overall_similarity": float(overall_proxy),
            "by_oracle_domain": dict(domain_counts),
        },
    }


# ============================================================
# Result wrapper
# ============================================================
class ComparisonResult:
    def __init__(
        self,
        similarity_percent: float,
        changes: List[Dict[str, Any]],
        folder_changes: Optional[List[Dict[str, Any]]] = None,
        group_deltas: Optional[List[Dict[str, Any]]] = None,
        same: int = 0,
        modified: int = 0,
        added: int = 0,
        removed: int = 0,
    ):
        self.similarity = similarity_percent
        self.changes = changes
        self.folder_changes = folder_changes or []
        self.group_deltas = group_deltas or []
        self.same = same
        self.modified = modified
        self.added = added
        self.removed = removed

    def to_dict(self) -> Dict[str, Any]:
        return {
            "similarity": self.similarity,
            "same": self.same,
            "modified": self.modified,
            "added": self.added,
            "removed": self.removed,
            "total_changes": len(self.changes),
            "changes": self.changes,
            "folder_changes": self.folder_changes,
            "group_deltas": self.group_deltas,
        }


# ============================================================
# Public API: compare files (ZIP/XML/XML.GZ/CSV)
# ============================================================
def compare_files(
    file_a_bytes: bytes,
    file_a_name: str,
    file_b_bytes: bytes,
    file_b_name: str,
    *,
    ignore_case: bool = False,
    trim_whitespace: bool = True,
    similarity_pairing: bool = True,
    sim_threshold: float = 0.65,
    ignore_columns: Optional[str] = None,
) -> ComparisonResult:
    """
    Compare two files (ZIP/XML/XML.GZ/CSV).
    Keeps temp directory for drilldown usage.
    """
    work_dir = Path(tempfile.mkdtemp(prefix="comparison_"))
    dir_id = _register_comparison_dir(work_dir)

    try:
        file_a_path = work_dir / f"A_{file_a_name}"
        file_b_path = work_dir / f"B_{file_b_name}"
        file_a_path.write_bytes(file_a_bytes)
        file_b_path.write_bytes(file_b_bytes)

        ext_a = file_a_name.lower().split(".")[-1] if "." in file_a_name else ""
        ext_b = file_b_name.lower().split(".")[-1] if "." in file_b_name else ""

        csv_dir_a = work_dir / "csv_a"
        csv_dir_b = work_dir / "csv_b"
        csv_dir_a.mkdir(exist_ok=True)
        csv_dir_b.mkdir(exist_ok=True)

        if ext_a == "zip":
            artsA = _scan_zip_and_convert(file_a_path, csv_dir_a)
        else:
            artsA = _scan_single_file_and_convert(file_a_path, csv_dir_a, file_a_name)

        if ext_b == "zip":
            artsB = _scan_zip_and_convert(file_b_path, csv_dir_b)
        else:
            artsB = _scan_single_file_and_convert(file_b_path, csv_dir_b, file_b_name)

        okA = [x for x in artsA if x.status == "OK" and x.csv_path]
        okB = [x for x in artsB if x.status == "OK" and x.csv_path]
        if not okA and not okB:
            return ComparisonResult(0.0, [], same=0, modified=0, added=0, removed=0)

        ignore_set = _parse_ignore_columns(ignore_columns)

        result = compare_by_group_filename(
            okA,
            okB,
            ignore_case=ignore_case,
            trim_whitespace=trim_whitespace,
            similarity_pairing=similarity_pairing,
            sim_threshold=sim_threshold,
            ignore_columns=ignore_set,
        )

        folder_changes, group_changes = compute_structure_changes(artsA, artsB)
        summary = result.get("summary", {}) or {}
        rows = result.get("rows", []) or []

        return ComparisonResult(
            similarity_percent=float(summary.get("overall_similarity", 0.0)),
            changes=rows,
            folder_changes=folder_changes,
            group_deltas=group_changes,
            same=int(summary.get("same", 0)),
            modified=int(summary.get("modified", 0)),
            added=int(summary.get("added", 0)),
            removed=int(summary.get("removed", 0)),
        )

    except Exception as e:
        logger.exception("Comparison failed (dir_id=%s): %s", dir_id, e)
        cleanup_comparison_dir(dir_id)
        raise


# ============================================================
# Public API: compare sessions (CSV output dirs)
# ============================================================
def compare_sessions(left_session_id: str, right_session_id: str) -> Dict[str, Any]:
    """
    Compare output files from two sessions (CSV only).
    """
    try:
        left_dir = get_session_dir(left_session_id) / "output"
        right_dir = get_session_dir(right_session_id) / "output"

        if not left_dir.exists() or not right_dir.exists():
            return {"error": "Session output directories not found"}

        artsA = [_artifact_from_csv_file(p, str(p), p.name) for p in left_dir.glob("*.csv")]
        artsB = [_artifact_from_csv_file(p, str(p), p.name) for p in right_dir.glob("*.csv")]

        if not artsA or not artsB:
            return {"error": "No CSV files found in session outputs"}

        result = compare_by_group_filename(
            artsA,
            artsB,
            ignore_case=False,
            trim_whitespace=True,
            similarity_pairing=True,
            sim_threshold=0.65,
            ignore_columns=set(DEFAULT_IGNORE_COLUMNS),
        )
        folder_changes, group_changes = compute_structure_changes(artsA, artsB)

        summary = result.get("summary", {}) or {}
        return {
            "summary": {
                "total_files": len(artsA) + len(artsB),
                "matched_files": int(summary.get("same", 0)) + int(summary.get("modified", 0)),
                "average_similarity": float(summary.get("overall_similarity", 0.0)) / 100.0,
                "same": int(summary.get("same", 0)),
                "modified": int(summary.get("modified", 0)),
                "added": int(summary.get("added", 0)),
                "removed": int(summary.get("removed", 0)),
            },
            "results": result.get("rows", []) or [],
            "folder_changes": folder_changes,
            "group_changes": group_changes,
        }

    except Exception as e:
        logger.exception("Session comparison failed: %s", e)
        return {"error": str(e)}


# ============================================================
# Public API: drilldown for a specific file pair
# ============================================================
def get_file_drilldown(
    csv_path_a: Optional[str] = None,
    csv_path_b: Optional[str] = None,
    *,
    ignore_case: bool = False,
    trim_whitespace: bool = True,
    similarity_pairing: bool = True,
    sim_threshold: float = 0.65,
    ignore_columns: Optional[str] = None,
    max_rows: int = 60000,
    max_cols: int = 240,
) -> Dict[str, Any]:
    """
    Returns drilldown diff for a specific file pair (tabular).
    Applies ignore_columns server-side.
    """
    if not csv_path_a and not csv_path_b:
        return {"error": "Missing CSV paths"}

    if csv_path_a and not Path(csv_path_a).exists():
        return {"error": "CSV file A not found"}
    if csv_path_b and not Path(csv_path_b).exists():
        return {"error": "CSV file B not found"}

    ignore_set = _parse_ignore_columns(ignore_columns)

    try:
        if csv_path_a and csv_path_b:
            delta = compute_keyless_csv_delta(
                csv_path_a,
                csv_path_b,
                ignore_case=ignore_case,
                trim_ws=trim_whitespace,
                similarity_pairing=similarity_pairing,
                sim_threshold=sim_threshold,
                ignore_columns=ignore_set,
                return_rows=True,
                max_rows=max_rows,
                max_cols=max_cols,
            )
            return {
                "header": delta.get("header", []),
                "stats": delta.get("stats", {}),
                "truncated": delta.get("truncated", False),
                "deltaA": delta.get("deltaA", {}),
                "deltaB": delta.get("deltaB", {}),
                "row_count_A": delta.get("row_count_A", 0),
                "row_count_B": delta.get("row_count_B", 0),
                "col_count": delta.get("col_count", 0),
            }

        # Single-side preview for ADDED/REMOVED
        if csv_path_a:
            header, rowsA = _read_csv_matrix(csv_path_a, max_rows=max_rows, max_cols=max_cols)
            width = min(len(header), max_cols)
            header = (header + [f"COL_{i}" for i in range(len(header), width)])[:width]
            ignore_idx = {i for i, h in enumerate(header) if _norm_colname(h) in ignore_set}
            non_ignored = [i for i in range(width) if i not in ignore_idx]

            deltaA_rows = []
            for i, row in enumerate(rowsA):
                rec = {
                    "_kind_": "REMOVED",
                    "_rowA_": i,
                    "_rowB_": "",
                    "_changed_cols_": list(non_ignored),
                }
                for ci in range(width):
                    col_name = header[ci] if ci < len(header) else f"COL_{ci}"
                    rec[col_name] = row[ci] if ci < len(row) else ""
                deltaA_rows.append(rec)

            return {
                "header": header,
                "stats": {"modified": 0, "added": 0, "removed": len(rowsA), "equal": 0},
                "truncated": False,
                "deltaA": {"headers": ["_kind_", "_rowA_", "_rowB_"] + header, "rows": deltaA_rows},
                "deltaB": {"headers": ["_kind_", "_rowA_", "_rowB_"], "rows": []},
                "row_count_A": len(rowsA),
                "row_count_B": 0,
                "col_count": width,
            }

        if csv_path_b:
            header, rowsB = _read_csv_matrix(csv_path_b, max_rows=max_rows, max_cols=max_cols)
            width = min(len(header), max_cols)
            header = (header + [f"COL_{i}" for i in range(len(header), width)])[:width]
            ignore_idx = {i for i, h in enumerate(header) if _norm_colname(h) in ignore_set}
            non_ignored = [i for i in range(width) if i not in ignore_idx]

            deltaB_rows = []
            for i, row in enumerate(rowsB):
                rec = {
                    "_kind_": "ADDED",
                    "_rowA_": "",
                    "_rowB_": i,
                    "_changed_cols_": list(non_ignored),
                }
                for ci in range(width):
                    col_name = header[ci] if ci < len(header) else f"COL_{ci}"
                    rec[col_name] = row[ci] if ci < len(row) else ""
                deltaB_rows.append(rec)

            return {
                "header": header,
                "stats": {"modified": 0, "added": len(rowsB), "removed": 0, "equal": 0},
                "truncated": False,
                "deltaA": {"headers": ["_kind_", "_rowA_", "_rowB_"], "rows": []},
                "deltaB": {"headers": ["_kind_", "_rowA_", "_rowB_"] + header, "rows": deltaB_rows},
                "row_count_A": 0,
                "row_count_B": len(rowsB),
                "col_count": width,
            }

        return {"error": "Missing CSV paths"}

    except Exception as e:
        logger.exception("Drilldown comparison failed: %s", e)
        return {"error": str(e)}
