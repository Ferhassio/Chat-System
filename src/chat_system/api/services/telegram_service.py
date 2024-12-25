from typing import Optional, Dict, Any
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.chat_system.core.decorators import cached
from src.chat_system.core.config import settings
from src.chat_system.db.models import User, TelegramProfile
from src.chat_system.core.cache import cache
from src.chat_system.api.services.photo_service import photo_service

class TelegramService:
    def __init__(self, session: AsyncSession):
        self.session = session
    
    @cached("telegram:user", ttl=settings.CACHE_USER_TTL)
    async def get_user_by_telegram_id(self, telegram_id: int) -> Optional[dict]:
        """Get user by Telegram ID with caching"""
        query = select(User).join(TelegramProfile).where(
            TelegramProfile.telegram_id == telegram_id
        )
        result = await self.session.execute(query)
        user = result.scalar_one_or_none()
        if user:
            user_dict = user.to_dict()
            # Добавляем пути к фотографиям
            user_dict['photos'] = photo_service.get_photo_paths(user.id)
            return user_dict
        return None
    
    @cached("telegram:state", ttl=300)  # 5 minutes cache for dialog states
    async def get_dialog_state(self, telegram_id: int) -> Optional[Dict[str, Any]]:
        """Get dialog state for Telegram user"""
        query = select(TelegramProfile).where(
            TelegramProfile.telegram_id == telegram_id
        )
        result = await self.session.execute(query)
        profile = result.scalar_one_or_none()
        return profile.dialog_state if profile else None
    
    async def update_dialog_state(
        self, 
        telegram_id: int, 
        state: Dict[str, Any]
    ) -> None:
        """Update dialog state and invalidate cache"""
        query = select(TelegramProfile).where(
            TelegramProfile.telegram_id == telegram_id
        )
        result = await self.session.execute(query)
        profile = result.scalar_one_or_none()
        
        if profile:
            profile.dialog_state = state
            await self.session.commit()
            # Инвалидируем кэш состояния диалога
            await cache.delete(f"telegram:state:{telegram_id}")
    
    @cached("telegram:settings", ttl=settings.CACHE_USER_TTL)
    async def get_telegram_settings(self, telegram_id: int) -> Optional[Dict[str, Any]]:
        """Get Telegram user settings"""
        query = select(TelegramProfile).where(
            TelegramProfile.telegram_id == telegram_id
        )
        result = await self.session.execute(query)
        profile = result.scalar_one_or_none()
        return profile.settings if profile else None
    
    async def update_telegram_settings(
        self, 
        telegram_id: int, 
        settings: Dict[str, Any]
    ) -> None:
        """Update Telegram settings and invalidate cache"""
        query = select(TelegramProfile).where(
            TelegramProfile.telegram_id == telegram_id
        )
        result = await self.session.execute(query)
        profile = result.scalar_one_or_none()
        
        if profile:
            profile.settings.update(settings)
            await self.session.commit()
            # Инвалидируем кэш настроек
            await cache.delete(f"telegram:settings:{telegram_id}")
    
    async def link_telegram_account(
        self, 
        user_id: int, 
        telegram_id: int, 
        username: str,
        photo_url: Optional[str] = None
    ) -> None:
        """Link Telegram account to user and save photo"""
        # Проверяем существующий профиль
        query = select(TelegramProfile).where(
            TelegramProfile.telegram_id == telegram_id
        )
        result = await self.session.execute(query)
        profile = result.scalar_one_or_none()
        
        if profile:
            # Обновляем существующий профиль
            profile.user_id = user_id
            profile.username = username
            if photo_url:
                profile.photo_url = photo_url
        else:
            # Создаем новый профиль
            profile = TelegramProfile(
                user_id=user_id,
                telegram_id=telegram_id,
                username=username,
                photo_url=photo_url
            )
            self.session.add(profile)
        
        await self.session.commit()
        
        # Сохраняем фото если есть
        if photo_url:
            await photo_service.save_telegram_photo(telegram_id, photo_url)
        
        # Инвалидируем все связанные кэши
        await cache.delete(f"telegram:user:{telegram_id}")
        await cache.delete(f"user:{user_id}")
        await cache.delete(f"telegram:settings:{telegram_id}")
        await cache.delete(f"telegram:state:{telegram_id}")
        await cache.delete(f"telegram:photo:{telegram_id}")
    
    async def unlink_telegram_account(
        self,
        telegram_id: int
    ) -> None:
        """Unlink Telegram account and cleanup photos"""
        query = select(TelegramProfile).where(
            TelegramProfile.telegram_id == telegram_id
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
            await cache.delete(f"telegram:user:{telegram_id}")
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