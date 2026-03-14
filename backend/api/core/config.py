"""
Application Configuration with Environment-Specific Settings.

Supports: development, staging, production, testing environments.
Load order: defaults -> .env file -> .env.{ENV} file -> environment variables

Non-breaking improvements:
- ENV vs ENVIRONMENT alias
- Fix TestingConfig DATABASE_URL default bug
- Build RATE_LIMIT_EXEMPT_PATHS using API_PREFIX to avoid prefix mismatch
- Make DATABASE_URL optional with a safe default (None)
"""

from __future__ import annotations

import os
from enum import Enum
from functools import lru_cache
from typing import List, Optional

from pydantic import AnyHttpUrl, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Environment(str, Enum):
    """Application environments."""
    DEVELOPMENT = "development"
    STAGING = "staging"
    PRODUCTION = "production"
    TESTING = "testing"


class BaseConfig(BaseSettings):
    """Base configuration with common settings."""

    # ======================
    # Application
    # ======================
    APP_NAME: str = "RET-v4"
    APP_VERSION: str = "4.0.0"
    ENV: Environment = Environment.DEVELOPMENT
    DEBUG: bool = False

    # Optional: used by main.py in strict startup scenarios (safe addition)
    STRICT_STARTUP: bool = False

    # ======================
    # API
    # ======================
    API_HOST: str = "0.0.0.0"
    API_PORT: int = 8000
    API_PREFIX: str = "/api/v1"

    FRONTEND_URL: Optional[AnyHttpUrl] = None

    CORS_ORIGINS: List[str] = [
        "http://localhost:3000",
        "http://localhost:5173",
    ]

    # ======================
    # Database
    # ======================
    # ✅ Make truly optional to avoid import-time crashes in modules that import settings
    DATABASE_URL: Optional[str] = None
    DATABASE_POOL_SIZE: int = 5
    DATABASE_MAX_OVERFLOW: int = 10
    DATABASE_POOL_TIMEOUT: int = 30

    # ======================
    # Session Storage (SQLite)
    # ======================
    RET_SESSION_DB: str = "./runtime/ret_session.db"

    # ======================
    # Security / JWT
    # ======================
    JWT_SECRET_KEY: Optional[str] = None
    JWT_ALGORITHM: str = "HS256"
    JWT_ISSUER: str = "ret-v4"
    JWT_AUDIENCE: str = "ret-v4-api"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 300
    REFRESH_TOKEN_EXPIRE_DAYS: int = 70

    # Login security
    MAX_LOGIN_ATTEMPTS: int = 5
    LOGIN_LOCKOUT_MINUTES: int = 15

    # Security Headers
    ENABLE_SECURITY_HEADERS: bool = True
    HSTS_MAX_AGE: int = 31536000  # 1 year

    # ======================
    # Runtime / Logging
    # ======================
    RET_RUNTIME_ROOT: str = "./runtime"
    LOG_LEVEL: str = "INFO"
    LOG_FORMAT: str = "json"  # json or text
    LOG_FILE: Optional[str] = None

    # ======================
    # Session Cache (LRU)
    # ======================
    SESSION_CACHE_MAX_SIZE: int = 100000
    SESSION_CACHE_TTL_SECONDS: int = 36000  # 1 hour

    # ======================
    # AI / RET
    # ======================
    RET_AI_TEMPERATURE: float = 0.7
    AI_STRATEGY: str = "advanced"

    # ======================
    # Conversion Timeouts
    # ======================
    CONVERSION_TIMEOUT_SECONDS: int = 30000
    ZIP_SCAN_TIMEOUT_SECONDS: int = 12000
    XML_PARSE_TIMEOUT_SECONDS: int = 6000

    # ======================
    # Parallel Conversion Settings
    # ======================
    CONVERSION_DEFAULT_WORKERS: int = 32
    CONVERSION_MAX_WORKERS: int = 64
    CONVERSION_MIN_WORKERS: int = 16
    CONVERSION_STREAMING_THRESHOLD_MB: int = 100
    CONVERSION_BATCH_SIZE: int = 1000
    CONVERSION_PROGRESS_LOG_INTERVAL: int = 100
    CONVERSION_MAX_ROWS_PER_XLSX: int = 50000
    CONVERSION_AUTO_WORKER_SCALING: bool = True

    # ======================
    # Advanced RAG Configuration
    # ======================
    RAG_USE_ADVANCED: bool = True
    RAG_TOP_K_VECTOR: int = 20
    RAG_TOP_K_LEXICAL: int = 15
    RAG_TOP_K_SUMMARY: int = 5
    RAG_MAX_CHUNKS: int = 15
    RAG_MAX_CONTEXT_CHARS: int = 40000
    RAG_VECTOR_WEIGHT: float = 0.70
    RAG_LEXICAL_WEIGHT: float = 0.30
    RAG_SUMMARY_WEIGHT: float = 0.10
    RAG_CHUNK_SIZE: int = 1500
    RAG_CHUNK_OVERLAP: int = 200
    RAG_CHUNK_MIN: int = 900
    RAG_CHUNK_MAX: int = 3500
    RAG_CHUNK_MAX_COLS: int = 120
    RAG_CELL_MAX_CHARS: int = 250
    RAG_RRF_K: int = 60
    RAG_INDEX_SKIP_UNCHANGED: bool = True
    RAG_SUMMARY_SAMPLE_ROWS: int = 50
    RAG_ENABLE_QUERY_TRANSFORM: bool = True
    RAG_ENABLE_SUMMARIES: bool = True

    # ── Hybrid Retrieval Fine-tuning ──
    RAG_LEX_TOP_N_TOKENS: int = 80
    RAG_FEEDBACK_BOOST: float = 0.15
    RAG_RERANK_TOP_M: int = 30

    # ── XML Record Indexing ──
    RAG_XML_MAX_RECORDS_PER_FILE: int = 5000
    RAG_XML_MAX_CHARS_PER_RECORD: int = 6000
    RAG_XML_FIELD_MAX_LEN: int = 300

    # ── Citation Enforcement ──
    RAG_ENABLE_CITATION_REPAIR: bool = True
    RAG_CITATION_REPAIR_TEMPERATURE: float = 0.0

    # ======================
    # Azure OpenAI
    # ======================
    AZURE_OPENAI_API_KEY: Optional[str] = None
    AZURE_OPENAI_ENDPOINT: Optional[AnyHttpUrl] = None
    AZURE_OPENAI_API_VERSION: Optional[str] = "2024-10-21"
    AZURE_OPENAI_CHAT_MODEL: Optional[str] = "gpt-4o"
    AZURE_OPENAI_EMBED_MODEL: Optional[str] = "text-embedding-3-small"
    AZURE_OPENAI_TIMEOUT_SECONDS: int = 60
    AZURE_OPENAI_EMBED_TIMEOUT_SECONDS: int = 30

    # ======================
    # Rate Limiting
    # ======================
    RATE_LIMIT_REQUESTS: int = 100
    RATE_LIMIT_WINDOW_SECONDS: int = 60
    RATE_LIMIT_REQUESTS_PER_MINUTE: int = 500  # Alias for middleware

    # ✅ Keep field but auto-correct mismatch via validator below
    RATE_LIMIT_EXEMPT_PATHS: List[str] = [
        "/health",
        "/api/auth/refresh",
        "/api/auth/me",
        "/docs",
        "/openapi.json",
    ]

    # ======================
    # Resource Limits
    # ======================
    MAX_UPLOAD_SIZE_MB: int = 10000
    MAX_NESTED_ZIP_DEPTH: int = 50
    MAX_TOTAL_FILES: int = 10000
    MAX_TOTAL_MB: int = 10000
    MAX_PER_FILE_MB: int = 1000
    MAX_COMPRESSION_RATIO: int = 200
    MAX_INLINE_CONVERSION_BYTES: int = 10 * 1024 * 1024
    MAX_INLINE_CHANGES: int = 1000
    MAX_XLSX_ROWS: int = 100000
    MAX_XLSX_COLUMNS: int = 500

    # ======================
    # AI Limits
    # ======================
    AI_MAX_HISTORY: int = 50
    AI_MAX_TOKENS: int = 4000
    EMBED_BATCH_SIZE: int = 16
    EMBED_GROUP_TIMEOUT: int = 600
    EMBED_GROUP_TIMEOUT_PER_MB: float = 6.0
    EMBED_MAX_WORKERS: int = 2

    # ======================
    # Feature Flags (Phase 1)
    # ======================
    # LangGraph runtime — when True the RAG chat path uses the
    # LangGraph graph instead of UnifiedRAGService.chat().
    FEATURE_LANGGRAPH_ENABLED: bool = False

    # Streaming — when True the /chat/stream endpoint is active
    # and the graph emits SSE via astream_events.
    FEATURE_CHAT_STREAMING: bool = False

    # LangSmith tracing — when True every graph invocation is
    # traced via the LangSmith callback handler.
    FEATURE_LANGSMITH_TRACING: bool = False
    LANGSMITH_API_KEY: Optional[str] = None
    LANGSMITH_PROJECT: str = "ret-v4"

    # Checkpoint backend — "memory" for dev, "postgres" for prod.
    FEATURE_CHECKPOINT_BACKEND: str = "memory"

    # Human-in-the-Loop — when True certain graph nodes can
    # interrupt and wait for operator review.
    FEATURE_HITL_ENABLED: bool = False
    RAG_HITL_CONFIDENCE_THRESHOLD: float = 0.35

    # DSPy prompt optimization — when True the graph uses
    # DSPy-tuned signatures instead of static prompts.
    FEATURE_DSPY_ENABLED: bool = False

    # LLM response cache — when True, LangChain's global cache
    # stores prompt/response pairs in a local SQLite database
    # (runtime/cache/llm_cache.db) to avoid duplicate API calls.
    FEATURE_LLM_CACHE: bool = False

    # Record sidecar caching — when True the conversion step
    # writes chunk-ready text alongside CSVs so the embedder
    # skips redundant XML/CSV reparsing.
    FEATURE_SIDECAR_CACHE: bool = False

    # Token rotation — when True refresh tokens are rotated on
    # each use and reuse detection is enforced.
    FEATURE_TOKEN_ROTATION: bool = False

    # Per-session logging — when True a separate log file is
    # created per user+session under runtime/logs/sessions/.
    FEATURE_SESSION_LOGGING: bool = False

    # Performance metrics — when True hot-path timing is emitted
    # as structured log events for baseline measurement.
    FEATURE_PERF_METRICS: bool = True

    # ======================
    # Task Executor / Background Tasks
    # ======================
    TASK_EXECUTOR_MAX_WORKERS: int = 4
    BACKGROUND_TASK_MAX_CONCURRENT: int = 8  # asyncio.Semaphore limit for BackgroundTaskManager
    DB_JOB_UPDATE_TIMEOUT: int = 30  # seconds - timeout for worker->main loop DB updates
    REQUEST_TIMEOUT_SECONDS: int = 120  # default request timeout
    LONG_REQUEST_TIMEOUT_SECONDS: int = 600  # long-running request timeout
    EMBED_CONCURRENCY_LIMIT: int = 4  # concurrency limit for embedding operations

    EMBED_BATCH_MAX_RETRIES: int = 3
    EMBED_BACKOFF_BASE_SECONDS: float = 0.6
    EMBED_GROUP_MAX_RETRIES: int = 2
    EMBED_GROUP_BACKOFF_SECONDS: float = 1.5
    CHUNK_TARGET_CHARS: int = 10000

    # ----------------------
    # Compatibility properties
    # ----------------------
    @property
    def ENVIRONMENT(self) -> str:
        """Alias to prevent ENV vs ENVIRONMENT drift across the codebase."""
        return self.ENV.value

    @property
    def AZURE_OPENAI_CHAT_DEPLOYMENT(self) -> Optional[str]:
        """Return CHAT_MODEL as CHAT_DEPLOYMENT for backward compatibility."""
        return self.AZURE_OPENAI_CHAT_MODEL

    @property
    def AZURE_OPENAI_EMBED_DEPLOYMENT(self) -> Optional[str]:
        """Return EMBED_MODEL as EMBED_DEPLOYMENT for backward compatibility."""
        return self.AZURE_OPENAI_EMBED_MODEL

    @property
    def is_development(self) -> bool:
        """Check if running in development mode."""
        return self.ENV == Environment.DEVELOPMENT

    @property
    def is_production(self) -> bool:
        """Check if running in production mode."""
        return self.ENV == Environment.PRODUCTION

    # ----------------------
    # Validators
    # ----------------------
    @field_validator("CORS_ORIGINS")
    @classmethod
    def validate_cors_origins(cls, v: List[str]) -> List[str]:
        for origin in v:
            if origin == "*":
                continue
            if not str(origin).startswith(("http://", "https://")):
                raise ValueError(f"Invalid CORS origin format: {origin}")
        return v

    @model_validator(mode="after")
    def normalize_rate_limit_exempt_paths(self) -> "BaseConfig":
        """
        ✅ Fix mismatch between /api/... and actual API_PREFIX (/api/v1).
        If user didn't explicitly override RATE_LIMIT_EXEMPT_PATHS, rebuild using API_PREFIX.
        """
        # If user has custom exempt paths in env, keep them.
        # Heuristic: if list contains an /api/auth path, we rewrite to API_PREFIX.
        prefix = self.API_PREFIX or "/api/v1"

        rebuilt = []
        for p in self.RATE_LIMIT_EXEMPT_PATHS or []:
            if p.startswith("/api/auth/"):
                rebuilt.append(p.replace("/api", prefix, 1) if prefix != "/api" else p)
            else:
                rebuilt.append(p)

        # Ensure core exempt paths exist
        must_have = [
            "/health",
            f"{prefix}/auth/refresh",
            f"{prefix}/auth/me",
            "/docs",
            "/openapi.json",
        ]
        for m in must_have:
            if m not in rebuilt:
                rebuilt.append(m)

        self.RATE_LIMIT_EXEMPT_PATHS = rebuilt
        return self

    model_config = SettingsConfigDict(
        env_file=".env",
        case_sensitive=False,
        extra="ignore",
    )


class DevelopmentConfig(BaseConfig):
    """Development environment configuration."""

    ENV: Environment = Environment.DEVELOPMENT
    DEBUG: bool = True
    LOG_LEVEL: str = "DEBUG"
    LOG_FORMAT: str = "text"

    # Relaxed security for development
    JWT_SECRET_KEY: Optional[str] = "dev-secret-key-do-not-use-in-production"
    ENABLE_SECURITY_HEADERS: bool = False

    # Smaller pool for SQLite
    DATABASE_POOL_SIZE: int = 1
    DATABASE_MAX_OVERFLOW: int = 0

    # Higher rate limits for testing
    RATE_LIMIT_REQUESTS: int = 1000

    model_config = SettingsConfigDict(
        env_file=(".env", ".env.development"),
        case_sensitive=False,
        extra="ignore",
    )


class StagingConfig(BaseConfig):
    """Staging environment configuration."""

    ENV: Environment = Environment.STAGING
    DEBUG: bool = False
    LOG_LEVEL: str = "INFO"

    CORS_ORIGINS: List[str] = []  # Must be explicitly configured

    # Moderate security
    ENABLE_SECURITY_HEADERS: bool = True
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60

    model_config = SettingsConfigDict(
        env_file=(".env", ".env.staging"),
        case_sensitive=False,
        extra="ignore",
    )

    @field_validator("JWT_SECRET_KEY")
    @classmethod
    def jwt_secret_must_be_set(cls, v: Optional[str]) -> str:
        if not v or v == "dev-secret-key-do-not-use-in-production":
            raise ValueError("JWT_SECRET_KEY must be set in staging environment")
        return v


class ProductionConfig(BaseConfig):
    """Production environment configuration - strictest security."""

    ENV: Environment = Environment.PRODUCTION
    DEBUG: bool = False
    LOG_LEVEL: str = "WARNING"
    LOG_FORMAT: str = "json"

    CORS_ORIGINS: List[str] = []  # Must be explicitly configured

    # Strict security
    ENABLE_SECURITY_HEADERS: bool = True
    HSTS_MAX_AGE: int = 63072000  # 2 years
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 15
    REFRESH_TOKEN_EXPIRE_DAYS: int = 1

    # Production database settings
    DATABASE_POOL_SIZE: int = 20
    DATABASE_MAX_OVERFLOW: int = 30

    # Stricter rate limiting
    RATE_LIMIT_REQUESTS: int = 60
    RATE_LIMIT_WINDOW_SECONDS: int = 60

    model_config = SettingsConfigDict(
        env_file=(".env", ".env.production"),
        case_sensitive=False,
        extra="ignore",
    )

    @field_validator("JWT_SECRET_KEY")
    @classmethod
    def jwt_secret_must_be_secure(cls, v: Optional[str]) -> str:
        if not v:
            raise ValueError("JWT_SECRET_KEY is required in production")
        if v == "dev-secret-key-do-not-use-in-production":
            raise ValueError("Cannot use development secret key in production")
        if len(v) < 32:
            raise ValueError("JWT_SECRET_KEY must be at least 32 characters in production")
        return v

    @field_validator("DATABASE_URL")
    @classmethod
    def database_must_not_be_sqlite(cls, v: Optional[str]) -> str:
        if not v:
            raise ValueError("DATABASE_URL is required in production")
        if v.startswith("sqlite"):
            raise ValueError("SQLite is not supported in production. Use PostgreSQL.")
        return v

    @model_validator(mode="after")
    def validate_production_settings(self) -> "ProductionConfig":
        """Ensure all critical production settings are configured."""
        if not self.AZURE_OPENAI_API_KEY:
            raise ValueError("AZURE_OPENAI_API_KEY is required in production")
        if not self.CORS_ORIGINS:
            raise ValueError("CORS_ORIGINS must be explicitly configured in production")
        return self


class TestingConfig(BaseConfig):
    """Testing environment configuration."""

    ENV: Environment = Environment.TESTING
    DEBUG: bool = True
    LOG_LEVEL: str = "DEBUG"

    model_config = SettingsConfigDict(
        env_file=(".env", ".env.testing"),
        case_sensitive=False,
        extra="ignore",
    )

    def __init__(self, **kwargs):
        # ✅ FIX: give DATABASE_URL a real default for tests (can be overridden by env)
        kwargs.setdefault("DATABASE_URL", "sqlite+aiosqlite:///./runtime/test.db")
        kwargs.setdefault("JWT_SECRET_KEY", "test-secret-key")
        kwargs.setdefault("AZURE_OPENAI_API_KEY", None)
        super().__init__(**kwargs)


# Configuration factory
_config_map = {
    Environment.DEVELOPMENT: DevelopmentConfig,
    Environment.STAGING: StagingConfig,
    Environment.PRODUCTION: ProductionConfig,
    Environment.TESTING: TestingConfig,
}


@lru_cache()
def get_settings() -> BaseConfig:
    """
    Get settings for the current environment.

    Environment is determined by the ENV environment variable.
    Defaults to development if not set.
    """
    env_str = os.getenv("ENV", "development").lower()
    try:
        env = Environment(env_str)
    except ValueError:
        env = Environment.DEVELOPMENT

    config_class = _config_map.get(env, DevelopmentConfig)
    return config_class()


# Create settings instance
settings = get_settings()
