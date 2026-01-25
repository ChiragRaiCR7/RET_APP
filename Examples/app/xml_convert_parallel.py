from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor
from pathlib import Path
from typing import List, Callable, Optional, Set
import multiprocessing
# Fixed import: use local app package
from app.xml_to_csv import xml_to_csv
from app.zip_scanner import XmlEntry
from app.utils import infer_group


def optimize_workers(avg_mb: float, total_files: int) -> tuple[int, str]:
    """
    Determine optimal number of workers and executor type.
    
    Returns:
        (num_workers, executor_type)  # executor_type: 'thread' or 'process'
    """
    cpu_count = multiprocessing.cpu_count()
    
    # Large files: use fewer process workers
    if avg_mb >= 2.0 and total_files >= 50:
        return (max(2, cpu_count // 2), 'process')
    
    # Very large files: definitely process-based
    if avg_mb >= 10.0:
        return (max(2, cpu_count // 2), 'process')
    
    # Small files: use more thread workers
    if avg_mb < 1.0:
        return (min(32, cpu_count * 4), 'thread')
    
    # Medium files: moderate threading
    return (min(16, cpu_count * 2), 'thread')


def convert_inventory_parallel(
    xml_inventory: List[XmlEntry],
    out_root: Path,
    custom_prefixes: Set[str],
    workers: Optional[int] = None,
    progress_callback: Optional[Callable[[int, int], None]] = None
) -> List[dict]:
    """
    Convert XML inventory to CSV in parallel.
    
    Args:
        xml_inventory: List of XML files to convert
        out_root: Output directory root
        custom_prefixes: Custom group prefixes for organization
        workers: Number of workers (None = auto-detect)
        progress_callback: Callback(files_done, files_total)
    
    Returns:
        List of conversion results with stats
    """
    out_root.mkdir(exist_ok=True, parents=True)
    
    if not xml_inventory:
        return []
    
    # Calculate optimal workers
    total_files = len(xml_inventory)
    total_mb = sum(e.size for e in xml_inventory) / (1024 * 1024)
    avg_mb = total_mb / total_files if total_files > 0 else 0
    
    if workers is None:
        workers, executor_type = optimize_workers(avg_mb, total_files)
    else:
        executor_type = 'process' if avg_mb >= 2.0 else 'thread'
    
    print(f"Using {executor_type} executor with {workers} workers")
    print(f"Processing {total_files} files, avg size: {avg_mb:.2f} MB")
    
    # Choose executor
    Executor = ProcessPoolExecutor if executor_type == 'process' else ThreadPoolExecutor
    
    results = []
    files_done = 0
    
    def convert_task(entry: XmlEntry) -> dict:
        """Task to convert single XML file"""
        return convert_single_xml(entry, out_root, custom_prefixes)
    
    with Executor(max_workers=workers) as executor:
        futures = [executor.submit(convert_task, entry) for entry in xml_inventory]
        
        for future in futures:
            try:
                result = future.result(timeout=300)  # 5 min timeout
                results.append(result)
                files_done += 1
                
                # Update progress
                if progress_callback and files_done % 5 == 0:
                    progress_callback(files_done, total_files)
                    
            except Exception as e:
                results.append({
                    'success': False,
                    'error': str(e),
                    'entry': None
                })
                files_done += 1
    
    # Final progress update
    if progress_callback:
        progress_callback(files_done, total_files)
    
    return results


def convert_single_xml(
    entry: XmlEntry, 
    out_root: Path, 
    custom_prefixes: Set[str]
) -> dict:
    """
    Convert a single XML file to CSV.
    This function runs in a separate process/thread.
    
    Args:
        entry: XML entry to convert
        out_root: Output root directory
        custom_prefixes: Custom group prefixes
    
    Returns:
        Dict with conversion results
    """
    import time
    from pathlib import Path
    
    start_time = time.time()
    
    try:
        # Determine group
        group = infer_group(entry.logical_path, custom_prefixes)
        
        # Create group directory
        group_dir = out_root / group
        group_dir.mkdir(exist_ok=True, parents=True)
        
        # Output path
        csv_path = group_dir / f"{entry.stub}.csv"
        
        # Convert XML to CSV
        success = xml_to_csv(Path(entry.xml_path), csv_path)
        
        if success:
            # Count rows
            try:
                with open(csv_path, 'r', encoding='utf-8') as f:
                    rows = sum(1 for _ in f) - 1  # Subtract header
            except:
                rows = 0
            
            # Get columns
            try:
                with open(csv_path, 'r', encoding='utf-8') as f:
                    import csv as csv_module
                    reader = csv_module.reader(f)
                    headers = next(reader, [])
                    cols = len(headers)
            except:
                cols = 0
            
            return {
                'success': True,
                'group': group,
                'filename': entry.filename,
                'logical_path': entry.logical_path,
                'csv_path': str(csv_path),
                'rows': rows,
                'cols': cols,
                'size_mb': round(entry.size / (1024 * 1024), 2),
                'duration': round(time.time() - start_time, 3),
                'error': None
            }
        else:
            return {
                'success': False,
                'group': group,
                'filename': entry.filename,
                'logical_path': entry.logical_path,
                'error': 'No records found',
                'duration': round(time.time() - start_time, 3)
            }
            
    except Exception as e:
        return {
            'success': False,
            'filename': entry.filename,
            'logical_path': entry.logical_path,
            'error': str(e),
            'duration': round(time.time() - start_time, 3)
        }


def batch_convert_with_stats(
    xml_inventory: List[XmlEntry],
    out_root: Path,
    custom_prefixes: Set[str],
    workers: Optional[int] = None
) -> dict:
    """
    Convert inventory and return detailed statistics.
    
    Returns:
        Dict with comprehensive conversion statistics
    """
    import time
    from collections import Counter
    
    start_time = time.time()
    
    results = convert_inventory_parallel(
        xml_inventory,
        out_root,
        custom_prefixes,
        workers
    )
    
    duration = time.time() - start_time
    
    successful = [r for r in results if r.get('success')]
    errors = [r for r in results if not r.get('success')]
    
    # Group statistics
    group_counts = Counter(r['group'] for r in successful if 'group' in r)
    
    # Row/column statistics
    total_rows = sum(r.get('rows', 0) for r in successful)
    total_cols = sum(r.get('cols', 0) for r in successful)
    
    # Performance statistics
    avg_duration = sum(r.get('duration', 0) for r in results) / len(results) if results else 0
    total_mb = sum(r.get('size_mb', 0) for r in results)
    throughput = total_mb / duration if duration > 0 else 0
    
    return {
        'total_files': len(results),
        'successful': len(successful),
        'errors': len(errors),
        'duration_seconds': round(duration, 2),
        'throughput_mb_per_sec': round(throughput, 2),
        'total_rows': total_rows,
        'avg_cols': round(total_cols / len(successful), 1) if successful else 0,
        'avg_duration_per_file': round(avg_duration, 3),
        'group_counts': dict(group_counts),
        'error_reasons': [r.get('error') for r in errors[:10]],  # First 10 errors
        'results': results
    }
