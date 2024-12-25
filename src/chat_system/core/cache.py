from typing import Any, Optional
import json
import aioredis
from src.chat_system.core.config import settings

class RedisCache:
    def __init__(self):
        self._redis: Optional[aioredis.Redis] = None
        
    async def init_cache(self):
        """Initialize Redis connection pool"""
        self._redis = await aioredis.from_url(
            settings.REDIS_URL,
            encoding="utf-8",
            decode_responses=True,
            max_connections=settings.REDIS_MAX_CONNECTIONS
        )
    
    async def get(self, key: str) -> Any:
        """Get value from cache"""
        if not self._redis:
            return None
        value = await self._redis.get(key)
        return json.loads(value) if value else None
    
    async def set(self, key: str, value: Any, ttl: Optional[int] = None) -> bool:
        """Set value in cache with optional TTL"""
        if not self._redis:
            return False
        ttl = ttl or settings.REDIS_CACHE_TTL
        return await self._redis.set(
            key,
            json.dumps(value),
            ex=ttl
        )
    
    async def delete(self, key: str) -> bool:
        """Delete value from cache"""
        if not self._redis:
            return False
        return bool(await self._redis.delete(key))
    
    async def clear_all(self) -> bool:
        """Clear all cache"""
        if not self._redis:
            return False
        return bool(await self._redis.flushdb())
    
    async def close(self):
        """Close Redis connection"""
        if self._redis:
            await self._redis.close()

# Global cache instance
cache = RedisCache() 