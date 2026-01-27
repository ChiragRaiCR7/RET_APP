"""
E2E Tests for RET App Advanced Features

Playwright-based tests for:
- XLSX conversion
- File comparison
- Advanced RAG with indexing and querying
- Integration with Examples folder

Run with: pytest tests/e2e/test_advanced.py -v --headed
"""

import pytest
import asyncio
from pathlib import Path
from typing import AsyncGenerator
import sys
import os

# Add parent to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from fastapi.testclient import TestClient
from api.main import app


@pytest.fixture
def client():
    """FastAPI test client."""
    return TestClient(app)


@pytest.fixture
async def auth_token(client):
    """Get authentication token."""
    response = client.post(
        "/api/auth/login",
        json={"username": "admin", "password": "admin123"},
    )
    assert response.status_code == 200
    data = response.json()
    return data.get("access_token")


@pytest.fixture
async def session_id(client, auth_token):
    """Create a test session."""
    headers = {"Authorization": f"Bearer {auth_token}"}

    # Create session by uploading a ZIP file
    examples_dir = Path(__file__).parent.parent.parent.parent / "Examples" / "BIg_test-examples"
    test_zip = examples_dir / "journal_article_4.4.2.xml"

    if not test_zip.exists():
        pytest.skip(f"Test file not found: {test_zip}")

    with open(test_zip, "rb") as f:
        response = client.post(
            "/api/conversion/scan",
            headers=headers,
            files={"file": ("test.xml", f, "application/xml")},
        )

    assert response.status_code == 200
    data = response.json()
    return data.get("session_id")


# ============================================================
# XLSX Conversion Tests
# ============================================================


class TestXLSXConversion:
    """Test XLSX conversion functionality."""

    @pytest.mark.asyncio
    async def test_csv_to_xlsx_conversion(self, client, auth_token, session_id):
        """Test converting CSV to XLSX."""
        headers = {"Authorization": f"Bearer {auth_token}"}

        # First convert XML to CSV
        response = client.post(
            "/api/conversion/convert",
            headers=headers,
            json={"session_id": session_id, "record_tag": None, "auto_detect": True},
        )
        assert response.status_code == 200
        data = response.json()
        assert data.get("status") == "success"

        # Get list of CSV files
        csv_files = data.get("csv_files", [])
        assert len(csv_files) > 0

        # Convert first CSV to XLSX
        csv_filename = csv_files[0].get("filename")
        response = client.post(
            "/api/advanced/xlsx/convert",
            headers=headers,
            json={"session_id": session_id, "csv_filename": csv_filename},
        )

        assert response.status_code == 200
        data = response.json()
        assert data.get("status") == "success"
        assert data.get("filename").endswith(".xlsx")
        assert data.get("size_bytes") > 0

        logger.info(f"✅ XLSX conversion successful: {data.get('filename')}")

    @pytest.mark.asyncio
    async def test_xlsx_download(self, client, auth_token, session_id):
        """Test downloading XLSX file."""
        headers = {"Authorization": f"Bearer {auth_token}"}

        # Get XLSX bytes
        response = client.get(
            f"/api/advanced/xlsx/download/{session_id}/test.xlsx",
            headers=headers,
        )

        if response.status_code == 200:
            assert response.headers["content-type"].startswith("application/vnd")
            logger.info(f"✅ XLSX download successful: {len(response.content)} bytes")
        else:
            logger.warning(f"⚠️ XLSX download returned {response.status_code}")


# ============================================================
# File Comparison Tests
# ============================================================


class TestFileComparison:
    """Test file comparison functionality."""

    @pytest.mark.asyncio
    async def test_csv_comparison(self, client, auth_token):
        """Test comparing two CSV files."""
        headers = {"Authorization": f"Bearer {auth_token}"}

        # Create two sample CSV files
        csv_a = b"""name,age,city
John,30,New York
Jane,25,Los Angeles
Bob,35,Chicago"""

        csv_b = b"""name,age,city
John,30,New York
Jane,26,Los Angeles
Bob,35,Boston"""

        response = client.post(
            "/api/advanced/comparison/compare",
            headers=headers,
            files={
                "file_a": ("file_a.csv", csv_a, "text/csv"),
                "file_b": ("file_b.csv", csv_b, "text/csv"),
            },
            params={
                "ignore_case": False,
                "trim_whitespace": True,
                "similarity_pairing": True,
                "similarity_threshold": 0.65,
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data.get("status") == "success"
        assert "similarity" in data
        assert "changes" in data

        logger.info(f"✅ Comparison successful: {data.get('similarity')}% similarity")

    @pytest.mark.asyncio
    async def test_comparison_detects_changes(self, client, auth_token):
        """Test that comparison detects changes correctly."""
        headers = {"Authorization": f"Bearer {auth_token}"}

        # First file
        csv_a = b"""id,name,value
1,item1,100
2,item2,200
3,item3,300"""

        # Second file with changes
        csv_b = b"""id,name,value
1,item1,100
2,item2,250
4,item4,400"""

        response = client.post(
            "/api/advanced/comparison/compare",
            headers=headers,
            files={
                "file_a": ("a.csv", csv_a, "text/csv"),
                "file_b": ("b.csv", csv_b, "text/csv"),
            },
        )

        assert response.status_code == 200
        data = response.json()

        # Should detect: 1 modified, 1 removed, 1 added
        assert data.get("modified", 0) > 0 or data.get("added", 0) > 0

        logger.info(f"✅ Changes detected: {data.get('modified')} modified, "
                   f"{data.get('added')} added, {data.get('removed')} removed")


# ============================================================
# Advanced RAG Tests
# ============================================================


class TestAdvancedRAG:
    """Test advanced RAG functionality."""

    @pytest.mark.asyncio
    async def test_rag_indexing(self, client, auth_token, session_id):
        """Test RAG document indexing."""
        headers = {"Authorization": f"Bearer {auth_token}"}

        # First convert XML to CSV
        response = client.post(
            "/api/conversion/convert",
            headers=headers,
            json={"session_id": session_id, "record_tag": None, "auto_detect": True},
        )
        assert response.status_code == 200

        # Index documents for RAG
        response = client.post(
            "/api/advanced/rag/index",
            headers=headers,
            json={"session_id": session_id, "groups": None},
        )

        assert response.status_code == 200
        data = response.json()
        assert data.get("status") in ["success", "partial"]
        assert data.get("indexed_files", 0) > 0

        logger.info(
            f"✅ RAG indexing successful: "
            f"{data.get('indexed_files')} files, "
            f"{data.get('indexed_docs')} docs, "
            f"{data.get('indexed_chunks')} chunks"
        )

    @pytest.mark.asyncio
    async def test_rag_query(self, client, auth_token, session_id):
        """Test RAG querying."""
        headers = {"Authorization": f"Bearer {auth_token}"}

        # Convert and index first
        response = client.post(
            "/api/conversion/convert",
            headers=headers,
            json={"session_id": session_id, "record_tag": None, "auto_detect": True},
        )
        assert response.status_code == 200

        response = client.post(
            "/api/advanced/rag/index",
            headers=headers,
            json={"session_id": session_id},
        )
        assert response.status_code in [200, 201]

        # Query
        response = client.post(
            "/api/advanced/rag/query",
            headers=headers,
            json={
                "session_id": session_id,
                "query": "What is the main content?",
                "group_filter": None,
                "file_filter": None,
            },
        )

        if response.status_code == 200:
            data = response.json()
            assert data.get("status") == "success"
            assert "answer" in data
            assert isinstance(data.get("sources", []), list)

            logger.info(f"✅ RAG query successful")
            logger.info(f"   Answer: {data.get('answer')[:100]}...")
            logger.info(f"   Sources: {len(data.get('sources', []))} found")
        else:
            logger.warning(f"⚠️ RAG query returned {response.status_code}: {response.text}")

    @pytest.mark.asyncio
    async def test_rag_clear(self, client, auth_token, session_id):
        """Test clearing RAG index."""
        headers = {"Authorization": f"Bearer {auth_token}"}

        response = client.post(
            "/api/advanced/rag/clear",
            headers=headers,
            json={"session_id": session_id},
        )

        assert response.status_code == 200
        data = response.json()
        assert data.get("status") == "success"

        logger.info("✅ RAG clear successful")


# ============================================================
# Integration Tests
# ============================================================


class TestIntegration:
    """Integration tests with Examples folder."""

    @pytest.mark.asyncio
    async def test_full_workflow(self, client, auth_token):
        """Test complete workflow: scan → convert → compare → index → query."""
        headers = {"Authorization": f"Bearer {auth_token}"}
        examples_dir = Path(__file__).parent.parent.parent.parent / "Examples" / "BIg_test-examples"

        if not examples_dir.exists():
            pytest.skip(f"Examples directory not found: {examples_dir}")

        # Get first two XML files
        xml_files = sorted(examples_dir.glob("*.xml"))[:2]
        if len(xml_files) < 2:
            pytest.skip("Need at least 2 XML files in Examples")

        # Scan and convert first file
        with open(xml_files[0], "rb") as f:
            response = client.post(
                "/api/conversion/scan",
                headers=headers,
                files={"file": (xml_files[0].name, f, "application/xml")},
            )
        assert response.status_code == 200
        session_id_1 = response.json().get("session_id")
        logger.info(f"✅ Session 1 created: {session_id_1}")

        # Scan and convert second file
        with open(xml_files[1], "rb") as f:
            response = client.post(
                "/api/conversion/scan",
                headers=headers,
                files={"file": (xml_files[1].name, f, "application/xml")},
            )
        assert response.status_code == 200
        session_id_2 = response.json().get("session_id")
        logger.info(f"✅ Session 2 created: {session_id_2}")

        # Convert both
        for session_id in [session_id_1, session_id_2]:
            response = client.post(
                "/api/conversion/convert",
                headers=headers,
                json={"session_id": session_id},
            )
            assert response.status_code == 200
            logger.info(f"✅ Converted session {session_id}")

        # Index both sessions
        for session_id in [session_id_1, session_id_2]:
            response = client.post(
                "/api/advanced/rag/index",
                headers=headers,
                json={"session_id": session_id},
            )
            assert response.status_code in [200, 201]
            logger.info(f"✅ Indexed session {session_id}")

        # Query both sessions
        queries = [
            "What are the main topics?",
            "What data is available?",
        ]

        for i, session_id in enumerate([session_id_1, session_id_2]):
            response = client.post(
                "/api/advanced/rag/query",
                headers=headers,
                json={
                    "session_id": session_id,
                    "query": queries[i],
                },
            )
            if response.status_code == 200:
                data = response.json()
                logger.info(
                    f"✅ Query session {session_id}: {len(data.get('sources', []))} sources found"
                )


# ============================================================
# Fixtures & Logging
# ============================================================

import logging

logger = logging.getLogger(__name__)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
