#!/usr/bin/env python
"""
Comprehensive test script for the RET v4 file upload and conversion workflow.
Tests: scan -> detect groups -> convert -> verify output
"""

import sys
import json
import tempfile
import zipfile
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent))

from api.services.conversion_service import scan_zip_with_groups, convert_session, infer_group
from api.services.storage_service import get_session_dir, cleanup_session


def create_test_xml(content: str) -> bytes:
    """Create a simple XML content"""
    return content.encode('utf-8')


def create_test_zip() -> bytes:
    """Create a test ZIP file with XML files in different groups"""
    with tempfile.NamedTemporaryFile(suffix='.zip', delete=False) as tmp:
        with zipfile.ZipFile(tmp.name, 'w') as z:
            # Add files for different groups
            z.writestr('JOURNAL/article_001.xml', '''<?xml version="1.0"?>
<root>
  <article>
    <title>Test Article</title>
    <author>John Doe</author>
    <year>2025</year>
  </article>
</root>''')
            
            z.writestr('JOURNAL/article_002.xml', '''<?xml version="1.0"?>
<root>
  <article>
    <title>Another Article</title>
    <author>Jane Smith</author>
    <year>2025</year>
  </article>
</root>''')
            
            z.writestr('BOOK/book_001.xml', '''<?xml version="1.0"?>
<root>
  <book>
    <title>Test Book</title>
    <author>Bob Johnson</author>
    <isbn>123456</isbn>
  </book>
</root>''')
            
            z.writestr('DISS/dissertation_001.xml', '''<?xml version="1.0"?>
<root>
  <dissertation>
    <title>PhD Research</title>
    <student>Alice Brown</student>
    <school>University</school>
  </dissertation>
</root>''')
        
        with open(tmp.name, 'rb') as f:
            return f.read()


def test_group_inference():
    """Test group inference logic"""
    print("\n" + "="*60)
    print("TEST 1: Group Inference")
    print("="*60)
    
    test_cases = [
        ("JOURNAL/article_001.xml", "article_001.xml", "JOURNAL"),
        ("BOOK/chapter_1/book_001.xml", "book_001.xml", "BOOK"),
        ("DISS/diss_2025.xml", "diss_2025.xml", "DISS"),
        ("OTHER/some_file.xml", "some_file.xml", "OTHER"),
    ]
    
    for path, filename, expected_group in test_cases:
        result = infer_group(path, filename)
        status = "✓" if result == expected_group else "✗"
        print(f"{status} Path: {path} -> Group: {result} (expected: {expected_group})")
        assert result == expected_group, f"Expected {expected_group}, got {result}"


def test_zip_scan():
    """Test ZIP scanning and group detection"""
    print("\n" + "="*60)
    print("TEST 2: ZIP Scan and Group Detection")
    print("="*60)
    
    zip_data = create_test_zip()
    result = scan_zip_with_groups(zip_data, "test.zip", "test_user")
    
    print(f"✓ Session ID: {result['session_id']}")
    print(f"✓ XML files found: {result['xml_count']}")
    print(f"✓ Groups detected: {result['group_count']}")
    print(f"✓ Groups: {[g['name'] for g in result['groups']]}")
    
    assert result['xml_count'] == 4, f"Expected 4 XML files, got {result['xml_count']}"
    assert result['group_count'] == 3, f"Expected 3 groups, got {result['group_count']}"
    
    group_names = {g['name'] for g in result['groups']}
    expected_groups = {'ARTICLE', 'BOOK', 'DISSERTATION'}
    assert group_names == expected_groups, f"Expected groups {expected_groups}, got {group_names}"
    
    return result['session_id']


def test_conversion(session_id: str):
    """Test conversion of XML to CSV"""
    print("\n" + "="*60)
    print("TEST 3: XML to CSV Conversion")
    print("="*60)
    
    # Convert all files
    result = convert_session(session_id)
    
    print(f"✓ Conversion completed")
    print(f"✓ Success: {result['stats']['success']}")
    print(f"✓ Failed: {result['stats']['failed']}")
    print(f"✓ Total: {result['stats']['total_files']}")
    
    assert result['stats']['success'] == 4, f"Expected 4 successful conversions, got {result['stats']['success']}"
    
    # Verify CSV files exist
    sess_dir = get_session_dir(session_id)
    csv_files = list((sess_dir / 'output').glob('*.csv'))
    print(f"✓ CSV files created: {len(csv_files)}")
    assert len(csv_files) == 4, f"Expected 4 CSV files, got {len(csv_files)}"
    
    # Show file contents
    for csv_file in csv_files:
        lines = csv_file.read_text().split('\n')
        print(f"  - {csv_file.name}: {len(lines)-1} rows (plus header)")


def test_group_filtered_conversion(session_id: str):
    """Test conversion with group filtering"""
    print("\n" + "="*60)
    print("TEST 4: Conversion with Group Filtering")
    print("="*60)
    
    # Create new session with fresh data
    zip_data = create_test_zip()
    result = scan_zip_with_groups(zip_data, "test_filtered.zip", "test_user")
    session_id = result['session_id']
    
    # Convert only ARTICLE group (which has 2 files)
    result = convert_session(session_id, groups=['ARTICLE'])
    
    print(f"✓ ARTICLE group only conversion")
    print(f"✓ Success: {result['stats']['success']}")
    assert result['stats']['success'] == 2, f"Expected 2 ARTICLE files, got {result['stats']['success']}"
    
    return session_id


def test_cleanup(session_id: str):
    """Test session cleanup"""
    print("\n" + "="*60)
    print("TEST 5: Session Cleanup")
    print("="*60)
    
    sess_dir = get_session_dir(session_id)
    assert sess_dir.exists(), "Session directory should exist before cleanup"
    print(f"✓ Session directory exists: {sess_dir}")
    
    cleanup_session(session_id)
    assert not sess_dir.exists(), "Session directory should not exist after cleanup"
    print(f"✓ Session cleaned up successfully")


def main():
    print("\n" + "="*60)
    print("RET v4 FILE UPLOAD & CONVERSION WORKFLOW TEST")
    print("="*60)
    
    try:
        # Test 1: Group inference
        test_group_inference()
        
        # Test 2: ZIP scanning
        session_id = test_zip_scan()
        
        # Test 3: Conversion
        test_conversion(session_id)
        
        # Test 4: Group filtering
        session_id = test_group_filtered_conversion(session_id)
        
        # Test 5: Cleanup
        test_cleanup(session_id)
        
        print("\n" + "="*60)
        print("✓ ALL TESTS PASSED")
        print("="*60)
        return 0
        
    except Exception as e:
        print(f"\n✗ TEST FAILED: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
