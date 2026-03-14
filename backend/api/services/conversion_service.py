
"""
Conversion Service — XML-to-CSV/XLSX Pipeline (Refactored).

Now supports:
- Scan ZIP/XML/XML.GZ/CSV/XLSX/XLS (nested ZIPs supported via scan_zip_for_files)
- Grouping via module prefix
- Parallel XML -> CSV/XLSX conversion with REAL NAME output naming (path_to_logical wired)
- Exclusion list that can hide files AND skip them from conversion
- Copy-through scanned CSV/XLSX/XLS into output for consistent post-conversion display
- ✅ Convert ALL scanned .XLS into .CSV as well (handles BIFF XLS, HTML-as-XLS, mislabeled XLSX)
- Preview CSV/XLSX/XLS in tabular form (XLS requires xlrd; HTML-as-XLS uses pandas.read_html)
"""

import csv
import io
import json
import hashlib
import shutil
import time
import zipfile
import logging
from pathlib import Path
from typing import List, Dict, Optional, Set, Any, Tuple, Literal
from collections import defaultdict
from urllib.parse import unquote

from api.services.storage_service import (
    create_session_dir,
    get_session_dir,
    save_upload,
    get_session_metadata,
    save_session_metadata,
)
from api.services.xml_processing_service import (
    scan_zip_for_files,
    infer_group,
)
from api.services.xlsx_service import get_xlsx_bytes_from_csv
from api.services.parallel_converter import convert_parallel
from api.core.config import settings

logger = logging.getLogger(__name__)

GroupMode = Literal["zip", "folder", "hybrid"]
CONVERSION_MAX_WORKERS = getattr(settings, "CONVERSION_MAX_WORKERS", 64)

META_SCANNED_FILES = "scanned_files"
META_XML_FILES = "xml_files"  # backward compatible
META_EXCLUDED_LOGICAL = "excluded_logical_paths"  # used to skip conversion


# ---------------------------------------------------------------------------
# Generic helpers
# ---------------------------------------------------------------------------

def _sha_short(s: str, n: int = 16) -> str:
    return hashlib.sha1(s.encode("utf-8")).hexdigest()[:n]


def _format_size(size_bytes: int) -> str:
    size: float = float(size_bytes)
    for unit in ["B", "KB", "MB", "GB"]:
        if size < 1024:
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} TB"


def _assert_session_owner(session_id: str, user_id: str):
    meta = get_session_metadata(session_id)
    stored_user = meta.get("user_id", "")
    if stored_user and stored_user != user_id:
        raise ValueError("Unauthorized")


def _safe_cell_value(value) -> str:
    if value is None:
        return ""
    try:
        import math
        if isinstance(value, float) and math.isnan(value):
            return ""
    except (TypeError, ValueError):
        pass
    return str(value)


def _infer_file_type_from_name(filename: str) -> str:
    lower = (filename or "").lower()
    if lower.endswith(".csv"):
        return "csv"
    if lower.endswith(".xlsx"):
        return "xlsx"
    if lower.endswith(".xls"):
        return "xls"
    if lower.endswith(".xml"):
        return "xml"
    return "file"


def _excluded_set(meta: Dict[str, Any]) -> Set[str]:
    return set((meta.get(META_EXCLUDED_LOGICAL, []) or []))


def _resolve_output_file(out_dir: Path, filename: str) -> Path:
    """
    Resolve a filename inside out_dir:
    - try exact
    - try URL-decoded
    - try uppercase variants
    """
    if not filename:
        raise FileNotFoundError("Filename is required")

    candidates = [filename, unquote(filename), filename.upper(), unquote(filename).upper()]
    for c in candidates:
        p = out_dir / c
        if p.exists():
            return p

    raise FileNotFoundError(f"File not found: {filename}")


# ---------------------------------------------------------------------------
# XLS helpers (✅ NEW: robust parsing + XLS->CSV conversion)
# ---------------------------------------------------------------------------

def _read_xls_like_to_dataframe(xls_path: Path):
    """
    Reads a file with .xls extension that might actually be:
    - BIFF .xls
    - HTML table (common "Export to Excel" output)
    - mislabeled .xlsx (zip/PK header)
    Returns a pandas DataFrame (best-effort).
    """
    try:
        import pandas as pd
    except ImportError as e:
        raise RuntimeError("XLS->CSV conversion requires pandas") from e

    with open(xls_path, "rb") as fh:
        head = fh.read(4096)

    head_l = head.lstrip().lower()

    # Case 1: mislabeled XLSX saved as .xls (zip signature)
    if head.startswith(b"PK"):
        try:
            return pd.read_excel(xls_path, engine="openpyxl")
        except Exception as e:
            raise RuntimeError(f"File looks like XLSX but failed to read as XLSX: {str(e)}") from e

    # Case 2: HTML exported as .xls
    if head_l.startswith(b"<html") or b"<!doctype html" in head_l or b"<table" in head_l:
        try:
            tables = pd.read_html(xls_path)  # requires lxml or html5lib+bs4
            if not tables:
                raise RuntimeError("No HTML tables found in this .xls file.")
            best = max(tables, key=lambda d: (d.shape[0] * d.shape[1], d.shape[0], d.shape[1]))
            return best
        except ImportError as e:
            raise RuntimeError(
                "HTML-as-XLS conversion requires an HTML parser. Install lxml (recommended) or html5lib+beautifulsoup4."
            ) from e
        except Exception as e:
            raise RuntimeError(f"Failed to parse HTML-as-XLS: {str(e)}") from e

    # Case 3: XML/SpreadsheetML saved as .xls (rare)
    if head_l.startswith(b"<?xml") or b"<workbook" in head_l:
        raise RuntimeError(
            "This .xls appears to be XML/SpreadsheetML. Convert it to XLSX/CSV first, or implement SpreadsheetML parsing."
        )

    # Case 4: true BIFF .xls
    try:
        return pd.read_excel(xls_path, engine="xlrd")  # needs xlrd==2.0.1
    except ImportError as e:
        raise RuntimeError("BIFF .xls conversion requires xlrd==2.0.1 (pip install xlrd==2.0.1)") from e
    except Exception as e:
        raise RuntimeError(f"Failed to read BIFF XLS: {str(e)}") from e


def _write_dataframe_to_csv(df, csv_path: Path, max_rows: Optional[int] = None) -> Tuple[int, int]:
    """
    Writes dataframe to CSV (utf-8). Returns (rows, cols).
    """
    try:
        import pandas as pd  # noqa: F401
    except ImportError as e:
        raise RuntimeError("CSV writing requires pandas") from e

    if max_rows is not None:
        df = df.head(max_rows)

    csv_path.parent.mkdir(parents=True, exist_ok=True)

    df.columns = [str(c) for c in df.columns]
    df.to_csv(csv_path, index=False, encoding="utf-8")

    return int(len(df)), int(len(df.columns))


# ---------------------------------------------------------------------------
# CSV I/O for edit features
# ---------------------------------------------------------------------------

def _load_csv(path: Path):
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


# ---------------------------------------------------------------------------
# Exclusion list API
# ---------------------------------------------------------------------------

def get_exclusion_list(session_id: str, user_id: str) -> List[str]:
    _assert_session_owner(session_id, user_id)
    meta = get_session_metadata(session_id)
    excluded = meta.get(META_EXCLUDED_LOGICAL, []) or []
    return [str(x) for x in excluded]


def set_exclusion_list(session_id: str, user_id: str, excluded_logical_paths: List[str]) -> Dict[str, Any]:
    _assert_session_owner(session_id, user_id)
    meta = get_session_metadata(session_id)
    cleaned = sorted({(x or "").strip() for x in (excluded_logical_paths or []) if (x or "").strip()})
    meta[META_EXCLUDED_LOGICAL] = cleaned
    save_session_metadata(session_id, meta)
    return {"session_id": session_id, "excluded_count": len(cleaned), "excluded": cleaned}


# ---------------------------------------------------------------------------
# Naming helpers for downloads/preserve_structure
# ---------------------------------------------------------------------------

def _sanitize_path(p: str) -> str:
    p = (p or "").replace("\\", "/").lstrip("/")
    parts = []
    for part in p.split("/"):
        if part in ("", ".", ".."):
            continue
        parts.append(part)
    return "/".join(parts) or "file"


def logical_xml_to_output_relpath(logical_path: str, out_ext: str = ".csv") -> str:
    lp = _sanitize_path(logical_path)
    lower = lp.lower()

    if lower.endswith(".xml"):
        lp = lp[:-4] + out_ext
    elif lower.endswith(".xml.gz"):
        lp = lp[:-7] + out_ext
    else:
        base = Path(lp).name
        parent = str(Path(lp).parent).replace("\\", "/")
        stem = Path(base).stem
        lp = f"{parent}/{stem}{out_ext}" if parent not in ("", ".") else f"{stem}{out_ext}"
        lp = _sanitize_path(lp)

    return lp


# ---------------------------------------------------------------------------
# Index helpers
# ---------------------------------------------------------------------------

def refresh_conversion_index(session_id: str) -> Dict[str, Any]:
    index = _build_index_from_output(session_id)
    sess_dir = get_session_dir(session_id)
    (sess_dir / "conversion_index.json").write_text(json.dumps(index, indent=2))
    return index


def _save_conversion_index(session_id: str, files_index: List[Dict[str, Any]]):
    sess_dir = get_session_dir(session_id)
    index_path = sess_dir / "conversion_index.json"

    index = {
        "session_id": session_id,
        "converted_at": time.time(),
        "files": [],
        "groups": defaultdict(list),
    }

    out_dir = sess_dir / "output"

    for f in files_index:
        fname = (f.get("filename") or "").upper()
        p = out_dir / fname

        file_info = {
            "filename": fname,
            "group": f.get("group", "MISC"),
            "rows": f.get("rows", 0),
            "columns": f.get("columns", 0),
            "file_type": f.get("file_type") or _infer_file_type_from_name(fname),
            "logical_path": f.get("logical_path", ""),
            "path": str(p),
            "size_bytes": p.stat().st_size if p.exists() else 0,
        }
        index["files"].append(file_info)
        index["groups"][file_info["group"]].append(file_info)

    index["groups"] = dict(index["groups"])
    index_path.write_text(json.dumps(index, indent=2))


def get_conversion_index(session_id: str, user_id: str) -> Dict:
    meta = get_session_metadata(session_id)
    if meta.get("user_id") and meta.get("user_id") != user_id:
        raise ValueError("Unauthorized")

    sess_dir = get_session_dir(session_id)
    index_path = sess_dir / "conversion_index.json"
    if not index_path.exists():
        return _build_index_from_output(session_id)

    return json.loads(index_path.read_text())


def _build_index_from_output(session_id: str) -> Dict:
    sess_dir = get_session_dir(session_id)
    out_dir = sess_dir / "output"

    if not out_dir.exists():
        return {"session_id": session_id, "files": [], "groups": {}}

    files: List[Dict[str, Any]] = []
    groups: Dict[str, List[Dict[str, Any]]] = defaultdict(list)

    for p in out_dir.iterdir():
        if not p.is_file():
            continue
        if p.suffix.lower() not in (".csv", ".xlsx", ".xls"):
            continue

        ftype = _infer_file_type_from_name(p.name)
        rows = 0
        cols = 0

        if ftype == "csv":
            try:
                with open(p, "r", encoding="utf-8-sig", newline="") as f:
                    reader = csv.reader(f)
                    headers = next(reader, [])
                    cols = len(headers)
                    rows = sum(1 for _ in reader)
            except Exception:
                pass

        group = infer_group(p.stem, p.name)

        file_info = {
            "filename": p.name.upper(),
            "group": group,
            "rows": rows,
            "columns": cols,
            "file_type": ftype,
            "logical_path": "",
            "path": str(p),
            "size_bytes": p.stat().st_size,
        }
        files.append(file_info)
        groups[group].append(file_info)

    return {"session_id": session_id, "files": files, "groups": dict(groups)}


# ---------------------------------------------------------------------------
# Scan
# ---------------------------------------------------------------------------

def scan_zip_with_groups(
    file_bytes: bytes,
    filename: str,
    user_id: str,
    group_mode: GroupMode = "zip",
    group_prefix_len: Optional[int] = None,
    max_depth: int = 10,
    max_files: int = 20000,
    max_unzipped_bytes: int = 300 * 1024 * 1024,
) -> Dict:
    from api.utils.metrics import timed_block

    with timed_block("scan_zip_with_groups", size_bytes=len(file_bytes), extra={"filename": filename}):
        return _scan_zip_with_groups_impl(
            file_bytes, filename, user_id, group_mode,
            group_prefix_len, max_depth, max_files, max_unzipped_bytes,
        )


def _scan_zip_with_groups_impl(
    file_bytes: bytes,
    filename: str,
    user_id: str,
    group_mode: GroupMode = "zip",
    group_prefix_len: Optional[int] = None,
    max_depth: int = 10,
    max_files: int = 20000,
    max_unzipped_bytes: int = 300 * 1024 * 1024,
) -> Dict:
    session_id = create_session_dir(user_id)
    sess_dir = get_session_dir(session_id)

    extract_dir = sess_dir / "extracted"
    extract_dir.mkdir(parents=True, exist_ok=True)

    upload_path = save_upload(session_id, filename, file_bytes)

    lower = filename.lower().strip()
    is_zip = lower.endswith(".zip")
    is_xml = lower.endswith(".xml") or lower.endswith(".xml.gz")
    is_csv = lower.endswith(".csv")
    is_xlsx = lower.endswith(".xlsx")
    is_xls = lower.endswith(".xls")

    scanned_files: List[Dict[str, Any]] = []
    groups: Dict[str, List[Dict[str, Any]]] = {}
    total_size = 0

    if is_zip:
        scanned_files, groups, total_size = scan_zip_for_files(
            upload_path,
            temp_dir=sess_dir,
            max_depth=max_depth,
            custom_prefixes=None,
            group_prefix_len=group_prefix_len,
            max_files=max_files,
            max_unzipped_bytes=max_unzipped_bytes,
            include_extensions={".xml", ".xml.gz", ".csv", ".xlsx", ".xls"},
        )
    elif is_xml or is_csv or is_xlsx or is_xls:
        dest = extract_dir / filename
        shutil.copy(upload_path, dest)
        size = dest.stat().st_size
        group = infer_group(filename, filename, None)
        ftype = "xml" if is_xml else ("csv" if is_csv else ("xlsx" if is_xlsx else "xls"))
        entry = {
            "filename": filename,
            "path": filename,
            "logical_path": filename,
            "group": group,
            "size": size,
            "abs_path": str(dest),
            "file_type": ftype,
            "business_zip": "",
            "folder_path": "",
            "root_folder": "",
            "zip_chain": [],
        }
        scanned_files = [entry]
        groups = {group: [entry]}
        total_size = size
    else:
        raise ValueError(f"Unsupported file type: {filename}")

    xml_files = [f for f in scanned_files if f.get("file_type") == "xml"]
    type_counts = defaultdict(int)
    for f in scanned_files:
        type_counts[f.get("file_type", "file")] += 1

    metadata = {
        "session_id": session_id,
        "user_id": user_id,
        "uploaded_file": filename,
        "xml_count": len(xml_files),
        "file_count": len(scanned_files),
        "type_counts": dict(type_counts),
        "groups": {k: len(v) for k, v in groups.items()},
        "group_list": list(groups.keys()),
        "total_size": total_size,
        "group_prefix_len": group_prefix_len,
        "max_depth": max_depth,
        META_SCANNED_FILES: scanned_files,
        META_XML_FILES: xml_files,
        META_EXCLUDED_LOGICAL: [],
    }
    save_session_metadata(session_id, metadata)

    # Load admin auto-embed config to annotate groups
    try:
        from api.services.admin_service import get_ai_indexing_config_data
        ai_cfg = get_ai_indexing_config_data() or {}
        embed_enabled = bool(ai_cfg.get("auto_embed_enabled"))
        embed_groups = {str(g).strip().upper() for g in (ai_cfg.get("auto_embedded_groups") or []) if g}
    except Exception:
        embed_enabled = False
        embed_groups = set()

    def _group_entry(name: str, files: list) -> dict:
        entry = {
            "name": name,
            "file_count": len(files),
            "size": sum(x.get("size", 0) for x in files),
        }
        if not embed_enabled:
            entry["auto_embed_eligible"] = False
            entry["auto_embed_reason"] = "Auto-embedding disabled by admin"
        elif embed_groups and name.upper() not in embed_groups:
            entry["auto_embed_eligible"] = False
            entry["auto_embed_reason"] = "Group not in admin auto-embed list"
        else:
            entry["auto_embed_eligible"] = True
            entry["auto_embed_reason"] = "Admin-configured for auto-embedding"
        return entry

    return {
        "session_id": session_id,
        "xml_count": len(xml_files),
        "file_count": len(scanned_files),
        "group_count": len(groups),
        "files": scanned_files,
        "groups": [
            _group_entry(g, fl)
            for g, fl in sorted(groups.items())
        ],
        "summary": {
            "totalFiles": len(scanned_files),
            "totalGroups": len(groups),
            "totalSize": total_size,
            "typeCounts": dict(type_counts),
        },
    }


def get_session_info(session_id: str, user_id: str) -> Dict:
    sess_dir = get_session_dir(session_id)
    if not sess_dir.exists():
        raise ValueError(f"Session {session_id} not found")
    meta = get_session_metadata(session_id)
    if meta.get("user_id") != user_id:
        raise ValueError("Unauthorized")
    return meta


# ---------------------------------------------------------------------------
# Conversion (respects exclusion list)
# ---------------------------------------------------------------------------

def _copy_non_xml_inputs_to_output(
    scanned_files: List[Dict[str, Any]],
    out_dir: Path,
    groups_filter: Optional[List[str]],
    excluded: Set[str],
) -> Tuple[List[Dict[str, Any]], int]:
    """
    Copy scanned CSV/XLSX/XLS into output for post-conversion display.
    ✅ Additionally converts every copied .XLS into a .CSV.

    Skips excluded logical paths.
    Returns: (entries, skipped_count)
    """
    filter_set = set(groups_filter) if groups_filter else None
    skipped = 0
    out_dir.mkdir(parents=True, exist_ok=True)

    copied_entries: List[Dict[str, Any]] = []

    for f in scanned_files or []:
        ftype = f.get("file_type")
        if ftype not in ("csv", "xlsx", "xls"):
            continue

        logical = (f.get("logical_path") or "").strip()
        if logical and logical in excluded:
            skipped += 1
            continue

        group = f.get("group", "EXTRAS")
        if filter_set and group not in filter_set:
            skipped += 1
            continue

        src = Path(f.get("abs_path", ""))
        if not src.exists():
            continue

        # 1) Copy original file to output
        dst_name = src.name.upper()
        dst = out_dir / dst_name

        if dst.exists():
            lp = logical or f.get("path") or dst_name
            suffix = _sha_short(lp, 8).upper()
            dst_name = f"{Path(dst_name).stem}__{suffix}{Path(dst_name).suffix}".upper()
            dst = out_dir / dst_name

        shutil.copy(src, dst)

        rows = 0
        cols = 0
        if dst.suffix.lower() == ".csv":
            try:
                with open(dst, "r", encoding="utf-8-sig", newline="") as fh:
                    reader = csv.reader(fh)
                    headers = next(reader, [])
                    cols = len(headers)
                    rows = sum(1 for _ in reader)
            except Exception:
                pass

        copied_entries.append({
            "filename": dst.name.upper(),
            "group": group,
            "rows": rows,
            "columns": cols,
            "file_type": ftype,
            "logical_path": logical,
        })

        # 2) If original is XLS, also generate CSV
        if ftype == "xls":
            try:
                csv_name = f"{Path(dst.name).stem}.CSV"
                csv_path = out_dir / csv_name

                if csv_path.exists():
                    lp = (logical or f.get("path") or dst.name) + "::CSV"
                    suffix = _sha_short(lp, 8).upper()
                    csv_name = f"{Path(dst.name).stem}__{suffix}.CSV"
                    csv_path = out_dir / csv_name

                df = _read_xls_like_to_dataframe(dst)
                csv_rows, csv_cols = _write_dataframe_to_csv(df, csv_path)

                copied_entries.append({
                    "filename": csv_path.name.upper(),
                    "group": group,
                    "rows": csv_rows,
                    "columns": csv_cols,
                    "file_type": "csv",
                    "logical_path": logical,
                })

            except Exception as e:
                logger.warning(f"XLS->CSV conversion failed for {dst.name}: {e}")

    return copied_entries, skipped


def convert_session(session_id: str, groups: Optional[List[str]] = None, output_format: str = "csv") -> Dict:
    """
    Convert XML -> CSV/XLSX using convert_parallel with path_to_logical and skip excluded files.
    Also copies non-XML files through and converts .XLS -> .CSV (see _copy_non_xml_inputs_to_output).
    """
    from api.utils.metrics import timed_block

    with timed_block("convert_session", extra={"session_id": session_id, "groups": groups}):
        return _convert_session_impl(session_id, groups, output_format)


def _convert_session_impl(session_id: str, groups: Optional[List[str]] = None, output_format: str = "csv") -> Dict:
    sess_dir = get_session_dir(session_id)
    extract_dir = sess_dir / "extracted"
    out_dir = sess_dir / "output"
    out_dir.mkdir(exist_ok=True)

    output_format = (output_format or "csv").lower().strip()
    if output_format not in ("csv", "xlsx"):
        output_format = "csv"

    if not extract_dir.exists():
        return {
            "session_id": session_id,
            "stats": {
                "total_files": 0, "success": 0, "failed": 0, "skipped": 0,
                "total_rows": 0, "duration": 0.0, "avg_time_per_file": 0.0
            },
            "converted_files": [],
            "errors": [{"file": "N/A", "error": "No extracted files found. Please scan a file first."}],
        }

    meta = get_session_metadata(session_id)
    scanned_files = meta.get(META_SCANNED_FILES) or meta.get(META_XML_FILES) or []
    excluded = _excluded_set(meta)

    copied_entries, skipped_nonxml = _copy_non_xml_inputs_to_output(scanned_files, out_dir, groups, excluded)

    xml_file_list = list(extract_dir.rglob("*.xml"))
    if not xml_file_list:
        _save_conversion_index(session_id, copied_entries)
        return {
            "session_id": session_id,
            "stats": {
                "total_files": 0, "success": 0, "failed": 0, "skipped": skipped_nonxml,
                "total_rows": 0, "duration": 0.0, "avg_time_per_file": 0.0
            },
            "converted_files": copied_entries,
            "errors": [],
        }

    path_to_group = {
        f.get("abs_path"): f.get("group")
        for f in scanned_files
        if f.get("abs_path") and f.get("group")
    }
    path_to_logical = {
        f.get("abs_path"): f.get("logical_path")
        for f in scanned_files
        if f.get("abs_path") and f.get("logical_path")
    }

    filtered_xml: List[Path] = []
    skipped_xml = 0
    for xp in xml_file_list:
        lp = path_to_logical.get(str(xp), "")
        if lp and lp in excluded:
            skipped_xml += 1
            continue
        filtered_xml.append(xp)

    if not filtered_xml:
        _save_conversion_index(session_id, copied_entries)
        return {
            "session_id": session_id,
            "stats": {
                "total_files": 0, "success": 0, "failed": 0,
                "skipped": skipped_nonxml + skipped_xml,
                "total_rows": 0, "duration": 0.0, "avg_time_per_file": 0.0
            },
            "converted_files": copied_entries,
            "errors": [],
        }

    num_workers = int(CONVERSION_MAX_WORKERS) if CONVERSION_MAX_WORKERS else 64

    stats, converted_files, errors = convert_parallel(
        session_id=session_id,
        extract_dir=extract_dir,
        output_dir=out_dir,
        xml_files=filtered_xml,
        path_to_group=path_to_group,
        groups_filter=groups,
        output_format=output_format,
        num_workers=num_workers,
        progress_callback=None,
        path_to_logical=path_to_logical,
    )

    combined: List[Dict[str, Any]] = []
    combined.extend(copied_entries)
    for cf in converted_files:
        combined.append({
            "filename": (cf.get("filename") or "").upper(),
            "group": cf.get("group", "MISC"),
            "rows": cf.get("rows", 0),
            "columns": cf.get("columns", 0),
            "file_type": cf.get("file_type") or cf.get("format") or "csv",
            "logical_path": cf.get("logical_path", ""),
        })

    _save_conversion_index(session_id, combined)

    # Generate sidecar cache for embedding acceleration
    if getattr(settings, "FEATURE_SIDECAR_CACHE", False):
        try:
            from api.utils.sidecar import generate_sidecars_for_dir
            file_groups = {
                (cf.get("filename") or "").upper(): cf.get("group", "EXTRAS")
                for cf in converted_files
            }
            sc_count = generate_sidecars_for_dir(out_dir, file_groups)
            logger.info("Generated %d sidecar cache files for session %s", sc_count, session_id)
        except Exception as sc_err:
            logger.warning("Sidecar generation failed (non-fatal): %s", sc_err)

    result_skipped = getattr(stats, "skipped", 0) + skipped_nonxml + skipped_xml

    return {
        "session_id": session_id,
        "stats": {
            "total_files": getattr(stats, "total_files", len(filtered_xml)),
            "success": getattr(stats, "success", 0),
            "failed": getattr(stats, "failed", 0),
            "skipped": result_skipped,
            "total_rows": getattr(stats, "total_rows", 0),
            "duration": getattr(stats, "total_duration", 0.0),
            "avg_time_per_file": getattr(stats, "average_time_per_file", 0.0),
        },
        "converted_files": combined,
        "errors": errors,
    }


# ---------------------------------------------------------------------------
# List / preview / download
# ---------------------------------------------------------------------------

def list_converted_files(session_id: str, user_id: str, group: Optional[str] = None) -> Dict:
    """
    List output files for a session.

    ✅ Change: Only return CSV files (including CSV generated from XLS).
    We still keep XLS/XLSX in output for downloads/history, but hide them from UI listing.
    """
    index = get_conversion_index(session_id, user_id)
    meta = get_session_metadata(session_id)
    excluded = _excluded_set(meta)

    files = index.get("files", []) or []
    groups_data = index.get("groups", {}) or {}

    def _is_csv(f: Dict[str, Any]) -> bool:
        ft = (f.get("file_type") or "").lower().strip()
        name = (f.get("filename") or "").lower().strip()
        return ft == "csv" or name.endswith(".csv")

    # 1) Apply exclusion list
    if excluded:
        files = [f for f in files if (f.get("logical_path") or "") not in excluded]
        groups_data = {
            g: [f for f in flist if (f.get("logical_path") or "") not in excluded]
            for g, flist in groups_data.items()
        }

    # 2) ✅ CSV-only filtering
    files = [f for f in files if _is_csv(f)]
    groups_data = {
        g: [f for f in flist if _is_csv(f)]
        for g, flist in groups_data.items()
    }

    # Remove empty groups after filtering
    groups_data = {g: flist for g, flist in groups_data.items() if flist}

    # 3) Group filter param (still supported)
    if group and group in groups_data:
        files = groups_data[group]
    elif group:
        # group specified but after CSV filter there are no files
        files = []

    # 4) Build group list
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
        "total_files": len(files),
        "total_groups": len(groups_data),
        "excluded_count": len(excluded),
        "groups": group_list,
        "files": [
            {
                "filename": (f.get("filename") or "").upper(),
                "group": f.get("group", "MISC"),
                "rows": f.get("rows", 0),
                "columns": f.get("columns", 0),
                "file_type": "csv",
                "size": _format_size(f.get("size_bytes", 0)),
            }
            for f in files
        ],
    }

def get_file_preview(session_id: str, user_id: str, filename: str, max_rows: int = 100) -> Dict:
    """
    Preview CSV/XLSX/XLS.
    For XLS, supports BIFF XLS and HTML-as-XLS (common exports).
    """
    meta = get_session_metadata(session_id)
    if meta.get("user_id") and meta.get("user_id") != user_id:
        raise ValueError("Unauthorized")

    sess_dir = get_session_dir(session_id)
    out_dir = sess_dir / "output"
    file_path = _resolve_output_file(out_dir, filename)
    lower = file_path.name.lower()

    headers: List[str] = []
    rows: List[List[str]] = []
    total_rows = 0

    if lower.endswith(".csv"):
        try:
            with open(file_path, "r", encoding="utf-8-sig", newline="") as f:
                reader = csv.DictReader(f)
                headers = list(reader.fieldnames or [])
                for i, row in enumerate(reader):
                    total_rows += 1
                    if i < max_rows:
                        rows.append([_safe_cell_value(row.get(h)) for h in headers])
        except UnicodeDecodeError:
            with open(file_path, "r", encoding="latin-1", newline="") as f:
                reader = csv.DictReader(f)
                headers = list(reader.fieldnames or [])
                for i, row in enumerate(reader):
                    total_rows += 1
                    if i < max_rows:
                        rows.append([_safe_cell_value(row.get(h)) for h in headers])

    elif lower.endswith(".xlsx"):
        try:
            import pandas as pd
            df = pd.read_excel(file_path, nrows=max_rows + 1, engine="openpyxl")
            headers = [str(h) for h in df.columns.tolist()]
            total_rows = len(df)
            for row_num, (idx, r) in enumerate(df.iterrows()):
                if row_num < max_rows:
                    rows.append([_safe_cell_value(r.get(h)) for h in headers])
        except ImportError as e:
            raise RuntimeError("XLSX preview requires pandas + openpyxl") from e
        except Exception as e:
            raise RuntimeError(f"Failed to read XLSX file: {str(e)}") from e

    elif lower.endswith(".xls"):
        try:
            df = _read_xls_like_to_dataframe(file_path).head(max_rows)
            headers = [str(h) for h in df.columns.tolist()]
            total_rows = len(df)
            for _, r in df.iterrows():
                rows.append([_safe_cell_value(r.get(h)) for h in headers])
        except Exception as e:
            raise RuntimeError(f"Failed to preview XLS: {str(e)}") from e

    else:
        raise RuntimeError("Unsupported file type for preview")

    return {
        "filename": file_path.name.upper(),
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
    sess_dir = get_session_dir(session_id)
    meta = get_session_metadata(session_id)
    if meta.get("user_id") and meta.get("user_id") != user_id:
        raise ValueError("Unauthorized")

    out_dir = sess_dir / "output"
    if not out_dir.exists():
        raise FileNotFoundError("No output found")

    index = get_conversion_index(session_id, user_id)
    files = index.get("files", [])
    if groups:
        files = [f for f in files if f.get("group") in groups]
    if not files:
        raise ValueError("No files to download")

    output_format = (output_format or "csv").lower().strip()
    if output_format not in ("csv", "xlsx"):
        output_format = "csv"

    buf = io.BytesIO()

    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for finfo in files:
            fname = (finfo.get("filename") or "").upper()
            fpath = out_dir / fname
            if not fpath.exists():
                continue

            ftype = finfo.get("file_type") or _infer_file_type_from_name(fname)
            logical_path = finfo.get("logical_path") or fname

            if output_format == "xlsx":
                if ftype == "csv":
                    xlsx_bytes = get_xlsx_bytes_from_csv(str(fpath))
                    out_name = (
                        logical_xml_to_output_relpath(logical_path, ".xlsx")
                        if preserve_structure else (Path(fname).stem + ".xlsx")
                    )
                    zf.writestr(out_name, xlsx_bytes)
                else:
                    out_name = _sanitize_path(logical_path) if preserve_structure else fname
                    zf.write(fpath, out_name)
            else:
                if ftype == "csv":
                    out_name = (
                        logical_xml_to_output_relpath(logical_path, ".csv")
                        if preserve_structure else fname
                    )
                    zf.write(fpath, out_name)
                else:
                    out_name = _sanitize_path(logical_path) if preserve_structure else fname
                    zf.write(fpath, out_name)

    ext = "xlsx" if output_format == "xlsx" else "csv"
    zip_name = f"converted_{ext}_{session_id[:8]}.zip"
    return buf.getvalue(), zip_name


def download_single_file(
    session_id: str,
    user_id: str,
    filename: str,
    output_format: str = "csv",
) -> Tuple[bytes, str, str]:
    sess_dir = get_session_dir(session_id)
    meta = get_session_metadata(session_id)
    if meta.get("user_id") and meta.get("user_id") != user_id:
        raise ValueError("Unauthorized")

    out_dir = sess_dir / "output"
    file_path = _resolve_output_file(out_dir, filename)

    ftype = _infer_file_type_from_name(file_path.name)
    output_format = (output_format or "csv").lower().strip()
    if output_format not in ("csv", "xlsx"):
        output_format = "csv"

    if output_format == "xlsx":
        if ftype == "csv":
            xlsx_bytes = get_xlsx_bytes_from_csv(str(file_path))
            out_name = (Path(file_path.name).stem + ".xlsx").upper()
            return xlsx_bytes, out_name, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        if ftype == "xlsx":
            return file_path.read_bytes(), file_path.name.upper(), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        if ftype == "xls":
            return file_path.read_bytes(), file_path.name.upper(), "application/vnd.ms-excel"

    if ftype == "csv":
        return file_path.read_bytes(), file_path.name.upper(), "text/csv"

    return file_path.read_bytes(), file_path.name.upper(), "application/octet-stream"


# ---------------------------------------------------------------------------
# Edit APIs (CSV only)
# ---------------------------------------------------------------------------

def add_row_to_file(session_id: str, user_id: str, filename: str, row: Dict[str, Any]) -> Dict[str, Any]:
    _assert_session_owner(session_id, user_id)
    out_dir = get_session_dir(session_id) / "output"
    file_path = _resolve_output_file(out_dir, filename)

    if file_path.suffix.lower() != ".csv":
        raise ValueError("Row editing is supported only for CSV files")

    headers, rows = _load_csv(file_path)

    new_cols = [c for c in row.keys() if c not in headers]
    if new_cols:
        headers.extend(new_cols)
        for existing in rows:
            for c in new_cols:
                existing.setdefault(c, "")

    rows.append({h: _safe_cell_value(row.get(h)) for h in headers})
    _write_csv(file_path, headers, rows)

    index = refresh_conversion_index(session_id)
    return {"filename": file_path.name.upper(), "rows": len(rows), "columns": len(headers), "index": index}


def add_new_file(session_id: str, user_id: str, filename: str, group: Optional[str], headers: List[str]) -> Dict[str, Any]:
    _assert_session_owner(session_id, user_id)
    if not headers:
        raise ValueError("Headers are required to create a file")

    out_dir = get_session_dir(session_id) / "output"
    out_dir.mkdir(parents=True, exist_ok=True)

    filename = filename.upper()
    if not filename.endswith(".CSV"):
        filename = f"{Path(filename).stem}.CSV"

    file_path = out_dir / filename
    if file_path.exists():
        raise FileExistsError("File already exists")

    _write_csv(file_path, headers, [])
    index = refresh_conversion_index(session_id)

    if group:
        for f in index.get("files", []):
            if f.get("filename") == filename:
                f["group"] = group
        (get_session_dir(session_id) / "conversion_index.json").write_text(json.dumps(index, indent=2))

    return {"filename": filename, "group": group, "headers": headers}


def delete_file(session_id: str, user_id: str, filename: str) -> Dict[str, Any]:
    _assert_session_owner(session_id, user_id)
    out_dir = get_session_dir(session_id) / "output"
    filename_u = filename.upper()

    removed = 0
    for p in (out_dir / filename, out_dir / filename_u, out_dir / unquote(filename), out_dir / unquote(filename).upper()):
        if p.exists():
            p.unlink()
            removed += 1

    stem = Path(filename_u).stem
    for ext in (".CSV", ".XLSX"):
        p = out_dir / f"{stem}{ext}"
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
    file_path = _resolve_output_file(out_dir, filename)

    if file_path.suffix.lower() != ".csv":
        raise ValueError("Cell editing is supported only for CSV files")

    headers, rows = _load_csv(file_path)
    updated = 0

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
