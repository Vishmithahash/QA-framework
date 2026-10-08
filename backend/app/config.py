from functools import lru_cache
from pathlib import Path
from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import make_url

BASE_DIR = Path(__file__).resolve().parent.parent
ENV_FILE = BASE_DIR / ".env"


class Settings(BaseSettings):
    APP_NAME: str = "Agentic AI QA Framework API"
    APP_ENV: str = "development"
    DEBUG: bool = False
    DATABASE_URL: SecretStr = Field(..., description="PostgreSQL connection string")

    model_config = SettingsConfigDict(
        env_file=ENV_FILE,
        env_file_encoding="utf-8",
        extra="ignore",
        hide_input_in_errors=True,
    )

    @field_validator("DATABASE_URL", mode="after")
    @classmethod
    def validate_database_url(cls, v: SecretStr) -> SecretStr:
        secret_val = v.get_secret_value().strip()
        if not secret_val:
            raise ValueError("DATABASE_URL must not be empty.")

        try:
            parsed = make_url(secret_val)
        except Exception:
            raise ValueError("DATABASE_URL is not a valid database URL.") from None

        allowed_schemes = ("postgresql", "postgres", "postgresql+psycopg")
        if parsed.drivername not in allowed_schemes:
            raise ValueError(
                "DATABASE_URL must use postgresql://, postgres://, or postgresql+psycopg:// scheme."
            )

        sslmode = parsed.query.get("sslmode")
        if sslmode:
            normalized_ssl = sslmode.lower()
            if normalized_ssl in ("disable", "allow", "prefer"):
                raise ValueError(
                    f"Insecure sslmode '{sslmode}' is not allowed. Must be 'require', 'verify-ca', or 'verify-full'."
                )
            if normalized_ssl not in ("require", "verify-ca", "verify-full"):
                raise ValueError(
                    f"Unsupported sslmode '{sslmode}'. Must be 'require', 'verify-ca', or 'verify-full'."
                )

        return v


@lru_cache
def get_settings() -> Settings:
    return Settings()
