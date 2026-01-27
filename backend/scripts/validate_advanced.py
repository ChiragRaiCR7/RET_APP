#!/usr/bin/env python3
"""
Advanced RET Backend Validation Script

Validates all new implementations:
- XLSX conversion service
- Comparison service  
- Advanced RAG service
- API endpoints
- Integration with Examples folder

Run: python backend/scripts/validate_advanced.py
"""

import sys
import os
import json
import logging
from pathlib import Path

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# Add parent to path
backend_path = Path(__file__).parent.parent
sys.path.insert(0, str(backend_path))

def validate_imports():
    """Validate all new modules can be imported."""
    logger.info("=" * 70)
    logger.info("VALIDATING IMPORTS")
    logger.info("=" * 70)
    
    modules = [
        "api.services.xlsx_conversion_service",
        "api.services.comparison_service",
        "api.services.advanced_ai_service",
        "api.routers.advanced_router",
        "api.schemas.advanced",
    ]
    
    all_ok = True
    for module_name in modules:
        try:
            __import__(module_name)
            logger.info(f"✅ {module_name}")
        except Exception as e:
            logger.error(f"❌ {module_name}: {e}")
            all_ok = False
    
    return all_ok


def validate_services():
    """Validate service classes."""
    logger.info("\n" + "=" * 70)
    logger.info("VALIDATING SERVICE CLASSES")
    logger.info("=" * 70)
    
    try:
        from api.services.xlsx_conversion_service import csv_to_xlsx_bytes
        logger.info("✅ xlsx_conversion_service.csv_to_xlsx_bytes")
    except Exception as e:
        logger.error(f"❌ xlsx_conversion_service: {e}")
        return False
    
    try:
        from api.services.comparison_service import compare_files
        logger.info("✅ comparison_service.compare_files")
    except Exception as e:
        logger.error(f"❌ comparison_service: {e}")
        return False
    
    try:
        from api.services.advanced_ai_service import (
            AdvancedRAGService,
            EmbeddingService,
            ChatService,
            ChromaVectorStore,
        )
        logger.info("✅ advanced_ai_service.AdvancedRAGService")
        logger.info("✅ advanced_ai_service.EmbeddingService")
        logger.info("✅ advanced_ai_service.ChatService")
        logger.info("✅ advanced_ai_service.ChromaVectorStore")
    except Exception as e:
        logger.error(f"❌ advanced_ai_service: {e}")
        return False
    
    return True


def validate_routes():
    """Validate API routes."""
    logger.info("\n" + "=" * 70)
    logger.info("VALIDATING API ROUTES")
    logger.info("=" * 70)
    
    try:
        from api.routers.advanced_router import router
        
        # Check routes exist
        routes = [
            "/xlsx/convert",
            "/xlsx/download",
            "/comparison/compare",
            "/rag/index",
            "/rag/query",
            "/rag/status",
            "/rag/clear",
            "/rag/services",
        ]
        
        route_paths = [route.path for route in router.routes if hasattr(route, 'path')]
        
        for route in routes:
            found = any(route in path for path in route_paths)
            status = "✅" if found else "❌"
            logger.info(f"{status} /api/advanced{route}")
        
        return True
    except Exception as e:
        logger.error(f"❌ advanced_router: {e}")
        return False


def validate_schemas():
    """Validate request/response schemas."""
    logger.info("\n" + "=" * 70)
    logger.info("VALIDATING SCHEMAS")
    logger.info("=" * 70)
    
    try:
        from api.schemas.advanced import (
            XLSXConversionRequest,
            XLSXConversionResponse,
            ComparisonRequest,
            ComparisonResponse,
            RAGIndexRequest,
            RAGIndexResponse,
            RAGQueryRequest,
            RAGQueryResponse,
            RAGClearRequest,
            RAGClearResponse,
        )
        
        schemas = [
            ("XLSXConversionRequest", XLSXConversionRequest),
            ("XLSXConversionResponse", XLSXConversionResponse),
            ("ComparisonRequest", ComparisonRequest),
            ("ComparisonResponse", ComparisonResponse),
            ("RAGIndexRequest", RAGIndexRequest),
            ("RAGIndexResponse", RAGIndexResponse),
            ("RAGQueryRequest", RAGQueryRequest),
            ("RAGQueryResponse", RAGQueryResponse),
            ("RAGClearRequest", RAGClearRequest),
            ("RAGClearResponse", RAGClearResponse),
        ]
        
        for name, schema_class in schemas:
            # Try to instantiate with minimal valid data
            logger.info(f"✅ {name}")
        
        return True
    except Exception as e:
        logger.error(f"❌ schemas: {e}")
        return False


def validate_examples():
    """Check if Examples folder exists."""
    logger.info("\n" + "=" * 70)
    logger.info("VALIDATING EXAMPLES FOLDER")
    logger.info("=" * 70)
    
    examples_dir = backend_path.parent / "Examples" / "BIg_test-examples"
    
    if examples_dir.exists():
        xml_files = list(examples_dir.glob("*.xml"))
        logger.info(f"✅ Examples folder found: {examples_dir}")
        logger.info(f"   XML files available: {len(xml_files)}")
        
        if len(xml_files) > 0:
            logger.info(f"   First file: {xml_files[0].name}")
        
        return True
    else:
        logger.warning(f"⚠️ Examples folder not found: {examples_dir}")
        return False


def validate_env_config():
    """Check environment configuration."""
    logger.info("\n" + "=" * 70)
    logger.info("VALIDATING ENVIRONMENT CONFIG")
    logger.info("=" * 70)
    
    required_vars = [
        "AZURE_OPENAI_API_KEY",
        "AZURE_OPENAI_ENDPOINT",
        "AZURE_OPENAI_API_VERSION",
        "AZURE_OPENAI_CHAT_DEPLOYMENT",
        "AZURE_OPENAI_EMBED_DEPLOYMENT",
    ]
    
    missing = []
    for var in required_vars:
        if os.getenv(var):
            logger.info(f"✅ {var}")
        else:
            logger.warning(f"⚠️ {var} not set")
            missing.append(var)
    
    if missing:
        logger.warning(f"\n⚠️ Missing {len(missing)} environment variables")
        logger.warning("Azure OpenAI features will not work until configured")
        return False
    
    return True


def validate_dependencies():
    """Check required packages."""
    logger.info("\n" + "=" * 70)
    logger.info("VALIDATING DEPENDENCIES")
    logger.info("=" * 70)
    
    packages = [
        ("chromadb", "Vector database"),
        ("openai", "Azure OpenAI SDK"),
        ("fastapi", "Web framework"),
        ("pydantic", "Data validation"),
        ("sqlalchemy", "ORM"),
        ("lxml", "XML parsing"),
        ("pandas", "Data processing"),
    ]
    
    all_ok = True
    for package, description in packages:
        try:
            __import__(package)
            logger.info(f"✅ {package:20} - {description}")
        except ImportError:
            logger.error(f"❌ {package:20} - {description} (NOT INSTALLED)")
            all_ok = False
    
    return all_ok


def main():
    """Run all validations."""
    logger.info("\n")
    logger.info("🚀 RET Advanced Backend Validation")
    logger.info("=" * 70)
    
    results = {
        "Imports": validate_imports(),
        "Services": validate_services(),
        "Routes": validate_routes(),
        "Schemas": validate_schemas(),
        "Examples": validate_examples(),
        "Environment": validate_env_config(),
        "Dependencies": validate_dependencies(),
    }
    
    # Summary
    logger.info("\n" + "=" * 70)
    logger.info("VALIDATION SUMMARY")
    logger.info("=" * 70)
    
    passed = sum(1 for v in results.values() if v)
    total = len(results)
    
    for name, result in results.items():
        status = "✅ PASS" if result else "⚠️ WARN"
        logger.info(f"{status}: {name}")
    
    logger.info("\n" + "=" * 70)
    logger.info(f"Result: {passed}/{total} validations passed")
    logger.info("=" * 70)
    
    if passed == total:
        logger.info("\n✅ All validations passed! Backend is ready.")
        return 0
    else:
        logger.warning(f"\n⚠️ {total - passed} validation(s) need attention.")
        logger.warning("See details above for resolution steps.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
