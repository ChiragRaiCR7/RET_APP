from typing import List, Optional

from pydantic import AnyHttpUrl
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # ======================
    # Application
    # ======================
    APP_NAME: str = "RET-v4"
    ENV: str = "development"
    DEBUG: bool = False

    # ======================
    # API
    # ======================
    API_HOST: str = "0.0.0.0"
    API_PORT: int = 8000

    FRONTEND_URL: Optional[AnyHttpUrl] = None

    CORS_ORIGINS: List[str] = [
        "http://localhost:3000",
        "http://localhost:5173",
    ]

    # ======================
    # Database
    # ======================
    DATABASE_URL: Optional[str] = "sqlite:///./test.db"

    # ======================
    # Session Storage (SQLite)
    # ======================
    RET_SESSION_DB: str = "./runtime/ret_session.db"

    # ======================
    # Security / JWT
    # ======================
    JWT_SECRET_KEY: Optional[str] = "dev-secret-key-do-not-use-in-production"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # ======================
    # Runtime / Logging
    # ======================
    RET_RUNTIME_ROOT: str = "./runtime"
    LOG_LEVEL: str = "INFO"

    # ======================
    # Session Cache (LRU)
    # ======================
    SESSION_CACHE_MAX_SIZE: int = 1000
    SESSION_CACHE_TTL_SECONDS: int = 3600  # 1 hour

    # ======================
    # AI / RET
    # ======================
    RET_AI_TEMPERATURE: float = 0.7

    # ======================
    # Azure OpenAI (optional in dev)
    # ======================
    AZURE_OPENAI_API_KEY: Optional[str] = None
    AZURE_OPENAI_ENDPOINT: Optional[AnyHttpUrl] = None
    AZURE_OPENAI_API_VERSION: Optional[str] = None
    AZURE_OPENAI_CHAT_MODEL: Optional[str] = None  # Deployment name for chat
    AZURE_OPENAI_EMBED_MODEL: Optional[str] = None
    
    @property
    def AZURE_OPENAI_CHAT_DEPLOYMENT(self) -> Optional[str]:
        """Return CHAT_MODEL as CHAT_DEPLOYMENT for backward compatibility"""
        return self.AZURE_OPENAI_CHAT_MODEL

    # ======================
    # Pydantic Settings
    # ======================
    model_config = SettingsConfigDict(
        env_file=".env",
        case_sensitive=False,
        extra="ignore",  # Ignore extra fields instead of forbid
    )


settings = Settings()
