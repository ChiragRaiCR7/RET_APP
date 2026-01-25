import csv
from pathlib import Path

def write_csv(records: list[dict], out_path: Path):
    if not records:
        return

    with open(out_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=records[0].keys())
        writer.writeheader()
        writer.writerows(records)
