# xml_utils.py
"""
XML helper utilities:
 - xml_to_rows: convert bytes -> list[dict] + headers (order)
 - detect_record_tag_auto: attempt to find repeating child tag
 - infer_group helpers (filename/folder-based)
This module tries to use lxml when available (recommended) and falls back to ElementTree.
"""
from typing import List, Dict, Any, Optional, Tuple, Set
from collections import Counter
from pathlib import Path
import logging

logger = logging.getLogger(__name__)

try:
    from lxml import etree as LET
    LXML = True
except Exception:
    import xml.etree.ElementTree as LET  # type: ignore
    LXML = False

def strip_ns(tag: str) -> str:
    if not tag:
        return tag
    if "}" in tag:
        return tag.split("}", 1)[1]
    return tag

def extract_alpha_prefix(token: str) -> str:
    out = []
    for ch in token:
        if ch.isalpha():
            out.append(ch)
        else:
            break
    return "".join(out).upper()

def infer_group_from_filename(filename: str, custom_prefixes: Optional[Set[str]] = None) -> str:
    base = Path(filename).stem
    token = base.split("_", 1)[0] if "_" in base else base
    alpha = extract_alpha_prefix(token)
    if custom_prefixes:
        return alpha if alpha in custom_prefixes else "OTHER"
    return alpha if alpha else "OTHER"

def infer_group(logical_path: str, filename: str, custom_prefixes: Optional[Set[str]] = None) -> str:
    if logical_path and "/" in logical_path:
        last_seg = logical_path.split("/")[-1]
        token = last_seg.split("_", 1)[0] if "_" in last_seg else last_seg
        alpha = extract_alpha_prefix(token)
        if custom_prefixes:
            return alpha if alpha in custom_prefixes else infer_group_from_filename(filename, custom_prefixes)
        return alpha if alpha else infer_group_from_filename(filename, custom_prefixes)
    return infer_group_from_filename(filename, custom_prefixes)

def xml_to_rows(
    xml_bytes: bytes,
    record_tag: Optional[str] = None,
    auto_detect: bool = True,
    path_sep: str = ".",
    include_root: bool = False,
) -> Tuple[List[Dict[str, Any]], List[str], str]:
    """
    Convert xml bytes -> (rows, header_order, record_tag_used)
    - rows: list of dict where keys are flattened element paths/attributes
    - header_order: discovered header order (first-seen)
    - record_tag_used: tag used to split records or fallback descriptor
    """
    # parse
    try:
        if LXML:
            parser = LET.XMLParser(resolve_entities=False, no_network=True, recover=True, huge_tree=True)
            root = LET.fromstring(xml_bytes, parser=parser)
        else:
            root = LET.fromstring(xml_bytes)
    except Exception as e:
        logger.exception("XML parse failed")
        raise ValueError(f"XML parse error: {e}")

    # determine record elements
    tag_used = ""
    if record_tag:
        tag_used = record_tag
        elems = list(root.findall(f".//{record_tag}")) if hasattr(root, "findall") else [root]
        if not elems:
            elems = [root]
    elif auto_detect:
        children = list(root)
        if children:
            child_tags = [strip_ns(getattr(c, "tag", "") or "") for c in children]
            counts = Counter(child_tags)
            repeated = [t for t, c in counts.items() if c > 1 and t]
            if repeated:
                chosen = repeated[0]
                tag_used = chosen
                elems = [c for c in children if strip_ns(getattr(c, "tag", "") or "") == chosen]
            else:
                tag_used = "FALLBACK:root_children"
                elems = children
        else:
            tag_used = "FALLBACK:root"
            elems = [root]
    else:
        tag_used = "FALLBACK:root"
        elems = [root]

    header_order: List[str] = []
    header_seen = set()
    rows: List[Dict[str, Any]] = []

    def add_to_row(row: dict, key: str, value: Any):
        v = "" if value is None else (str(value).strip())
        row[key] = v
        if key not in header_seen:
            header_order.append(key)
            header_seen.add(key)

    def flatten_element(elem, current_path: str):
        # attributes
        attrib = getattr(elem, "attrib", {}) or {}
        for ak, av in attrib.items():
            add_to_row(current_row, f"{current_path}@{ak}", av)

        children = list(elem)
        if not children:
            text_val = (getattr(elem, "text", "") or "").strip()
            if current_path or include_root:
                add_to_row(current_row, current_path, text_val)
            return

        local_counts = {}
        for child in children:
            child_tag = strip_ns(getattr(child, "tag", "") or "")
            base = f"{current_path}{path_sep}{child_tag}" if current_path else child_tag
            local_counts[base] = local_counts.get(base, 0) + 1
            idx = local_counts[base]
            child_path = base if idx == 1 else f"{base}[{idx}]"
            flatten_element(child, child_path)

    for rec in elems:
        current_row: Dict[str, Any] = {}
        # start path depends on include_root
        start_path = strip_ns(getattr(rec, "tag", "") or "") if include_root else ""
        flatten_element(rec, start_path)
        rows.append(current_row)

    return rows, header_order, tag_used

def detect_record_tag_auto(xml_path: str) -> Optional[str]:
    """
    Parse xml file and detect a repeating immediate child tag under root.
    Return tag name (without namespace) or None.
    """
    try:
        if LXML:
            parser = LET.XMLParser(resolve_entities=False, no_network=True, recover=True, huge_tree=True)
            tree = LET.parse(str(xml_path), parser=parser)
            root = tree.getroot()
        else:
            tree = LET.parse(str(xml_path))
            root = tree.getroot()
        kids = list(root)
        if not kids:
            return None
        tags = [strip_ns(getattr(k, "tag", "") or "") for k in kids]
        counts = Counter(tags)
        repeated = [t for t, c in counts.items() if c > 1 and t]
        return repeated[0] if repeated else None
    except Exception:
        return None
