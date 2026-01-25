import zipfile
from pathlib import Path
from typing import List, Dict

from api.services.storage_service import (
    create_session_dir,
    get_session_dir,
    save_upload,
)
from api.utils.file_utils import safe_extract_zip
from api.utils.xml_utils import flatten_xml
from api.utils.csv_utils import write_csv


def scan_zip(file_bytes: bytes, filename: str) -> Dict:
    session_id = create_session_dir()
    sess_dir = get_session_dir(session_id)

    zip_path = save_upload(session_id, filename, file_bytes)

    extract_dir = sess_dir / "extracted"
    extract_dir.mkdir()

    safe_extract_zip(zip_path, extract_dir)

    xml_files: List[Dict[str, str]] = []

    for p in extract_dir.rglob("*.xml"):
        xml_files.append({
            "filename": p.name,
            "path": str(p.relative_to(extract_dir)),
        })

    return {
        "session_id": session_id,
        "xml_count": len(xml_files),
        "files": xml_files,
    }


def convert_session(session_id: str) -> Dict:
    sess_dir = get_session_dir(session_id)
    extract_dir = sess_dir / "extracted"
    out_dir = sess_dir / "output"

    success = 0
    failed = 0

    for xml_file in extract_dir.rglob("*.xml"):
        try:
            records = flatten_xml(str(xml_file))
            csv_name = xml_file.stem + ".csv"
            write_csv(records, out_dir / csv_name)
            success += 1
        except Exception:
            failed += 1

    return {
        "session_id": session_id,
        "stats": {
            "total_files": success + failed,
            "success": success,
            "failed": failed,
        },
    }
