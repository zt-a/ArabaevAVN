from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    BOT_TOKEN: str = Field(default="")
    REDIS_URL: str = Field(default="redis://localhost:6379/0")
    DB_URL: str = Field(default="sqlite:///./avn_bot.db")
    CHECK_INTERVAL_MINUTES: int = Field(default=5)
    TIMEZONE: str = Field(default="Asia/Bishkek")
    NOTIFY_BEFORE_MINUTES: list[int] = Field(default=[10, 5])
    NOTIFY_AT_END: bool = Field(default=True)
    NOTIFY_BREAK_START_END: bool = Field(default=True)
    ADMIN_IDS: list[int] = Field(default=[])
    USER_AGENT: str = Field(default="Mozilla/5.0 (compatible; AVNBot/1.0)")
    LOG_LEVEL: str = Field(default="INFO")


settings = Settings()
