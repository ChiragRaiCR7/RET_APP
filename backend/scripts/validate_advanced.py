
#!/usr/bin/env python3
"""
Advanced RET Backend Validation Script

Validates:
- XLSX conversion service
- Comparison service
- Advanced RAG service
- API endpoints
- Integration with Examples folder

Run:
  python backend/scripts/validate_advanced.py
"""

import sys
import os
import logging
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

backend_path = Path(__file__).parent.parent
sys.path.insert(0, str(backend_path))


def validate_imports():
    logger.info("=" * 70)
    logger.info("VALIDATING IMPORTS")
    logger.info("=" * 70)

    modules = [
        "api.services.xlsx_service",
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
    logger.info("\n" + "=" * 70)
    logger.info("VALIDATING SERVICE CLASSES")
    logger.info("=" * 70)

    try:
        from api.services.xlsx_service import csv_to_xlsx_bytes
        logger.info("✅ xlsx_service.csv_to_xlsx_bytes")
    except Exception as e:
        logger.error(f"❌ xlsx_service: {e}")
        return False

    try:
        from api.services.comparison_service import compare_files
        logger.info("✅ comparison_service.compare_files")
    except Exception as e:
        logger.error(f"❌ comparison_service: {e}")
        return False

    try:
        from api.services.advanced_ai_service import (
            UnifiedRAGService,
            EmbeddingService,
            ChatService,
            ChromaVectorStore,
        )
        logger.info("✅ advanced_ai_service.UnifiedRAGService")
        logger.info("✅ advanced_ai_service.EmbeddingService")
        logger.info("✅ advanced_ai_service.ChatService")
        logger.info("✅ advanced_ai_service.ChromaVectorStore")
    except Exception as e:
        logger.error(f"❌ advanced_ai_service: {e}")
        return False

    return True


def validate_routes():
    logger.info("\n" + "=" * 70)
    logger.info("VALIDATING API ROUTES")
    logger.info("=" * 70)

    try:
        from api.routers.advanced_router import router

        routes = [
            "/xlsx/convert",
            "/xlsx/download",
        ]

        route_paths = [str(getattr(r, "path", "")) for r in router.routes]

        for route in routes:
            found = any(route in path for path in route_paths)
            status = "✅" if found else "❌"
            logger.info(f"{status} /api/advanced{route}")

        return True
    except Exception as e:
        logger.error(f"❌ advanced_router: {e}")
        return False


def validate_schemas():
    logger.info("\n" + "=" * 70)
    logger.info("VALIDATING SCHEMAS")
    logger.info("=" * 70)

    try:
        from api.schemas.advanced import (
            XLSXConversionRequest,
            XLSXConversionResponse,
            ComparisonRequest,
            ComparisonResponse,
            RAGEmbeddingRequest,
            RAGEmbeddingResponse,
            RAGQueryRequest,
            RAGQueryResponse,
            RAGClearRequest,
            RAGClearResponse,
        )

        _ = [
            XLSXConversionRequest,
            XLSXConversionResponse,
            ComparisonRequest,
            ComparisonResponse,
            RAGEmbeddingRequest,
            RAGEmbeddingResponse,
            RAGQueryRequest,
            RAGQueryResponse,
            RAGClearRequest,
            RAGClearResponse,
        ]

        logger.info("✅ Schemas import OK")
        return True
    except Exception as e:
        logger.error(f"❌ schemas: {e}")
        return False


def validate_examples():
    logger.info("\n" + "=" * 70)
    logger.info("VALIDATING EXAMPLES FOLDER")
    logger.info("=" * 70)

    examples_dir = backend_path.parent / "Examples" / "BIg_test-examples"

    if examples_dir.exists():
        xml_files = list(examples_dir.glob("*.xml"))
        logger.info(f"✅ Examples folder found: {examples_dir}")
        logger.info(f"   XML files available: {len(xml_files)}")
        if xml_files:
            logger.info(f"   First file: {xml_files[0].name}")
        return True

    logger.warning(f"⚠️ Examples folder not found: {examples_dir}")
    return False


def validate_env_config():
    logger.info("\n" + "=" * 70)
    logger.info("VALIDATING ENVIRONMENT CONFIG")
    logger.info("=" * 70)

    # Accept either naming scheme:
    # - *_MODEL (your current settings fields)
    # - *_DEPLOYMENT (legacy docs / some scripts)
    required_groups = [
        ("AZURE_OPENAI_API_KEY",),
        ("AZURE_OPENAI_ENDPOINT",),
        ("AZURE_OPENAI_API_VERSION",),
        ("AZURE_OPENAI_CHAT_MODEL", "AZURE_OPENAI_CHAT_DEPLOYMENT"),
        ("AZURE_OPENAI_EMBED_MODEL", "AZURE_OPENAI_EMBED_DEPLOYMENT"),
    ]

    missing_groups = []

    for group in required_groups:
        if any(os.getenv(var) for var in group):
            chosen = next((v for v in group if os.getenv(v)), group[0])
            logger.info(f"✅ {chosen}")
        else:
            logger.warning(f"⚠️ Missing one of: {', '.join(group)}")
            missing_groups.append(group)

    if missing_groups:
        logger.warning(f"\n⚠️ Missing {len(missing_groups)} required configuration group(s).")
        logger.warning("Azure OpenAI features will not work until configured.")
        return False

    return True


def validate_dependencies():
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

    logger.warning(f"\n⚠️ {total - passed} validation(s) need attention.")
    logger.warning("See details above for resolution steps.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
