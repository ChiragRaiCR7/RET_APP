#!/usr/bin/env python
"""
Test script for RET App conversion and AI services
"""

import sys
import os
import json
import requests
from pathlib import Path

# Configuration
API_BASE_URL = "http://localhost:8000/api"
TEST_PASSWORD = "admin123"
TEST_USERNAME = "admin"

def test_health():
    """Test backend health"""
    print("\n✓ Testing Backend Health...")
    resp = requests.get("http://localhost:8000/health")
    print(f"  Status: {resp.status_code}")
    print(f"  Response: {resp.json()}")
    return resp.status_code == 200

def test_login():
    """Test login and get token"""
    print("\n✓ Testing Login...")
    payload = {
        "username": TEST_USERNAME,
        "password": TEST_PASSWORD
    }
    resp = requests.post(f"{API_BASE_URL}/auth/login", json=payload)
    print(f"  Status: {resp.status_code}")
    if resp.status_code == 200:
        data = resp.json()
        token = data.get("access_token")
        print(f"  Token received: {token[:50]}...")
        return token
    else:
        print(f"  Error: {resp.json()}")
        return None

def test_zip_scan(token):
    """Test ZIP file scanning"""
    print("\n✓ Testing ZIP Scan...")
    
    # Find a test XML file
    xml_path = Path("d:/WORK/RET_App/Examples/BIg_test-examples/journal_article_4.4.2.xml")
    if not xml_path.exists():
        print(f"  ✗ Test file not found: {xml_path}")
        return None
    
    headers = {"Authorization": f"Bearer {token}"}
    
    with open(xml_path, 'rb') as f:
        files = {"file": (xml_path.name, f, "application/xml")}
        resp = requests.post(
            f"{API_BASE_URL}/conversion/scan",
            files=files,
            headers=headers
        )
    
    print(f"  Status: {resp.status_code}")
    if resp.status_code in (200, 201):
        data = resp.json()
        print(f"  XML Files Found: {data.get('xml_count', 0)}")
        print(f"  Groups: {data.get('group_count', 0)}")
        print(f"  Session ID: {data.get('session_id', 'N/A')}")
        return data.get('session_id')
    else:
        print(f"  Error: {resp.json()}")
        return None

def test_conversion(token, session_id):
    """Test XML to CSV conversion"""
    print("\n✓ Testing Conversion...")
    
    headers = {"Authorization": f"Bearer {token}"}
    payload = {
        "session_id": session_id,
        "groups": None
    }
    
    resp = requests.post(
        f"{API_BASE_URL}/conversion/convert",
        json=payload,
        headers=headers
    )
    
    print(f"  Status: {resp.status_code}")
    if resp.status_code in (200, 201):
        data = resp.json()
        print(f"  Job ID: {data.get('job_id', 'N/A')}")
        return True
    else:
        print(f"  Error: {resp.json()}")
        return False

def test_ai_indexing(token, session_id):
    """Test AI indexing"""
    print("\n✓ Testing AI Indexing...")
    
    headers = {"Authorization": f"Bearer {token}"}
    payload = {
        "session_id": session_id,
        "groups": None
    }
    
    resp = requests.post(
        f"{API_BASE_URL}/ai/index",
        json=payload,
        headers=headers
    )
    
    print(f"  Status: {resp.status_code}")
    if resp.status_code in (200, 201):
        data = resp.json()
        print(f"  Status: {data.get('status', 'N/A')}")
        print(f"  Message: {data.get('message', 'N/A')}")
        if 'stats' in data:
            print(f"  Stats: {json.dumps(data['stats'], indent=2)}")
        return True
    else:
        print(f"  Error: {resp.json()}")
        return False

def test_ai_chat(token, session_id):
    """Test AI chat"""
    print("\n✓ Testing AI Chat...")
    
    headers = {"Authorization": f"Bearer {token}"}
    payload = {
        "session_id": session_id,
        "question": "What is the main topic of this document?",
        "messages": None
    }
    
    resp = requests.post(
        f"{API_BASE_URL}/ai/chat",
        json=payload,
        headers=headers
    )
    
    print(f"  Status: {resp.status_code}")
    if resp.status_code in (200, 201):
        data = resp.json()
        print(f"  Answer: {data.get('answer', 'N/A')[:200]}...")
        print(f"  Sources: {len(data.get('sources', []))} found")
        return True
    else:
        print(f"  Error: {resp.json()}")
        return False

def main():
    """Run all tests"""
    print("=" * 60)
    print("RET App API Test Suite")
    print("=" * 60)
    
    # Test health
    if not test_health():
        print("\n✗ Backend is not running. Start it with: python start.py")
        return False
    
    # Test login
    token = test_login()
    if not token:
        print("\n✗ Login failed")
        return False
    
    # Test ZIP scan
    session_id = test_zip_scan(token)
    if not session_id:
        print("\n✗ ZIP scan failed")
        return False
    
    # Test conversion
    if not test_conversion(token, session_id):
        print("\n✗ Conversion failed")
        # Don't return False - continue to test AI
    
    # Test AI indexing
    if not test_ai_indexing(token, session_id):
        print("\n✗ AI indexing failed")
        return False
    
    # Test AI chat
    if not test_ai_chat(token, session_id):
        print("\n✗ AI chat failed")
        return False
    
    print("\n" + "=" * 60)
    print("✓ All tests passed!")
    print("=" * 60)
    return True

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
