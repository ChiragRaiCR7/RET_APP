from pathlib import Path
from typing import Set
import re


def infer_group(logical_path: str, custom_prefixes: Set[str]) -> str:
    """
    Infer group from file path or filename.
    
    Args:
        logical_path: Full logical path in ZIP
        custom_prefixes: Set of custom prefixes to match
    
    Returns:
        Group name (uppercase prefix or "OTHER")
    """
    # Try folder-based grouping first
    folder = folder_of(logical_path)
    if folder != "(root)":
        group = infer_group_from_folder(folder, custom_prefixes)
        if group != "OTHER":
            return group
    
    # Fallback to filename-based grouping
    filename = Path(logical_path).name
    return infer_group_from_filename(filename, custom_prefixes)


def folder_of(path: str) -> str:
    """Extract folder from path"""
    return path.rsplit("/", 1)[0] if "/" in path else "(root)"


def basename_no_ext(name: str) -> str:
    """Get basename without extension"""
    return Path(name).stem


def extract_alpha_prefix(token: str) -> str:
    """Extract leading alphabetic characters from token"""
    out = []
    for ch in token:
        if ch.isalpha():
            out.append(ch)
        else:
            break
    return "".join(out).upper()


def infer_group_from_folder(folder_full: str, custom_prefixes: Set[str]) -> str:
    """Infer group from folder path"""
    if folder_full == "(root)":
        return "(root)"
    
    last_seg = folder_full.split("/")[-1] if "/" in folder_full else folder_full
    token = last_seg.split("_", 1)[0] if "_" in last_seg else last_seg
    alpha_prefix = extract_alpha_prefix(token)
    
    if custom_prefixes:
        return alpha_prefix if alpha_prefix in custom_prefixes else "OTHER"
    return alpha_prefix if alpha_prefix else "OTHER"


def infer_group_from_filename(filename: str, custom_prefixes: Set[str]) -> str:
    """Infer group from filename"""
    base = basename_no_ext(filename)
    token = base.split("_", 1)[0] if "_" in base else base
    alpha_prefix = extract_alpha_prefix(token)
    
    if custom_prefixes:
        return alpha_prefix if alpha_prefix in custom_prefixes else "OTHER"
    return alpha_prefix if alpha_prefix else "OTHER"


def sanitize_zip_entry(path: str) -> str:
    """Sanitize ZIP entry path for security"""
    # Remove leading/trailing slashes and backslashes
    p = path.replace("\\", "/").strip("/")
    
    # Remove dangerous path components
    parts = []
    for part in p.split("/"):
        if part in ("", ".", ".."):
            continue
        parts.append(part)
    
    out = "/".join(parts)
    return out or "file"


def logical_xml_to_output_relpath(logical_path: str, out_ext: str = ".csv") -> str:
    """
    Convert XML logical path to output relative path.
    Preserves directory structure, changes extension.
    """
    lp = sanitize_zip_entry(logical_path)
    
    if lp.lower().endswith(".xml"):
        return lp[:-4] + out_ext
    else:
        # Handle edge case where extension is missing
        base = Path(lp).name
        parent = str(Path(lp).parent).replace("\\", "/")
        stem = Path(base).stem
        
        if parent in ("", "."):
            result = f"{stem}{out_ext}"
        else:
            result = f"{parent}/{stem}{out_ext}"
        
        return sanitize_zip_entry(result)


def format_bytes(bytes_val: float) -> str:
    """Format bytes as human-readable string"""
    for unit in ['B', 'KB', 'MB', 'GB']:
        if bytes_val < 1024:
            return f"{bytes_val:.2f} {unit}"
        bytes_val /= 1024.00
    return f"{bytes_val:.2f} TB"


def format_duration(seconds: float) -> str:
    """Format duration as human-readable string"""
    if seconds < 60:
        return f"{seconds:.1f}s"
    elif seconds < 3600:
        minutes = seconds / 60
        return f"{minutes:.1f}m"
    else:
        hours = seconds / 3600
        return f"{hours:.1f}h"


def safe_filename(filename: str) -> str:
    """Make filename safe for filesystem"""
    # Remove/replace unsafe characters
    safe = re.sub(r'[<>:"/\\|?*]', '_', filename)
    # Remove control characters
    safe = re.sub(r'[\x00-\x1f\x7f]', '', safe)
    # Limit length
    if len(safe) > 255:
        name, ext = Path(safe).stem, Path(safe).suffix
        safe = name[:255-len(ext)] + ext
    return safe or "unnamed"


def validate_zip_path(path: str, base_dir: Path) -> bool:
    """
    Validate that a ZIP entry path doesn't escape base directory.
    Security check against path traversal attacks.
    """
    try:
        full_path = (base_dir / path).resolve()
        return str(full_path).startswith(str(base_dir.resolve()))
    except:
        return False
