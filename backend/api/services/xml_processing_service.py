"""
XML Processing Service using LXML and logic from main.py
Handles:
- ZIP file extraction and scanning with NESTED ZIP support
- XML file detection
- Group detection from MODULE PREFIX of business ZIPs
- XML to CSV flattening
- Record-wise chunking for embeddings

Grouping Strategy:
- Groups are defined by the MODULE PREFIX of business ZIPs (e.g., AR_PAYMENT_TERM.zip → AR)
- Root ZIPs (like "Manufacturing and Supply Chain...zip") do NOT become groups
- Batch ZIPs (like "1_BATCH.zip", "2_BATCH.zip") do NOT become groups - they inherit from parent
- Folders are traversed but do NOT become groups
"""

import os
import re
import tempfile
import zipfile
import shutil
import time
from pathlib import Path
from typing import List, Dict, Tuple, Optional, Iterator, Set, Literal
from collections import Counter, defaultdict
from dataclasses import dataclass, field
import logging

# LXML is required for better performance and proper XML handling
try:
    from lxml import etree as ET
    LXML_AVAILABLE = True
    logger = logging.getLogger(__name__)
    logger.info("Using LXML for XML processing (recommended)")
except ImportError:
    import xml.etree.ElementTree as ET
    LXML_AVAILABLE = False
    logger = logging.getLogger(__name__)
    logger.warning("LXML not available - using slower ElementTree. Install lxml for better performance: pip install lxml")

logger = logging.getLogger(__name__)

# Pattern to detect batch ZIPs like: 1_BATCH.zip, 7_BATCH (1).zip, 123_BATCH.zip, etc.
BATCH_ZIP_PATTERN = re.compile(r"^\d+[_\-]?BATCH", re.IGNORECASE)

# Pattern to detect root/container ZIPs that should NOT become groups
# These are usually long names with timestamps like: "Manufacturing and Supply Chain...20260113_055727.zip"
ROOT_ZIP_PATTERN = re.compile(r".*_\d{8}_\d{4,6}.*\.zip$", re.IGNORECASE)

# Memory-efficient processing thresholds
STREAMING_THRESHOLD_MB = 100  # Use streaming for files larger than this
MAX_MEMORY_ROWS = 50000  # Maximum rows to keep in memory at once


@dataclass
class XmlFileEntry:
    """Represents a single XML file found during scanning"""
    filename: str
    path: str  # Logical path within the ZIP hierarchy
    group: str
    size: int
    abs_path: str  # Physical path on disk
    # Metadata for tree display
    business_zip: str = ""  # The business ZIP this file belongs to (e.g., "AR_PAYMENT_TERM.zip")
    folder_path: str = ""   # Folder path after the business ZIP
    root_folder: str = ""   # First folder after business ZIP
    zip_chain: List[str] = field(default_factory=list)  # Chain of ZIPs traversed


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
    """Extract alphabetic prefix from a string (letters before first non-letter)"""
    out = []
    for ch in token:
        if ch.isalpha():
            out.append(ch)
        else:
            break
    return "".join(out).upper()


def is_batch_zip(filename: str) -> bool:
    """Check if filename is a batch ZIP like 1_BATCH.zip, 7_BATCH.zip, etc."""
    stem = Path(filename).stem
    return bool(BATCH_ZIP_PATTERN.match(stem))


def is_root_zip(filename: str) -> bool:
    """Check if filename looks like a root/container ZIP (not a business module ZIP)"""
    # Root ZIPs typically have timestamps and long descriptive names
    if ROOT_ZIP_PATTERN.match(filename):
        return True
    # Also check if the name has spaces (business ZIPs usually don't)
    stem = Path(filename).stem
    if " " in stem and len(stem) > 30:
        return True
    return False


def extract_group_from_zipname(zip_filename: str, prefix_len: Optional[int] = None) -> Optional[str]:
    """
    Extract group name from ZIP filename or folder name.
    Uses actual ZIP/folder name as group, removing extension and cleaning up.
    
    Examples:
        AR_PAYMENT_TERM.zip → AR_PAYMENT_TERM
        Manufacturing.zip → Manufacturing
        1_book.zip → book (numbered prefixes use base name)
        2_BATCH.zip → None (batch ZIPs don't become groups)
    
    Args:
        zip_filename: ZIP filename or folder name
        prefix_len: Ignored (kept for backward compatibility)
    
    Returns:
        Group name (uppercase) or None if not a valid business ZIP/folder
    """
    stem = Path(zip_filename).stem
    
    # Skip batch ZIPs
    if is_batch_zip(zip_filename):
        return None
    
    # Skip root ZIPs
    if is_root_zip(zip_filename):
        return None
    
    # Handle numbered prefixes like "1_book" or "2_article" → use base name
    # Check if stem starts with digit(s) followed by underscore or dash
    import re
    numbered_match = re.match(r'^(\d+)[_-](.+)$', stem)
    if numbered_match:
        # Use the part after the number separator
        base_name = numbered_match.group(2)
        return base_name.upper()
    
    # Return full stem as group name
    return stem.upper()


def infer_group_from_folder(folder_full: str, custom_prefixes: Optional[Set[str]] = None) -> str:
    """Infer group from folder path (legacy support)"""
    if not folder_full or "/" not in folder_full:
        return "EXTRAS"

    # Get first folder
    root_folder = folder_full.split("/")[0]
    alpha = extract_alpha_prefix(root_folder)

    if custom_prefixes and alpha in custom_prefixes:
        return alpha
    return alpha if alpha else "EXTRAS"


def infer_group_from_filename(filename: str, custom_prefixes: Optional[Set[str]] = None) -> str:
    """Infer group from filename (legacy support)"""
    base = Path(filename).stem
    token = base.split("_", 1)[0] if "_" in base else base
    alpha = extract_alpha_prefix(token)

    if custom_prefixes and alpha in custom_prefixes:
        return alpha
    return alpha if alpha else "EXTRAS"


def infer_group(logical_path: str, filename: str, custom_prefixes: Optional[Set[str]] = None) -> str:
    """Infer group from path and filename (legacy fallback)"""
    # Try folder-based detection first
    group = infer_group_from_folder(logical_path, custom_prefixes)
    if group != "EXTRAS":
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
    group_prefix_len: Optional[int] = None,
    max_files: int = 20000,
    max_unzipped_bytes: int = 300 * 1024 * 1024,
) -> Tuple[List[Dict], Dict[str, List[Dict]], int]:
    """
    Recursively scan ZIP (and nested ZIPs) for XML files.
    Groups by MODULE PREFIX of business ZIPs.
    
    Grouping Rules:
    - Business ZIPs like AR_PAYMENT_TERM.zip → group "AR"
    - Root ZIPs (long names with timestamps) do NOT become groups
    - Batch ZIPs (1_BATCH.zip) inherit group from nearest business ZIP
    - Folders are traversed but do NOT affect grouping
    
    Args:
        zip_path: Path to the ZIP file
        temp_dir: Working directory (will use session dir if provided)
        max_depth: Maximum nesting depth for ZIPs within ZIPs
        custom_prefixes: Optional set of known prefixes
        group_prefix_len: Optional max length for group prefix (2, 3, 4...)
        max_files: Maximum XML files to collect
        max_unzipped_bytes: Maximum total bytes to extract
    
    Returns:
        (xml_files_list, groups_dict, total_size)
    """
    if temp_dir is None:
        temp_dir = Path(tempfile.mkdtemp(prefix="ret_scan_"))
    
    extract_dir = temp_dir / "extracted"
    extract_dir.mkdir(parents=True, exist_ok=True)
    
    xml_files: List[Dict] = []
    groups: Dict[str, List[Dict]] = defaultdict(list)
    total_bytes_copied = 0
    files_found = 0
    
    def _get_group_for_zip_chain(zip_chain: List[str]) -> str:
        """
        Find the module group from a chain of ZIP names.

        The chain goes from root to current, e.g.:
        ["Manufacturing...zip", "businessObjectData", "AR_PAYMENT_TERM.zip"]

        We find the first valid business ZIP/folder (not root, not batch) and use its name as group.
        If no business ZIP found, XML is at the container root level → "ROOT".
        """
        for zip_name in zip_chain:
            # Try to extract group from ZIP files
            if zip_name.lower().endswith(".zip"):
                group = extract_group_from_zipname(zip_name, group_prefix_len)
                if group:
                    return group
            else:
                # It's a folder - use folder name as group (unless it looks like a generic path)
                folder_name = Path(zip_name).name
                # Skip generic folder names like "businessObjectData", "data", "files", etc.
                if folder_name.lower() not in ["businessobjectdata", "data", "files", "content", "extracted"]:
                    # Handle numbered folders like "1_book" → "book"
                    import re
                    numbered_match = re.match(r'^(\d+)[_-](.+)$', folder_name)
                    if numbered_match:
                        return numbered_match.group(2).upper()
                    return folder_name.upper()

        # No business ZIP/folder found — XML is at root level
        return "ROOT"
    
    def _recursive_scan(
        current_path: Path,
        depth: int,
        zip_chain: List[str],
        current_group: str,
    ):
        """Recursively scan directory for XMLs and nested ZIPs"""
        nonlocal total_bytes_copied, files_found
        
        if depth > max_depth:
            logger.warning(f"Max depth {max_depth} reached, stopping recursion")
            return
        
        if files_found >= max_files:
            logger.warning(f"Max files {max_files} reached, stopping scan")
            return
        
        if not current_path.exists():
            return
        
        # Collect items to process (files and directories)
        try:
            items = list(current_path.iterdir())
        except Exception as e:
            logger.warning(f"Failed to read directory {current_path}: {e}")
            return
        
        # Process nested ZIPs first (so we can recurse into them)
        nested_zips = [p for p in items if p.suffix.lower() == ".zip" and p.is_file()]
        xml_files_here = [p for p in items if p.suffix.lower() == ".xml" and p.is_file()]
        subdirs = [p for p in items if p.is_dir()]
        
        # Process nested ZIPs
        for nested_idx, nested_zip in enumerate(nested_zips, 1):
            if total_bytes_copied >= max_unzipped_bytes:
                logger.warning(f"  Max unzipped bytes {max_unzipped_bytes} reached at depth {depth}")
                break
            
            nested_name = nested_zip.name
            
            # Determine the group for this ZIP's contents
            new_chain = zip_chain + [nested_name]
            nested_group = _get_group_for_zip_chain(new_chain)
            
            # If this ZIP is a batch ZIP, inherit the current group
            if is_batch_zip(nested_name):
                nested_group = current_group
            
            logger.info(f"  [Depth {depth}] Processing nested ZIP {nested_idx}/{len(nested_zips)}: {nested_name} → group='{nested_group}'")
            
            # Extract nested ZIP
            nested_extract_dir = extract_dir / f"_nested_{depth}_{nested_zip.stem}"
            try:
                nested_extract_dir.mkdir(parents=True, exist_ok=True)
                zip_entries = 0
                
                with zipfile.ZipFile(nested_zip, 'r') as zf:
                    nested_total = len(zf.infolist())
                    for info in zf.infolist():
                        if info.is_dir():
                            continue
                        
                        # Check compression ratio
                        if info.compress_size > 0:
                            ratio = info.file_size / info.compress_size
                            if ratio > 200:
                                logger.warning(f"    Skipping {info.filename}: high compression ratio {ratio}")
                                continue
                        
                        total_bytes_copied += info.file_size
                        if total_bytes_copied > max_unzipped_bytes:
                            logger.warning(f"    Stopping extraction of {nested_name}: max bytes exceeded")
                            break
                        
                        zf.extract(info, nested_extract_dir)
                        zip_entries += 1
                
                logger.info(f"    ✓ Extracted {zip_entries} entries from {nested_name}")
                
                # Recurse into the extracted content
                _recursive_scan(nested_extract_dir, depth + 1, new_chain, nested_group)
                
            except Exception as e:
                logger.error(f"    ✗ Failed to extract nested ZIP {nested_name}: {e}")
        
        # Process XML files at this level
        if xml_files_here:
            logger.info(f"  [Depth {depth}] Found {len(xml_files_here)} XML files in '{current_path.name}'")
        
        for xml_idx, xml_file in enumerate(xml_files_here, 1):
            if files_found >= max_files:
                logger.warning(f"  Max files limit {max_files} reached")
                break
            
            try:
                file_size = xml_file.stat().st_size
                relative_path = str(xml_file.relative_to(extract_dir))
                
                # Determine the group for this XML
                # Use the current_group determined by the ZIP chain
                group = current_group if current_group != "EXTRAS" else infer_group_from_filename(xml_file.name, custom_prefixes)
                
                # Build folder path metadata
                folder_path = ""
                root_folder = ""
                if "/" in relative_path:
                    folder_parts = relative_path.rsplit("/", 1)[0].split("/")
                    folder_path = "/".join(folder_parts)
                    root_folder = folder_parts[0] if folder_parts else ""
                
                file_info = {
                    "filename": xml_file.name,
                    "path": relative_path,
                    "group": group,
                    "size": file_size,
                    "abs_path": str(xml_file),
                    "business_zip": zip_chain[-1] if zip_chain and zip_chain[-1].lower().endswith(".zip") else "",
                    "folder_path": folder_path,
                    "root_folder": root_folder,
                    "zip_chain": zip_chain.copy(),
                }
                
                xml_files.append(file_info)
                groups[group].append(file_info)
                files_found += 1
                
                if files_found % 50 == 0:
                    logger.info(f"    Progress: {files_found} XML files processed...")
                
            except Exception as e:
                logger.warning(f"    ✗ Failed to process XML {xml_file.name}: {e}")
        
        # Process subdirectories (folders - just traverse, don't change group)
        for subdir in subdirs:
            if total_bytes_copied >= max_unzipped_bytes:
                break
            if files_found >= max_files:
                break
            
            folder_name = subdir.name
            new_chain = zip_chain + [folder_name]
            
            # Skip system/hidden folders
            if folder_name.startswith('.') or folder_name.startswith('_'):
                continue
            
            # Folders do NOT change the group - we inherit from the ZIP
            _recursive_scan(subdir, depth, new_chain, current_group)
    
    # Step 1: Extract root ZIP
    scan_start = time.time()
    logger.info(f"========== Starting ZIP scan: {zip_path.name} ==========")
    logger.info(f"  Max depth: {max_depth}, Max files: {max_files}, Max bytes: {max_unzipped_bytes}")
    root_zip_name = zip_path.name
    is_root = is_root_zip(root_zip_name)
    
    try:
        with zipfile.ZipFile(zip_path, 'r') as zf:
            total_entries = len(zf.infolist())
            logger.info(f"  Extracting root ZIP with {total_entries} entries...")
            extracted_count = 0
            for info in zf.infolist():
                if info.is_dir():
                    continue
                
                # Check compression ratio
                if info.compress_size > 0:
                    ratio = info.file_size / info.compress_size
                    if ratio > 200:
                        logger.warning(f"  Skipping {info.filename}: high compression ratio {ratio}")
                        continue
                
                total_bytes_copied += info.file_size
                if total_bytes_copied > max_unzipped_bytes:
                    logger.warning(f"  Stopping extraction: max bytes {total_bytes_copied} exceeded limit {max_unzipped_bytes}")
                    break
                
                zf.extract(info, extract_dir)
                extracted_count += 1
                if extracted_count % 100 == 0:
                    logger.info(f"  Extracted {extracted_count}/{total_entries} entries ({total_bytes_copied / 1024 / 1024:.1f} MB)")
            
            logger.info(f"  ✓ Root ZIP extraction complete: {extracted_count} files, {total_bytes_copied / 1024 / 1024:.1f} MB")
    except Exception as e:
        logger.error(f"Failed to extract root ZIP: {e}")
        raise
    
    # Step 2: Recursively scan extracted content
    # Root ZIPs get "ROOT" group; business ZIPs get their name as group
    root_chain = [root_zip_name]
    initial_group = "ROOT" if is_root else extract_group_from_zipname(root_zip_name, group_prefix_len) or "ROOT"
    
    _recursive_scan(extract_dir, depth=1, zip_chain=root_chain, current_group=initial_group)
    
    total_size = sum(f["size"] for f in xml_files)

    # ── Group deduplication ──────────────────────────────────────────
    # ZIP names and folder names can both produce the same group name.
    # Merge duplicates (case-insensitive) so each file belongs to exactly
    # one canonical group and no file appears in multiple groups.
    canonical: Dict[str, str] = {}           # lower -> first-seen original
    merged_groups: Dict[str, List[Dict]] = defaultdict(list)
    seen_file_ids: Dict[str, str] = {}       # abs_path -> assigned group

    for group_name, file_list in groups.items():
        key = group_name.strip().upper()
        canon = canonical.setdefault(key, key)

        for finfo in file_list:
            fid = finfo.get("abs_path", finfo.get("path", ""))
            if fid in seen_file_ids:
                # Already assigned to another group – skip duplicate
                continue
            # Normalise the group stored on the file entry
            finfo["group"] = canon
            merged_groups[canon].append(finfo)
            seen_file_ids[fid] = canon

    groups = dict(merged_groups)

    # Also normalise group on the flat xml_files list
    for f in xml_files:
        key = (f.get("group") or "EXTRAS").strip().upper()
        f["group"] = canonical.get(key, key)

    scan_duration = time.time() - scan_start
    logger.info(f"========== Scan complete in {scan_duration:.2f}s ==========")
    logger.info(f"  XML files found: {len(xml_files)}")
    logger.info(f"  Groups detected: {len(groups)}")
    logger.info(f"  Total size: {total_size / 1024 / 1024:.2f} MB")
    logger.info(f"  Average: {scan_duration / max(len(xml_files), 1):.3f}s per file")
    for group_name, group_files in sorted(groups.items()):
        logger.info(f"    Group '{group_name}': {len(group_files)} files")
    
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


def xml_to_rows_streaming(
    xml_path: Path,
    record_tag: Optional[str] = None,
    auto_detect: bool = True,
    path_sep: str = ".",
    include_root: bool = False,
    max_field_len: int = 300,
    chunk_size: int = 10000
) -> Iterator[Tuple[List[dict], List[str], str]]:
    """
    Stream-parse large XML files and yield rows in chunks to avoid memory issues.
    
    For files larger than STREAMING_THRESHOLD_MB, this function yields rows in batches
    instead of loading the entire file into memory.
    
    Args:
        xml_path: Path to XML file
        record_tag: Optional specific record tag to look for
        auto_detect: Auto-detect record tag if not specified
        path_sep: Field path separator
        include_root: Include root element in paths
        max_field_len: Maximum field length
        chunk_size: Rows per chunk to yield
    
    Yields:
        Tuples of (rows, headers, detected_record_tag)
    """
    if not LXML_AVAILABLE:
        logger.warning("Streaming requires LXML. Falling back to full load.")
        # Fallback to non-streaming
        with open(xml_path, "rb") as f:
            xml_bytes = f.read()
        rows, headers, tag_used = xml_to_rows(
            xml_bytes, record_tag, auto_detect, path_sep, include_root, max_field_len
        )
        yield rows, headers, tag_used
        return
    
    try:
        # First pass: detect record tag if needed
        detected_tag = record_tag
        if auto_detect and not record_tag:
            # Quick scan to detect record tag
            tree = ET.parse(str(xml_path))
            root = tree.getroot()
            detected_tag, _ = find_record_elements(root, None, True)
            del tree, root  # Free memory
        
        # Second pass: stream parse with iterparse
        context = ET.iterparse(str(xml_path), events=('end',), tag=detected_tag if detected_tag else None)
        
        rows_batch = []
        header_order = []
        header_seen = set()
        
        for event, elem in context:
            # Skip if not our target tag (when no specific tag)
            if detected_tag and strip_ns(elem.tag) != detected_tag:
                elem.clear()
                continue
            
            row = {}
            flatten_element(
                elem, "", row, header_order, header_seen,
                path_sep, include_root, max_field_len
            )
            
            if row:
                rows_batch.append(row)
            
            # Clear element to free memory
            elem.clear()
            while elem.getprevious() is not None:
                del elem.getparent()[0]
            
            # Yield batch when chunk size reached
            if len(rows_batch) >= chunk_size:
                yield rows_batch, header_order, detected_tag or "root"
                rows_batch = []
        
        # Yield remaining rows
        if rows_batch:
            yield rows_batch, header_order, detected_tag or "root"
        
        del context
        
    except Exception as e:
        logger.error(f"Streaming parse failed for {xml_path}: {e}")
        # Fallback to regular parsing if streaming fails
        try:
            with open(xml_path, "rb") as f:
                xml_bytes = f.read()
            rows, headers, tag_used = xml_to_rows(
                xml_bytes, record_tag, auto_detect, path_sep, include_root, max_field_len
            )
            yield rows, headers, tag_used
        except Exception as fallback_err:
            logger.exception(f"Fallback parse also failed: {fallback_err}")
            yield [], [], ""


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
