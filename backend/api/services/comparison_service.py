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
from api.utils.diff_utils import compute_row_diff

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
    added_columns: Optional[List[str]] = None
    removed_columns: Optional[List[str]] = None
    modified_columns: Optional[List[str]] = None

    def __post_init__(self):
        if self.added_columns is None:
            self.added_columns = []
        if self.removed_columns is None:
            self.removed_columns = []
        if self.modified_columns is None:
            self.modified_columns = []

    def to_dict(self) -> Dict:
        """Convert to dictionary"""
        from dataclasses import asdict
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
    # Handle None values explicitly to prevent comparison errors
    if value is None:
        return ""
    # Convert to string, handling None explicitly in case of weird edge cases
    if isinstance(value, str):
        s = value
    else:
        try:
            s = str(value) if value is not None else ""
        except Exception:
            s = ""
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
    try:
        # Normalize all values, handling None values properly
        vals_a = [normalize_value(v, ignore_case, trim_ws) for v in (row_a.values() if row_a else [])]
        vals_b = [normalize_value(v, ignore_case, trim_ws) for v in (row_b.values() if row_b else [])]

        text_a = " ".join(vals_a)
        text_b = " ".join(vals_b)

        if not text_a and not text_b:
            return 1.0
        if not text_a or not text_b:
            return 0.0

        matcher = difflib.SequenceMatcher(None, text_a, text_b)
        return float(matcher.ratio())
    except (TypeError, AttributeError) as e:
        # If comparison fails due to type issues, return 0.0 similarity
        logger.warning(f"Row similarity calculation failed: {e}")
        return 0.0


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
    """Load CSV from bytes with robust encoding and newline handling"""
    encodings = ["utf-8-sig", "utf-8", "latin-1", "cp1252"]
    text = None
    
    # Try to decode with different encodings
    for encoding in encodings:
        try:
            text = file_bytes.decode(encoding)
            break
        except UnicodeDecodeError:
            continue
    
    if text is None:
        # Last resort: decode with errors replaced
        text = file_bytes.decode('utf-8', errors='replace')
    
    rows = []
    
    # The csv module needs proper newline handling for fields with embedded newlines.
    # Write to a temp file with newline='' to let csv handle it properly.
    import tempfile
    import os
    
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
        # Fallback: normalize newlines and try StringIO
        try:
            # Normalize line endings
            text = text.replace('\r\n', '\n').replace('\r', '\n')
            reader = csv.DictReader(io.StringIO(text))
            rows = list(reader)
        except csv.Error as e2:
            logger.warning(f"Fallback also failed for {filename}: {e2}")
            # Last resort: line-by-line with error recovery
            try:
                reader = csv.DictReader(io.StringIO(text))
                for row in reader:
                    try:
                        if row:
                            rows.append(row)
                    except csv.Error:
                        continue
            except Exception:
                pass
    
    logger.info(f"Loaded {len(rows)} rows from {filename}")
    return rows


def load_csv_from_path(csv_path: str) -> Tuple[List[str], List[Dict[str, str]]]:
    """Load CSV file and return (headers, rows_list) with robust encoding handling."""
    headers: List[str] = []
    rows: List[Dict[str, str]] = []
    encodings = ["utf-8-sig", "utf-8", "latin-1", "cp1252"]

    for encoding in encodings:
        try:
            with open(csv_path, "r", newline="", encoding=encoding, errors="replace") as f:
                reader = csv.DictReader(f)
                headers = list(reader.fieldnames or [])

                for row in reader:
                    if row:
                        rows.append(row)
                return headers, rows
        except UnicodeDecodeError:
            continue
        except csv.Error as e:
            # Try to handle newline issues by reading with errors='replace'
            logger.warning(f"CSV parsing error with {encoding}, trying next: {e}")
            continue
        except Exception as e:
            if encoding == encodings[-1]:
                logger.error(f"Error loading CSV {csv_path}: {e}")
                raise
            continue

    # Return empty if all encodings fail
    logger.warning(f"Could not load CSV {csv_path} with any encoding")
    return headers, rows


def read_csv(path: Path) -> list[dict]:
    """
    Read CSV file with robust encoding and newline handling.
    Tries multiple encodings and handles embedded newlines gracefully.
    """
    # Try different encodings in order of likelihood
    encodings = ["utf-8-sig", "utf-8", "latin-1", "cp1252"]
    
    for encoding in encodings:
        try:
            with open(path, newline="", encoding=encoding, errors="replace") as f:
                # First, try to read with standard DictReader
                try:
                    reader = csv.DictReader(f)
                    rows = list(reader)
                    return rows
                except csv.Error as csv_err:
                    # If standard parsing fails, try with relaxed quoting
                    f.seek(0)
                    reader = csv.DictReader(f, quoting=csv.QUOTE_MINIMAL)
                    try:
                        rows = list(reader)
                        return rows
                    except csv.Error:
                        # Last resort: read line by line skipping bad lines
                        f.seek(0)
                        rows = []
                        reader = csv.DictReader(f)
                        for row in reader:
                            try:
                                if row:
                                    rows.append(row)
                            except Exception:
                                continue  # Skip problematic rows
                        if rows:
                            return rows
                        raise csv_err
        except UnicodeDecodeError:
            continue  # Try next encoding
        except Exception as e:
            if encoding == encodings[-1]:
                # Last encoding failed, log and raise
                logger.error(f"Failed to read CSV {path}: {e}")
                raise
            continue
    
    # Fallback: return empty list if all attempts fail
    logger.warning(f"Could not read CSV {path} with any encoding")
    return []


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
        # Convert all None values to empty strings to avoid comparison issues
        clean_row = {}
        for k, v in row.items():
            # Ensure both key and value are strings to avoid None comparison errors
            clean_key = str(k) if k is not None else ""
            clean_val = str(v) if v is not None else ""
            clean_row[clean_key] = clean_val
        # Sort by keys to create consistent signature
        items = [(k, clean_row[k]) for k in sorted(clean_row.keys())]
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


def load_file(file_bytes: bytes, filename: str) -> List[Dict]:
    """Load a CSV or JSON file from bytes"""
    if filename.lower().endswith('.json'):
        try:
            text = file_bytes.decode('utf-8')
            data = json.loads(text)
            if isinstance(data, list):
                return data
            else:
                return [data]
        except Exception as e:
            logger.error(f"Error loading JSON {filename}: {e}")
            raise
    else:
        # Default to CSV
        return load_csv(file_bytes, filename)


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


# ============================================================
# ZIP Comparison Functions (NEW)
# ============================================================

@dataclass
class ZipFileComparison:
    """Comparison result for a single file in ZIP."""
    filename: str
    logical_path: str
    group: str
    status: ChangeType
    left_row_count: int = 0
    right_row_count: int = 0
    rows_added: int = 0
    rows_removed: int = 0
    error: Optional[str] = None

    def to_dict(self) -> Dict:
        return {
            "filename": self.filename,
            "logical_path": self.logical_path,
            "group": self.group,
            "status": self.status.value if isinstance(self.status, ChangeType) else str(self.status),
            "left_row_count": self.left_row_count,
            "right_row_count": self.right_row_count,
            "rows_added": self.rows_added,
            "rows_removed": self.rows_removed,
            "error": self.error,
        }


@dataclass
class ZipGroupComparison:
    """Comparison result for a group in ZIP."""
    group: str
    files_added: int = 0
    files_removed: int = 0
    files_modified: int = 0
    files_unchanged: int = 0
    rows_added: int = 0
    rows_removed: int = 0
    file_comparisons: List[ZipFileComparison] = None

    def __post_init__(self):
        if self.file_comparisons is None:
            self.file_comparisons = []

    def to_dict(self) -> Dict:
        return {
            "group": self.group,
            "files_added": self.files_added,
            "files_removed": self.files_removed,
            "files_modified": self.files_modified,
            "files_unchanged": self.files_unchanged,
            "rows_added": self.rows_added,
            "rows_removed": self.rows_removed,
            "file_comparisons": [f.to_dict() for f in self.file_comparisons],
        }


@dataclass 
class ZipComparisonResult:
    """Full comparison result between two ZIPs."""
    left_zip_name: str
    right_zip_name: str
    group_comparisons: Dict[str, ZipGroupComparison] = None
    summary: Dict[str, Any] = None
    elapsed_seconds: float = 0.0
    errors: List[str] = None

    def __post_init__(self):
        if self.group_comparisons is None:
            self.group_comparisons = {}
        if self.summary is None:
            self.summary = {}
        if self.errors is None:
            self.errors = []

    def to_dict(self) -> Dict:
        return {
            "left_zip_name": self.left_zip_name,
            "right_zip_name": self.right_zip_name,
            "group_comparisons": {k: v.to_dict() for k, v in self.group_comparisons.items()},
            "summary": self.summary,
            "elapsed_seconds": self.elapsed_seconds,
            "errors": self.errors,
        }


def compare_zip_files(
    left_zip_path: Path,
    right_zip_path: Path,
    session_dir: Path,
    custom_prefixes: Optional[set] = None,
    selected_groups: Optional[List[str]] = None,
    max_files: int = 5000,
) -> ZipComparisonResult:
    """
    Compare two ZIP files with detailed delta analysis.
    
    Args:
        left_zip_path: Path to first ZIP
        right_zip_path: Path to second ZIP
        session_dir: Session directory for extraction
        custom_prefixes: Custom group prefixes
        selected_groups: Filter to specific groups (None = all)
        max_files: Maximum files to process per ZIP
    
    Returns:
        ZipComparisonResult with full comparison data
    """
    import time
    from api.services.zip_service import scan_zip_file, get_detected_groups
    from api.services.xml_service import xml_to_rows, compute_keyless_csv_delta
    from api.services.rag_service import infer_group
    
    t0 = time.time()
    custom_prefixes = custom_prefixes or set()
    errors = []
    
    # Create separate directories for each ZIP
    left_dir = session_dir / "compare_left"
    right_dir = session_dir / "compare_right"
    left_dir.mkdir(parents=True, exist_ok=True)
    right_dir.mkdir(parents=True, exist_ok=True)
    
    # Scan both ZIPs
    logger.info(f"Scanning left ZIP: {left_zip_path}")
    left_scan = scan_zip_file(left_zip_path, left_dir, custom_prefixes, max_files=max_files)
    
    logger.info(f"Scanning right ZIP: {right_zip_path}")
    right_scan = scan_zip_file(right_zip_path, right_dir, custom_prefixes, max_files=max_files)
    
    errors.extend(left_scan.errors)
    errors.extend(right_scan.errors)
    
    # Build lookup by identifier
    def _extract_identifier(path: str, filename: str) -> str:
        parts = path.replace("\\", "/").strip("/").split("/")
        if len(parts) >= 2:
            return f"{parts[-2]}/{parts[-1]}".lower()
        return filename.lower()
    
    left_by_id = {_extract_identifier(e.logical_path, e.filename): e for e in left_scan.xml_entries}
    right_by_id = {_extract_identifier(e.logical_path, e.filename): e for e in right_scan.xml_entries}
    
    all_ids = set(left_by_id.keys()) | set(right_by_id.keys())
    
    # Filter by selected groups if specified
    def get_group(entry):
        if entry:
            return infer_group(entry.logical_path, entry.filename, custom_prefixes)
        return "unknown"
    
    # Compare each pair
    file_comparisons: List[ZipFileComparison] = []
    group_stats: Dict[str, ZipGroupComparison] = {}
    
    for ident in sorted(all_ids):
        left_entry = left_by_id.get(ident)
        right_entry = right_by_id.get(ident)
        
        group = get_group(left_entry or right_entry)
        
        # Filter by selected groups
        if selected_groups and group not in selected_groups:
            continue
        
        if group not in group_stats:
            group_stats[group] = ZipGroupComparison(group=group)
        
        filename = (left_entry or right_entry).filename
        logical_path = (left_entry or right_entry).logical_path
        
        # Determine comparison status
        if left_entry is None:
            # Added in right
            try:
                result = xml_to_rows(right_entry.xml_path)
                comparison = ZipFileComparison(
                    filename=filename,
                    logical_path=logical_path,
                    group=group,
                    status=ChangeType.ADDED,
                    right_row_count=result.row_count,
                    rows_added=result.row_count,
                )
            except Exception as e:
                comparison = ZipFileComparison(
                    filename=filename,
                    logical_path=logical_path,
                    group=group,
                    status=ChangeType.ADDED,
                    error=str(e),
                )
            group_stats[group].files_added += 1
            group_stats[group].rows_added += comparison.rows_added
            
        elif right_entry is None:
            # Removed from right
            try:
                result = xml_to_rows(left_entry.xml_path)
                comparison = ZipFileComparison(
                    filename=filename,
                    logical_path=logical_path,
                    group=group,
                    status=ChangeType.REMOVED,
                    left_row_count=result.row_count,
                    rows_removed=result.row_count,
                )
            except Exception as e:
                comparison = ZipFileComparison(
                    filename=filename,
                    logical_path=logical_path,
                    group=group,
                    status=ChangeType.REMOVED,
                    error=str(e),
                )
            group_stats[group].files_removed += 1
            group_stats[group].rows_removed += comparison.rows_removed
            
        else:
            # Both exist - compare
            try:
                left_result = xml_to_rows(left_entry.xml_path)
                right_result = xml_to_rows(right_entry.xml_path)
                
                delta = compute_keyless_csv_delta(
                    left_result.rows,
                    left_result.header,
                    right_result.rows,
                    right_result.header,
                )
                
                has_changes = bool(delta.added_rows or delta.removed_rows)
                status = ChangeType.MODIFIED if has_changes else ChangeType.SAME
                
                comparison = ZipFileComparison(
                    filename=filename,
                    logical_path=logical_path,
                    group=group,
                    status=status,
                    left_row_count=left_result.row_count,
                    right_row_count=right_result.row_count,
                    rows_added=len(delta.added_rows),
                    rows_removed=len(delta.removed_rows),
                )
                
                if status == ChangeType.MODIFIED:
                    group_stats[group].files_modified += 1
                else:
                    group_stats[group].files_unchanged += 1
                    
                group_stats[group].rows_added += len(delta.added_rows)
                group_stats[group].rows_removed += len(delta.removed_rows)
                
            except Exception as e:
                comparison = ZipFileComparison(
                    filename=filename,
                    logical_path=logical_path,
                    group=group,
                    status=ChangeType.MODIFIED,
                    error=str(e),
                )
                group_stats[group].files_modified += 1
        
        file_comparisons.append(comparison)
        group_stats[group].file_comparisons.append(comparison)
    
    elapsed = time.time() - t0
    
    # Build summary
    summary = {
        "total_files_compared": len(file_comparisons),
        "files_added": sum(gs.files_added for gs in group_stats.values()),
        "files_removed": sum(gs.files_removed for gs in group_stats.values()),
        "files_modified": sum(gs.files_modified for gs in group_stats.values()),
        "files_unchanged": sum(gs.files_unchanged for gs in group_stats.values()),
        "total_rows_added": sum(gs.rows_added for gs in group_stats.values()),
        "total_rows_removed": sum(gs.rows_removed for gs in group_stats.values()),
        "groups": list(group_stats.keys()),
        "left_xml_count": len(left_scan.xml_entries),
        "right_xml_count": len(right_scan.xml_entries),
    }
    
    logger.info(
        f"ZIP comparison complete: {len(file_comparisons)} files compared, "
        f"+{summary['files_added']} -{summary['files_removed']} ~{summary['files_modified']}"
    )
    
    return ZipComparisonResult(
        left_zip_name=left_zip_path.name,
        right_zip_name=right_zip_path.name,
        group_comparisons=group_stats,
        summary=summary,
        elapsed_seconds=elapsed,
        errors=errors,
    )


def summarize_comparison_for_chat(result: ZipComparisonResult) -> str:
    """
    Generate a natural language summary of comparison results.
    
    Args:
        result: ZipComparisonResult
    
    Returns:
        Summary text suitable for chat context
    """
    lines = [
        f"## Comparison: {result.left_zip_name} vs {result.right_zip_name}",
        "",
        f"**Total files compared:** {result.summary.get('total_files_compared', 0)}",
        f"- Added: {result.summary.get('files_added', 0)}",
        f"- Removed: {result.summary.get('files_removed', 0)}",
        f"- Modified: {result.summary.get('files_modified', 0)}",
        f"- Unchanged: {result.summary.get('files_unchanged', 0)}",
        "",
        f"**Row changes:** +{result.summary.get('total_rows_added', 0)} / -{result.summary.get('total_rows_removed', 0)}",
        "",
        "### Changes by Group:",
    ]
    
    for group, gs in sorted(result.group_comparisons.items()):
        if gs.files_added or gs.files_removed or gs.files_modified:
            lines.append(f"- **{group}**: +{gs.files_added} added, -{gs.files_removed} removed, ~{gs.files_modified} modified")
    
    if result.errors:
        lines.append("")
        lines.append(f"### Errors ({len(result.errors)}):")
        for err in result.errors[:10]:
            lines.append(f"- {err}")
    
    return "\n".join(lines)
