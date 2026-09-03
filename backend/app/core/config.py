from functools import lru_cache
from pathlib import Path
from urllib.parse import quote_plus

from pydantic import AliasChoices, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore", case_sensitive=False
    )

    app_name: str = "Shaverma-chi"
    business_name: str = "شاورماچی"
    brand_tagline: str = "Run your business with clarity"
    brand_primary_color: str = "#2563eb"
    brand_logo_url: str | None = None
    app_locale: str = "fa"
    app_timezone: str = "Asia/Tehran"
    business_day_start_hour: int = Field(default=5, ge=0, le=23)
    currency_label: str = "تومان"
    app_env: str = "development"
    app_secret_key: str = Field(default="development-only-secret-change-me-please")
    access_token_minutes: int = 480
    api_host: str = "0.0.0.0"
    api_port: int = 8100
    upload_dir: Path = Path("uploads")
    max_upload_mb: int = 5

    database_host: str = Field(
        default="127.0.0.1", validation_alias=AliasChoices("DATABASE_HOST", "MYSQL_HOST")
    )
    database_port: int = Field(default=3306, validation_alias=AliasChoices("DATABASE_PORT", "MYSQL_PORT"))
    database_name: str = Field(
        default="blue_me", validation_alias=AliasChoices("DATABASE_NAME", "MYSQL_DATABASE")
    )
    database_user: str = Field(
        default="blue_me", validation_alias=AliasChoices("DATABASE_USER", "MYSQL_USER")
    )
    database_password: str = Field(
        default="blue_me", validation_alias=AliasChoices("DATABASE_PASSWORD", "MYSQL_PASSWORD")
    )
    database_url_override: str | None = None

    root_username: str = "root"
    root_password: str = "change-me-now"
    root_full_name: str = "Root Administrator"

    @field_validator("brand_primary_color")
    @classmethod
    def valid_hex_color(cls, value: str) -> str:
        if len(value) != 7 or not value.startswith("#"):
            return "#2563eb"
        try:
            int(value[1:], 16)
        except ValueError:
            return "#2563eb"
        return value.lower()

    @property
    def database_url(self) -> str:
        if self.database_url_override:
            return self.database_url_override
        return (
            "mysql+pymysql://"
            f"{quote_plus(self.database_user)}:{quote_plus(self.database_password)}@"
            f"{self.database_host}:{self.database_port}/{self.database_name}?charset=utf8mb4"
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
