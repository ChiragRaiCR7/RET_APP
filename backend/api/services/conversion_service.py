import zipfile
import hashlib
from pathlib import Path
from typing import List, Dict, Optional, Set
from collections import Counter

from api.services.storage_service import (
    create_session_dir,
    get_session_dir,
    save_upload,
    get_session_metadata,
    save_session_metadata,
)
from api.utils.file_utils import safe_extract_zip
from api.utils.xml_utils import flatten_xml
from api.utils.csv_utils import write_csv


def extract_alpha_prefix(token: str) -> str:
    """Extract alphabetic prefix from a string"""
    out = []
    for ch in token:
        if ch.isalpha():
            out.append(ch)
        else:
            break
    return "".join(out).upper()


def infer_group(logical_path: str, filename: str) -> str:
    """Infer group from file path and filename"""
    # Try folder-based detection - use the first (root) folder
    if "/" in logical_path:
        # Get the root folder (first element)
        root_folder = logical_path.split("/")[0]
        alpha = extract_alpha_prefix(root_folder)
        if alpha:
            return alpha
    
    # Fall back to filename-based detection
    base = Path(filename).stem
    token = base.split("_", 1)[0] if "_" in base else base
    alpha = extract_alpha_prefix(token)
    return alpha if alpha else "OTHER"


def scan_zip_with_groups(file_bytes: bytes, filename: str, user_id: str) -> Dict:
    """Scan ZIP file and detect groups"""
    session_id = create_session_dir(user_id)
    sess_dir = get_session_dir(session_id)

    zip_path = save_upload(session_id, filename, file_bytes)

    extract_dir = sess_dir / "extracted"
    extract_dir.mkdir(exist_ok=True)

    safe_extract_zip(zip_path, extract_dir)

    # Find all XML files and group them
    xml_files: List[Dict[str, str]] = []
    groups: Dict[str, List[Dict]] = {}
    group_counter: Counter = Counter()

    for p in extract_dir.rglob("*.xml"):
        relative_path = str(p.relative_to(extract_dir))
        group = infer_group(relative_path, p.name)
        
        file_info = {
            "filename": p.name,
            "path": relative_path,
            "group": group,
            "size": p.stat().st_size,
        }
        
        xml_files.append(file_info)
        
        if group not in groups:
            groups[group] = []
        groups[group].append(file_info)
        group_counter[group] += 1

    # Calculate summary stats
    total_size = sum(p.stat().st_size for p in extract_dir.rglob("*.xml"))
    
    # Save metadata
    metadata = {
        "user_id": user_id,
        "uploaded_file": filename,
        "xml_count": len(xml_files),
        "groups": dict(group_counter),
        "group_list": list(groups.keys()),
        "total_size": total_size,
    }
    save_session_metadata(session_id, metadata)

    return {
        "session_id": session_id,
        "xml_count": len(xml_files),
        "group_count": len(groups),
        "files": xml_files,
        "groups": [
            {
                "name": group,
                "file_count": len(files),
                "size": sum(f["size"] for f in files),
            }
            for group, files in sorted(groups.items())
        ],
        "summary": {
            "totalFiles": len(xml_files),
            "totalGroups": len(groups),
            "totalSize": total_size,
        }
    }


def get_session_info(session_id: str, user_id: str) -> Dict:
    """Get information about a session"""
    sess_dir = get_session_dir(session_id)
    if not sess_dir.exists():
        raise ValueError(f"Session {session_id} not found")
    
    metadata = get_session_metadata(session_id)
    if metadata.get("user_id") != user_id:
        raise ValueError("Unauthorized")
    
    return metadata


def convert_session(session_id: str, groups: Optional[List[str]] = None) -> Dict:
    """Convert XML files in session to CSV, optionally filtering by group"""
    sess_dir = get_session_dir(session_id)
    extract_dir = sess_dir / "extracted"
    out_dir = sess_dir / "output"
    out_dir.mkdir(exist_ok=True)

    success = 0
    failed = 0
    converted_files = []

    for xml_file in extract_dir.rglob("*.xml"):
        relative_path = str(xml_file.relative_to(extract_dir))
        group = infer_group(relative_path, xml_file.name)
        
        # Skip if groups filter is specified and file doesn't match
        if groups and group not in groups:
            continue
        
        try:
            records = flatten_xml(str(xml_file))
            csv_name = xml_file.stem + ".csv"
            csv_path = out_dir / csv_name
            write_csv(records, csv_path)
            
            converted_files.append({
                "filename": csv_name,
                "group": group,
                "rows": len(records),
            })
            success += 1
        except Exception as e:
            failed += 1
            # Log error but continue

    return {
        "session_id": session_id,
        "stats": {
            "total_files": success + failed,
            "success": success,
            "failed": failed,
        },
        "converted_files": converted_files,
    }

