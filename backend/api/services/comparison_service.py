from pathlib import Path
import csv
from typing import List

from api.services.storage_service import get_session_dir
from api.utils.vector_utils import hash_vector, cosine_similarity
from api.utils.diff_utils import compute_row_diff


def read_csv(path: Path) -> list[dict]:
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        return list(reader)


def compare_sessions(left_session_id: str, right_session_id: str):
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

    return {
        "summary": summary,
        "results": results,
    }
