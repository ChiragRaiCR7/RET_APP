import zipfile
import hashlib
import csv
from pathlib import Path
from typing import List, Dict, Optional, Set, Tuple
from collections import Counter, defaultdict
import logging

from api.services.storage_service import (
    create_session_dir,
    get_session_dir,
    save_upload,
    get_session_metadata,
    save_session_metadata,
)
from api.utils.file_utils import safe_extract_zip
from api.services.xml_processing_service import (
    xml_to_rows,
    scan_zip_for_xml,
    infer_group,
    extract_alpha_prefix,
)

logger = logging.getLogger(__name__)





def scan_zip_with_groups(file_bytes: bytes, filename: str, user_id: str) -> Dict:
    """Scan ZIP file and detect groups"""
    session_id = create_session_dir(user_id)
    sess_dir = get_session_dir(session_id)

    zip_path = save_upload(session_id, filename, file_bytes)

    # Use xml_processing_service to scan ZIP
    try:
        xml_files, groups, total_size = scan_zip_for_xml(zip_path, sess_dir)
    except Exception as e:
        logger.error(f"Failed to scan ZIP: {e}")
        raise
    
    # Create extracted directory reference
    extract_dir = sess_dir / "extracted"
    
    # Save metadata
    metadata = {
        "user_id": user_id,
        "uploaded_file": filename,
        "xml_count": len(xml_files),
        "groups": {k: len(v) for k, v in groups.items()},
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
    errors = []

    for xml_file in extract_dir.rglob("*.xml"):
        relative_path = str(xml_file.relative_to(extract_dir))
        group = infer_group(relative_path, xml_file.name)
        
        # Skip if groups filter is specified and file doesn't match
        if groups and group not in groups:
            continue
        
        try:
            # Read XML and convert to rows
            with open(xml_file, 'rb') as f:
                xml_bytes = f.read()
            
            rows, headers, tag_used = xml_to_rows(
                xml_bytes,
                record_tag=None,
                auto_detect=True,
                path_sep=".",
                include_root=False,
            )
            
            if not rows:
                logger.warning(f"No records found in {xml_file}")
                errors.append({
                    "file": xml_file.name,
                    "error": "No records found"
                })
                failed += 1
                continue
            
            # Write CSV
            csv_name = xml_file.stem + ".csv"
            csv_path = out_dir / csv_name
            
            with open(csv_path, 'w', newline='', encoding='utf-8') as f:
                writer = csv.DictWriter(f, fieldnames=headers)
                writer.writeheader()
                for row in rows:
                    # Ensure all fields exist
                    row_data = {h: row.get(h, '') for h in headers}
                    writer.writerow(row_data)
            
            converted_files.append({
                "filename": csv_name,
                "group": group,
                "rows": len(rows),
                "columns": len(headers),
            })
            success += 1
            logger.info(f"Converted {xml_file.name} to {csv_name}: {len(rows)} rows")
        except Exception as e:
            failed += 1
            error_msg = str(e)
            logger.error(f"Failed to convert {xml_file.name}: {error_msg}")
            errors.append({
                "file": xml_file.name,
                "error": error_msg
            })

    return {
        "session_id": session_id,
        "stats": {
            "total_files": success + failed,
            "success": success,
            "failed": failed,
        },
        "converted_files": converted_files,
        "errors": errors,
    }

