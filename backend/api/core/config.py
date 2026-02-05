"""
Application Configuration with Environment-Specific Settings.

Supports: development, staging, production environments.
Load order: defaults -> .env file -> .env.{ENV} file -> environment variables
"""
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
    DATABASE_URL: Optional[str] = "sqlite:///./test.db"
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
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7
    
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
    SESSION_CACHE_MAX_SIZE: int = 1000
    SESSION_CACHE_TTL_SECONDS: int = 3600  # 1 hour

    # ======================
    # AI / RET
    # ======================
    RET_AI_TEMPERATURE: float = 0.7
    AI_STRATEGY: str = "advanced"  # lite, langchain, advanced
    
    # ======================
    # Advanced RAG Configuration
    # ======================
    RAG_USE_ADVANCED: bool = True  # Use Advanced RAG Engine with LangGraph
    RAG_TOP_K_VECTOR: int = 20  # Top K for vector retrieval
    RAG_TOP_K_LEXICAL: int = 15  # Top K for lexical retrieval
    RAG_TOP_K_SUMMARY: int = 5  # Top K for summary retrieval
    RAG_MAX_CHUNKS: int = 15  # Max chunks for context
    RAG_MAX_CONTEXT_CHARS: int = 40000  # Max characters in context
    RAG_VECTOR_WEIGHT: float = 0.6  # Weight for vector similarity in fusion
    RAG_LEXICAL_WEIGHT: float = 0.3  # Weight for lexical similarity in fusion
    RAG_SUMMARY_WEIGHT: float = 0.1  # Weight for summary similarity in fusion
    RAG_CHUNK_SIZE: int = 1500  # Chunk size for text splitting
    RAG_CHUNK_OVERLAP: int = 200  # Overlap between chunks
    RAG_ENABLE_QUERY_TRANSFORM: bool = True  # Enable LLM-based query transformation
    RAG_ENABLE_SUMMARIES: bool = True  # Generate and index document summaries

    # ======================
    # Azure OpenAI
    # ======================
    AZURE_OPENAI_API_KEY: Optional[str] = None
    AZURE_OPENAI_ENDPOINT: Optional[AnyHttpUrl] = None
    AZURE_OPENAI_API_VERSION: Optional[str] = "2024-02-01"
    AZURE_OPENAI_CHAT_MODEL: Optional[str] = "gpt-4o"
    AZURE_OPENAI_EMBED_MODEL: Optional[str] = "text-embedding-3-small"
    
    # ======================
    # Rate Limiting
    # ======================
    RATE_LIMIT_REQUESTS: int = 100
    RATE_LIMIT_WINDOW_SECONDS: int = 60

    @property
    def AZURE_OPENAI_CHAT_DEPLOYMENT(self) -> Optional[str]:
        """Return CHAT_MODEL as CHAT_DEPLOYMENT for backward compatibility."""
        return self.AZURE_OPENAI_CHAT_MODEL

    @property
    def is_development(self) -> bool:
        """Check if running in development mode."""
        return self.ENV == Environment.DEVELOPMENT

    @property
    def is_production(self) -> bool:
        """Check if running in production mode."""
        return self.ENV == Environment.PRODUCTION

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
    
    # Provide defaults without re-declaring types (avoids type variance issues)
    # Types are inherited from BaseConfig
    model_config = SettingsConfigDict(
        env_file=(".env", ".env.testing"),
        case_sensitive=False,
        extra="ignore",
    )
    
    def __init__(self, **kwargs):
        # Set testing defaults before Pydantic processing
        kwargs.setdefault("DATABASE_URL", "sqlite:///:memory:")
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
        # Fall back to development for unknown environments
        env = Environment.DEVELOPMENT
    
    config_class = _config_map.get(env, DevelopmentConfig)
    return config_class()


# Create settings instance
settings = get_settings()
