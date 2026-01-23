"""
Simple, generic XML -> CSV converter used by xml_convert_parallel.

Function:
    xml_to_csv(xml_input: Path|str, csv_output: Path|str) -> bool

This implementation is intentionally defensive and generic:
 - It tries to detect a "record" level in the XML (children of root,
   or grandchildren) and flattens simple sub-elements and attributes
   into CSV columns.
 - Returns True on success, False on failure/no-records.
"""
from pathlib import Path
from typing import Union
import xml.etree.ElementTree as ET
import csv

def xml_to_csv(xml_input: Union[Path, str], csv_output: Union[Path, str]) -> bool:
    xml_path = Path(xml_input)
    csv_path = Path(csv_output)
    try:
        tree = ET.parse(xml_path)
        root = tree.getroot()

        # Gather candidate record elements:
        children = list(root)
        if not children:
            return False

        tags = [c.tag for c in children]
        # Heuristic: if all direct children share the same tag and there are multiple,
        # use them as "records".
        if len(set(tags)) == 1 and len(children) > 1:
            records = children
        else:
            # otherwise try grandchildren (e.g., <rows><row>...</row></rows>)
            grandchildren = []
            for c in children:
                grandchildren.extend(list(c))
            if grandchildren:
                records = grandchildren
            else:
                # fallback: use direct children as records
                records = children

        # Build headers (union of subelement tags + attributes)
        headers = set()
        rows = []
        for rec in records:
            row = {}
            for sub in list(rec):
                headers.add(sub.tag)
                row[sub.tag] = (sub.text or "").strip()
            for k, v in rec.attrib.items():
                col = f"@{k}"
                headers.add(col)
                row[col] = v
            rows.append(row)

        if not rows:
            return False

        headers = sorted(headers)
        csv_path.parent.mkdir(parents=True, exist_ok=True)
        with open(csv_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=headers, extrasaction="ignore")
            writer.writeheader()
            for r in rows:
                writer.writerow({h: r.get(h, "") for h in headers})

        return True
    except Exception:
        return False
