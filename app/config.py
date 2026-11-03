from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    openai_api_key: str = ""
    openai_model: str = "gpt-4o-mini"
    access_token: str = ""
    github_token: str = ""
    render: bool = False
    database_url: str = ""
    deployment_notice: str = ""
    db_path: str = "data/investigations.sqlite3"
    source_mode: Literal["github", "snapshot"] = "github"
    provider: Literal["openai", "sample"] = "openai"
    max_daily_runs: int = Field(default=20, ge=1, le=100)
    max_stored_runs: int = Field(default=200, ge=1, le=1000)
