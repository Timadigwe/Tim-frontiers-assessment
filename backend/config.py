"""Environment-backed settings."""

from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    mcp_server_url: str = "https://order-mcp-74afyau24q-uc.a.run.app/mcp"
    openrouter_api_key: str = ""
    openrouter_model: str = "openai/gpt-4o-mini"
    openrouter_referer: str = "https://example.com"
    openrouter_title: str = "Support Assistant"
    session_store_dir: str = "/tmp/chat-sessions"


@lru_cache
def get_settings() -> Settings:
    return Settings()
