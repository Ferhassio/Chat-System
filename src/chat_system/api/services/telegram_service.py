from typing import Optional, Dict, Any, UUID
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.chat_system.core.decorators import cached
from src.chat_system.core.config import settings
from src.chat_system.db.models import User
from src.chat_system.core.cache import cache

class TelegramService:
    def __init__(self, session: AsyncSession):
        self.session = session
    
    @cached("telegram:user", ttl=settings.CACHE_USER_TTL)
    async def get_user_by_telegram_id(self, telegram_id: int, bot_id: UUID) -> Optional[dict]:
        """Get user by Telegram ID and Bot ID with caching"""
        query = select(User).where(
            User.telegram_id == telegram_id,
            User.bot_id == bot_id
        )
        result = await self.session.execute(query)
        user = result.scalar_one_or_none()
        if user:
            return user.to_dict()
        return None
    
    async def link_telegram_account(
        self, 
        user_id: int, 
        telegram_id: int, 
        bot_id: UUID,
        username: str,
        photo_url: Optional[str] = None
    ) -> None:
        """Link Telegram account to user with Bot ID"""
        user = await self.session.get(User, user_id)
        if user:
            user.telegram_id = telegram_id
            user.bot_id = bot_id
            await self.session.commit()
            
            # Invalidate user cache
            await cache.delete(f"telegram:user:{telegram_id}:{bot_id}")
            await cache.delete(f"user:{user_id}")
    
    async def unlink_telegram_account(
        self,
        telegram_id: int,
        bot_id: UUID
    ) -> None:
        """Unlink Telegram account and cleanup photos with Bot ID"""
        query = select(TelegramProfile).where(
            TelegramProfile.telegram_id == telegram_id,
            TelegramProfile.bot_id == bot_id
        )
        result = await self.session.execute(query)
        profile = result.scalar_one_or_none()
        
        if profile:
            user_id = profile.user_id
            await self.session.delete(profile)
            await self.session.commit()
            
            # Удаляем фотографии
            await photo_service.delete_user_photos(user_id)
            
            # Инвалидируем кэши
            await cache.delete(f"telegram:user:{telegram_id}:{bot_id}")
            await cache.delete(f"user:{user_id}")
            await cache.delete(f"telegram:settings:{telegram_id}")
            await cache.delete(f"telegram:state:{telegram_id}")
            await cache.delete(f"telegram:photo:{user_id}")
    
    async def update_user_photo(
        self, 
        telegram_id: int, 
        photo_url: str
    ) -> Optional[Dict[str, str]]:
        """Update user's photo from Telegram"""
        query = select(User).join(TelegramProfile).where(
            TelegramProfile.telegram_id == telegram_id
        )
        result = await self.session.execute(query)
        user = result.scalar_one_or_none()
        
        if not user:
            return None
            
        # Сохраняем фото и получаем пути
        photo_paths = await photo_service.save_telegram_photo(
            user.id,
            photo_url
        )
        
        if photo_paths:
            # Обновляем информацию о фото в профиле
            profile = await self.session.get(TelegramProfile, telegram_id)
            if profile:
                profile.photo_url = photo_url
                await self.session.commit()
                
                # Инвалидируем кэш пользователя
                await cache.delete(f"telegram:user:{telegram_id}")
                await cache.delete(f"user:{user.id}")
        
        return photo_paths 