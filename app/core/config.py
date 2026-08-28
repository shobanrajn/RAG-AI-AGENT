import os
from functools import lru_cache
from dotenv import load_dotenv

load_dotenv()


class Settings:

    def __getattr__(self, name: str):
        key = name.upper()
        value = os.getenv(key)
        if value is None:
            raise RuntimeError(f"Missing required environment variable: {key}")
        return value

    def get(self, name: str, default=None, cast=None):
        value = os.getenv(name.upper())
        if value is None:
            return default
        if cast is not None:
            return cast(value)
        return value


@lru_cache
def get_settings():
    return Settings()


settings = get_settings()