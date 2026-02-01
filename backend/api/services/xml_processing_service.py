"""
XML Processing Service using LXML and logic from main.py
Handles:
- ZIP file extraction and scanning
- XML file detection
- Group detection from files and paths
- XML to CSV flattening
- Record-wise chunking for embeddings
"""

import os
import tempfile
import zipfile
from pathlib import Path
from typing import List, Dict, Tuple, Optional, Iterator, Set
from collections import Counter, defaultdict
import logging

try:
    from lxml import etree as ET
except ImportError:
    import xml.etree.ElementTree as ET

logger = logging.getLogger(__name__)


def strip_ns(tag) -> str:
    """Remove namespace from XML tag.
    Handles Comments and ProcessingInstructions which have callable tags.
    """
    # Handle Comments and ProcessingInstructions (tag is a function)
    if not isinstance(tag, str):
        # For Comment/PI elements, return a special marker
        if callable(tag):
            return "__SKIP__"
        return str(tag) if tag else "__SKIP__"
    
    if '}' in tag:
        return tag.split('}', 1)[1]
    return tag


def extract_alpha_prefix(token: str) -> str:
    """Extract alphabetic prefix from a string"""
    out = []
    for ch in token:
        if ch.isalpha():
            out.append(ch)
        else:
            break
    return "".join(out).upper()


def infer_group_from_folder(folder_full: str, custom_prefixes: Optional[Set[str]] = None) -> str:
    """Infer group from folder path"""
    if not folder_full or "/" not in folder_full:
        return "OTHER"
    
    # Get first folder
    root_folder = folder_full.split("/")[0]
    alpha = extract_alpha_prefix(root_folder)
    
    if custom_prefixes and alpha in custom_prefixes:
        return alpha
    return alpha if alpha else "OTHER"


def infer_group_from_filename(filename: str, custom_prefixes: Optional[Set[str]] = None) -> str:
    """Infer group from filename"""
    base = Path(filename).stem
    token = base.split("_", 1)[0] if "_" in base else base
    alpha = extract_alpha_prefix(token)
    
    if custom_prefixes and alpha in custom_prefixes:
        return alpha
    return alpha if alpha else "OTHER"


def infer_group(logical_path: str, filename: str, custom_prefixes: Optional[Set[str]] = None) -> str:
    """Infer group from path and filename"""
    # Try folder-based detection first
    group = infer_group_from_folder(logical_path, custom_prefixes)
    if group != "OTHER":
        return group
    
    # Fall back to filename-based
    return infer_group_from_filename(filename, custom_prefixes)


def safe_extract_zip(
    zip_path: Path,
    extract_to: Path,
    max_ratio: int = 200,
    max_total_mb: Optional[int] = None,
) -> Tuple[int, int]:
    """
    Safely extract ZIP with compression checks
    Returns: (files_extracted, total_bytes)
    """
    extract_to.mkdir(parents=True, exist_ok=True)
    files_extracted = 0
    total_bytes = 0
    
    try:
        with zipfile.ZipFile(zip_path, 'r') as zf:
            for info in zf.infolist():
                # Check compression ratio
                if info.compress_size > 0:
                    ratio = info.file_size / info.compress_size
                    if ratio > max_ratio:
                        logger.warning(f"Skipping {info.filename}: compression ratio {ratio} > {max_ratio}")
                        continue
                
                # Check total size
                if max_total_mb and total_bytes + info.file_size > max_total_mb * 1024 * 1024:
                    logger.warning(f"Stopping extraction: total size would exceed {max_total_mb}MB")
                    break
                
                # Extract
                zf.extract(info, extract_to)
                files_extracted += 1
                total_bytes += info.file_size
    
    except Exception as e:
        logger.error(f"Failed to extract ZIP: {e}")
        raise
    
    return files_extracted, total_bytes


def scan_zip_for_xml(
    zip_path: Path,
    temp_dir: Optional[Path] = None,
    max_depth: int = 10,
    custom_prefixes: Optional[Set[str]] = None,
) -> Tuple[List[Dict], Dict[str, List[Dict]], int]:
    """
    Scan ZIP for XML files and group them
    
    Returns:
        (xml_files_list, groups_dict, total_size)
    """
    if temp_dir is None:
        temp_dir = Path(tempfile.mkdtemp(prefix="ret_scan_"))
    
    extract_dir = temp_dir / "extracted"
    extract_dir.mkdir(parents=True, exist_ok=True)
    
    # Extract ZIP
    safe_extract_zip(zip_path, extract_dir)
    
    # Find XML files
    xml_files: List[Dict[str, str]] = []
    groups: Dict[str, List[Dict]] = defaultdict(list)
    group_counter: Counter = Counter()
    total_size = 0
    
    for xml_path in extract_dir.rglob("*.xml"):
        relative_path = str(xml_path.relative_to(extract_dir))
        group = infer_group(relative_path, xml_path.name, custom_prefixes)
        
        file_size = xml_path.stat().st_size
        total_size += file_size
        
        file_info = {
            "filename": xml_path.name,
            "path": relative_path,
            "group": group,
            "size": file_size,
            "abs_path": str(xml_path),
        }
        
        xml_files.append(file_info)
        groups[group].append(file_info)
        group_counter[group] += 1
    
    return xml_files, dict(groups), total_size


def flatten_element(
    elem,
    current_path: str,
    row: dict,
    header_order: List[str],
    header_seen: set,
    path_sep: str = ".",
    include_root: bool = False,
    max_field_len: int = 300
):
    """Recursively flatten XML element into row dict - matching main.py logic"""
    stack = [(elem, current_path)]
    
    while stack:
        node, base_path = stack.pop()
        tag_name = strip_ns(node.tag if hasattr(node, 'tag') else str(node))
        
        if not base_path:
            path_here = tag_name if include_root else ""
        else:
            path_here = base_path
        
        # Add attributes
        attrib = getattr(node, 'attrib', {})
        if attrib and path_here:
            for attr_name, attr_val in attrib.items():
                key = f"{path_here}@{attr_name}"
                if key not in row:
                    val = str(attr_val)[:max_field_len] if attr_val else ""
                    row[key] = val
                    if key not in header_seen:
                        header_order.append(key)
                        header_seen.add(key)
        
        # Check for child elements
        children = list(node) if hasattr(node, '__iter__') else []
        
        if not children:
            # Leaf node - add text content
            text_val = (getattr(node, 'text', '') or '').strip()
            if path_here:
                if path_here not in row:
                    row[path_here] = text_val[:max_field_len] if text_val else ""
                    if path_here not in header_seen:
                        header_order.append(path_here)
                        header_seen.add(path_here)
        else:
            # Process children with index tracking for repeated tags
            from collections import defaultdict
            local_counts = defaultdict(int)
            
            for child in reversed(children):
                child_tag = strip_ns(child.tag)
                # Skip Comments and ProcessingInstructions
                if child_tag == "__SKIP__":
                    continue
                key_base = f"{path_here}{path_sep}{child_tag}" if path_here else child_tag
                local_counts[key_base] += 1
                idx = local_counts[key_base]
                child_path = key_base if idx == 1 else f"{key_base}[{idx}]"
                stack.append((child, child_path))


def find_record_elements(root, record_tag: Optional[str], auto_detect: bool) -> Tuple[str, List]:
    """Find record elements in XML - matching main.py logic"""
    # If explicit record tag provided, use it
    if record_tag:
        # Try exact match with namespace stripping
        matches = [el for el in root.iter() if strip_ns(el.tag) == record_tag]
        if matches:
            return record_tag, matches
        # Fallback to findall
        elements = root.findall(f".//{record_tag}")
        if elements:
            return record_tag, elements
        # If nothing found, fall back to root
        return record_tag, [root]
    
    if auto_detect:
        # Find repeated child tag among root's immediate children
        # Filter out Comments and ProcessingInstructions
        children = [c for c in root if strip_ns(c.tag) != "__SKIP__"]
        if children:
            child_tags = [strip_ns(c.tag) for c in children]
            counts = Counter(child_tags)
            repeated = [t for t, c in counts.items() if c > 1]
            if repeated:
                chosen = repeated[0]
                elems = [c for c in children if strip_ns(c.tag) == chosen]
                return f"AUTO:{chosen}", elems
    
    # Fallback: treat each root child as a record (excluding Comments/PIs)
    elems = [c for c in root if strip_ns(c.tag) != "__SKIP__"]
    return "FALLBACK:root_children", elems if elems else [root]


def xml_to_rows(
    xml_bytes: bytes,
    record_tag: Optional[str] = None,
    auto_detect: bool = True,
    path_sep: str = ".",
    include_root: bool = False,
    max_field_len: int = 300
) -> Tuple[List[dict], List[str], str]:
    """
    Parse XML and convert to rows
    
    Returns:
        (rows, headers, detected_record_tag)
    """
    try:
        root = ET.fromstring(xml_bytes)
    except Exception as e:
        logger.error(f"Failed to parse XML: {e}")
        return [], [], ""
    
    record_tag_used, records = find_record_elements(root, record_tag, auto_detect)
    
    rows = []
    header_order = []
    header_seen = set()
    
    for record in records:
        row = {}
        flatten_element(
            record, "", row, header_order, header_seen,
            path_sep, include_root, max_field_len
        )
        if row:
            rows.append(row)
    
    return rows, header_order, record_tag_used


def iter_xml_record_chunks(
    xml_path: str,
    record_tag: Optional[str] = None,
    auto_detect: bool = True,
    max_records: int = 5000,
    max_chars_per_record: int = 6000,
) -> Iterator[Tuple[int, str, str]]:
    """
    Stream XML records in chunks (for embeddings)
    
    Yields:
        (record_index, record_tag, serialized_record_text)
    """
    try:
        tree = ET.parse(xml_path)
        root = tree.getroot()
    except Exception as e:
        logger.error(f"Failed to parse {xml_path}: {e}")
        return
    
    record_tag_used, records = find_record_elements(root, record_tag, auto_detect)
    
    for idx, record in enumerate(records):
        if idx >= max_records:
            break
        
        try:
            record_str = ET.tostring(record, encoding='unicode')
            # Truncate if needed
            if len(record_str) > max_chars_per_record:
                record_str = record_str[:max_chars_per_record] + "..."
            
            yield idx, record_tag_used, record_str
        except Exception as e:
            logger.warning(f"Failed to serialize record {idx}: {e}")
            continue


def write_rows_to_csv(rows: List[dict], headers: List[str], out_csv: Path):
    """Write rows to CSV file"""
    import csv
    
    try:
        with open(out_csv, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=headers)
            writer.writeheader()
            writer.writerows(rows)
        logger.info(f"Wrote {len(rows)} rows to {out_csv}")
    except Exception as e:
        logger.error(f"Failed to write CSV: {e}")
        raise


def detect_record_tag_auto(xml_path: str) -> Optional[str]:
    """Auto-detect record tag from XML file"""
    try:
        tree = ET.parse(xml_path)
        root = tree.getroot()
        
        child_tags = Counter()
        for child in root:
            tag = strip_ns(child.tag)
            child_tags[tag] += 1
        
        if child_tags:
            return child_tags.most_common(1)[0][0]
    except Exception as e:
        logger.error(f"Failed to detect record tag: {e}")
    
    return None
