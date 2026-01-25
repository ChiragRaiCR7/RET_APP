import zipfile
from pathlib import Path

def safe_extract_zip(zip_path: Path, target: Path):
    with zipfile.ZipFile(zip_path) as z:
        for member in z.infolist():
            extracted = target / member.filename
            if not extracted.resolve().startswith(target.resolve()):
                raise ValueError("Zip path traversal detected")
        z.extractall(target)
