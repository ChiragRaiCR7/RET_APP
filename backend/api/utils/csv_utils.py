# csv_utils.py
from pathlib import Path
import csv
from typing import List, Dict, Any

def write_csv(records: List[Dict[str, Any]], out_path: Path) -> None:
    """
    Write a list of dict records to CSV.
    - If records is empty, create an empty file.
    - Header order follows the first record's keys (stable).
    """
    out_path.parent.mkdir(parents=True, exist_ok=True)

    if not records:
        # create empty placeholder file
        with open(out_path, "w", encoding="utf-8", newline="") as f:
            f.write("")
        return

    headers = list(records[0].keys())
    with open(out_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=headers)
        writer.writeheader()
        for r in records:
            # normalize None -> empty string
            writer.writerow({k: ("" if v is None else v) for k, v in r.items()})
