#!/usr/bin/env python3
"""
Comprehensive Admin API Test Suite
Tests all admin endpoints to ensure proper functionality
"""

import requests
import json
import time

BASE_URL = "http://localhost:8000"
ADMIN_USERNAME = "admin"
ADMIN_PASSWORD = "admin123"

# Test results
test_results = []
admin_token = None
test_user_id = None

def log_test(name, passed, details=""):
    """Log test result"""
    status = "✅ PASS" if passed else "❌ FAIL"
    test_results.append({"name": name, "passed": passed})
    print(f"{status}: {name}")
    if details:
        print(f"   → {details}")

def login_as_admin():
    """Login and get admin token"""
    global admin_token
    response = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"username": ADMIN_USERNAME, "password": ADMIN_PASSWORD}
    )
    if response.status_code == 200:
        admin_token = response.json().get("access_token")
        log_test("Admin Login", True, f"Token: {admin_token[:20]}...")
        return True
    else:
        log_test("Admin Login", False, f"Status {response.status_code}: {response.text}")
        return False

def get_headers():
    """Get auth headers"""
    return {
        "Authorization": f"Bearer {admin_token}",
        "Content-Type": "application/json"
    }

def test_admin_stats():
    """Test GET /api/admin/stats"""
    response = requests.get(
        f"{BASE_URL}/api/admin/stats",
        headers=get_headers()
    )
    passed = response.status_code == 200
    data = response.json() if passed else {}
    log_test(
        "GET /api/admin/stats",
        passed,
        f"Stats: {data}"
    )
    return passed

def test_list_users():
    """Test GET /api/admin/users"""
    response = requests.get(
        f"{BASE_URL}/api/admin/users",
        headers=get_headers()
    )
    passed = response.status_code == 200
    users = response.json() if passed else []
    log_test(
        "GET /api/admin/users",
        passed,
        f"Found {len(users)} users"
    )
    return passed, users

def test_create_user():
    """Test POST /api/admin/users"""
    global test_user_id
    payload = {
        "username": f"test_user_{int(time.time())}",
        "password": "test_password_123",
        "role": "user"
    }
    response = requests.post(
        f"{BASE_URL}/api/admin/users",
        headers=get_headers(),
        json=payload
    )
    passed = response.status_code == 200
    if passed:
        data = response.json()
        test_user_id = data.get("id")
        log_test(
            "POST /api/admin/users",
            passed,
            f"Created user {payload['username']} (ID: {test_user_id})"
        )
    else:
        log_test(
            "POST /api/admin/users",
            passed,
            f"Status {response.status_code}: {response.text}"
        )
    return passed

def test_get_user():
    """Test GET /api/admin/users/{user_id}"""
    if not test_user_id:
        log_test("GET /api/admin/users/{user_id}", False, "No test user created")
        return False
    
    response = requests.get(
        f"{BASE_URL}/api/admin/users/{test_user_id}",
        headers=get_headers()
    )
    passed = response.status_code == 200
    data = response.json() if passed else {}
    log_test(
        "GET /api/admin/users/{user_id}",
        passed,
        f"User: {data.get('username', 'unknown')}"
    )
    return passed

def test_update_user_role():
    """Test PUT /api/admin/users/{user_id}/role"""
    if not test_user_id:
        log_test("PUT /api/admin/users/{user_id}/role", False, "No test user created")
        return False
    
    payload = {"role": "admin"}
    response = requests.put(
        f"{BASE_URL}/api/admin/users/{test_user_id}/role",
        headers=get_headers(),
        json=payload
    )
    passed = response.status_code == 200
    log_test(
        "PUT /api/admin/users/{user_id}/role",
        passed,
        f"Status {response.status_code}"
    )
    return passed

def test_generate_reset_token():
    """Test POST /api/admin/users/{user_id}/reset-token"""
    # Need to use admin user ID (1) since test user is deleted
    response = requests.post(
        f"{BASE_URL}/api/admin/users/1/reset-token",
        headers=get_headers()
    )
    passed = response.status_code == 200
    data = response.json() if passed else {}
    token = data.get("token", "")
    log_test(
        "POST /api/admin/users/{user_id}/reset-token",
        passed,
        f"Token generated: {token[:20]}..." if token else "No token"
    )
    return passed

def test_list_reset_requests():
    """Test GET /api/admin/reset-requests"""
    response = requests.get(
        f"{BASE_URL}/api/admin/reset-requests",
        headers=get_headers()
    )
    passed = response.status_code == 200
    requests_list = response.json() if passed else []
    log_test(
        "GET /api/admin/reset-requests",
        passed,
        f"Found {len(requests_list)} reset requests"
    )
    return passed

def test_list_sessions():
    """Test GET /api/admin/sessions"""
    response = requests.get(
        f"{BASE_URL}/api/admin/sessions",
        headers=get_headers()
    )
    passed = response.status_code == 200
    sessions = response.json() if passed else []
    log_test(
        "GET /api/admin/sessions",
        passed,
        f"Found {len(sessions)} sessions"
    )
    return passed

def test_cleanup_sessions():
    """Test POST /api/admin/sessions/cleanup"""
    response = requests.post(
        f"{BASE_URL}/api/admin/sessions/cleanup",
        headers=get_headers()
    )
    passed = response.status_code == 200
    data = response.json() if passed else {}
    log_test(
        "POST /api/admin/sessions/cleanup",
        passed,
        f"Deleted {data.get('deleted', 0)} sessions"
    )
    return passed

def test_list_audit_logs():
    """Test GET /api/admin/audit-logs"""
    response = requests.get(
        f"{BASE_URL}/api/admin/audit-logs",
        headers=get_headers()
    )
    passed = response.status_code == 200
    logs = response.json() if passed else []
    log_test(
        "GET /api/admin/audit-logs",
        passed,
        f"Found {len(logs)} audit logs"
    )
    return passed

def test_list_ops_logs():
    """Test GET /api/admin/ops-logs"""
    response = requests.get(
        f"{BASE_URL}/api/admin/ops-logs",
        headers=get_headers()
    )
    passed = response.status_code == 200
    logs = response.json() if passed else []
    log_test(
        "GET /api/admin/ops-logs",
        passed,
        f"Found {len(logs)} ops logs"
    )
    return passed

def test_delete_user():
    """Test DELETE /api/admin/users/{user_id}"""
    if not test_user_id:
        log_test("DELETE /api/admin/users/{user_id}", False, "No test user created")
        return False
    
    response = requests.delete(
        f"{BASE_URL}/api/admin/users/{test_user_id}",
        headers=get_headers()
    )
    passed = response.status_code == 200
    log_test(
        "DELETE /api/admin/users/{user_id}",
        passed,
        f"User {test_user_id} deleted"
    )
    return passed

def main():
    """Run all tests"""
    print("=" * 70)
    print("ADMIN API TEST SUITE")
    print("=" * 70)
    print()
    
    # Authentication
    print("📋 AUTHENTICATION")
    print("-" * 70)
    if not login_as_admin():
        print("\n❌ Cannot proceed without admin authentication")
        return
    print()
    
    # Admin Stats
    print("📊 DASHBOARD STATS")
    print("-" * 70)
    test_admin_stats()
    print()
    
    # User Management
    print("👥 USER MANAGEMENT")
    print("-" * 70)
    test_list_users()
    test_create_user()
    test_get_user()
    test_update_user_role()
    test_delete_user()
    print()
    
    # Password Reset
    print("🔐 PASSWORD RESET")
    print("-" * 70)
    test_generate_reset_token()
    test_list_reset_requests()
    print()
    
    # Session Management
    print("💾 SESSION MANAGEMENT")
    print("-" * 70)
    test_list_sessions()
    test_cleanup_sessions()
    print()
    
    # Logs
    print("📋 AUDIT & OPS LOGS")
    print("-" * 70)
    test_list_audit_logs()
    test_list_ops_logs()
    print()
    
    # Summary
    print("=" * 70)
    passed = sum(1 for r in test_results if r["passed"])
    total = len(test_results)
    percentage = (passed / total * 100) if total > 0 else 0
    
    if passed == total:
        print(f"✅ ALL TESTS PASSED ({passed}/{total} - {percentage:.0f}%)")
    else:
        print(f"⚠️  SOME TESTS FAILED ({passed}/{total} - {percentage:.0f}%)")
        print("\nFailed tests:")
        for r in test_results:
            if not r["passed"]:
                print(f"  ❌ {r['name']}")
    print("=" * 70)

if __name__ == "__main__":
    main()
