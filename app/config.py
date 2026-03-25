from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    app_name: str = "AI Case Comp"
    app_env: str = "development"
    app_version: str = "1.0.0"

    supabase_url: str = Field(..., alias="SUPABASE_URL")
    supabase_default_key: str = Field(..., alias="SUPABASE_DEFAULT_KEY")
    supabase_service_role_key: str = Field(..., alias="SUPABASE_SERVICE_ROLE_KEY")


@lru_cache
def get_settings() -> Settings:
    return Settings()
