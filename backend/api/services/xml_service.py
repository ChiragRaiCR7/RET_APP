"""
XML Service for RET App
Handles XML parsing, CSV conversion, and record chunking for RAG indexing.
Uses LXML for robust XML parsing.
"""
import csv
import hashlib
import io
import logging
from pathlib import Path
from typing import List, Dict, Optional, Tuple, Iterator, Set
from dataclasses import dataclass, field
from collections import Counter, OrderedDict
from lxml import etree

from api.services.rag_service import XmlEntry, CsvArtifact

logger = logging.getLogger(__name__)


# ============================================================
# Configuration
# ============================================================
MAX_TEXT_SIZE = 500_000
CHUNK_TARGET_CHARS = 10_000
MIN_RECORDS_DETECT = 2


@dataclass
class XmlToRowsResult:
    """Result from XML to CSV conversion."""
    stub: str
    header: List[str]
    rows: List[List[str]]
    row_count: int
    columns_detected: int
    record_tag: str
    root_tag: str
    errors: List[str] = field(default_factory=list)


@dataclass
class RecordChunk:
    """A chunk of XML records for embedding."""
    stub: str
    group: str
    chunk_index: int
    record_indices: List[int]
    text: str
    char_count: int


# ============================================================
# Tag Detection
# ============================================================
def detect_record_tag_auto(xml_path: str, min_count: int = MIN_RECORDS_DETECT) -> Tuple[Optional[str], Optional[str]]:
    """
    Auto-detect the repeating record tag in an XML file.
    
    Args:
        xml_path: Path to the XML file
        min_count: Minimum count for a tag to be considered a record tag
    
    Returns:
        Tuple of (record_tag, root_tag) or (None, None) if not detected
    """
    child_counts: Counter = Counter()
    root_tag = None
    
    try:
        for event, element in etree.iterparse(xml_path, events=("end",)):
            if root_tag is None:
                # Find the root (iterate continues to walk)
                pass
            parent = element.getparent()
            if parent is not None:
                if root_tag is None:
                    root_tag = parent.tag
                if parent.tag == root_tag:
                    child_counts[element.tag] += 1
            element.clear()
            while element.getprevious() is not None:
                try:
                    del element.getparent()[0]
                except TypeError:
                    break
    except Exception:
        pass
    
    # Fallback: parse small portion
    if not child_counts:
        try:
            tree = etree.parse(xml_path)
            root = tree.getroot()
            root_tag = root.tag
            for child in root:
                child_counts[child.tag] += 1
        except Exception:
            return None, None
    
    if not child_counts:
        return None, root_tag
    
    # Find most common child with at least min_count occurrences
    candidates = [(tag, cnt) for tag, cnt in child_counts.items() if cnt >= min_count]
    if not candidates:
        # Just pick the most common
        candidates = child_counts.most_common(1)
    
    if candidates:
        # Prefer the most common
        candidates.sort(key=lambda x: -x[1])
        return candidates[0][0], root_tag
    
    return None, root_tag


# ============================================================
# XML to Rows Conversion
# ============================================================
def _flatten_element(element, prefix: str = "", sep: str = "__") -> Dict[str, str]:
    """
    Flatten an XML element to a dictionary with path-based keys.
    
    Args:
        element: lxml Element
        prefix: Prefix for nested elements
        sep: Separator for nested paths
    
    Returns:
        Dictionary of flattened key-value pairs
    """
    result = OrderedDict()
    
    # Handle element text
    text = (element.text or "").strip()
    if text:
        key = prefix if prefix else element.tag
        result[key] = text
    
    # Handle attributes
    for attr_name, attr_val in element.attrib.items():
        key = f"{prefix}{sep}@{attr_name}" if prefix else f"@{attr_name}"
        result[key] = attr_val
    
    # Handle children
    for child in element:
        child_prefix = f"{prefix}{sep}{child.tag}" if prefix else child.tag
        child_data = _flatten_element(child, child_prefix, sep)
        result.update(child_data)
    
    # Handle tail text (sibling text after element)
    tail = (element.tail or "").strip()
    if tail and prefix:
        tail_key = f"{prefix}{sep}__tail__"
        result[tail_key] = tail
    
    return result


def xml_to_rows(
    xml_path: str,
    record_tag: Optional[str] = None,
    max_records: int = 50_000,
    max_columns: int = 1000,
) -> XmlToRowsResult:
    """
    Convert XML file to CSV-style rows.
    
    Args:
        xml_path: Path to XML file
        record_tag: Tag name for records (auto-detected if None)
        max_records: Maximum number of records to process
        max_columns: Maximum number of columns
    
    Returns:
        XmlToRowsResult with header and rows
    """
    path = Path(xml_path)
    stub = path.stem
    errors = []
    
    # Detect record tag if not provided
    detected_tag, root_tag = detect_record_tag_auto(xml_path)
    if record_tag is None:
        record_tag = detected_tag
    
    if record_tag is None:
        return XmlToRowsResult(
            stub=stub,
            header=[],
            rows=[],
            row_count=0,
            columns_detected=0,
            record_tag="",
            root_tag=root_tag or "",
            errors=["Could not detect record tag"]
        )
    
    # Parse and flatten records
    columns_seen: Set[str] = set()
    records: List[Dict[str, str]] = []
    
    try:
        for event, element in etree.iterparse(str(xml_path), events=("end",), tag=record_tag):
            if len(records) >= max_records:
                errors.append(f"Reached max records limit ({max_records})")
                break
            
            flat = _flatten_element(element, prefix="")
            records.append(flat)
            columns_seen.update(flat.keys())
            
            if len(columns_seen) > max_columns:
                errors.append(f"Exceeded max columns ({max_columns})")
                break
            
            # Memory cleanup
            element.clear()
            while element.getprevious() is not None:
                try:
                    del element.getparent()[0]
                except TypeError:
                    break
    except etree.XMLSyntaxError as e:
        errors.append(f"XML syntax error: {str(e)}")
    except Exception as e:
        errors.append(f"Error parsing XML: {str(e)}")
    
    if not records:
        return XmlToRowsResult(
            stub=stub,
            header=[],
            rows=[],
            row_count=0,
            columns_detected=0,
            record_tag=record_tag,
            root_tag=root_tag or "",
            errors=errors or ["No records found"]
        )
    
    # Build header (sorted for consistency)
    header = sorted(columns_seen)
    
    # Build rows
    rows = []
    for rec in records:
        row = [rec.get(col, "") for col in header]
        rows.append(row)
    
    return XmlToRowsResult(
        stub=stub,
        header=header,
        rows=rows,
        row_count=len(rows),
        columns_detected=len(header),
        record_tag=record_tag,
        root_tag=root_tag or "",
        errors=errors
    )


def rows_to_csv_string(header: List[str], rows: List[List[str]]) -> str:
    """Convert rows to CSV string."""
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(header)
    writer.writerows(rows)
    return output.getvalue()


def save_rows_to_csv(header: List[str], rows: List[List[str]], output_path: Path) -> None:
    """Save rows to a CSV file."""
    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(header)
        writer.writerows(rows)


# ============================================================
# Record Chunking for Embeddings
# ============================================================
def record_to_text(header: List[str], row: List[str], record_index: int) -> str:
    """
    Convert a single record to text for embedding.
    
    Args:
        header: Column headers
        row: Row values
        record_index: Index of this record
    
    Returns:
        Text representation of the record
    """
    lines = [f"[Record {record_index + 1}]"]
    for col, val in zip(header, row):
        if val:  # Skip empty values
            lines.append(f"  {col}: {val}")
    return "\n".join(lines)


def iter_record_chunks(
    header: List[str],
    rows: List[List[str]],
    stub: str,
    group: str,
    chunk_target_chars: int = CHUNK_TARGET_CHARS,
) -> Iterator[RecordChunk]:
    """
    Iterate over record chunks optimized for embedding.
    
    Groups records into chunks of approximately chunk_target_chars.
    
    Args:
        header: Column headers
        rows: Data rows
        stub: File identifier
        group: Group name
        chunk_target_chars: Target characters per chunk
    
    Yields:
        RecordChunk objects
    """
    current_text_parts = []
    current_indices = []
    current_len = 0
    chunk_index = 0
    
    for i, row in enumerate(rows):
        rec_text = record_to_text(header, row, i)
        rec_len = len(rec_text)
        
        # If adding this record exceeds target, emit current chunk
        if current_len > 0 and current_len + rec_len > chunk_target_chars:
            yield RecordChunk(
                stub=stub,
                group=group,
                chunk_index=chunk_index,
                record_indices=current_indices.copy(),
                text="\n\n".join(current_text_parts),
                char_count=current_len
            )
            chunk_index += 1
            current_text_parts = []
            current_indices = []
            current_len = 0
        
        current_text_parts.append(rec_text)
        current_indices.append(i)
        current_len += rec_len + 2  # +2 for \n\n separator
    
    # Emit final chunk
    if current_text_parts:
        yield RecordChunk(
            stub=stub,
            group=group,
            chunk_index=chunk_index,
            record_indices=current_indices,
            text="\n\n".join(current_text_parts),
            char_count=current_len
        )


def iter_xml_record_chunks(
    xml_entry: XmlEntry,
    group: str,
    chunk_target_chars: int = CHUNK_TARGET_CHARS,
    record_tag: Optional[str] = None,
) -> Iterator[RecordChunk]:
    """
    Convert XML to chunks directly for embedding.
    
    Args:
        xml_entry: XmlEntry from ZIP scanning
        group: Group name
        chunk_target_chars: Target characters per chunk
        record_tag: Override record tag detection
    
    Yields:
        RecordChunk objects
    """
    result = xml_to_rows(xml_entry.xml_path, record_tag=record_tag)
    
    if result.errors and not result.rows:
        logger.warning(f"XML to rows failed for {xml_entry.filename}: {result.errors}")
        return
    
    yield from iter_record_chunks(
        header=result.header,
        rows=result.rows,
        stub=xml_entry.stub,
        group=group,
        chunk_target_chars=chunk_target_chars
    )


# ============================================================
# CSV Processing
# ============================================================
def csv_to_chunks(
    csv_path: Path,
    group: str,
    chunk_target_chars: int = CHUNK_TARGET_CHARS,
    max_rows: int = 50_000,
) -> List[RecordChunk]:
    """
    Convert CSV file to chunks for embedding.
    
    Args:
        csv_path: Path to CSV file
        group: Group name
        chunk_target_chars: Target characters per chunk
        max_rows: Maximum rows to process
    
    Returns:
        List of RecordChunk objects
    """
    chunks = []
    stub = csv_path.stem
    
    try:
        with open(csv_path, "r", encoding="utf-8", errors="replace") as f:
            reader = csv.reader(f)
            header = next(reader, None)
            if not header:
                return []
            
            rows = []
            for i, row in enumerate(reader):
                if i >= max_rows:
                    break
                rows.append(row)
            
            for chunk in iter_record_chunks(header, rows, stub, group, chunk_target_chars):
                chunks.append(chunk)
    
    except Exception as e:
        logger.error(f"Error processing CSV {csv_path}: {e}")
    
    return chunks


# ============================================================
# Comparison / Delta Detection
# ============================================================
@dataclass
class DelteResult:
    """Result from comparing two datasets."""
    added_rows: List[List[str]]
    removed_rows: List[List[str]]
    changed_rows: List[Tuple[List[str], List[str]]]  # (old, new)
    common_header: List[str]
    left_only_cols: List[str]
    right_only_cols: List[str]


def compute_keyless_csv_delta(
    left_rows: List[List[str]],
    left_header: List[str],
    right_rows: List[List[str]],
    right_header: List[str],
) -> DelteResult:
    """
    Compute difference between two CSV datasets without a key column.
    Uses row hashing as a fallback.
    
    Args:
        left_rows: Rows from first dataset
        left_header: Header from first dataset
        right_rows: Rows from second dataset
        right_header: Header from second dataset
    
    Returns:
        DeltaResult with added, removed, and changed rows
    """
    # Find common columns
    left_set = set(left_header)
    right_set = set(right_header)
    common_cols = sorted(left_set & right_set)
    left_only = sorted(left_set - right_set)
    right_only = sorted(right_set - left_set)
    
    if not common_cols:
        # No common columns, treat all as different
        return DelteResult(
            added_rows=right_rows,
            removed_rows=left_rows,
            changed_rows=[],
            common_header=common_cols,
            left_only_cols=left_only,
            right_only_cols=right_only
        )
    
    # Get indices for common columns
    left_indices = [left_header.index(c) for c in common_cols]
    right_indices = [right_header.index(c) for c in common_cols]
    
    def row_hash(row: List[str], indices: List[int]) -> str:
        vals = [row[i] if i < len(row) else "" for i in indices]
        return hashlib.sha256("|".join(vals).encode()).hexdigest()
    
    def extract_common(row: List[str], indices: List[int]) -> List[str]:
        return [row[i] if i < len(row) else "" for i in indices]
    
    # Hash all rows
    left_hashes = {row_hash(r, left_indices): r for r in left_rows}
    right_hashes = {row_hash(r, right_indices): r for r in right_rows}
    
    left_keys = set(left_hashes.keys())
    right_keys = set(right_hashes.keys())
    
    added_keys = right_keys - left_keys
    removed_keys = left_keys - right_keys
    
    added_rows = [extract_common(right_hashes[k], right_indices) for k in added_keys]
    removed_rows = [extract_common(left_hashes[k], left_indices) for k in removed_keys]
    
    return DelteResult(
        added_rows=added_rows,
        removed_rows=removed_rows,
        changed_rows=[],  # Without keys, we can't detect changes vs add/remove
        common_header=common_cols,
        left_only_cols=left_only,
        right_only_cols=right_only
    )


# ============================================================
# Batch Processing
# ============================================================
def process_xml_entries_to_csv(
    xml_entries: List[XmlEntry],
    output_dir: Path,
    record_tag: Optional[str] = None,
) -> List[CsvArtifact]:
    """
    Process multiple XML entries to CSV files.
    
    Args:
        xml_entries: List of XmlEntry objects
        output_dir: Directory to write CSV files
        record_tag: Override record tag detection
    
    Returns:
        List of CsvArtifact objects
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    artifacts = []
    
    for entry in xml_entries:
        try:
            result = xml_to_rows(entry.xml_path, record_tag=record_tag)
            
            if result.rows:
                csv_path = output_dir / f"{entry.stub}.csv"
                save_rows_to_csv(result.header, result.rows, csv_path)
                
                artifacts.append(CsvArtifact(
                    stub=entry.stub,
                    csv_path=str(csv_path),
                    row_count=result.row_count,
                    columns=result.header,
                    source_xml=entry.logical_path,
                    group=""  # Set by caller
                ))
        except Exception as e:
            logger.error(f"Error processing {entry.filename}: {e}")
    
    return artifacts
