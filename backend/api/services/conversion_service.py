import zipfile
import csv
import shutil
import io
import json
import hashlib
import time
import re
from pathlib import Path
from typing import List, Dict, Optional, Set, Any, Tuple, Literal
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

# ---------------------------------------------------------------------------
# Helpers for edit/save operations
# ---------------------------------------------------------------------------

logger = logging.getLogger(__name__)

# Type alias for group mode (kept for backwards compatibility)
GroupMode = Literal["zip", "folder", "hybrid"]


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


def _assert_session_owner(session_id: str, user_id: str):
    metadata = get_session_metadata(session_id)
    stored_user = metadata.get("user_id", "")
    if stored_user and stored_user != user_id:
        raise ValueError("Unauthorized")


def _load_csv(path: Path):
    """Load CSV into (headers, rows as dicts). Handles BOM."""
    with open(path, "r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        headers = list(reader.fieldnames or [])
        rows = [dict(r) for r in reader]
    return headers, rows


def _write_csv(path: Path, headers: List[str], rows: List[Dict[str, Any]]):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=headers)
        writer.writeheader()
        for row in rows:
            writer.writerow({h: row.get(h, "") for h in headers})


def refresh_conversion_index(session_id: str) -> Dict[str, Any]:
    """Rebuild conversion_index.json from output directory."""
    index = _build_index_from_output(session_id)
    sess_dir = get_session_dir(session_id)
    index_path = sess_dir / "conversion_index.json"
    index_path.write_text(json.dumps(index, indent=2))
    return index


def add_row_to_file(session_id: str, user_id: str, filename: str, row: Dict[str, Any]) -> Dict[str, Any]:
    _assert_session_owner(session_id, user_id)
    out_dir = get_session_dir(session_id) / "output"
    file_path = out_dir / filename
    if not file_path.exists():
        raise FileNotFoundError(f"File not found: {filename}")

    headers, rows = _load_csv(file_path)
    # Expand headers for any new columns provided
    new_cols = [c for c in row.keys() if c not in headers]
    if new_cols:
        headers.extend(new_cols)
        for existing in rows:
            for c in new_cols:
                existing.setdefault(c, "")

    rows.append({h: _safe_cell_value(row.get(h)) for h in headers})
    _write_csv(file_path, headers, rows)
    index = refresh_conversion_index(session_id)
    return {"filename": filename, "rows": len(rows), "columns": len(headers), "index": index}


def add_new_file(session_id: str, user_id: str, filename: str, group: Optional[str], headers: List[str]) -> Dict[str, Any]:
    _assert_session_owner(session_id, user_id)
    if not headers:
        raise ValueError("Headers are required to create a file")
    out_dir = get_session_dir(session_id) / "output"
    out_dir.mkdir(parents=True, exist_ok=True)
    file_path = out_dir / filename
    if file_path.exists():
        raise FileExistsError("File already exists")

    _write_csv(file_path, headers, [])

    # Update index; allow overriding group via metadata in index
    index = refresh_conversion_index(session_id)
    if group:
        # Patch index entry with explicit group if needed
        for f in index.get("files", []):
            if f.get("filename") == filename:
                f["group"] = group
        index_path = get_session_dir(session_id) / "conversion_index.json"
        index_path.write_text(json.dumps(index, indent=2))

    return {"filename": filename, "group": group, "headers": headers}


def delete_file(session_id: str, user_id: str, filename: str) -> Dict[str, Any]:
    _assert_session_owner(session_id, user_id)
    out_dir = get_session_dir(session_id) / "output"
    file_path = out_dir / filename
    xlsx_path = out_dir / (Path(filename).stem + ".xlsx")
    removed = 0
    for p in [file_path, xlsx_path]:
        if p.exists():
            p.unlink()
            removed += 1
    if removed == 0:
        raise FileNotFoundError(f"File not found: {filename}")
    index = refresh_conversion_index(session_id)
    return {"removed": removed, "index": index}


def apply_cell_changes(session_id: str, user_id: str, filename: str, changes: List[Dict[str, Any]]) -> Dict[str, Any]:
    _assert_session_owner(session_id, user_id)
    if not changes:
        return {"updated": 0}

    out_dir = get_session_dir(session_id) / "output"
    file_path = out_dir / filename
    if not file_path.exists():
        raise FileNotFoundError(f"File not found: {filename}")

    headers, rows = _load_csv(file_path)
    updated = 0

    # Add missing columns if any change references them
    missing_cols = {c.get("column") for c in changes if c.get("column") not in headers}
    missing_cols.discard(None)
    if missing_cols:
        headers.extend([c for c in missing_cols if c])
        for row in rows:
            for c in missing_cols:
                row.setdefault(c, "")

    for change in changes:
        row_idx = change.get("row_index")
        col = change.get("column")
        val = change.get("value", "")
        if row_idx is None or col is None:
            continue
        if row_idx < 0 or row_idx >= len(rows):
            continue
        rows[row_idx][col] = _safe_cell_value(val)
        updated += 1

    _write_csv(file_path, headers, rows)
    index = refresh_conversion_index(session_id)
    return {"updated": updated, "rows": len(rows), "columns": len(headers), "index": index}


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


def scan_zip_with_groups(
    file_bytes: bytes,
    filename: str,
    user_id: str,
    group_mode: GroupMode = "zip",  # Kept for backwards compatibility
    group_prefix_len: Optional[int] = None,
    max_depth: int = 10,
    max_files: int = 20000,
    max_unzipped_bytes: int = 300 * 1024 * 1024,
) -> Dict:
    """
    Save uploaded file to a fresh session and scan it for XML files.
    Returns session metadata and groups.
    
    Groups are determined by the MODULE PREFIX of business ZIPs:
    - AR_PAYMENT_TERM.zip → AR
    - ATK_KR_TOPIC.zip → ATK
    - CST_COST_BOOK.zip → CST
    
    Root ZIPs and batch ZIPs do NOT become groups.
    Folders are traversed but do NOT affect grouping.
    
    Args:
        file_bytes: Raw file bytes
        filename: Original filename
        user_id: User ID for ownership
        group_mode: Legacy parameter (kept for compatibility, not used)
        group_prefix_len: Optional max prefix length (2, 3, 4...)
        max_depth: Maximum ZIP nesting depth
        max_files: Maximum XML files to collect
        max_unzipped_bytes: Maximum bytes to extract
    
    Returns:
        Scan result with session_id, xml_count, groups, files
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
            "business_zip": "",
            "folder_path": "",
            "root_folder": "",
            "zip_chain": [],
        }]
        groups = {group: xml_files}
        total_size = file_size
        
        logger.info(f"Processed single XML file: {filename} ({file_size} bytes)")
        
    elif is_zip:
        # ZIP file - extract and scan recursively
        xml_files, groups, total_size = scan_zip_for_xml(
            zip_path,
            temp_dir=sess_dir,
            max_depth=max_depth,
            custom_prefixes=None,
            group_prefix_len=group_prefix_len,
            max_files=max_files,
            max_unzipped_bytes=max_unzipped_bytes,
        )
        logger.info(f"Scanned ZIP: {filename}, found {len(xml_files)} XML files in {len(groups)} groups")
    else:
        raise ValueError(f"Unsupported file type: {filename}")

    # Save metadata including file-to-group mappings
    metadata = {
        "session_id": session_id,
        "user_id": user_id,
        "uploaded_file": filename,
        "xml_count": len(xml_files),
        "groups": {k: len(v) for k, v in groups.items()},
        "group_list": list(groups.keys()),
        "total_size": total_size,
        "group_prefix_len": group_prefix_len,
        "max_depth": max_depth,
        "xml_files": xml_files,  # Store file-to-group mappings for consistent conversion
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


def convert_session(session_id: str, groups: Optional[List[str]] = None, output_format: str = "csv") -> Dict:
    """
    Convert all XML files present in session's extracted folder into CSVs or XLSX files.
    Result files are placed in session/output/.
    
    Args:
        session_id: Session ID
        groups: Optional list of groups to convert
        output_format: Output format ('csv' or 'xlsx')
    """
    sess_dir = get_session_dir(session_id)
    extract_dir = sess_dir / "extracted"
    out_dir = sess_dir / "output"
    out_dir.mkdir(exist_ok=True)
    
    output_format = output_format.lower().strip()
    if output_format not in ["csv", "xlsx"]:
        output_format = "csv"
    
    logger.info(f"Converting session {session_id}, groups filter: {groups}, format: {output_format}")
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

    # Load file-to-group mappings from scan metadata
    metadata = get_session_metadata(session_id)
    xml_files_metadata = metadata.get("xml_files", [])
    
    # Build a mapping from abs_path to group for quick lookup
    path_to_group = {f["abs_path"]: f["group"] for f in xml_files_metadata}
    
    if not path_to_group:
        logger.warning(
            f"No file-to-group mappings found in session metadata. "
            f"This may be an old session or metadata is missing. "
            f"Groups will be inferred from paths/filenames."
        )
    
    xml_file_list = list(extract_dir.rglob("*.xml"))
    logger.info(f"Found {len(xml_file_list)} XML files in {extract_dir}")
    logger.info(f"Loaded {len(path_to_group)} file-to-group mappings from scan metadata")

    # Track used output names to prevent collisions
    used_csv_names: Set[str] = set()

    for xml_file in xml_file_list:
        relative_path = str(xml_file.relative_to(extract_dir))
        
        # Use stored group from scan metadata if available, otherwise infer
        abs_path_str = str(xml_file)
        if abs_path_str in path_to_group:
            group = path_to_group[abs_path_str]
            logger.debug(f"Using stored group for {xml_file.name}: {group}")
        else:
            group = infer_group(relative_path, xml_file.name)
            logger.warning(f"Group not found in metadata for {xml_file.name}, inferred: {group}")

        logger.debug(f"Processing {xml_file.name}, group={group}")

        if groups and group not in groups:
            logger.info(f"Skipping {xml_file.name}: group '{group}' not in filter {groups}")
            continue
        
        logger.info(f"Converting {xml_file.name} (group: {group})...")

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

            # Build unique CSV name preserving subdirectory context to prevent collisions
            relative_parts = xml_file.relative_to(extract_dir).parts
            if len(relative_parts) > 1:
                csv_name = "__".join(relative_parts[:-1]) + "__" + xml_file.stem + ".csv"
            else:
                csv_name = xml_file.stem + ".csv"

            # Handle any remaining collisions with a counter suffix
            base_csv_name = csv_name
            counter = 1
            while csv_name in used_csv_names:
                csv_name = base_csv_name.replace(".csv", f"_{counter}.csv")
                counter += 1
            used_csv_names.add(csv_name)

            csv_path = out_dir / csv_name
            with open(csv_path, "w", newline="", encoding="utf-8") as outf:
                writer = csv.DictWriter(outf, fieldnames=headers)
                writer.writeheader()
                for r in rows:
                    row_data = {h: r.get(h, "") for h in headers}
                    writer.writerow(row_data)
            
            # If XLSX format requested, convert CSV to XLSX
            if output_format == "xlsx":
                try:
                    from api.services.xlsx_service import csv_to_xlsx_bytes
                    xlsx_name = csv_name.replace(".csv", ".xlsx")
                    xlsx_path = out_dir / xlsx_name
                    
                    xlsx_bytes = csv_to_xlsx_bytes(str(csv_path))
                    with open(xlsx_path, "wb") as f:
                        f.write(xlsx_bytes)
                    
                    converted_files.append({
                        "filename": xlsx_name, 
                        "group": group, 
                        "rows": len(rows), 
                        "columns": len(headers),
                        "format": "xlsx"
                    })
                    logger.info("Converted %s -> %s (XLSX, %d rows, %d cols)", xml_file.name, xlsx_name, len(rows), len(headers))
                except Exception as xlsx_err:
                    logger.warning(f"XLSX conversion failed for {xml_file.name}, keeping CSV: {xlsx_err}")
                    converted_files.append({
                        "filename": csv_name, 
                        "group": group, 
                        "rows": len(rows), 
                        "columns": len(headers),
                        "format": "csv"
                    })
            else:
                converted_files.append({
                    "filename": csv_name, 
                    "group": group, 
                    "rows": len(rows), 
                    "columns": len(headers),
                    "format": "csv"
                })
                logger.info("Converted %s -> %s (%d rows, %d cols)", xml_file.name, csv_name, len(rows), len(headers))
            
            success += 1
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
    
    # Log detailed conversion summary
    skipped = len(xml_file_list) - success - failed
    logger.info(
        f"Conversion complete for session {session_id}: "
        f"{len(xml_file_list)} total XML files, "
        f"{success} converted, {failed} failed, {skipped} skipped (filtered)"
    )
    if groups:
        logger.info(f"Group filter applied: {groups}")
    
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


def _safe_cell_value(value) -> str:
    """Convert any cell value to string, handling None/NaN/etc."""
    if value is None:
        return ""
    # Handle pandas NaN or other float NaN
    try:
        import math
        if isinstance(value, float) and math.isnan(value):
            return ""
    except (TypeError, ValueError):
        pass
    return str(value)


def get_file_preview(
    session_id: str, 
    user_id: str, 
    filename: str, 
    max_rows: int = 100
) -> Dict:
    """
    Get preview data for a converted file (CSV or XLSX).
    Returns headers and rows for table display.
    """
    sess_dir = get_session_dir(session_id)
    
    # Verify ownership
    metadata = get_session_metadata(session_id)
    if metadata.get("user_id") and metadata.get("user_id") != user_id:
        raise ValueError("Unauthorized")
    
    out_dir = sess_dir / "output"
    file_path = out_dir / filename
    
    # Handle XLSX files - look for corresponding CSV or try to read XLSX
    is_xlsx = filename.lower().endswith('.xlsx')
    
    if is_xlsx:
        # Try to find corresponding CSV file first
        csv_filename = filename[:-5] + '.csv'
        csv_path = out_dir / csv_filename
        if csv_path.exists():
            file_path = csv_path
            is_xlsx = False
        elif not file_path.exists():
            raise FileNotFoundError(f"File not found: {filename}")
    
    if not file_path.exists():
        raise FileNotFoundError(f"File not found: {filename}")
    
    headers = []
    rows = []
    total_rows = 0
    
    if is_xlsx:
        # Try to read XLSX with pandas
        try:
            import pandas as pd
            df = pd.read_excel(file_path, nrows=max_rows + 1)
            headers = [str(h) for h in df.columns.tolist()]
            total_rows = len(df)
            
            for idx, row in df.iterrows():
                if idx < max_rows:
                    # Convert each cell to string, handling None/NaN
                    rows.append([_safe_cell_value(row.get(h)) for h in headers])
        except ImportError:
            logger.warning("pandas/openpyxl not available for XLSX preview")
            raise FileNotFoundError(f"XLSX preview not supported. CSV file not found: {filename[:-5]}.csv")
        except Exception as e:
            logger.warning(f"Failed to read XLSX {filename}: {e}")
            raise FileNotFoundError(f"Failed to read XLSX file: {str(e)}")
    else:
        # Read CSV file
        try:
            with open(file_path, "r", encoding="utf-8-sig", newline="") as f:
                reader = csv.DictReader(f)
                headers = list(reader.fieldnames or [])
                
                for i, row in enumerate(reader):
                    total_rows += 1
                    if i < max_rows:
                        # Convert row to list for table display, handling None values
                        rows.append([_safe_cell_value(row.get(h)) for h in headers])
        except UnicodeDecodeError:
            # Fallback to latin-1
            with open(file_path, "r", encoding="latin-1", newline="") as f:
                reader = csv.DictReader(f)
                headers = list(reader.fieldnames or [])
                
                for i, row in enumerate(reader):
                    total_rows += 1
                    if i < max_rows:
                        rows.append([_safe_cell_value(row.get(h)) for h in headers])
    
    return {
        "filename": filename,
        "headers": list(headers),
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

