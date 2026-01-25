import zipfile
from pathlib import Path
from dataclasses import dataclass
from typing import Callable, Optional, List
import time
import hashlib

@dataclass
class XmlEntry:
    logical_path: str
    xml_path: Path
    size: int
    filename: str = ""
    stub: str = ""
    
    def __post_init__(self):
        if not self.filename:
            self.filename = Path(self.logical_path).name
        if not self.stub:
            self.stub = self._generate_stub()
    
    def _generate_stub(self):
        """Generate unique stub for this file"""
        hash_val = hashlib.sha1(self.logical_path.encode()).hexdigest()[:16]
        return f"{Path(self.filename).stem}__{hash_val}"


def scan_zip_for_xml(
    zip_path: Path, 
    work_dir: Path, 
    max_depth: int = 50,
    max_files: int = 10000,
    max_ratio: int = 200,
    progress_callback: Optional[Callable[[int, int, int], None]] = None
) -> List[XmlEntry]:
    """
    Scan ZIP file for XML files with progress tracking.
    
    Args:
        zip_path: Path to ZIP file
        work_dir: Working directory for extraction
        max_depth: Maximum nested ZIP depth
        max_files: Maximum XML files to extract
        max_ratio: Maximum compression ratio (security)
        progress_callback: Callback(entries_done, entries_total, xml_found)
    
    Returns:
        List of XmlEntry objects
    """
    results = []
    stack = [(zip_path, "", 0)]
    xml_root = work_dir / "xml_files"
    xml_root.mkdir(parents=True, exist_ok=True)
    
    entries_done = 0
    entries_total = 0
    start_time = time.time()
    
    # First pass: count total entries
    try:
        with zipfile.ZipFile(zip_path) as z:
            entries_total = len([f for f in z.infolist() if not f.is_dir()])
    except:
        pass

    while stack:
        zpath, prefix, depth = stack.pop()
        
        if depth > max_depth:
            continue

        try:
            with zipfile.ZipFile(zpath) as z:
                for zi in z.infolist():
                    if zi.is_dir():
                        continue
                    
                    entries_done += 1
                    
                    # Update progress
                    if progress_callback and entries_done % 10 == 0:
                        progress_callback(entries_done, entries_total, len(results))

                    name = zi.filename
                    logical = f"{prefix}/{name}" if prefix else name
                    lower = name.lower()

                    # Security check: compression ratio
                    if zi.compress_size > 0:
                        ratio = zi.file_size / zi.compress_size
                        if ratio > max_ratio and zi.file_size > 50_000:
                            continue  # Skip suspicious files

                    if lower.endswith(".xml"):
                        # Extract XML file
                        stub = f"{Path(name).stem}__{hashlib.sha1(logical.encode()).hexdigest()[:16]}"
                        out = xml_root / f"{stub}.xml"
                        
                        with z.open(zi) as src:
                            content = src.read()
                            out.write_bytes(content)

                        results.append(
                            XmlEntry(
                                logical_path=logical,
                                xml_path=out,
                                size=zi.file_size,
                                filename=Path(name).name,
                                stub=stub
                            )
                        )
                        
                        # Limit total files
                        if len(results) >= max_files:
                            break

                    elif lower.endswith(".zip") and depth < max_depth:
                        # Extract nested ZIP
                        nested_stub = f"nested_{hashlib.sha1(logical.encode()).hexdigest()[:16]}"
                        nested = work_dir / f"{nested_stub}.zip"
                        
                        with z.open(zi) as src:
                            content = src.read()
                            nested.write_bytes(content)
                        
                        stack.append((nested, logical, depth + 1))
                
                if len(results) >= max_files:
                    break
                    
        except zipfile.BadZipFile:
            continue  # Skip corrupted ZIPs
        except Exception as e:
            print(f"Error scanning {zpath}: {e}")
            continue

    # Final progress update
    if progress_callback:
        progress_callback(entries_done, entries_total, len(results))

    return results


def quick_scan_xml_count(zip_path: Path, max_depth: int = 50) -> dict:
    """
    Quick scan to count XMLs without extracting.
    Returns basic statistics.
    """
    xml_count = 0
    zip_count = 0
    total_size = 0
    
    stack = [(zip_path, 0)]
    
    while stack:
        zpath, depth = stack.pop()
        
        if depth > max_depth:
            continue
        
        try:
            with zipfile.ZipFile(zpath) as z:
                for zi in z.infolist():
                    if zi.is_dir():
                        continue
                    
                    lower = zi.filename.lower()
                    
                    if lower.endswith(".xml"):
                        xml_count += 1
                        total_size += zi.file_size
                    elif lower.endswith(".zip") and depth < max_depth:
                        zip_count += 1
        except:
            pass
    
    return {
        "xml_count": xml_count,
        "nested_zips": zip_count,
        "total_size_mb": round(total_size / (1024 * 1024), 2)
    }
