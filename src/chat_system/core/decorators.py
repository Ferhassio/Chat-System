from functools import wraps
from typing import Any, Callable, Optional
from src.chat_system.core.cache import cache

def cached(prefix: str, ttl: Optional[int] = None):
    """
    Decorator for caching function results in Redis
    
    :param prefix: Prefix for cache key
    :param ttl: Time to live in seconds
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(*args, **kwargs) -> Any:
            # Generate cache key
            key_parts = [prefix]
            key_parts.extend(str(arg) for arg in args)
            key_parts.extend(f"{k}:{v}" for k, v in sorted(kwargs.items()))
            cache_key = ":".join(key_parts)
            
            # Try to get from cache
            cached_value = await cache.get(cache_key)
            if cached_value is not None:
                return cached_value
            
            # If not in cache, execute function
            result = await func(*args, **kwargs)
            
            # Cache the result
            await cache.set(cache_key, result, ttl)
            
            return result
        return wrapper
    return decorator 