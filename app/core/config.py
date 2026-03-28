from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    database_url: str = "sqlite+aiosqlite:///./university.db"
    secret_key: str = "super-secret-key-change-me"
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 60
    qr_refresh_interval: int = 60

    class Config:
        extra = "ignore"


@lru_cache()
def get_settings():
    return Settings()

settings = get_settings()
