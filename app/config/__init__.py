# pylint: disable=too-few-public-methods
"""
Settings Class :: For managing service settings
"""
import os
from functools import lru_cache
from pathlib import Path
from typing import Literal, Optional

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    Settings class manages loading the configuration
    settings based on env variables and files
    """

    log_level: str = "INFO"
    log_format: str = "[%(asctime)s] [%(levelname)s] %(message)s"
    thread_count: int = 1
    enable_local_log_handler: bool = False
    connection_fallback_email: Optional[str] = "admin@lyric.tech"



@lru_cache()
def get_settings() -> Settings:
    """
    Returns one single instance of settings
    """
    return Settings()
