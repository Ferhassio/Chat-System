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
    
    # Metrics
    METRICS_PORT: int = 9090
    ENABLE_TRACING: bool = True
    
    # Rate limiting
    DEFAULT_RATE_LIMIT: int = 100
    DEFAULT_RATE_LIMIT_PERIOD: int = 60
    
    # WebSocket
    WS_MESSAGE_QUEUE_SIZE: int = 100
    WS_HEARTBEAT_INTERVAL: int = 30
    
    # Telegram
    TELEGRAM_API_TIMEOUT: int = 30
    MAX_TELEGRAM_CONNECTIONS: int = 40
    TELEGRAM_RETRY_DELAY: int = 5
    
    # Message Queue
    MESSAGE_QUEUE_TIMEOUT: int = 30
    MAX_QUEUE_SIZE: int = 10000
    QUEUE_BATCH_SIZE: int = 100
    
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