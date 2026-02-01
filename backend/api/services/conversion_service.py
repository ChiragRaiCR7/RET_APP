import zipfile
import csv
import shutil
import io
import json
import hashlib
import time
from pathlib import Path
from typing import List, Dict, Optional, Set, Any, Tuple
from collections import defaultdict
import logging

from api.services.storage_service import (
    create_session_dir,
    get_session_dir,
    save_upload,
    get_session_metadata,
    save_session_metadata,
)
from api.services.xml_processing_service import (
    xml_to_rows,
    scan_zip_for_xml,
    infer_group,
)
from api.services.xlsx_service import get_xlsx_bytes_from_csv

logger = logging.getLogger(__name__)


def _sha_short(s: str, n: int = 16) -> str:
    """Generate short SHA1 hash of string"""
    return hashlib.sha1(s.encode("utf-8")).hexdigest()[:n]


def _format_size(size_bytes: int) -> str:
    """Format bytes to human readable"""
    for unit in ['B', 'KB', 'MB', 'GB']:
        if size_bytes < 1024:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024
    return f"{size_bytes:.1f} TB"


def _sanitize_path(p: str) -> str:
    """Sanitize path for ZIP entries"""
    p = (p or "").replace("\\", "/").lstrip("/")
    parts = []
    for part in p.split("/"):
        if part in ("", ".", ".."):
            continue
        parts.append(part)
    return "/".join(parts) or "file"


def logical_xml_to_output_relpath(logical_path: str, out_ext: str = ".csv") -> str:
    """Convert logical XML path to output CSV/XLSX path preserving structure"""
    lp = _sanitize_path(logical_path)
    if lp.lower().endswith(".xml"):
        lp = lp[:-4] + out_ext
    else:
        base = Path(lp).name
        parent = str(Path(lp).parent).replace("\\", "/")
        stem = Path(base).stem
        lp = f"{parent}/{stem}{out_ext}" if parent not in ("", ".") else f"{stem}{out_ext}"
        lp = _sanitize_path(lp)
    return lp


def scan_zip_with_groups(file_bytes: bytes, filename: str, user_id: str) -> Dict:
    """
    Save uploaded file to a fresh session and scan it for XML files; return session metadata and groups.
    Handles both ZIP files and single XML files.
    """
    session_id = create_session_dir(user_id)
    sess_dir = get_session_dir(session_id)
    extract_dir = sess_dir / "extracted"
    extract_dir.mkdir(parents=True, exist_ok=True)

    zip_path = save_upload(session_id, filename, file_bytes)
    
    is_xml = filename.lower().endswith(".xml")
    is_zip = filename.lower().endswith(".zip")
    
    xml_files = []
    groups = {}
    total_size = 0
    
    if is_xml:
        # Single XML file - copy to extracted folder
        dest_path = extract_dir / filename
        shutil.copy(zip_path, dest_path)
        
        file_size = dest_path.stat().st_size
        group = infer_group(filename, filename, None)
        
        xml_files = [{
            "filename": filename,
            "path": filename,
            "group": group,
            "size": file_size,
            "abs_path": str(dest_path),
        }]
        groups = {group: xml_files}
        total_size = file_size
        
        logger.info(f"Processed single XML file: {filename} ({file_size} bytes)")
        
    elif is_zip:
        # ZIP file - extract and scan
        xml_files, groups, total_size = scan_zip_for_xml(zip_path, sess_dir)
        logger.info(f"Scanned ZIP: {filename}, found {len(xml_files)} XML files in {len(groups)} groups")
    else:
        raise ValueError(f"Unsupported file type: {filename}")

    # save metadata
    metadata = {
        "session_id": session_id,
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
            {"name": group, "file_count": len(files), "size": sum(f["size"] for f in files)}
            for group, files in sorted(groups.items())
        ],
        "summary": {"totalFiles": len(xml_files), "totalGroups": len(groups), "totalSize": total_size},
    }


def get_session_info(session_id: str, user_id: str) -> Dict:
    sess_dir = get_session_dir(session_id)
    if not sess_dir.exists():
        raise ValueError(f"Session {session_id} not found")

    metadata = get_session_metadata(session_id)
    if metadata.get("user_id") != user_id:
        raise ValueError("Unauthorized")
    return metadata


def convert_session(session_id: str, groups: Optional[List[str]] = None) -> Dict:
    """
    Convert all XML files present in session's extracted folder into CSVs (optionally filtering by group).
    Result files are placed in session/output/.
    """
    sess_dir = get_session_dir(session_id)
    extract_dir = sess_dir / "extracted"
    out_dir = sess_dir / "output"
    out_dir.mkdir(exist_ok=True)
    
    logger.info(f"Converting session {session_id}, groups filter: {groups}")
    logger.info(f"Extract dir: {extract_dir}, exists: {extract_dir.exists()}")

    if not extract_dir.exists():
        logger.error(f"Extract directory does not exist: {extract_dir}")
        return {
            "session_id": session_id,
            "stats": {"total_files": 0, "success": 0, "failed": 0},
            "converted_files": [],
            "errors": [{"file": "N/A", "error": "No extracted files found. Please scan a file first."}],
        }

    success = 0
    failed = 0
    converted_files = []
    errors = []
    
    xml_file_list = list(extract_dir.rglob("*.xml"))
    logger.info(f"Found {len(xml_file_list)} XML files in {extract_dir}")

    for xml_file in xml_file_list:
        relative_path = str(xml_file.relative_to(extract_dir))
        group = infer_group(relative_path, xml_file.name)
        
        logger.debug(f"Processing {xml_file.name}, group={group}")

        if groups and group not in groups:
            logger.debug(f"Skipping {xml_file.name}, group {group} not in filter {groups}")
            continue

        try:
            with open(xml_file, "rb") as f:
                xml_bytes = f.read()
            
            logger.debug(f"Read {len(xml_bytes)} bytes from {xml_file.name}")

            rows, headers, tag_used = xml_to_rows(
                xml_bytes, 
                record_tag=None, 
                auto_detect=True, 
                path_sep=".", 
                include_root=False
            )
            
            logger.info(f"Parsed {xml_file.name}: {len(rows)} rows, {len(headers)} headers, tag={tag_used}")

            if not rows:
                failed += 1
                errors.append({"file": xml_file.name, "error": "No records found"})
                logger.warning("No records found in %s", xml_file)
                continue

            csv_name = xml_file.stem + ".csv"
            csv_path = out_dir / csv_name
            with open(csv_path, "w", newline="", encoding="utf-8") as outf:
                writer = csv.DictWriter(outf, fieldnames=headers)
                writer.writeheader()
                for r in rows:
                    row_data = {h: r.get(h, "") for h in headers}
                    writer.writerow(row_data)

            converted_files.append({
                "filename": csv_name, 
                "group": group, 
                "rows": len(rows), 
                "columns": len(headers)
            })
            success += 1
            logger.info("Converted %s -> %s (%d rows, %d cols)", xml_file.name, csv_name, len(rows), len(headers))
        except Exception as e:
            failed += 1
            errors.append({"file": xml_file.name, "error": str(e)})
            logger.exception("Failed to convert %s", xml_file.name)

    result = {
        "session_id": session_id,
        "stats": {"total_files": success + failed, "success": success, "failed": failed},
        "converted_files": converted_files,
        "errors": errors,
    }
    logger.info(f"Conversion complete: {result['stats']}")
    
    # Save conversion index to session
    _save_conversion_index(session_id, converted_files)
    
    return result


def _save_conversion_index(session_id: str, converted_files: List[Dict]):
    """Save conversion index for later retrieval"""
    sess_dir = get_session_dir(session_id)
    index_path = sess_dir / "conversion_index.json"
    
    # Build comprehensive index
    index = {
        "session_id": session_id,
        "converted_at": time.time(),
        "files": [],
        "groups": defaultdict(list),
    }
    
    out_dir = sess_dir / "output"
    
    for cf in converted_files:
        csv_path = out_dir / cf["filename"]
        file_info = {
            "filename": cf["filename"],
            "group": cf["group"],
            "rows": cf["rows"],
            "columns": cf.get("columns", 0),
            "csv_path": str(csv_path),
            "size_bytes": csv_path.stat().st_size if csv_path.exists() else 0,
        }
        index["files"].append(file_info)
        index["groups"][cf["group"]].append(file_info)
    
    index["groups"] = dict(index["groups"])
    index_path.write_text(json.dumps(index, indent=2))


def get_conversion_index(session_id: str, user_id: str) -> Dict:
    """Get conversion index for session"""
    sess_dir = get_session_dir(session_id)
    
    # Verify ownership
    metadata = get_session_metadata(session_id)
    if metadata.get("user_id") and metadata.get("user_id") != user_id:
        raise ValueError("Unauthorized")
    
    index_path = sess_dir / "conversion_index.json"
    if not index_path.exists():
        # Build index from output directory
        return _build_index_from_output(session_id)
    
    return json.loads(index_path.read_text())


def _build_index_from_output(session_id: str) -> Dict:
    """Build index by scanning output directory"""
    sess_dir = get_session_dir(session_id)
    out_dir = sess_dir / "output"
    
    if not out_dir.exists():
        return {"session_id": session_id, "files": [], "groups": {}}
    
    files = []
    groups = defaultdict(list)
    
    for csv_path in out_dir.glob("*.csv"):
        # Try to infer group from filename
        group = infer_group(csv_path.stem, csv_path.name)
        
        # Count rows and columns
        rows = 0
        cols = 0
        try:
            with open(csv_path, "r", encoding="utf-8-sig", newline="") as f:
                reader = csv.reader(f)
                headers = next(reader, [])
                cols = len(headers)
                rows = sum(1 for _ in reader)
        except Exception:
            pass
        
        file_info = {
            "filename": csv_path.name,
            "group": group,
            "rows": rows,
            "columns": cols,
            "csv_path": str(csv_path),
            "size_bytes": csv_path.stat().st_size,
        }
        files.append(file_info)
        groups[group].append(file_info)
    
    return {
        "session_id": session_id,
        "files": files,
        "groups": dict(groups),
    }


def list_converted_files(session_id: str, user_id: str, group: Optional[str] = None) -> Dict:
    """
    List converted files with optional group filter.
    Returns files grouped and with metadata for dropdown display.
    """
    index = get_conversion_index(session_id, user_id)
    
    files = index.get("files", [])
    groups_data = index.get("groups", {})
    
    if group and group in groups_data:
        files = groups_data[group]
    
    # Format for frontend
    group_list = [
        {
            "name": g,
            "file_count": len(files_list),
            "total_rows": sum(f.get("rows", 0) for f in files_list),
            "total_size": sum(f.get("size_bytes", 0) for f in files_list),
        }
        for g, files_list in groups_data.items()
    ]
    
    return {
        "session_id": session_id,
        "total_files": len(index.get("files", [])),
        "total_groups": len(groups_data),
        "groups": group_list,
        "files": [
            {
                "filename": f["filename"],
                "group": f["group"],
                "rows": f.get("rows", 0),
                "columns": f.get("columns", 0),
                "size": _format_size(f.get("size_bytes", 0)),
            }
            for f in files
        ],
    }


def get_file_preview(
    session_id: str, 
    user_id: str, 
    filename: str, 
    max_rows: int = 100
) -> Dict:
    """
    Get preview data for a converted file.
    Returns headers and rows for table display.
    """
    sess_dir = get_session_dir(session_id)
    
    # Verify ownership
    metadata = get_session_metadata(session_id)
    if metadata.get("user_id") and metadata.get("user_id") != user_id:
        raise ValueError("Unauthorized")
    
    out_dir = sess_dir / "output"
    csv_path = out_dir / filename
    
    if not csv_path.exists():
        raise FileNotFoundError(f"File not found: {filename}")
    
    headers = []
    rows = []
    total_rows = 0
    
    try:
        with open(csv_path, "r", encoding="utf-8-sig", newline="") as f:
            reader = csv.DictReader(f)
            headers = reader.fieldnames or []
            
            for i, row in enumerate(reader):
                total_rows += 1
                if i < max_rows:
                    # Convert row to list for table display
                    rows.append([row.get(h, "") for h in headers])
    except UnicodeDecodeError:
        # Fallback to latin-1
        with open(csv_path, "r", encoding="latin-1", newline="") as f:
            reader = csv.DictReader(f)
            headers = reader.fieldnames or []
            
            for i, row in enumerate(reader):
                total_rows += 1
                if i < max_rows:
                    rows.append([row.get(h, "") for h in headers])
    
    return {
        "filename": filename,
        "headers": headers,
        "rows": rows,
        "total_rows": total_rows,
        "preview_rows": len(rows),
        "columns": len(headers),
    }


def build_download_zip(
    session_id: str,
    user_id: str,
    output_format: str = "csv",
    groups: Optional[List[str]] = None,
    preserve_structure: bool = False,
) -> Tuple[bytes, str]:
    """
    Build download ZIP file with converted files.
    
    Args:
        session_id: Session ID
        user_id: User ID for authorization
        output_format: 'csv' or 'xlsx'
        groups: Optional list of groups to include
        preserve_structure: Whether to preserve original folder structure
    
    Returns:
        Tuple of (zip_bytes, filename)
    """
    sess_dir = get_session_dir(session_id)
    
    # Verify ownership
    metadata = get_session_metadata(session_id)
    if metadata.get("user_id") and metadata.get("user_id") != user_id:
        raise ValueError("Unauthorized")
    
    out_dir = sess_dir / "output"
    if not out_dir.exists():
        raise FileNotFoundError("No converted files found")
    
    # Get conversion index
    index = get_conversion_index(session_id, user_id)
    files = index.get("files", [])
    
    # Filter by groups if specified
    if groups:
        files = [f for f in files if f.get("group") in groups]
    
    if not files:
        raise ValueError("No files to download")
    
    buf = io.BytesIO()
    
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for file_info in files:
            csv_path = Path(file_info.get("csv_path", ""))
            if not csv_path.exists():
                csv_path = out_dir / file_info["filename"]
            
            if not csv_path.exists():
                continue
            
            if output_format.lower() == "xlsx":
                # Convert to XLSX
                xlsx_bytes = get_xlsx_bytes_from_csv(str(csv_path))
                xlsx_name = csv_path.stem + ".xlsx"
                
                if preserve_structure:
                    # Use original path structure
                    logical_path = file_info.get("logical_path", xlsx_name)
                    out_name = logical_xml_to_output_relpath(logical_path, ".xlsx")
                else:
                    out_name = xlsx_name
                
                zf.writestr(out_name, xlsx_bytes)
            else:
                # CSV
                csv_name = file_info["filename"]
                
                if preserve_structure:
                    logical_path = file_info.get("logical_path", csv_name)
                    out_name = logical_xml_to_output_relpath(logical_path, ".csv")
                else:
                    out_name = csv_name
                
                zf.write(csv_path, out_name)
    
    ext = "xlsx" if output_format.lower() == "xlsx" else "csv"
    filename = f"converted_{ext}_{session_id[:8]}.zip"
    
    return buf.getvalue(), filename


def download_single_file(
    session_id: str,
    user_id: str,
    filename: str,
    output_format: str = "csv",
) -> Tuple[bytes, str, str]:
    """
    Download a single converted file.
    
    Returns:
        Tuple of (file_bytes, filename, mime_type)
    """
    sess_dir = get_session_dir(session_id)
    
    # Verify ownership
    metadata = get_session_metadata(session_id)
    if metadata.get("user_id") and metadata.get("user_id") != user_id:
        raise ValueError("Unauthorized")
    
    out_dir = sess_dir / "output"
    csv_path = out_dir / filename
    
    if not csv_path.exists():
        raise FileNotFoundError(f"File not found: {filename}")
    
    if output_format.lower() == "xlsx":
        xlsx_bytes = get_xlsx_bytes_from_csv(str(csv_path))
        xlsx_name = csv_path.stem + ".xlsx"
        return xlsx_bytes, xlsx_name, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    else:
        return csv_path.read_bytes(), filename, "text/csv"

