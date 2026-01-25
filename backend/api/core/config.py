from pydantic_settings import BaseSettings
from typing import List

class Settings(BaseSettings):
    APP_NAME: str = "RET-v4"
    ENV: str = "development"
    DEBUG: bool = False

    API_HOST: str = "0.0.0.0"
    API_PORT: int = 8000

    DATABASE_URL: str

    JWT_SECRET_KEY: str
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    REDIS_URL: str

    RET_RUNTIME_ROOT: str = "./runtime"

    LOG_LEVEL: str = "INFO"

    CORS_ORIGINS: List[str] = ["http://localhost:3000", "http://localhost:5173"]
    AZURE_OPENAI_API_KEY: str = ""
    AZURE_OPENAI_ENDPOINT: str = ""
    AZURE_OPENAI_API_VERSION: str = ""
    AZURE_OPENAI_CHAT_MODEL: str = ""
    AZURE_OPENAI_EMBED_MODEL: str = ""


    class Config:
        env_file = ".env"
        case_sensitive = False


settings = Settings()
