"""
Comparison Service - Enhanced

Compares two CSV files and generates detailed difference reports.
Implements the comparison logic from main.py comparison tab.

Features:
- CSV-to-CSV comparison with similarity scoring
- Group and filename based matching
- Row-level and column-level diff tracking
- Support for ignore case and whitespace trimming
- Similarity pairing algorithm
- Hybrid comparison modes
"""

import csv
import hashlib
import logging
import json
import io
import zipfile
import difflib
from pathlib import Path
from typing import List, Dict, Tuple, Optional, Any
from dataclasses import dataclass, asdict
from enum import Enum

from api.services.storage_service import get_session_dir
from api.utils.vector_utils import hash_vector, cosine_similarity

logger = logging.getLogger(__name__)


class ChangeType(str, Enum):
    """Type of change detected"""
    ADDED = "added"
    REMOVED = "removed"
    MODIFIED = "modified"
    SAME = "same"


@dataclass
class DiffResult:
    """Represents a difference between two CSV rows."""
    group: str
    filename: str
    status: str  # SAME, MODIFIED, ADDED, REMOVED
    row_number_a: Optional[int] = None
    row_number_b: Optional[int] = None
    similarity_score: float = 1.0
    added_columns: List[str] = None
    removed_columns: List[str] = None
    modified_columns: List[str] = None

    def __post_init__(self):
        if self.added_columns is None:
            self.added_columns = []
        if self.removed_columns is None:
            self.removed_columns = []
        if self.modified_columns is None:
            self.modified_columns = []

    def to_dict(self) -> Dict:
        """Convert to dictionary"""
        return asdict(self)


class ComparisonResult:
    """Result of file comparison"""
    
    def __init__(self, similarity_percent: float, changes: List[Dict], diffs: Optional[List[DiffResult]] = None):
        self.similarity = similarity_percent
        self.changes = changes
        self.diffs = diffs or []
        self.added = sum(1 for c in changes if c.get("type") in ["added", ChangeType.ADDED])
        self.removed = sum(1 for c in changes if c.get("type") in ["removed", ChangeType.REMOVED])
        self.modified = sum(1 for c in changes if c.get("type") in ["modified", ChangeType.MODIFIED])
        self.same = sum(1 for c in changes if c.get("type") in ["same", ChangeType.SAME])
    
    def to_dict(self) -> Dict:
        """Convert to dict for JSON response"""
        return {
            "similarity": self.similarity,
            "added": self.added,
            "removed": self.removed,
            "modified": self.modified,
            "same": self.same,
            "total_changes": len(self.changes),
            "changes": self.changes,
            "diffs": [d.to_dict() for d in self.diffs],
        }


# ============================================================
# Utility Functions
# ============================================================

def normalize_value(value: Any, ignore_case: bool = False, trim_ws: bool = True) -> str:
    """Normalize a CSV cell value for comparison."""
    if value is None:
        return ""
    s = str(value)
    if trim_ws:
        s = s.strip()
    if ignore_case:
        s = s.lower()
    return s


def row_similarity(
    row_a: Dict[str, Any],
    row_b: Dict[str, Any],
    ignore_case: bool = False,
    trim_ws: bool = True,
) -> float:
    """
    Calculate similarity between two rows using SequenceMatcher.
    Returns a float between 0.0 and 1.0.
    """
    # Normalize all values
    vals_a = [normalize_value(v, ignore_case, trim_ws) for v in row_a.values()]
    vals_b = [normalize_value(v, ignore_case, trim_ws) for v in row_b.values()]

    text_a = " ".join(vals_a)
    text_b = " ".join(vals_b)

    if not text_a and not text_b:
        return 1.0
    if not text_a or not text_b:
        return 0.0

    matcher = difflib.SequenceMatcher(None, text_a, text_b)
    return float(matcher.ratio())


def compute_csv_hash(csv_path: str, ignore_case: bool = False, trim_ws: bool = True) -> str:
    """Compute a hash of normalized CSV content."""
    hasher = hashlib.sha256()

    try:
        with open(csv_path, "r", encoding="utf-8", errors="replace") as f:
            reader = csv.DictReader(f)
            if reader.fieldnames:
                hasher.update(",".join(reader.fieldnames).encode())

            for row in reader:
                if row:
                    normalized = tuple(
                        normalize_value(v, ignore_case, trim_ws)
                        for v in row.values()
                    )
                    hasher.update(str(normalized).encode())
    except Exception as e:
        logger.warning(f"Error computing hash for {csv_path}: {e}")

    return hasher.hexdigest()


def load_csv(file_bytes: bytes, filename: str) -> List[Dict]:
    """Load CSV from bytes"""
    try:
        text = file_bytes.decode('utf-8')
    except UnicodeDecodeError:
        text = file_bytes.decode('latin-1')
    
    reader = csv.DictReader(io.StringIO(text))
    rows = list(reader)
    
    logger.info(f"Loaded {len(rows)} rows from {filename}")
    return rows


def load_csv_from_path(csv_path: str) -> Tuple[List[str], List[Dict[str, str]]]:
    """Load CSV file and return (headers, rows_list)."""
    headers: List[str] = []
    rows: List[Dict[str, str]] = []

    try:
        with open(csv_path, "r", encoding="utf-8", errors="replace") as f:
            reader = csv.DictReader(f)
            headers = list(reader.fieldnames or [])

            for row in reader:
                if row:
                    rows.append(row)
    except Exception as e:
        logger.error(f"Error loading CSV {csv_path}: {e}")
        raise

    return headers, rows


def read_csv(path: Path) -> list[dict]:
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        return list(reader)


def compare_rows(row_a: Dict, row_b: Dict) -> Tuple[bool, List[Dict]]:
    """
    Compare two rows and detect field-level changes
    
    Returns:
        (is_equal, field_changes)
    """
    field_changes = []
    is_equal = True
    
    all_keys = set(row_a.keys()) | set(row_b.keys())
    
    for key in sorted(all_keys):
        val_a = row_a.get(key, "")
        val_b = row_b.get(key, "")
        
        if val_a != val_b:
            is_equal = False
            field_changes.append({
                "field": key,
                "old_value": str(val_a),
                "new_value": str(val_b),
                "indicator": "🟢"  # Green for change
            })
        else:
            field_changes.append({
                "field": key,
                "old_value": str(val_a),
                "new_value": str(val_b),
                "indicator": "🔴"  # Red for no change
            })
    
    return is_equal, field_changes


def compare_csvs(rows_a: List[Dict], rows_b: List[Dict]) -> ComparisonResult:
    """
    Compare two CSV data sets
    
    Uses SequenceMatcher for row-level comparison
    """
    changes = []
    
    # Build row signatures for matching
    def row_signature(row: Dict) -> str:
        """Create a signature from row for comparison"""
        items = sorted(row.items())
        return str(items)
    
    sigs_a = [row_signature(r) for r in rows_a]
    sigs_b = [row_signature(r) for r in rows_b]
    
    # Use SequenceMatcher to find matching rows
    matcher = difflib.SequenceMatcher(None, sigs_a, sigs_b)
    matches = matcher.get_matching_blocks()
    
    # Mark rows as matched
    matched_a = set()
    matched_b = set()
    
    for match in matches:
        for i in range(match.size):
            matched_a.add(match.a + i)
            matched_b.add(match.b + i)
    
    # Process matches - detect field-level changes
    for match in matches:
        for i in range(match.size):
            row_a = rows_a[match.a + i]
            row_b = rows_b[match.b + i]
            
            is_equal, field_changes = compare_rows(row_a, row_b)
            
            if not is_equal:
                changes.append({
                    "type": ChangeType.MODIFIED,
                    "row_id": str(match.a + i),
                    "row_index_a": match.a + i,
                    "row_index_b": match.b + i,
                    "field_changes": field_changes,
                })
    
    # Removed rows (in A but not matched in B)
    for i, row in enumerate(rows_a):
        if i not in matched_a:
            changes.append({
                "type": ChangeType.REMOVED,
                "row_id": str(i),
                "row_index": i,
                "row_data": row,
                "indicator": "🔴"
            })
    
    # Added rows (in B but not matched in A)
    for i, row in enumerate(rows_b):
        if i not in matched_b:
            changes.append({
                "type": ChangeType.ADDED,
                "row_id": str(i),
                "row_index": i,
                "row_data": row,
                "indicator": "🟢"
            })
    
    # Calculate similarity
    total_rows = max(len(rows_a), len(rows_b))
    if total_rows == 0:
        similarity = 100.0
    else:
        matched_rows = len([c for c in changes if c.get("type") == ChangeType.MODIFIED])
        similarity = (matched_rows / total_rows) * 100 if total_rows > 0 else 0
    
    return ComparisonResult(similarity, changes)


def compare_files(file_a_bytes: bytes, file_a_name: str,
                  file_b_bytes: bytes, file_b_name: str) -> ComparisonResult:
    """
    Compare two files (CSV or JSON)
    
    Returns comparison result with changes marked with indicators
    """
    try:
        # Load files
        rows_a = load_file(file_a_bytes, file_a_name)
        rows_b = load_file(file_b_bytes, file_b_name)
        
        # Compare
        result = compare_csvs(rows_a, rows_b)
        
        logger.info(
            f"Compared {file_a_name} vs {file_b_name}: "
            f"{result.similarity:.1f}% similarity, "
            f"+{result.added} -{result.removed} ±{result.modified}"
        )
        
        return result
    
    except Exception as e:
        logger.error(f"Comparison failed: {e}")
        raise


def compare_sessions(left_session_id: str, right_session_id: str) -> Dict:
    """
    Compare output files from two sessions
    Compares CSV files from each session's output directory
    """
    try:
        left_dir = get_session_dir(left_session_id) / "output"
        right_dir = get_session_dir(right_session_id) / "output"

        results = []
        similarities = []

        left_files = {f.name: f for f in left_dir.glob("*.csv")}
        right_files = {f.name: f for f in right_dir.glob("*.csv")}

        for filename, left_file in left_files.items():
            if filename not in right_files:
                continue

            right_file = right_files[filename]

            left_rows = read_csv(left_file)
            right_rows = read_csv(right_file)

            left_text = str(left_rows)
            right_text = str(right_rows)

            sim = cosine_similarity(
                hash_vector(left_text),
                hash_vector(right_text),
            )

            deltas = compute_row_diff(left_rows, right_rows)

            results.append({
                "filename": filename,
                "similarity": round(sim, 4),
                "deltas": deltas,
            })

            similarities.append(sim)

        summary = {
            "total_files": len(left_files),
            "matched_files": len(results),
            "average_similarity": round(sum(similarities) / len(similarities), 4) if similarities else 0.0,
        }

        logger.info(
            f"Compared sessions {left_session_id} vs {right_session_id}: "
            f"{summary['average_similarity']:.1f}% average similarity"
        )

        return {
            "summary": summary,
            "results": results,
        }
    
    except Exception as e:
        logger.error(f"Session comparison failed: {e}")
        raise
