#!/usr/bin/env python3
"""
RET-v4 Integration Test Suite
Tests all critical flows and ensures system works end-to-end
"""
import requests
import json
import sys
from pathlib import Path

BASE_URL = "http://localhost:8000"
API_URL = f"{BASE_URL}/api"

class Colors:
    GREEN = '\033[92m'
    RED = '\033[91m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    END = '\033[0m'

def print_test(name, passed, message=""):
    symbol = f"{Colors.GREEN}✅{Colors.END}" if passed else f"{Colors.RED}❌{Colors.END}"
    print(f"{symbol} {name}")
    if message:
        print(f"  {message}")

def test_health():
    """Test health endpoint"""
    try:
        resp = requests.get(f"{BASE_URL}/health", timeout=5)
        passed = resp.status_code == 200
        print_test("Health Check", passed, f"Status: {resp.status_code}")
        return passed
    except Exception as e:
        print_test("Health Check", False, f"Error: {e}")
        return False

def test_login():
    """Test login flow"""
    try:
        resp = requests.post(
            f"{API_URL}/auth/login",
            json={"username": "admin", "password": "admin123"},
            timeout=5
        )
        
        if resp.status_code != 200:
            print_test("Login", False, f"Status: {resp.status_code}")
            return None
        
        data = resp.json()
        token = data.get("access_token")
        print_test("Login", bool(token), f"Token length: {len(token) if token else 0}")
        return token
    except Exception as e:
        print_test("Login", False, f"Error: {e}")
        return None

def test_get_user(token):
    """Test get current user"""
    try:
        resp = requests.get(
            f"{API_URL}/auth/me",
            headers={"Authorization": f"Bearer {token}"},
            timeout=5
        )
        
        passed = resp.status_code == 200
        if passed:
            user = resp.json()
            print_test("Get User", passed, f"Username: {user.get('username')}")
        else:
            print_test("Get User", passed, f"Status: {resp.status_code}")
        
        return passed
    except Exception as e:
        print_test("Get User", False, f"Error: {e}")
        return False

def test_get_users_admin(token):
    """Test list users (admin)"""
    try:
        resp = requests.get(
            f"{API_URL}/admin/users",
            headers={"Authorization": f"Bearer {token}"},
            timeout=5
        )
        
        passed = resp.status_code == 200
        if passed:
            users = resp.json()
            print_test("List Users (Admin)", passed, f"Found: {len(users)} users")
        else:
            print_test("List Users (Admin)", passed, f"Status: {resp.status_code}")
        
        return passed
    except Exception as e:
        print_test("List Users (Admin)", False, f"Error: {e}")
        return False

def test_unauthorized_access():
    """Test that unauthorized access is blocked"""
    try:
        resp = requests.get(
            f"{API_URL}/auth/me",
            timeout=5
        )
        
        passed = resp.status_code == 403 or resp.status_code == 401
        print_test("Unauthorized Access Blocked", passed, f"Status: {resp.status_code}")
        return passed
    except Exception as e:
        print_test("Unauthorized Access Blocked", False, f"Error: {e}")
        return False

def test_invalid_token():
    """Test invalid token rejection"""
    try:
        resp = requests.get(
            f"{API_URL}/auth/me",
            headers={"Authorization": "Bearer invalid_token"},
            timeout=5
        )
        
        passed = resp.status_code == 401
        print_test("Invalid Token Rejection", passed, f"Status: {resp.status_code}")
        return passed
    except Exception as e:
        print_test("Invalid Token Rejection", False, f"Error: {e}")
        return False

def test_password_reset():
    """Test password reset request"""
    try:
        resp = requests.post(
            f"{API_URL}/auth/password-reset/request",
            json={"username": "admin"},
            timeout=5
        )
        
        passed = resp.status_code == 200
        print_test("Password Reset Request", passed, f"Status: {resp.status_code}")
        return passed
    except Exception as e:
        print_test("Password Reset Request", False, f"Error: {e}")
        return False

def test_cors_headers():
    """Test CORS headers"""
    try:
        resp = requests.get(
            f"{BASE_URL}/health",
            headers={
                "Origin": "http://localhost:5173",
                "Access-Control-Request-Method": "GET"
            },
            timeout=5
        )
        
        has_cors = "access-control-allow-origin" in resp.headers
        print_test("CORS Headers", has_cors, f"Has CORS headers: {has_cors}")
        return has_cors
    except Exception as e:
        print_test("CORS Headers", False, f"Error: {e}")
        return False

def main():
    """Run all integration tests"""
    print(f"\n{Colors.BLUE}{'='*60}")
    print("RET-v4 Integration Test Suite")
    print(f"{'='*60}{Colors.END}\n")
    
    print(f"{Colors.BLUE}Basic Connectivity{Colors.END}")
    print("-" * 40)
    
    tests = [
        ("Server Running", lambda: test_health()),
        ("CORS Configured", lambda: test_cors_headers()),
    ]
    
    results = {}
    for name, test_func in tests:
        try:
            results[name] = test_func()
        except Exception as e:
            print_test(name, False, str(e))
            results[name] = False
    
    if not results.get("Server Running"):
        print(f"\n{Colors.RED}❌ Server not running. Start it with: python start.py{Colors.END}\n")
        return 1
    
    print(f"\n{Colors.BLUE}Authentication Flow{Colors.END}")
    print("-" * 40)
    
    token = test_login()
    results["Login"] = token is not None
    
    if token:
        results["Get User"] = test_get_user(token)
        results["List Users (Admin)"] = test_get_users_admin(token)
    
    print(f"\n{Colors.BLUE}Security Tests{Colors.END}")
    print("-" * 40)
    
    results["Unauthorized Access Blocked"] = test_unauthorized_access()
    results["Invalid Token Rejection"] = test_invalid_token()
    
    print(f"\n{Colors.BLUE}Feature Tests{Colors.End}")
    print("-" * 40)
    
    results["Password Reset Request"] = test_password_reset()
    
    # Summary
    print(f"\n{Colors.BLUE}{'='*60}")
    print("Test Summary")
    print(f"{'='*60}{Colors.END}")
    
    passed = sum(1 for v in results.values() if v)
    total = len(results)
    
    for name, result in results.items():
        status = f"{Colors.GREEN}✅{Colors.END}" if result else f"{Colors.RED}❌{Colors.END}"
        print(f"{status} {name}")
    
    print(f"\n{Colors.BLUE}Result: {passed}/{total} tests passed{Colors.END}\n")
    
    if passed == total:
        print(f"{Colors.GREEN}🎉 All integration tests passed!{Colors.END}")
        print(f"System is ready for development/deployment.\n")
        return 0
    else:
        print(f"{Colors.RED}⚠️  Some tests failed.{Colors.END}")
        print(f"Please check the errors above.\n")
        return 1

if __name__ == "__main__":
    try:
        exit_code = main()
        sys.exit(exit_code)
    except KeyboardInterrupt:
        print(f"\n{Colors.YELLOW}Tests interrupted by user.{Colors.END}\n")
        sys.exit(1)
    except Exception as e:
        print(f"\n{Colors.RED}Fatal error: {e}{Colors.END}\n")
        sys.exit(1)
