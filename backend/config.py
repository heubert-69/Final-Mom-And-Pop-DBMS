from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    # Oracle DB
    oracle_user: str = "delivery_user"
    oracle_password: str = "delivery_pass"
    oracle_dsn: str = "localhost:1521/XEPDB1"

    # JWT
    secret_key: str = "super-secret-change-in-production-please"
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 60 * 24  # 24 hours

    # App
    app_name: str = "Delivery Management System"
    debug: bool = False

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


@lru_cache()
def get_settings() -> Settings:
    return Settings()
