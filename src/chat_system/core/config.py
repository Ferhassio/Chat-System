import os
from pathlib import Path
from typing import Optional

from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    """Application settings"""
    
    # Base
    DEBUG: bool = False
    SECRET_KEY: str = "your-super-secret-key-here-please-change-in-production"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24  # 24 hours
    
    # Database
    DATABASE_URL: str = "postgresql+asyncpg://postgres:VetkaSotona666@localhost:5432/chat_system"
    
    # Redis
    REDIS_URL: str = "redis://localhost:6379/0"
    REDIS_CACHE_TTL: int = 3600  # 1 hour default TTL
    REDIS_MAX_CONNECTIONS: int = 100
    
    # Storage
    STORAGE_PATH: str = "storage"
    AVATAR_PATH: str = "storage/avatars"
    AVATAR_SIZES: dict = {
        "small": (64, 64),
        "medium": (128, 128),
        "large": (256, 256)
    }
    AVATAR_FORMAT: str = "JPEG"
    AVATAR_QUALITY: int = 85
    
    # Metrics
    METRICS_PORT: int = 9090
    ENABLE_TRACING: bool = True
    
    # Rate limiting
    DEFAULT_RATE_LIMIT: int = 300  # Увеличено с 100
    DEFAULT_RATE_LIMIT_PERIOD: int = 60
    
    # WebSocket
    WS_MESSAGE_QUEUE_SIZE: int = 1000  # Увеличено со 100
    WS_HEARTBEAT_INTERVAL: int = 30
    
    # Telegram
    TELEGRAM_API_TIMEOUT: int = 30
    MAX_TELEGRAM_CONNECTIONS: int = 150  # Увеличено с 40
    TELEGRAM_RETRY_DELAY: int = 5
    TELEGRAM_PHOTO_TTL: int = 86400  # 24 hours cache for photos
    
    # Message Queue
    MESSAGE_QUEUE_TIMEOUT: int = 30
    MAX_QUEUE_SIZE: int = 50000  # Увеличено с 10000
    QUEUE_BATCH_SIZE: int = 200  # Увеличено со 100
    
    # Cache settings
    CACHE_USER_TTL: int = 1800  # 30 minutes
    CACHE_CHAT_TTL: int = 3600  # 1 hour
    CACHE_MESSAGE_TTL: int = 7200  # 2 hours
    
    class Config:
        env_file = ".env"
        case_sensitive = True

# Create settings instance
settings = Settings()

# Ensure required directories exist
BASE_DIR = Path(__file__).resolve().parent.parent.parent.parent
TEMPLATES_DIR = BASE_DIR / "templates"
STATIC_DIR = BASE_DIR / "static"

for directory in [TEMPLATES_DIR, STATIC_DIR]:
    directory.mkdir(exist_ok=True) 