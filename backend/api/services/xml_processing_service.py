
"""
XML Processing Service (extended) using LXML and logic from main.py

Handles:
- ZIP scanning with NESTED ZIP support (in-memory scan; writes ONLY target files to disk)
- File detection: XML, XML.GZ, CSV, XLSX, XLS
- Group detection from business ZIP names (root ZIPs do NOT become groups)
- XML to CSV flattening
- Streaming record chunking for embeddings

UPDATED GROUPING STRATEGY (per requirement):
- All detected group names follow a naming pattern like:
    2-3 letters + "_" + rest   (e.g., AR_PAYMENT_TERM, FND_APP_TREE, ORA_FND_...)
- We now create the group using ONLY these 2-3 letters.
    AR_PAYMENT_TERM -> AR
    FND_APP_DESCRIPTIVE_FLEXFIELD -> FND
    ORA_FND_* -> ORA
- If a name has no usable alphabetic prefix of length >= 2, it falls back to EXTRAS.

Other grouping rules kept:
- Root/container ZIPs do NOT become groups (group becomes "ROOT")
- Batch ZIPs (1_BATCH.zip, 2_BATCH.zip) do NOT become groups - they inherit parent group
- Folders are traversed but do NOT become groups

IMPORTANT GROUP RULE (also required):
- All groups with the same name must be merged into the same group.
  This file enforces canonical group keys using normalize_group_name().

NEW (per requirement):
- Scanning now includes not only XML but also CSV/XLSX/XLS.
- All discovered files are returned in the SAME grouping structure and the same UI metadata model.
- Backwards compatible: scan_zip_for_xml() still returns ONLY XML entries.
"""

from __future__ import annotations

import io
import re
import time
import gzip
import zipfile
import tempfile
import shutil
import hashlib
import logging
from pathlib import Path
from typing import Any, List, Dict, Tuple, Optional, Iterator, Set, Literal, cast
from collections import Counter, defaultdict
from dataclasses import dataclass, field

# -----------------------------------------------------------------------------
# Logging / XML parser (LXML optional)
# -----------------------------------------------------------------------------

logger = logging.getLogger(__name__)

try:
    from lxml import etree as ET  # type: ignore
    LXML_AVAILABLE = True
    logger.info("Using LXML for XML processing (recommended)")
except ImportError:
    import xml.etree.ElementTree as ET  # type: ignore
    LXML_AVAILABLE = False
    logger.warning(
        "LXML not available - using ElementTree. "
        "Install lxml for better performance: pip install lxml"
    )

# -----------------------------------------------------------------------------
# Patterns & thresholds
# -----------------------------------------------------------------------------

BATCH_ZIP_PATTERN = re.compile(r"^\d+[_\-]?BATCH", re.IGNORECASE)
ROOT_ZIP_PATTERN = re.compile(r".*_\d{8}_\d{4,6}.*\.zip$", re.IGNORECASE)

STREAMING_THRESHOLD_MB = 100  # Use streaming for files larger than this
MAX_MEMORY_ROWS = 50000

DEFAULT_MAX_RATIO = 200
MAX_NESTED_ZIP_UNCOMPRESSED_MB = 256  # skip huge nested ZIP members (uncompressed)

_INVALID_WIN_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1F]')

ScanFileType = Literal["xml", "csv", "xlsx", "xls"]


# -----------------------------------------------------------------------------
# Data model
# -----------------------------------------------------------------------------

@dataclass
class ScanFileEntry:
    """
    Represents a single discovered file (XML/CSV/XLSX/XLS) found during scanning.
    """
    filename: str                     # original member name (e.g. AR_SOMETHING.xml)
    path: str                         # sanitized member path inside its containing zip
    logical_path: str                 # zip_chain + member path (real/meaningful name)
    group: str
    size: int                         # bytes written (inflated for xml.gz)
    abs_path: str                     # physical path on disk for conversion / pass-through
    file_type: ScanFileType           # xml/csv/xlsx/xls

    # Metadata for UI/tree display
    business_zip: str = ""
    folder_path: str = ""
    root_folder: str = ""
    zip_chain: List[str] = field(default_factory=list)


# -----------------------------------------------------------------------------
# Canonical group handling (merges same-name groups)
# -----------------------------------------------------------------------------

def normalize_group_name(group: Optional[str]) -> str:
    g = (group or "").strip().upper()
    return g if g else "EXTRAS"


def _module_prefix_2_3(name: str) -> str:
    """
    Extract module group as ONLY 2–3 letters.

    Rules:
    - Remove leading numeric prefix like "1_" or "2-" if present
    - Take the substring before first "_" (primary delimiter)
    - Keep only alphabetic characters from that substring
    - If >=2 letters: return first 3 letters (so result is 2–3 letters)
    - Else: return "EXTRAS"
    """
    s = (name or "").strip()
    if not s:
        return "EXTRAS"

    s = Path(s).stem
    s = re.sub(r"^\d+[_\-]+", "", s)

    prefix = s.split("_", 1)[0] if "_" in s else s
    letters = "".join(ch for ch in prefix if ch.isalpha()).upper()

    if len(letters) >= 2:
        return normalize_group_name(letters[:3])
    return "EXTRAS"


def _disk_name_from_logical_path(logical_path: str, suffix: str) -> str:
    """
    Produce a safe deterministic short disk filename based on logical path.

    The *logical_path* preserves the "real name" for UI + later output naming.
    """
    logical_path = _sanitize_member_path(logical_path)
    base = Path(logical_path).name
    base = _INVALID_WIN_CHARS.sub("_", base)
    stem = Path(base).stem[:40] or "file"
    h = hashlib.sha1(logical_path.encode("utf-8")).hexdigest()[:16]
    return f"{stem}__{h}{suffix}"


# -----------------------------------------------------------------------------
# Utility functions
# -----------------------------------------------------------------------------

def strip_ns(tag: Any) -> str:
    if not isinstance(tag, str):
        if callable(tag):
            return "__SKIP__"
        return str(tag) if tag else "__SKIP__"
    if "}" in tag:
        return tag.split("}", 1)[1]
    return tag


def extract_alpha_prefix(token: str) -> str:
    out: List[str] = []
    for ch in token:
        if ch.isalpha():
            out.append(ch)
        else:
            break
    return "".join(out).upper()


def is_batch_zip(filename: str) -> bool:
    stem = Path(filename).stem
    return bool(BATCH_ZIP_PATTERN.match(stem))


def is_root_zip(filename: str) -> bool:
    if ROOT_ZIP_PATTERN.match(filename):
        return True
    stem = Path(filename).stem
    if " " in stem and len(stem) > 30:
        return True
    return False


def extract_group_from_zipname(zip_filename: str, prefix_len: Optional[int] = None) -> Optional[str]:
    """
    Extract group from ZIP filename using ONLY 2–3 letter module prefix.
    Batch + root/container ZIPs return None.
    """
    if is_batch_zip(zip_filename):
        return None
    if is_root_zip(zip_filename):
        return None
    stem = Path(zip_filename).stem
    return _module_prefix_2_3(stem)


def infer_group_from_folder(folder_full: str, custom_prefixes: Optional[Set[str]] = None) -> str:
    if not folder_full:
        return "EXTRAS"
    folder_full = folder_full.replace("\\", "/")
    root_folder = folder_full.split("/", 1)[0] if "/" in folder_full else folder_full
    return _module_prefix_2_3(root_folder)


def infer_group_from_filename(filename: str, custom_prefixes: Optional[Set[str]] = None) -> str:
    base = Path(filename).stem
    return _module_prefix_2_3(base)


def infer_group(logical_path: str, filename: str, custom_prefixes: Optional[Set[str]] = None) -> str:
    group = infer_group_from_folder(logical_path, custom_prefixes)
    if group != "EXTRAS":
        return group
    return infer_group_from_filename(filename, custom_prefixes)


def _sanitize_member_path(p: str) -> str:
    p = (p or "").replace("\\", "/").lstrip("/")
    parts: List[str] = []
    for seg in p.split("/"):
        seg = (seg or "").strip()
        if not seg or seg in {".", ".."}:
            continue
        seg = _INVALID_WIN_CHARS.sub("_", seg)
        parts.append(seg)
    return "/".join(parts)


def _short_name(logical_path: str, suffix: str) -> str:
    return _disk_name_from_logical_path(logical_path, suffix)


def _compression_ratio(info: zipfile.ZipInfo) -> float:
    if info.compress_size and info.compress_size > 0:
        return info.file_size / info.compress_size
    return 1.0


def _copy_zip_member_to_file(zf: zipfile.ZipFile, info: zipfile.ZipInfo, out_path: Path) -> int:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with zf.open(info, "r") as src, open(out_path, "wb") as dst:
        shutil.copyfileobj(src, dst, length=1024 * 1024)
    return info.file_size


def _copy_gzipped_xml_member_to_file(
    zf: zipfile.ZipFile,
    info: zipfile.ZipInfo,
    out_path: Path,
    max_bytes_remaining: int,
) -> int:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    written = 0

    with zf.open(info, "r") as compressed_stream:
        with gzip.GzipFile(fileobj=compressed_stream, mode="rb") as gz:
            with open(out_path, "wb") as dst:
                while True:
                    chunk = gz.read(1024 * 1024)
                    if not chunk:
                        break
                    written += len(chunk)
                    if written > max_bytes_remaining:
                        raise RuntimeError("max_unzipped_bytes exceeded while inflating .xml.gz")
                    dst.write(chunk)
    return written


# -----------------------------------------------------------------------------
# Extended ZIP scanning (in-memory nested scan)
# -----------------------------------------------------------------------------

def scan_zip_for_files(
    zip_path: Path,
    temp_dir: Optional[Path] = None,
    max_depth: int = 10,
    custom_prefixes: Optional[Set[str]] = None,
    group_prefix_len: Optional[int] = None,
    max_files: int = 20000,
    max_unzipped_bytes: int = 300 * 1024 * 1024,
    include_extensions: Optional[Set[str]] = None,
) -> Tuple[List[Dict], Dict[str, List[Dict]], int]:
    """
    Recursively scan ZIP (and nested ZIPs) for target files.

    Writes ONLY: XML, XML.GZ, CSV, XLSX, XLS
    Uses deterministic short hashed disk filenames (prevents Windows path issues),
    while preserving real/meaningful names via logical_path.

    Returns:
        (files_list, groups_dict, total_bytes_written)

    NOTE:
      - files_list entries are dicts compatible with older code paths
      - groups_dict maps group -> list[entry dict]
    """
    if temp_dir is None:
        temp_dir = Path(tempfile.mkdtemp(prefix="ret_scan_"))

    extract_dir = temp_dir / "extracted"
    extract_dir.mkdir(parents=True, exist_ok=True)

    if include_extensions is None:
        include_extensions = {".xml", ".xml.gz", ".csv", ".xlsx", ".xls"}

    files_found = 0
    total_bytes_written = 0
    scan_start = time.time()

    discovered: List[Dict] = []
    groups: Dict[str, List[Dict]] = defaultdict(list)

    def _get_group_for_chain(zip_chain: List[str], fallback_group: str) -> str:
        for name in zip_chain:
            if name.lower().endswith(".zip"):
                g = extract_group_from_zipname(name, group_prefix_len)
                if g:
                    return normalize_group_name(g)
        return normalize_group_name(fallback_group or "ROOT")

    def _business_zip_from_chain(zip_chain: List[str]) -> str:
        for name in reversed(zip_chain):
            if name.lower().endswith(".zip"):
                return name
        return ""

    def _detect_file_type(member_lower: str) -> Optional[ScanFileType]:
        if member_lower.endswith(".xml") or member_lower.endswith(".xml.gz"):
            return "xml"
        if member_lower.endswith(".csv"):
            return "csv"
        if member_lower.endswith(".xlsx"):
            return "xlsx"
        if member_lower.endswith(".xls"):
            return "xls"
        return None

    def _suffix_for_member(member_lower: str) -> str:
        if member_lower.endswith(".xml.gz") or member_lower.endswith(".xml"):
            return ".xml"  # always store inflated/normalized as .xml on disk
        if member_lower.endswith(".csv"):
            return ".csv"
        if member_lower.endswith(".xlsx"):
            return ".xlsx"
        if member_lower.endswith(".xls"):
            return ".xls"
        return ".bin"

    def _walk_zip_bytes(
        zip_bytes: bytes,
        display_name: str,
        depth: int,
        zip_chain: List[str],
        current_group: str,
    ) -> None:
        nonlocal total_bytes_written, files_found

        if depth > max_depth:
            logger.warning(f"Max depth {max_depth} reached at {display_name}")
            return
        if files_found >= max_files:
            logger.warning(f"Max files {max_files} reached")
            return
        if total_bytes_written >= max_unzipped_bytes:
            logger.warning(f"Max unzipped bytes {max_unzipped_bytes} reached at depth {depth}")
            return

        current_group = normalize_group_name(current_group)

        try:
            with zipfile.ZipFile(io.BytesIO(zip_bytes), "r") as zf:
                for info in zf.infolist():
                    if info.is_dir():
                        continue

                    member = _sanitize_member_path(info.filename)
                    lower = member.lower()

                    if member.startswith("__MACOSX/"):
                        continue

                    ratio = _compression_ratio(info)
                    if ratio > DEFAULT_MAX_RATIO:
                        logger.warning(
                            f"Skipping {member}: compression ratio {ratio:.1f} > {DEFAULT_MAX_RATIO}"
                        )
                        continue

                    # Nested ZIP
                    if lower.endswith(".zip"):
                        nested_name = Path(member).name

                        if info.file_size > MAX_NESTED_ZIP_UNCOMPRESSED_MB * 1024 * 1024:
                            logger.warning(
                                f"Skipping nested ZIP {nested_name}: "
                                f"uncompressed size {info.file_size/(1024*1024):.1f}MB exceeds "
                                f"{MAX_NESTED_ZIP_UNCOMPRESSED_MB}MB"
                            )
                            continue

                        new_chain = zip_chain + [nested_name]
                        nested_group = _get_group_for_chain(new_chain, current_group)

                        # Batch ZIP inherits parent group
                        if is_batch_zip(nested_name):
                            nested_group = current_group

                        try:
                            nested_bytes = zf.read(info)
                        except Exception as e:
                            logger.error(f"Failed reading nested ZIP {nested_name}: {e}")
                            continue

                        _walk_zip_bytes(nested_bytes, nested_name, depth + 1, new_chain, nested_group)
                        continue

                    # Target file types
                    # respect include_extensions (".xml.gz" is special)
                    is_xml_gz = lower.endswith(".xml.gz")
                    ext = ".xml.gz" if is_xml_gz else Path(lower).suffix

                    if ext not in include_extensions:
                        continue

                    ftype = _detect_file_type(lower)
                    if not ftype:
                        continue

                    if files_found >= max_files:
                        return

                    logical_path = "/".join([c for c in zip_chain if c] + [member])

                    raw_group = current_group
                    if raw_group in ("", "EXTRAS", None):
                        raw_group = infer_group(member, Path(member).name, custom_prefixes)

                    group = normalize_group_name(_module_prefix_2_3(raw_group))

                    folder_path = str(Path(member).parent).replace("\\", "/")
                    root_folder = member.split("/", 1)[0] if "/" in member else ""

                    try:
                        # enforce budget
                        if total_bytes_written >= max_unzipped_bytes:
                            return

                        out_suffix = _suffix_for_member(lower)
                        out_name = _short_name(logical_path, suffix=out_suffix)
                        out_path = extract_dir / out_name

                        written = 0
                        if lower.endswith(".xml.gz"):
                            remaining = max_unzipped_bytes - total_bytes_written
                            if remaining <= 0:
                                logger.warning("Stopping: no remaining byte budget for xml.gz inflation")
                                return
                            written = _copy_gzipped_xml_member_to_file(
                                zf, info, out_path, max_bytes_remaining=remaining
                            )
                        else:
                            if total_bytes_written + info.file_size > max_unzipped_bytes:
                                logger.warning(
                                    f"Stopping: write would exceed max bytes at {member}"
                                )
                                return
                            written = _copy_zip_member_to_file(zf, info, out_path)

                        total_bytes_written += written
                        files_found += 1

                        file_info = {
                            "filename": Path(member).name,
                            "path": member,
                            "logical_path": logical_path,
                            "group": group,
                            "size": written,
                            "abs_path": str(out_path),
                            "file_type": ftype,
                            "business_zip": _business_zip_from_chain(zip_chain),
                            "folder_path": folder_path if folder_path != "." else "",
                            "root_folder": root_folder,
                            "zip_chain": zip_chain.copy(),
                        }
                        discovered.append(file_info)
                        groups[group].append(file_info)

                        if files_found % 250 == 0:
                            logger.info(
                                f"Scan progress: {files_found} files written "
                                f"({total_bytes_written / (1024 * 1024):.1f} MB)"
                            )

                    except RuntimeError as budget_err:
                        logger.warning(f"Stopping due to byte budget: {budget_err}")
                        return
                    except Exception as e:
                        logger.error(f"Failed processing member {member}: {e}", exc_info=True)
                        continue

        except zipfile.BadZipFile:
            logger.error(f"Bad zip encountered: {display_name}")
        except Exception as e:
            logger.error(f"ZIP scan error in {display_name}: {e}", exc_info=True)

    logger.info(f"========== Starting ZIP scan (in-memory): {zip_path.name} ==========")
    logger.info(f"  Max depth: {max_depth}, Max files: {max_files}, Max bytes: {max_unzipped_bytes}")
    logger.info(f"  Include extensions: {sorted(include_extensions)}")

    root_name = zip_path.name
    root_is_container = is_root_zip(root_name)

    initial_group_raw = "ROOT" if root_is_container else (
        extract_group_from_zipname(root_name, group_prefix_len) or "ROOT"
    )
    initial_group = normalize_group_name(initial_group_raw)

    root_bytes = zip_path.read_bytes()
    _walk_zip_bytes(root_bytes, root_name, depth=1, zip_chain=[root_name], current_group=initial_group)

    # Canonical regroup + de-dup
    canonical_groups: Dict[str, List[Dict]] = defaultdict(list)
    seen_ids: Set[str] = set()

    for finfo in discovered:
        g = normalize_group_name(finfo.get("group"))
        finfo["group"] = g
        fid = finfo.get("abs_path") or finfo.get("logical_path") or finfo.get("path") or ""
        if fid in seen_ids:
            continue
        seen_ids.add(fid)
        canonical_groups[g].append(finfo)

    groups = dict(canonical_groups)
    total_size = sum(f.get("size", 0) for f in discovered)
    scan_duration = time.time() - scan_start

    logger.info(f"========== Scan complete in {scan_duration:.2f}s ==========")
    logger.info(f"  Files written: {len(discovered)}")
    logger.info(f"  Groups detected: {len(groups)}")
    logger.info(f"  Total size (written): {total_size / 1024 / 1024:.2f} MB")
    for group_name, group_files in sorted(groups.items()):
        logger.info(f"    Group '{group_name}': {len(group_files)} files")

    return discovered, groups, total_size


# -----------------------------------------------------------------------------
# Backwards compatible scan_zip_for_xml (returns ONLY XML entries)
# -----------------------------------------------------------------------------

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
    Backwards compatible wrapper:
    - Scans XML/XML.GZ only
    - Returns the same structure as the original function
    """
    include = {".xml", ".xml.gz"}
    files, groups, total = scan_zip_for_files(
        zip_path=zip_path,
        temp_dir=temp_dir,
        max_depth=max_depth,
        custom_prefixes=custom_prefixes,
        group_prefix_len=group_prefix_len,
        max_files=max_files,
        max_unzipped_bytes=max_unzipped_bytes,
        include_extensions=include,
    )
    # filter xml entries only
    xml_files = [f for f in files if f.get("file_type") == "xml"]
    xml_groups: Dict[str, List[Dict]] = defaultdict(list)
    for f in xml_files:
        xml_groups[f["group"]].append(f)
    return xml_files, dict(xml_groups), sum(f.get("size", 0) for f in xml_files)


# -----------------------------------------------------------------------------
# XML flattening and parsing (unchanged)
# -----------------------------------------------------------------------------

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
    stack = [(elem, current_path)]

    while stack:
        node, base_path = stack.pop()
        tag_name = strip_ns(node.tag if hasattr(node, "tag") else str(node))

        if not base_path:
            path_here = tag_name if include_root else ""
        else:
            path_here = base_path

        attrib = getattr(node, "attrib", {})
        if attrib and path_here:
            for attr_name, attr_val in attrib.items():
                key = f"{path_here}@{attr_name}"
                if key not in row:
                    val = str(attr_val)[:max_field_len] if attr_val else ""
                    row[key] = val
                    if key not in header_seen:
                        header_order.append(key)
                        header_seen.add(key)

        children = list(node) if hasattr(node, "__iter__") else []

        if not children:
            text_val = (getattr(node, "text", "") or "").strip()
            if path_here and path_here not in row:
                row[path_here] = text_val[:max_field_len] if text_val else ""
                if path_here not in header_seen:
                    header_order.append(path_here)
                    header_seen.add(path_here)
        else:
            local_counts = defaultdict(int)
            for child in reversed(children):
                child_tag = strip_ns(child.tag)
                if child_tag == "__SKIP__":
                    continue
                key_base = f"{path_here}{path_sep}{child_tag}" if path_here else child_tag
                local_counts[key_base] += 1
                idx = local_counts[key_base]
                child_path = key_base if idx == 1 else f"{key_base}[{idx}]"
                stack.append((child, child_path))


def find_record_elements(root, record_tag: Optional[str], auto_detect: bool) -> Tuple[str, List]:
    if record_tag:
        matches = [el for el in root.iter() if strip_ns(el.tag) == record_tag]
        if matches:
            return record_tag, matches
        elements = root.findall(f".//{record_tag}")
        if elements:
            return record_tag, elements
        return record_tag, [root]

    if auto_detect:
        children = [c for c in root if strip_ns(c.tag) != "__SKIP__"]
        if children:
            child_tags = [strip_ns(c.tag) for c in children]
            counts = Counter(child_tags)
            repeated = [t for t, c in counts.items() if c > 1]
            if repeated:
                chosen = repeated[0]
                elems = [c for c in children if strip_ns(c.tag) == chosen]
                return f"AUTO:{chosen}", elems

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
    try:
        root = ET.fromstring(xml_bytes)
    except Exception as e:
        logger.error(f"Failed to parse XML: {e}")
        return [], [], ""

    record_tag_used, records = find_record_elements(root, record_tag, auto_detect)

    rows: List[dict] = []
    header_order: List[str] = []
    header_seen = set()

    for record in records:
        row = {}
        flatten_element(record, "", row, header_order, header_seen, path_sep, include_root, max_field_len)
        if row:
            rows.append(row)

    return rows, header_order, record_tag_used


# ---------------------------------------------------------------------------
# Fast record-tag detection via partial iterparse (no full tree)
# ---------------------------------------------------------------------------

def _detect_tag_iterparse(xml_path, *, max_children: int = 200) -> Optional[str]:
    """Detect the most-common direct child tag of the root using iterparse.

    Only reads the first ``max_children`` children of the document root,
    so memory usage is constant regardless of file size.  Falls back to
    ``None`` if detection fails (caller should use full-tree detection).
    """
    try:
        child_tags: Counter = Counter()
        depth = 0
        children_seen = 0

        for event, elem in ET.iterparse(str(xml_path), events=("start", "end")):
            if event == "start":
                depth += 1
                if depth == 2:  # direct children of root
                    tag = strip_ns(elem.tag)
                    if tag != "__SKIP__":
                        child_tags[tag] += 1
                    children_seen += 1
                    if children_seen >= max_children:
                        break
            elif event == "end":
                # Free memory as we go
                elem.clear()
                depth -= 1

        if child_tags:
            most_common_tag, count = child_tags.most_common(1)[0]
            if count > 1:
                return most_common_tag
            # Only one child — use it as record tag
            if len(child_tags) == 1:
                return most_common_tag
        return None
    except Exception as exc:
        logger.debug("Partial-iterparse tag detection failed: %s", exc)
        return None


def xml_to_rows_streaming(
    xml_path: Path,
    record_tag: Optional[str] = None,
    auto_detect: bool = True,
    path_sep: str = ".",
    include_root: bool = False,
    max_field_len: int = 300,
    chunk_size: int = 10000
) -> Iterator[Tuple[List[dict], List[str], str]]:
    if not LXML_AVAILABLE:
        logger.warning("Streaming requires LXML. Falling back to full load.")
        with open(xml_path, "rb") as f:
            xml_bytes = f.read()
        rows, headers, tag_used = xml_to_rows(xml_bytes, record_tag, auto_detect, path_sep, include_root, max_field_len)
        yield rows, headers, tag_used
        return

    try:
        detected_tag = record_tag
        if auto_detect and not record_tag:
            # Use partial iterparse to detect record tag without loading full tree
            detected_tag = _detect_tag_iterparse(xml_path)
            if detected_tag:
                logger.debug("Streaming tag detection (iterparse): %s for %s", detected_tag, xml_path.name)
            else:
                # Fallback to full tree only if partial detection failed
                logger.debug("Partial iterparse detection failed, falling back to full tree for %s", xml_path.name)
                tree = ET.parse(str(xml_path))
                root = tree.getroot()
                detected_tag, _ = find_record_elements(root, None, True)
                del tree, root

        if LXML_AVAILABLE:
            lxml_et = cast(Any, ET)
            context = lxml_et.iterparse(
                str(xml_path),
                events=("end",),
                tag=detected_tag if detected_tag else None,
            )
        else:
            context = ET.iterparse(str(xml_path), events=("end",))

        rows_batch: List[dict] = []
        header_order: List[str] = []
        header_seen = set()

        for _, elem in context:
            if detected_tag and strip_ns(elem.tag) != detected_tag:
                elem.clear()
                continue

            row = {}
            flatten_element(elem, "", row, header_order, header_seen, path_sep, include_root, max_field_len)
            if row:
                rows_batch.append(row)

            elem.clear()
            if LXML_AVAILABLE:
                elem_any = cast(Any, elem)
                while elem_any.getprevious() is not None:
                    del elem_any.getparent()[0]

            if len(rows_batch) >= chunk_size:
                yield rows_batch, header_order, detected_tag or "root"
                rows_batch = []

        if rows_batch:
            yield rows_batch, header_order, detected_tag or "root"

        del context

    except Exception as e:
        logger.error(f"Streaming parse failed for {xml_path}: {e}")
        try:
            with open(xml_path, "rb") as f:
                xml_bytes = f.read()
            rows, headers, tag_used = xml_to_rows(xml_bytes, record_tag, auto_detect, path_sep, include_root, max_field_len)
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
    # Detect record tag via partial iterparse when possible
    record_tag_used = record_tag
    if auto_detect and not record_tag_used:
        record_tag_used = _detect_tag_iterparse(xml_path)

    # Fallback to full tree only if partial detection failed
    if not record_tag_used:
        try:
            tree = ET.parse(xml_path)
            root = tree.getroot()
            record_tag_used, records = find_record_elements(root, record_tag, auto_detect)
            for idx, record in enumerate(records):
                if idx >= max_records:
                    break
                try:
                    record_str = ET.tostring(record, encoding="unicode")
                    if len(record_str) > max_chars_per_record:
                        record_str = record_str[:max_chars_per_record] + "..."
                    yield idx, record_tag_used, record_str
                except Exception as e:
                    logger.warning(f"Failed to serialize record {idx}: {e}")
            del tree, root
            return
        except Exception as e:
            logger.error(f"Failed to parse {xml_path}: {e}")
            return

    # Use iterparse for memory-efficient chunked iteration
    idx = 0
    try:
        for event, elem in ET.iterparse(str(xml_path), events=("end",)):
            if strip_ns(elem.tag) != record_tag_used:
                continue
            if idx >= max_records:
                break
            try:
                record_str = ET.tostring(elem, encoding="unicode")
                if len(record_str) > max_chars_per_record:
                    record_str = record_str[:max_chars_per_record] + "..."
                yield idx, record_tag_used, record_str
            except Exception as e:
                logger.warning(f"Failed to serialize record {idx}: {e}")
            idx += 1
            elem.clear()
            if LXML_AVAILABLE:
                elem_any = cast(Any, elem)
                while elem_any.getprevious() is not None:
                    del elem_any.getparent()[0]
    except Exception as e:
        logger.error(f"Iterparse failed for {xml_path}: {e}")


def write_rows_to_csv(rows: List[dict], headers: List[str], out_csv: Path):
    import csv
    try:
        out_csv.parent.mkdir(parents=True, exist_ok=True)
        with open(out_csv, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=headers)
            writer.writeheader()
            writer.writerows(rows)
        logger.info(f"Wrote {len(rows)} rows to {out_csv}")
    except Exception as e:
        logger.error(f"Failed to write CSV: {e}")
        raise


def detect_record_tag_auto(xml_path: str) -> Optional[str]:
    """Detect the most common root-child tag. Uses partial iterparse first."""
    tag = _detect_tag_iterparse(xml_path)
    if tag:
        return tag

    # Fallback to full tree if iterparse detection failed
    try:
        tree = ET.parse(xml_path)
        root = tree.getroot()

        child_tags: Counter = Counter()
        for child in root:
            t = strip_ns(child.tag)
            child_tags[t] += 1
        del tree, root

        if child_tags:
            return child_tags.most_common(1)[0][0]
    except Exception as e:
        logger.error(f"Failed to detect record tag: {e}")

    return None
















