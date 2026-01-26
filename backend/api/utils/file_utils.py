import zipfile
from pathlib import Path

def safe_extract_zip(zip_path: Path, target: Path):
    """Safely extract ZIP file with path traversal protection"""
    target_resolve = target.resolve()
    
    with zipfile.ZipFile(zip_path) as z:
        for member in z.infolist():
            extracted = (target / member.filename).resolve()
            # Check if extracted path is within target directory
            try:
                extracted.relative_to(target_resolve)
            except ValueError:
                raise ValueError(f"Zip path traversal detected: {member.filename}")
        z.extractall(target)

