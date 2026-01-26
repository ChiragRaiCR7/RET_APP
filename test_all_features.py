#!/usr/bin/env python3
"""
RET v4 Comprehensive API Test Suite
Tests all API endpoints and AI/RAG functionality
"""

import requests
import json
import time
import sys
from pathlib import Path
from typing import Dict, Any, Optional, Tuple
import base64

# ============================================================================
# Configuration
# ============================================================================

API_BASE_URL = "http://localhost:8000/api"
TIMEOUT = 30

# Test credentials (update if different)
TEST_USERNAME = "admin"
TEST_PASSWORD = ""  # Will be prompted or checked from demo users

# Example ZIP location (from Examples folder)
EXAMPLE_ZIP_PATH = Path(r"d:\WORK\RET_App\Examples\BIg_test-examples")
EXAMPLE_XMLS = [
    "journal_article_4.4.2.xml",
    "book_4.4.2.xml",
    "dissertation_4.4.2.xml",
]

# ============================================================================
# Test Results Tracking
# ============================================================================

class TestResults:
    def __init__(self):
        self.total = 0
        self.passed = 0
        self.failed = 0
        self.errors = []
    
    def add_pass(self, test_name: str):
        self.passed += 1
        self.total += 1
        print(f"  ✅ {test_name}")
    
    def add_fail(self, test_name: str, reason: str):
        self.failed += 1
        self.total += 1
        print(f"  ❌ {test_name}: {reason}")
        self.errors.append(f"{test_name}: {reason}")
    
    def print_summary(self):
        print("\n" + "="*70)
        print(f"SUMMARY: {self.passed}/{self.total} tests passed")
        print("="*70)
        if self.failed > 0:
            print("\nFailed tests:")
            for error in self.errors:
                print(f"  - {error}")
        print()

# ============================================================================
# Helper Functions
# ============================================================================

def print_header(text: str):
    print(f"\n{'='*70}")
    print(f"  {text}")
    print('='*70)

def print_section(text: str):
    print(f"\n{text}")
    print("-" * len(text))

def log_request(method: str, endpoint: str, data: Optional[Dict] = None):
    """Log API request details"""
    print(f"\n  → {method} {API_BASE_URL}{endpoint}")
    if data:
        print(f"    Payload: {json.dumps(data, indent=2)[:200]}...")

def log_response(response: requests.Response, success: bool = True):
    """Log API response"""
    status = "✓" if success else "✗"
    print(f"  {status} Status: {response.status_code}")
    try:
        data = response.json()
        print(f"    Response: {json.dumps(data, indent=2)[:300]}...")
        return data
    except:
        print(f"    Response: {response.text[:200]}...")
        return None

def save_token(token: str, filepath: str = ".test_token"):
    """Save token to file for reuse"""
    Path(filepath).write_text(token)

def load_token(filepath: str = ".test_token") -> Optional[str]:
    """Load token from file"""
    try:
        return Path(filepath).read_text().strip()
    except:
        return None

# ============================================================================
# Test: Health & System
# ============================================================================

def test_health():
    """Test 1: Backend health check"""
    print_section("Test 1: Backend Health Check")
    
    try:
        response = requests.get(f"http://localhost:8000/health", timeout=TIMEOUT)
        if response.status_code == 200:
            data = response.json()
            if data.get("status") == "ok":
                print(f"  ✅ Backend is healthy: {data}")
                return True
            else:
                print(f"  ❌ Unexpected response: {data}")
                return False
    except requests.exceptions.ConnectionError:
        print(f"  ❌ Cannot connect to backend at {API_BASE_URL}")
        print(f"     Please ensure backend is running: uvicorn api.main:app --reload")
        return False
    except Exception as e:
        print(f"  ❌ Error: {e}")
        return False

# ============================================================================
# Test: Authentication
# ============================================================================

def test_login() -> Tuple[bool, Optional[Dict]]:
    """Test 2: Login and get tokens"""
    print_section("Test 2: Authentication - Login")
    
    if not TEST_PASSWORD:
        print("  ⚠️  Password not configured. Skipping login test.")
        print("     To run: Set TEST_PASSWORD in script or use demo user credentials")
        return False, None
    
    login_data = {
        "username": TEST_USERNAME,
        "password": TEST_PASSWORD,
    }
    
    log_request("POST", "/auth/login", login_data)
    
    try:
        response = requests.post(
            f"{API_BASE_URL}/auth/login",
            json=login_data,
            timeout=TIMEOUT
        )
        
        if response.status_code == 200:
            data = log_response(response, True)
            if data and "access_token" in data:
                token = data["access_token"]
                save_token(token)
                print(f"  ✅ Login successful, token saved")
                return True, data
            else:
                print(f"  ❌ No access_token in response")
                return False, None
        else:
            log_response(response, False)
            print(f"  ❌ Login failed with status {response.status_code}")
            return False, None
    except Exception as e:
        print(f"  ❌ Exception: {e}")
        return False, None

def test_get_me(token: str) -> bool:
    """Test 3: Get current user info"""
    print_section("Test 3: Get Current User (/me)")
    
    headers = {"Authorization": f"Bearer {token}"}
    
    log_request("GET", "/auth/me")
    
    try:
        response = requests.get(
            f"{API_BASE_URL}/auth/me",
            headers=headers,
            timeout=TIMEOUT
        )
        
        if response.status_code == 200:
            data = log_response(response, True)
            if data and "username" in data:
                print(f"  ✅ Got user info: {data.get('username')}")
                return True
            else:
                print(f"  ❌ No username in response")
                return False
        else:
            log_response(response, False)
            return False
    except Exception as e:
        print(f"  ❌ Exception: {e}")
        return False

# ============================================================================
# Test: File Upload & Conversion
# ============================================================================

def test_zip_scan(token: str, xml_file_name: str) -> Tuple[bool, Optional[Dict]]:
    """Test 4: Upload and scan ZIP file"""
    print_section(f"Test 4: ZIP Scan - {xml_file_name}")
    
    # Find the example file
    example_file = EXAMPLE_ZIP_PATH / xml_file_name
    
    if not example_file.exists():
        # Try to find it in Examples/app
        example_file = Path(r"d:\WORK\RET_App\Examples\app") / xml_file_name
    
    if not example_file.exists():
        print(f"  ❌ Example file not found: {xml_file_name}")
        print(f"     Searched: {EXAMPLE_ZIP_PATH}")
        return False, None
    
    headers = {"Authorization": f"Bearer {token}"}
    
    print(f"  Using file: {example_file}")
    print(f"  File size: {example_file.stat().st_size} bytes")
    
    try:
        with open(example_file, "rb") as f:
            files = {"file": (example_file.name, f, "application/xml")}
            log_request("POST", "/conversion/scan")
            
            response = requests.post(
                f"{API_BASE_URL}/conversion/scan",
                headers=headers,
                files=files,
                timeout=TIMEOUT
            )
        
        if response.status_code == 200:
            data = log_response(response, True)
            if data and "session_id" in data:
                print(f"  ✅ ZIP scan successful, session created")
                return True, data
            else:
                print(f"  ❌ No session_id in response")
                return False, None
        else:
            log_response(response, False)
            print(f"  ❌ Scan failed with status {response.status_code}")
            return False, None
    except Exception as e:
        print(f"  ❌ Exception: {e}")
        return False, None

def test_conversion(token: str, session_id: str, groups: list) -> Tuple[bool, Optional[str]]:
    """Test 5: Convert XML to CSV"""
    print_section(f"Test 5: XML to CSV Conversion - Groups: {groups}")
    
    headers = {"Authorization": f"Bearer {token}"}
    
    conversion_data = {
        "session_id": session_id,
        "groups": groups,
        "output_format": "csv",
    }
    
    log_request("POST", "/conversion/convert", conversion_data)
    
    try:
        response = requests.post(
            f"{API_BASE_URL}/conversion/convert",
            headers=headers,
            json=conversion_data,
            timeout=TIMEOUT
        )
        
        if response.status_code == 200:
            data = log_response(response, True)
            if data and "job_id" in data:
                job_id = data["job_id"]
                print(f"  ✅ Conversion job created: {job_id}")
                return True, job_id
            else:
                print(f"  ❌ No job_id in response")
                return False, None
        else:
            log_response(response, False)
            return False, None
    except Exception as e:
        print(f"  ❌ Exception: {e}")
        return False, None

def test_job_status(token: str, job_id: str) -> Tuple[bool, Optional[Dict]]:
    """Test 6: Check job status"""
    print_section(f"Test 6: Job Status - Job ID: {job_id}")
    
    headers = {"Authorization": f"Bearer {token}"}
    
    log_request("GET", f"/jobs/{job_id}")
    
    # Try multiple times with delay for async job completion
    max_attempts = 10
    for attempt in range(max_attempts):
        try:
            response = requests.get(
                f"{API_BASE_URL}/jobs/{job_id}",
                headers=headers,
                timeout=TIMEOUT
            )
            
            if response.status_code == 200:
                data = log_response(response, True)
                status = data.get("status") if data else "unknown"
                
                if status == "completed":
                    print(f"  ✅ Job completed successfully")
                    return True, data
                elif status == "failed":
                    print(f"  ❌ Job failed: {data.get('error')}")
                    return False, data
                else:
                    print(f"  ⏳ Job status: {status} (attempt {attempt+1}/{max_attempts})")
                    time.sleep(2)
            else:
                log_response(response, False)
                return False, None
        except Exception as e:
            print(f"  ❌ Exception: {e}")
            return False, None
    
    print(f"  ⏱️  Job did not complete within {max_attempts*2} seconds")
    return False, None

# ============================================================================
# Test: Comparison
# ============================================================================

def test_file_comparison(token: str) -> bool:
    """Test 7: Compare two CSV files"""
    print_section("Test 7: File Comparison")
    
    headers = {"Authorization": f"Bearer {token}"}
    
    # Create sample CSV data
    csv1 = "id,name,age\n1,John,30\n2,Jane,28"
    csv2 = "id,name,age\n1,John,31\n2,Jane,28\n3,Bob,35"
    
    print(f"  File A:\n{csv1}")
    print(f"  File B:\n{csv2}")
    
    try:
        files = {
            "sideA": ("file_a.csv", csv1.encode(), "text/csv"),
            "sideB": ("file_b.csv", csv2.encode(), "text/csv"),
        }
        
        log_request("POST", "/comparison/run")
        
        response = requests.post(
            f"{API_BASE_URL}/comparison/run",
            headers=headers,
            files=files,
            timeout=TIMEOUT
        )
        
        if response.status_code == 200:
            data = log_response(response, True)
            if data and "similarity_percentage" in data:
                print(f"  ✅ Comparison successful: {data['similarity_percentage']}% similar")
                print(f"     - Added rows: {data.get('added_rows', 0)}")
                print(f"     - Modified rows: {data.get('modified_rows', 0)}")
                return True
            else:
                print(f"  ❌ Missing expected fields in response")
                return False
        else:
            log_response(response, False)
            return False
    except Exception as e:
        print(f"  ❌ Exception: {e}")
        return False

# ============================================================================
# Test: AI & RAG
# ============================================================================

def test_ai_index(token: str, session_id: str, groups: list) -> Tuple[bool, Optional[Dict]]:
    """Test 8: Index groups to Chroma DB"""
    print_section(f"Test 8: AI Indexing to Chroma DB - Groups: {groups}")
    
    headers = {"Authorization": f"Bearer {token}"}
    
    index_data = {
        "session_id": session_id,
        "groups": groups,
    }
    
    log_request("POST", "/ai/index", index_data)
    
    try:
        response = requests.post(
            f"{API_BASE_URL}/ai/index",
            headers=headers,
            json=index_data,
            timeout=60  # Indexing can take longer
        )
        
        if response.status_code == 200:
            data = log_response(response, True)
            if data and "indexed_groups" in data:
                print(f"  ✅ Indexing successful")
                print(f"     - Indexed groups: {data.get('indexed_groups')}")
                print(f"     - Total documents: {data.get('message')}")
                return True, data
            else:
                print(f"  ❌ Missing expected fields in response")
                return False, None
        else:
            log_response(response, False)
            if response.status_code == 404:
                print(f"  ℹ️  /ai/index endpoint not found. Ensure backend is updated.")
            return False, None
    except requests.exceptions.Timeout:
        print(f"  ⏱️  Indexing timeout (>60s). Large dataset might need more time.")
        return False, None
    except Exception as e:
        print(f"  ❌ Exception: {e}")
        return False, None

def test_ai_chat(token: str, session_id: str, question: str) -> Tuple[bool, Optional[Dict]]:
    """Test 9: Chat with AI using RAG"""
    print_section(f"Test 9: AI Chat with RAG")
    
    headers = {"Authorization": f"Bearer {token}"}
    
    chat_data = {
        "session_id": session_id,
        "question": question,
    }
    
    print(f"  Question: {question}")
    log_request("POST", "/ai/chat", chat_data)
    
    try:
        response = requests.post(
            f"{API_BASE_URL}/ai/chat",
            headers=headers,
            json=chat_data,
            timeout=60
        )
        
        if response.status_code == 200:
            data = log_response(response, True)
            if data and "answer" in data:
                print(f"  ✅ AI chat successful")
                print(f"     Answer: {data.get('answer', '')[:300]}...")
                if "citations" in data:
                    print(f"     Citations: {len(data['citations'])} sources")
                return True, data
            else:
                print(f"  ❌ Missing expected fields in response")
                return False, None
        else:
            log_response(response, False)
            if response.status_code == 404:
                print(f"  ℹ️  /ai/chat endpoint not found. Ensure backend is updated.")
            return False, None
    except Exception as e:
        print(f"  ❌ Exception: {e}")
        return False, None

def test_ai_clear_memory(token: str, session_id: str) -> bool:
    """Test 10: Clear AI session memory"""
    print_section(f"Test 10: Clear AI Session Memory")
    
    headers = {"Authorization": f"Bearer {token}"}
    
    log_request("POST", f"/ai/clear/{session_id}")
    
    try:
        response = requests.post(
            f"{API_BASE_URL}/ai/clear/{session_id}",
            headers=headers,
            timeout=TIMEOUT
        )
        
        if response.status_code == 200:
            data = log_response(response, True)
            print(f"  ✅ Memory cleared successfully")
            return True
        else:
            log_response(response, False)
            if response.status_code == 404:
                print(f"  ℹ️  /ai/clear endpoint not found or session doesn't exist")
            return False
    except Exception as e:
        print(f"  ❌ Exception: {e}")
        return False

# ============================================================================
# Test: Admin Features
# ============================================================================

def test_admin_features(token: str) -> bool:
    """Test 11: Admin panel access"""
    print_section("Test 11: Admin Features")
    
    headers = {"Authorization": f"Bearer {token}"}
    
    log_request("GET", "/admin/users")
    
    try:
        response = requests.get(
            f"{API_BASE_URL}/admin/users",
            headers=headers,
            timeout=TIMEOUT
        )
        
        if response.status_code == 200:
            data = log_response(response, True)
            print(f"  ✅ Admin endpoint accessible")
            return True
        elif response.status_code == 403:
            print(f"  ℹ️  User is not an admin (403 Forbidden) - Expected for non-admin")
            return True
        else:
            log_response(response, False)
            return False
    except Exception as e:
        print(f"  ❌ Exception: {e}")
        return False

# ============================================================================
# Main Test Runner
# ============================================================================

def main():
    print_header("RET v4 Comprehensive API Test Suite")
    print(f"API Base URL: {API_BASE_URL}")
    print(f"Timestamp: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    
    results = TestResults()
    
    # Test 1: Health
    if not test_health():
        print("\n❌ Backend is not running. Please start it first:")
        print("   cd backend")
        print("   .venv\\Scripts\\Activate.ps1")
        print("   uvicorn api.main:app --reload")
        sys.exit(1)
    results.add_pass("Backend health check")
    
    # Test 2-3: Authentication
    login_success, login_data = test_login()
    if login_success and login_data:
        token = login_data["access_token"]
        results.add_pass("Login")
        
        if test_get_me(token):
            results.add_pass("Get current user")
        else:
            results.add_fail("Get current user", "Failed to fetch user info")
    else:
        token = load_token()
        if token:
            print(f"\n✅ Using saved token from previous run")
            results.add_pass("Using cached token")
        else:
            print("\n❌ Login required. Provide credentials:")
            print("   Set TEST_PASSWORD in script or create demo users:")
            print("   python scripts/demo_users.py")
            sys.exit(1)
    
    # Test 4-6: File Upload & Conversion
    scan_success, scan_data = test_zip_scan(token, EXAMPLE_XMLS[0])
    if scan_success and scan_data:
        results.add_pass("ZIP file scan")
        session_id = scan_data["session_id"]
        groups = [g["name"] for g in scan_data.get("groups", [])][:2]  # Use first 2 groups
        
        if groups:
            conv_success, job_id = test_conversion(token, session_id, groups)
            if conv_success:
                results.add_pass("Start conversion job")
                
                if job_id:
                    if test_job_status(token, job_id):
                        results.add_pass("Check job status")
                    else:
                        results.add_fail("Check job status", "Job did not complete")
            else:
                results.add_fail("Start conversion job", "Job creation failed")
        else:
            print("\n⚠️  No groups detected in scan. AI testing may be limited.")
    else:
        results.add_fail("ZIP file scan", "Scan failed")
        session_id = None
    
    # Test 7: Comparison
    if test_file_comparison(token):
        results.add_pass("File comparison")
    else:
        results.add_fail("File comparison", "Comparison failed")
    
    # Test 8-10: AI & RAG
    if scan_success and scan_data and session_id:
        groups = [g["name"] for g in scan_data.get("groups", [])][:1]  # Use first group
        
        if groups:
            ai_success, index_data = test_ai_index(token, session_id, groups)
            if ai_success:
                results.add_pass("AI indexing to Chroma DB")
                
                # Test AI chat with sample questions
                sample_questions = [
                    "What is the main content?",
                    "What are the key elements in the data?",
                ]
                
                for question in sample_questions:
                    if test_ai_chat(token, session_id, question):
                        results.add_pass(f"AI chat: '{question[:30]}...'")
                    else:
                        results.add_fail(f"AI chat: '{question[:30]}...'", "Chat failed")
                        break
                
                # Test clear memory
                if test_ai_clear_memory(token, session_id):
                    results.add_pass("Clear AI session memory")
                else:
                    results.add_fail("Clear AI session memory", "Clear failed")
            else:
                results.add_fail("AI indexing to Chroma DB", "Indexing failed or endpoint not available")
        else:
            print("\n⚠️  No groups available for AI testing")
    else:
        print("\n⚠️  Session not available for AI testing")
    
    # Test 11: Admin
    if test_admin_features(token):
        results.add_pass("Admin features access")
    else:
        results.add_fail("Admin features access", "Admin endpoint failed")
    
    # Summary
    results.print_summary()
    
    # Return exit code based on results
    if results.failed == 0:
        print("✅ All tests passed!")
        sys.exit(0)
    else:
        print(f"❌ {results.failed} test(s) failed")
        sys.exit(1)

if __name__ == "__main__":
    main()
