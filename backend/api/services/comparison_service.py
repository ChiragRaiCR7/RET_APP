"""
Comparison Service - Enhanced ZIP/XML/CSV Comparison

Features:
- ZIP-to-ZIP comparison with nested extraction
- XML-to-CSV conversion using lxml
- Group and filename based matching with cosine similarity
- Row-level and column-level diff tracking with GitHub-style indicators
- Support for ignore case and whitespace trimming
- Similarity pairing algorithm using Jaccard similarity
"""

import csv
import hashlib
import logging
import json
import io
import os
import re
import math
import time
import zipfile
import difflib
import tempfile
import shutil
from pathlib import Path
from typing import List, Dict, Tuple, Optional, Any, Set
from dataclasses import dataclass, field, asdict
from collections import defaultdict, Counter
from enum import Enum

from api.services.storage_service import get_session_dir, create_session_dir

logger = logging.getLogger(__name__)


# ============================================================
# Constants
# ============================================================
COS_DIM = 1 << 18
_TOKEN_RE = re.compile(r"[A-Za-z0-9_./\-]{2,64}")


class ChangeType(str, Enum):
    """Type of change detected"""
    ADDED = "ADDED"
    REMOVED = "REMOVED"
    MODIFIED = "MODIFIED"
    SAME = "SAME"


# ============================================================
# Data Classes
# ============================================================
@dataclass
class CsvArtifact:
    """Represents a processed CSV file with metadata"""
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
    vec_norm: Optional[float] = None

    def get(self, key: str, default=None):
        return getattr(self, key, default)

    def to_dict(self) -> Dict[str, Any]:
        d = {
            "logical_path": self.logical_path,
            "filename": self.filename,
            "group": self.group,
            "stub": self.stub,
            "csv_path": self.csv_path,
            "csv_sha256": self.csv_sha256,
            "rows": int(self.rows),
            "cols": int(self.cols),
            "tag_used": self.tag_used,
            "status": self.status,
            "err_msg": self.err_msg,
        }
        return d


@dataclass
class DeltaRow:
    """Represents a row-level change"""
    kind: str  # "MODIFIED"|"ADDED"|"REMOVED"
    rowA: Optional[int]
    rowB: Optional[int]
    changed_cols: List[int] = field(default_factory=list)
    old_vals: Dict[int, str] = field(default_factory=dict)
    new_vals: Dict[int, str] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "kind": self.kind,
            "rowA": self.rowA,
            "rowB": self.rowB,
            "changed_cols": self.changed_cols,
            "old_vals": self.old_vals,
            "new_vals": self.new_vals,
        }


# ============================================================
# Utility Functions
# ============================================================
def _safe_str(value) -> str:
    """Safely convert any value to string, handling None/NaN."""
    if value is None:
        return ""
    try:
        if isinstance(value, float) and math.isnan(value):
            return ""
    except (TypeError, ValueError):
        pass
    return str(value)


def sha_short(s: str, n: int = 16) -> str:
    """Generate short SHA1 hash of string"""
    return hashlib.sha1(s.encode("utf-8")).hexdigest()[:n]


def _hash_token(token: str, dim: int = COS_DIM) -> int:
    """Hash a token to a dimension index"""
    return int(hashlib.blake2b(token.encode("utf-8"), digest_size=8).hexdigest(), 16) % dim


def _norm_cell(v: Any, *, ignore_case: bool = False, trim_ws: bool = True) -> str:
    """Normalize a cell value for comparison"""
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
    """Hash a normalized row string"""
    return hashlib.sha1(s.encode("utf-8")).hexdigest()


def _token_set(s: str) -> Set[str]:
    """Extract token set from string for Jaccard similarity"""
    return set(_TOKEN_RE.findall((s or "").lower()))


def _jaccard(a: Set[str], b: Set[str]) -> float:
    """Calculate Jaccard similarity between two token sets"""
    if not a or not b:
        return 0.0
    inter = len(a & b)
    uni = len(a | b)
    return float(inter / max(uni, 1))


def cosine_sparse(a: Dict[int, float], an: float, b: Dict[int, float], bn: float) -> float:
    """Calculate cosine similarity between sparse vectors"""
    if not a or not b or an <= 0.0 or bn <= 0.0:
        return 0.0
    if len(a) > len(b):
        a, b = b, a
        an, bn = bn, an
    dot = 0.0
    for k, av in a.items():
        bv = b.get(k)
        if bv is not None:
            dot += av * bv
    return float(dot / (an * bn))


def normalize_value(value: Any, ignore_case: bool = False, trim_ws: bool = True) -> str:
    """Normalize a CSV cell value for comparison."""
    return _norm_cell(value, ignore_case=ignore_case, trim_ws=trim_ws)


# ============================================================
# File I/O Functions
# ============================================================
def _open_text_fallback(path: str):
    """Open text file with encoding fallback"""
    encodings = ["utf-8-sig", "utf-8", "latin-1", "cp1252"]
    for enc in encodings:
        try:
            f = open(path, "r", encoding=enc, newline="", errors="replace")
            return f
        except UnicodeDecodeError:
            continue
    return open(path, "r", encoding="utf-8", errors="replace", newline="")


def _read_csv_matrix(path: str, *, max_rows: int = 60000, max_cols: int = 240) -> Tuple[List[str], List[List[str]]]:
    """Read CSV file into header and rows matrix"""
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
        logger.warning(f"Error reading CSV {path}: {e}")
    return header, rows


def stream_hash_and_vector(path: str, dim: int = COS_DIM) -> Tuple[str, Dict[int, float], float]:
    """Stream file to compute SHA256 hash and token vector"""
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
        logger.warning(f"Error computing hash/vector for {path}: {e}")
        return "", {}, 0.0


def write_rows_to_csv(rows: List[Dict], headers: List[str], csv_path: Path):
    """Write rows to CSV file"""
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=headers)
        writer.writeheader()
        for row in rows:
            writer.writerow({h: row.get(h, "") for h in headers})


# ============================================================
# Keyless CSV Delta Comparison (GitHub-style)
# ============================================================
def compute_keyless_csv_delta(
    a_csv: str,
    b_csv: str,
    *,
    ignore_case: bool = False,
    trim_ws: bool = True,
    similarity_pairing: bool = True,
    sim_threshold: float = 0.65,
    max_rows: int = 60000,
    max_cols: int = 240,
    max_output_changes: int = 5000,
) -> Dict[str, Any]:
    """
    Compare two CSV files and compute row-level deltas.
    Returns GitHub-style diff with indicators for changed cells.
    """
    hdrA, rowsA = _read_csv_matrix(a_csv, max_rows=max_rows, max_cols=max_cols)
    hdrB, rowsB = _read_csv_matrix(b_csv, max_rows=max_rows, max_cols=max_cols)

    header = hdrA if len(hdrA) >= len(hdrB) else hdrB
    width = min(max(len(hdrA), len(hdrB)), max_cols)
    header = (header + [f"COL_{i}" for i in range(len(header), width)])[:width]

    def _row_norm_join(row: List[str]) -> str:
        return "\x1f".join(_norm_cell(c, ignore_case=ignore_case, trim_ws=trim_ws) for c in row)

    normA = [_row_norm_join(r[:width]) for r in rowsA]
    normB = [_row_norm_join(r[:width]) for r in rowsB]
    hA = [_row_hash(s) for s in normA]
    hB = [_row_hash(s) for s in normB]

    sm = difflib.SequenceMatcher(a=hA, b=hB, autojunk=False)
    opcodes = sm.get_opcodes()

    deltas: List[DeltaRow] = []
    stats = {"modified": 0, "added": 0, "removed": 0, "equal": 0}
    truncated = False

    def add_delta(dr: DeltaRow):
        nonlocal truncated
        if len(deltas) >= max_output_changes:
            truncated = True
            return
        deltas.append(dr)

    def changed_cols(a_row: List[str], b_row: List[str]) -> Tuple[List[int], Dict[int, str], Dict[int, str]]:
        ch: List[int] = []
        old: Dict[int, str] = {}
        new: Dict[int, str] = {}
        for i in range(width):
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
                    changed_cols=list(range(width)),
                    old_vals={k: _norm_cell(rowsA[ai][k] if k < len(rowsA[ai]) else "", ignore_case=ignore_case, trim_ws=trim_ws) for k in range(width)},
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
                    changed_cols=list(range(width)),
                    old_vals={},
                    new_vals={k: _norm_cell(rowsB[bj][k] if k < len(rowsB[bj]) else "", ignore_case=ignore_case, trim_ws=trim_ws) for k in range(width)}
                ))
            continue

        if tag == "replace":
            blockA = list(range(i1, i2))
            blockB = list(range(j1, j2))

            if (not similarity_pairing) or (len(blockA) == 0) or (len(blockB) == 0):
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
                    add_delta(DeltaRow(kind="REMOVED", rowA=ai, rowB=None, changed_cols=list(range(width)),
                                       old_vals={k: _norm_cell(rowsA[ai][k] if k < len(rowsA[ai]) else "", ignore_case=ignore_case, trim_ws=trim_ws) for k in range(width)},
                                       new_vals={}))

                for bj in blockB[m:]:
                    stats["added"] += 1
                    add_delta(DeltaRow(kind="ADDED", rowA=None, rowB=bj, changed_cols=list(range(width)),
                                       old_vals={},
                                       new_vals={k: _norm_cell(rowsB[bj][k] if k < len(rowsB[bj]) else "", ignore_case=ignore_case, trim_ws=trim_ws) for k in range(width)}))
                continue

            # Similarity pairing for replace blocks
            tokA = [_token_set(normA[ai]) for ai in blockA]
            tokB = [_token_set(normB[bj]) for bj in blockB]
            pairs: List[Tuple[float, int, int]] = []
            for ia, ai in enumerate(blockA):
                for jb, bj in enumerate(blockB):
                    sim = _jaccard(tokA[ia], tokB[jb])
                    if sim >= sim_threshold:
                        pairs.append((sim, ia, jb))
            pairs.sort(reverse=True, key=lambda x: x[0])

            usedA: Set[int] = set()
            usedB: Set[int] = set()
            matched: List[Tuple[int, int]] = []

            for sim, ia, jb in pairs:
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
                    add_delta(DeltaRow(kind="REMOVED", rowA=ai, rowB=None, changed_cols=list(range(width)),
                                       old_vals={k: _norm_cell(rowsA[ai][k] if k < len(rowsA[ai]) else "", ignore_case=ignore_case, trim_ws=trim_ws) for k in range(width)},
                                       new_vals={}))

            for idx, bj in enumerate(blockB):
                if idx not in usedB:
                    stats["added"] += 1
                    add_delta(DeltaRow(kind="ADDED", rowA=None, rowB=bj, changed_cols=list(range(width)),
                                       old_vals={},
                                       new_vals={k: _norm_cell(rowsB[bj][k] if k < len(rowsB[bj]) else "", ignore_case=ignore_case, trim_ws=trim_ws) for k in range(width)}))

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

            # Provide full row values for better preview (Excel-style view)
            if which == "A" and d.rowA is not None:
                src_row = rowsA[d.rowA]
            elif which == "B" and d.rowB is not None:
                src_row = rowsB[d.rowB]
            else:
                src_row = None

            if src_row is not None:
                # Fill all columns for display (bounded by width)
                for ci in range(width):
                    col_name = header[ci] if ci < len(header) else f"COL_{ci}"
                    rec[col_name] = src_row[ci] if ci < len(src_row) else ""
            else:
                # Fallback for cases without source row
                if d.kind == "MODIFIED":
                    vals = d.old_vals if which == "A" else d.new_vals
                    for ci in d.changed_cols:
                        col_name = header[ci] if ci < len(header) else f"COL_{ci}"
                        rec[col_name] = vals.get(ci, "")

                elif d.kind == "REMOVED" and which == "A":
                    non_empty = [ci for ci in range(width) if (d.old_vals.get(ci, "") or "").strip() != ""]
                    for ci in non_empty[:MAX_ADDED_REMOVED_COLS]:
                        col_name = header[ci] if ci < len(header) else f"COL_{ci}"
                        rec[col_name] = d.old_vals.get(ci, "")

                elif d.kind == "ADDED" and which == "B":
                    non_empty = [ci for ci in range(width) if (d.new_vals.get(ci, "") or "").strip() != ""]
                    for ci in non_empty[:MAX_ADDED_REMOVED_COLS]:
                        col_name = header[ci] if ci < len(header) else f"COL_{ci}"
                        rec[col_name] = d.new_vals.get(ci, "")

            rows_out.append(rec)
        return rows_out

    deltaA_rows = build_side_rows("A")
    deltaB_rows = build_side_rows("B")

    # Get unique headers from delta rows
    def get_delta_headers(rows: List[Dict]) -> List[str]:
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
# Helper function for group inference
# ============================================================
def infer_group(logical_path: str, filename: str, custom_prefixes: Optional[Set] = None) -> str:
    """Infer group from logical path and filename"""
    custom_prefixes = custom_prefixes or set()
    
    # Try to get group from path
    parts = logical_path.replace("\\", "/").strip("/").split("/")
    if len(parts) >= 2:
        candidate = parts[-2]
        if candidate.lower() not in {"", ".", "..", "output", "csv", "xml", "temp"}:
            return candidate
    
    # Try to get group from filename patterns
    name_lower = filename.lower()
    
    # Common patterns
    patterns = [
        ("journal", "journal"),
        ("book", "book"),
        ("conference", "conference"),
        ("proceeding", "proceedings"),
        ("dissertation", "dissertation"),
        ("grant", "grant"),
        ("peer_review", "peer_review"),
        ("posted", "posted_content"),
        ("crossmark", "crossmark"),
        ("resource", "resource"),
    ]
    
    for pattern, group in patterns:
        if pattern in name_lower:
            return group
    
    # Check custom prefixes
    for prefix in custom_prefixes:
        if name_lower.startswith(prefix.lower()):
            return prefix
    
    return "other"


# ============================================================
# Artifact Building from Input
# ============================================================
def _artifact_from_csv_file(csv_path: Path, logical_path: str, filename: str, custom_prefixes: Optional[Set] = None) -> CsvArtifact:
    """Create artifact from existing CSV file"""
    custom_prefixes = custom_prefixes or set()
    group = infer_group(logical_path, filename, custom_prefixes)
    stub = f"{Path(filename).stem}__{sha_short(logical_path, 16)}"
    sha, vec, vec_norm = stream_hash_and_vector(str(csv_path), dim=COS_DIM)
    
    # Count rows and cols
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
        tag_used="",
        status="OK",
        err_msg="",
        vec=vec,
        vec_norm=vec_norm
    )


# ============================================================
# Group + Filename Comparison with Cosine Similarity
# ============================================================
def _key_group_filename(x: CsvArtifact) -> Tuple[str, str]:
    return (str(x.group or ""), str(x.filename or ""))


def compare_by_group_filename(
    A: List[CsvArtifact],
    B: List[CsvArtifact],
) -> Dict[str, Any]:
    """
    Compare two sets of artifacts by group + filename.
    Uses SHA256 for exact match, then cosine similarity for pairing.
    """
    Aok = [x for x in A if x.status == "OK" and x.csv_path]
    Bok = [x for x in B if x.status == "OK" and x.csv_path]

    mapA: Dict[Tuple[str, str], List[CsvArtifact]] = defaultdict(list)
    mapB: Dict[Tuple[str, str], List[CsvArtifact]] = defaultdict(list)
    for x in Aok:
        mapA[_key_group_filename(x)].append(x)
    for x in Bok:
        mapB[_key_group_filename(x)].append(x)

    keys = set(mapA.keys()) | set(mapB.keys())
    rows: List[Dict[str, Any]] = []

    def greedy_pair_cos(a_list: List[CsvArtifact], b_list: List[CsvArtifact]) -> List[Tuple[int, int, float]]:
        pairs = []
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
        out = []
        for sim, i, j in pairs:
            if i in usedA or j in usedB:
                continue
            usedA.add(i)
            usedB.add(j)
            out.append((i, j, float(sim)))
        return out

    for k in sorted(keys):
        a_list = mapA.get(k, [])
        b_list = mapB.get(k, [])

        used_a = set()
        used_b = set()

        sha_to_b = defaultdict(list)
        for j, b in enumerate(b_list):
            if b.csv_sha256:
                sha_to_b[b.csv_sha256].append(j)

        # 1) Exact SHA match
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
                rows.append({
                    "group": k[0],
                    "filename": k[1],
                    "status": "SAME",
                    "similarity": 1.0,
                    "rows_a": int(a.rows or 0),
                    "rows_b": int(bb.rows or 0),
                    "cols_a": int(a.cols or 0),
                    "cols_b": int(bb.cols or 0),
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
        usedA, usedB = set(), set()

        for ia, ib, sim in paired:
            a = rem_a[ia]
            b = rem_b[ib]
            usedA.add(ia)
            usedB.add(ib)
            same_hash = (a.csv_sha256 and a.csv_sha256 == b.csv_sha256)
            if same_hash:
                status = "SAME"
                msg = "✅ Content identical (SHA256 match)."
                sim = 1.0
            else:
                status = "MODIFIED"
                msg = "🔴 Content differs (SHA mismatch)."

            rows.append({
                "group": k[0],
                "filename": k[1],
                "status": status,
                "similarity": float(max(0.0, min(1.0, sim))),
                "rows_a": int(a.rows or 0),
                "rows_b": int(b.rows or 0),
                "cols_a": int(a.cols or 0),
                "cols_b": int(b.cols or 0),
                "sha_a": a.csv_sha256 or "",
                "sha_b": b.csv_sha256 or "",
                "message": msg,
                "path_a": a.logical_path or "",
                "path_b": b.logical_path or "",
                "csv_path_a": a.csv_path or "",
                "csv_path_b": b.csv_path or "",
            })

        for i, a in enumerate(rem_a):
            if i not in usedA:
                rows.append({
                    "group": k[0],
                    "filename": k[1],
                    "status": "REMOVED",
                    "similarity": 0.0,
                    "rows_a": int(a.rows or 0),
                    "rows_b": 0,
                    "cols_a": int(a.cols or 0),
                    "cols_b": 0,
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
                rows.append({
                    "group": k[0],
                    "filename": k[1],
                    "status": "ADDED",
                    "similarity": 0.0,
                    "rows_a": 0,
                    "rows_b": int(b.rows or 0),
                    "cols_a": 0,
                    "cols_b": int(b.cols or 0),
                    "sha_a": "",
                    "sha_b": b.csv_sha256 or "",
                    "message": "➕ Present in Side B only.",
                    "path_a": "",
                    "path_b": b.logical_path or "",
                    "csv_path_a": "",
                    "csv_path_b": b.csv_path or "",
                })

    same = sum(1 for r in rows if r.get("status") == "SAME")
    modified = sum(1 for r in rows if r.get("status") == "MODIFIED")
    added = sum(1 for r in rows if r.get("status") == "ADDED")
    removed = sum(1 for r in rows if r.get("status") == "REMOVED")
    overall_proxy = (same / max(len(rows), 1)) * 100 if rows else 0.0

    return {
        "rows": rows,
        "summary": {
            "same": same,
            "modified": modified,
            "added": added,
            "removed": removed,
            "total_files": len(rows),
            "overall_similarity": float(overall_proxy),
        }
    }


# ============================================================
# Folder/Group Structure Analysis
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


def compute_structure_changes(
    artsA: List[CsvArtifact], 
    artsB: List[CsvArtifact]
) -> Tuple[List[Dict], List[Dict]]:
    """Compute folder and group structure changes"""
    foldersA = folder_counts(artsA)
    foldersB = folder_counts(artsB)
    folder_changes = []
    for f in sorted(set(foldersA) | set(foldersB)):
        a = foldersA.get(f, 0)
        b = foldersB.get(f, 0)
        if a != b:
            folder_changes.append({"folder": f, "count_a": a, "count_b": b, "delta": b - a})

    groupsA = group_counts(artsA)
    groupsB = group_counts(artsB)
    group_changes = []
    for g in sorted(set(groupsA) | set(groupsB)):
        a = groupsA.get(g, 0)
        b = groupsB.get(g, 0)
        if a != b:
            group_changes.append({"group": g, "count_a": a, "count_b": b, "delta": b - a})

    return folder_changes, group_changes


# ============================================================
# Build artifacts from ZIP/CSV files
# ============================================================
def build_artifacts_from_files(
    file_paths: List[Path],
    *,
    side_label: str,
    custom_prefixes: Optional[Set] = None,
) -> List[CsvArtifact]:
    """Build CSV artifacts from list of CSV file paths"""
    custom_prefixes = custom_prefixes or set()
    artifacts: List[CsvArtifact] = []
    
    for csv_path in file_paths:
        if csv_path.suffix.lower() == '.csv' and csv_path.exists():
            art = _artifact_from_csv_file(
                csv_path, 
                str(csv_path), 
                csv_path.name, 
                custom_prefixes
            )
            artifacts.append(art)
    
    return artifacts


# ============================================================
# Main Compare Files Function
# ============================================================
class ComparisonResult:
    """Result of file comparison"""
    
    def __init__(
        self, 
        similarity_percent: float, 
        changes: List[Dict],
        folder_changes: List[Dict] = None,
        group_deltas: List[Dict] = None,
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
    
    def to_dict(self) -> Dict:
        """Convert to dict for JSON response"""
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


def load_csv(file_bytes: bytes, filename: str) -> List[Dict]:
    """Load CSV from bytes with robust encoding and newline handling"""
    encodings = ["utf-8-sig", "utf-8", "latin-1", "cp1252"]
    text = None
    
    for encoding in encodings:
        try:
            text = file_bytes.decode(encoding)
            break
        except UnicodeDecodeError:
            continue
    
    if text is None:
        text = file_bytes.decode('utf-8', errors='replace')
    
    rows = []
    try:
        with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False, 
                                         encoding='utf-8', newline='') as tmp:
            tmp.write(text)
            tmp_path = tmp.name
        
        with open(tmp_path, 'r', encoding='utf-8', newline='') as f:
            reader = csv.DictReader(f)
            rows = list(reader)
        
        os.unlink(tmp_path)
    except Exception as e:
        logger.warning(f"CSV parsing error for {filename}: {e}, trying fallback")
        try:
            text = text.replace('\r\n', '\n').replace('\r', '\n')
            reader = csv.DictReader(io.StringIO(text))
            rows = list(reader)
        except Exception:
            pass
    
    return rows


def compare_files(file_a_bytes: bytes, file_a_name: str,
                  file_b_bytes: bytes, file_b_name: str) -> ComparisonResult:
    """
    Compare two files (ZIP/XML/CSV).
    Returns ComparisonResult object with changes and statistics.
    """
    # Create temp directory for work
    work_dir = Path(tempfile.mkdtemp(prefix="comparison_"))
    
    try:
        # Save files to temp directory
        file_a_path = work_dir / f"A_{file_a_name}"
        file_b_path = work_dir / f"B_{file_b_name}"
        file_a_path.write_bytes(file_a_bytes)
        file_b_path.write_bytes(file_b_bytes)
        
        # Determine file types
        ext_a = file_a_name.lower().split('.')[-1] if '.' in file_a_name else ''
        ext_b = file_b_name.lower().split('.')[-1] if '.' in file_b_name else ''
        
        # For CSV files, create artifacts directly
        if ext_a == 'csv' and ext_b == 'csv':
            artsA = [_artifact_from_csv_file(file_a_path, str(file_a_path), file_a_name)]
            artsB = [_artifact_from_csv_file(file_b_path, str(file_b_path), file_b_name)]
        else:
            # For ZIP files, scan and extract
            artsA = []
            artsB = []
            
            if ext_a == 'zip':
                csv_dir_a = work_dir / "csv_a"
                csv_dir_a.mkdir(exist_ok=True)
                artsA = _scan_zip_and_convert(file_a_path, csv_dir_a)
            else:
                artsA = [_artifact_from_csv_file(file_a_path, str(file_a_path), file_a_name)]
            
            if ext_b == 'zip':
                csv_dir_b = work_dir / "csv_b"
                csv_dir_b.mkdir(exist_ok=True)
                artsB = _scan_zip_and_convert(file_b_path, csv_dir_b)
            else:
                artsB = [_artifact_from_csv_file(file_b_path, str(file_b_path), file_b_name)]
        
        # Compare artifacts
        okA = [x for x in artsA if x.status == "OK" and x.csv_path]
        okB = [x for x in artsB if x.status == "OK" and x.csv_path]
        
        if not okA and not okB:
            return ComparisonResult(
                similarity_percent=0.0,
                changes=[],
                same=0,
                modified=0,
                added=0,
                removed=0,
            )
        
        # Compare by group + filename
        result = compare_by_group_filename(okA, okB)
        folder_changes, group_changes = compute_structure_changes(artsA, artsB)
        
        summary = result.get("summary", {})
        rows = result.get("rows", [])
        
        return ComparisonResult(
            similarity_percent=summary.get("overall_similarity", 0.0),
            changes=rows,
            folder_changes=folder_changes,
            group_deltas=group_changes,
            same=summary.get("same", 0),
            modified=summary.get("modified", 0),
            added=summary.get("added", 0),
            removed=summary.get("removed", 0),
        )
        
    except Exception as e:
        logger.exception(f"Comparison failed: {e}")
        raise
    finally:
        try:
            shutil.rmtree(work_dir, ignore_errors=True)
        except Exception:
            pass


def _scan_zip_and_convert(zip_path: Path, output_dir: Path) -> List[CsvArtifact]:
    """Scan ZIP file and convert XML files to CSV artifacts"""
    from lxml import etree
    
    artifacts: List[CsvArtifact] = []
    
    try:
        with zipfile.ZipFile(zip_path, 'r') as zf:
            for info in zf.infolist():
                if info.is_dir():
                    continue
                name_lower = info.filename.lower()
                
                # Process CSV files directly
                if name_lower.endswith('.csv'):
                    csv_path = output_dir / Path(info.filename).name
                    with zf.open(info.filename) as src:
                        csv_path.write_bytes(src.read())
                    art = _artifact_from_csv_file(csv_path, info.filename, Path(info.filename).name)
                    artifacts.append(art)
                
                # Convert XML files to CSV
                elif name_lower.endswith('.xml'):
                    try:
                        with zf.open(info.filename) as src:
                            xml_bytes = src.read()
                        
                        rows, headers = _xml_to_csv_rows(xml_bytes)
                        if rows:
                            stem = Path(info.filename).stem
                            csv_path = output_dir / f"{stem}.csv"
                            csv_path.parent.mkdir(parents=True, exist_ok=True)
                            
                            with open(csv_path, 'w', newline='', encoding='utf-8') as f:
                                writer = csv.DictWriter(f, fieldnames=headers)
                                writer.writeheader()
                                for row in rows:
                                    writer.writerow({h: row.get(h, "") for h in headers})
                            
                            art = _artifact_from_csv_file(csv_path, info.filename, Path(info.filename).name)
                            artifacts.append(art)
                    except Exception as e:
                        logger.warning(f"Failed to process {info.filename}: {e}")
    
    except zipfile.BadZipFile as e:
        logger.error(f"Bad ZIP file {zip_path}: {e}")
    
    return artifacts


def _xml_to_csv_rows(xml_bytes: bytes) -> Tuple[List[Dict], List[str]]:
    """Convert XML bytes to list of row dicts and headers"""
    from lxml import etree
    
    try:
        root = etree.fromstring(xml_bytes)
    except etree.XMLSyntaxError:
        return [], []
    
    # Find repeating elements (potential record tags)
    tag_counts: Dict[str, int] = Counter()
    for elem in root.iter():
        tag_counts[elem.tag] += 1
    
    # Find most common tag with count > 1 (likely records)
    record_tag = None
    max_count = 0
    for tag, count in tag_counts.items():
        if count > max_count and count > 1:
            max_count = count
            record_tag = tag
    
    if not record_tag:
        # Single record - flatten whole document
        row = _flatten_element(root, "")
        headers = list(row.keys())
        return [row], headers
    
    # Extract records
    rows = []
    all_keys = set()
    
    for elem in root.iter(record_tag):
        row = _flatten_element(elem, "")
        rows.append(row)
        all_keys.update(row.keys())
    
    headers = sorted(all_keys)
    return rows, headers


def _flatten_element(elem, prefix: str, sep: str = ".") -> Dict[str, str]:
    """Flatten XML element to dict with path keys"""
    result = {}
    
    # Element text
    if elem.text and elem.text.strip():
        key = f"{prefix}{elem.tag}" if prefix else elem.tag
        result[key] = elem.text.strip()
    
    # Attributes
    for attr, val in elem.attrib.items():
        key = f"{prefix}{elem.tag}@{attr}" if prefix else f"{elem.tag}@{attr}"
        result[key] = val
    
    # Children
    new_prefix = f"{prefix}{elem.tag}{sep}" if prefix else f"{elem.tag}{sep}"
    for child in elem:
        child_dict = _flatten_element(child, new_prefix, sep)
        result.update(child_dict)
    
    return result


# ============================================================
# Session Comparison (for async jobs)
# ============================================================
def compare_sessions(left_session_id: str, right_session_id: str) -> Dict:
    """
    Compare output files from two sessions.
    Used by async worker.
    """
    try:
        left_dir = get_session_dir(left_session_id) / "output"
        right_dir = get_session_dir(right_session_id) / "output"

        if not left_dir.exists() or not right_dir.exists():
            return {"error": "Session output directories not found"}

        # Build artifacts from session outputs
        artsA = []
        artsB = []
        
        for csv_file in left_dir.glob("*.csv"):
            art = _artifact_from_csv_file(csv_file, str(csv_file), csv_file.name)
            artsA.append(art)
        
        for csv_file in right_dir.glob("*.csv"):
            art = _artifact_from_csv_file(csv_file, str(csv_file), csv_file.name)
            artsB.append(art)

        if not artsA or not artsB:
            return {"error": "No CSV files found in session outputs"}

        # Compare
        result = compare_by_group_filename(artsA, artsB)
        folder_changes, group_changes = compute_structure_changes(artsA, artsB)

        summary = result.get("summary", {})
        
        return {
            "summary": {
                "total_files": len(artsA) + len(artsB),
                "matched_files": summary.get("same", 0) + summary.get("modified", 0),
                "average_similarity": summary.get("overall_similarity", 0.0) / 100,
            },
            "results": result.get("rows", []),
            "folder_changes": folder_changes,
            "group_changes": group_changes,
        }
    
    except Exception as e:
        logger.error(f"Session comparison failed: {e}")
        return {"error": str(e)}


# ============================================================
# Drilldown Comparison for Specific File Pair
# ============================================================
def get_file_drilldown(
    csv_path_a: Optional[str] = None,
    csv_path_b: Optional[str] = None,
    *,
    ignore_case: bool = False,
    trim_whitespace: bool = True,
    similarity_pairing: bool = True,
    sim_threshold: float = 0.65,
    max_rows: int = 60000,
    max_cols: int = 240,
) -> Dict[str, Any]:
    """
    Get detailed drilldown comparison for a specific file pair.
    Returns row-level deltas with cell-level change indicators.
    """
    if not csv_path_a and not csv_path_b:
        return {"error": "Missing CSV paths"}

    if csv_path_a and not Path(csv_path_a).exists():
        return {"error": "CSV file A not found"}
    if csv_path_b and not Path(csv_path_b).exists():
        return {"error": "CSV file B not found"}

    try:
        if csv_path_a and csv_path_b:
            delta = compute_keyless_csv_delta(
                csv_path_a, csv_path_b,
                ignore_case=ignore_case,
                trim_ws=trim_whitespace,
                similarity_pairing=similarity_pairing,
                sim_threshold=sim_threshold,
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
            deltaA_rows = []
            for i, row in enumerate(rowsA):
                rec = {
                    "_kind_": "REMOVED",
                    "_rowA_": i,
                    "_rowB_": "",
                    "_changed_cols_": list(range(width)),
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
            deltaB_rows = []
            for i, row in enumerate(rowsB):
                rec = {
                    "_kind_": "ADDED",
                    "_rowA_": "",
                    "_rowB_": i,
                    "_changed_cols_": list(range(width)),
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
        logger.error(f"Drilldown comparison failed: {e}")
        return {"error": str(e)}

