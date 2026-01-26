from xml.etree import ElementTree as ET
from typing import List, Dict, Any

def flatten_xml(xml_path: str) -> List[Dict[str, Any]]:
    """
    Flatten XML to list of dictionaries.
    Handles nested elements and attributes.
    """
    try:
        tree = ET.parse(xml_path)
        root = tree.getroot()
    except Exception as e:
        raise ValueError(f"Failed to parse XML: {e}")

    records = []
    
    # If root has multiple children, treat each as a record
    if len(root) > 0:
        for elem in root:
            record = _flatten_element(elem, prefix="")
            if record:
                records.append(record)
    else:
        # If root is the only element, flatten it
        record = _flatten_element(root, prefix="")
        if record:
            records.append(record)

    return records


def _flatten_element(elem: ET.Element, prefix: str = "", max_depth: int = 5) -> Dict[str, Any]:
    """Recursively flatten an XML element"""
    record = {}
    
    # Add attributes
    if elem.attrib:
        for key, value in elem.attrib.items():
            record_key = f"{prefix}{key}" if prefix else key
            record[record_key] = str(value)
    
    # Add text content
    text = (elem.text or "").strip()
    if text:
        record_key = f"{prefix}text" if prefix else "text"
        record[record_key] = text
    
    # Add child elements
    if max_depth > 0:
        for child in elem:
            child_prefix = f"{prefix}{child.tag}_" if prefix else f"{child.tag}_"
            child_record = _flatten_element(child, prefix=child_prefix, max_depth=max_depth - 1)
            record.update(child_record)
    
    return record
