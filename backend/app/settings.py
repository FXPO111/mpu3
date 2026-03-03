from __future__ import annotations

from typing import Any

from pydantic import field_validator
from typing import Annotated

from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    # App
    app_name: str = "mpu-platform"
    app_env: str = "dev"  # dev|prod
    frontend_url: str = "http://localhost:3000"

    # CORS (comma-separated or JSON list)
    cors_allow_origins: Annotated[list[str], NoDecode] = ["http://localhost:3000"]

    @field_validator("cors_allow_origins", mode="before")
    @classmethod
    def _parse_origins(cls, v: Any):
        if v is None:
            return ["http://localhost:3000"]
        if isinstance(v, list):
            return [str(x).strip() for x in v if str(x).strip()]
        if isinstance(v, str):
            s = v.strip()
            # allow JSON-ish list in env, but keep simple: comma separated
            if s.startswith("[") and s.endswith("]"):
                # very small safe parse without eval
                s = s.strip("[]")
            parts = [p.strip().strip('"').strip("'") for p in s.split(",")]
            return [p for p in parts if p]
        return v

    # DB
    database_url: str = "postgresql+psycopg://postgres:postgres@localhost:5432/mpu"

    # Auth/JWT
    jwt_secret: str = "change-me"
    jwt_exp_minutes: int = 60

    # Payments (Stripe)
    stripe_secret_key: str = "sk_test"
    stripe_webhook_secret: str = "whsec_test"

    # LLM (OpenAI)
    openai_api_key: str = ""
    openai_model: str = "gpt-4.1-mini"

    # Rate limits
    rate_limit_auth: str = "5/minute"
    rate_limit_ai: str = "30/minute"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()