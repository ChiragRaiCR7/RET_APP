"""Runtime configuration. Every value is overridable via environment or backend/.env."""

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=BACKEND_DIR / ".env", extra="ignore")

    env: Literal["development", "test", "production"] = "development"
    data_dir: Path = BACKEND_DIR / "data"
    # Browser origins allowed to call the API with cookies (dev: Vite server).
    allowed_origins: list[str] = ["http://localhost:5173", "http://127.0.0.1:5173"]
    # Served SPA build; when present the API also serves the frontend (single-origin deploy).
    frontend_dist: Path = BACKEND_DIR.parent / "frontend" / "dist"

    # Auth
    session_ttl_hours: int = 12
    max_failed_logins: int = 5
    lockout_minutes: int = 15
    reset_token_ttl_minutes: int = 60
    bootstrap_admin_username: str = "admin"
    # Unset => no admin is created; the first start logs a one-time instruction instead.
    bootstrap_admin_password: SecretStr | None = None

    # Upload / scan budgets (zip-bomb defence)
    max_upload_mb: int = 1024
    max_scan_files: int = 20_000
    max_unzipped_mb: int = 2048
    max_zip_depth: int = 10
    max_compression_ratio: int = 200
    max_field_chars: int = 300

    # Conversion
    conversion_workers: int = 0  # 0 => os.cpu_count()

    # AI search
    index_max_rows_per_workspace: int = 200_000
    retrieval_top_k: int = 12
    context_char_budget: int = 12_000

    # Azure OpenAI (names kept from v4 so existing .env files keep working)
    azure_openai_endpoint: str | None = None
    azure_openai_api_key: SecretStr | None = None
    azure_openai_api_version: str = "2024-10-21"
    azure_openai_chat_model: str | None = None  # deployment name
    azure_openai_timeout_seconds: float = 60.0

    @property
    def database_url(self) -> str:
        return f"sqlite:///{self.data_dir / 'ret.db'}"

    @property
    def workspaces_dir(self) -> Path:
        return self.data_dir / "workspaces"

    @property
    def llm_configured(self) -> bool:
        return bool(
            self.azure_openai_endpoint
            and self.azure_openai_api_key
            and self.azure_openai_chat_model
        )

    @property
    def secure_cookies(self) -> bool:
        return self.env == "production"


@lru_cache
def get_settings() -> Settings:
    return Settings()
