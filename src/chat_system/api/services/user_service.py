from typing import Optional, List
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.chat_system.core.decorators import cached
from src.chat_system.core.config import settings
from src.chat_system.db.models import User
from src.chat_system.api.schemas import UserCreate, UserUpdate

class UserService:
    def __init__(self, session: AsyncSession):
        self.session = session
    
    @cached("user", ttl=settings.CACHE_USER_TTL)
    async def get_user(self, user_id: int) -> Optional[dict]:
        """Get user by ID with caching"""
        query = select(User).where(User.id == user_id)
        result = await self.session.execute(query)
        user = result.scalar_one_or_none()
        return user.to_dict() if user else None
    
    @cached("user:profile", ttl=settings.CACHE_USER_TTL)
    async def get_user_profile(self, user_id: int) -> Optional[dict]:
        """Get user profile with extended information"""
        user = await self.get_user(user_id)
        if not user:
            return None
            
        # Добавляем дополнительную инфор��ацию
        query = select(
            User.total_messages,
            User.last_seen,
            User.status
        ).where(User.id == user_id)
        result = await self.session.execute(query)
        profile_data = result.first()
        
        if profile_data:
            user.update({
                "total_messages": profile_data.total_messages,
                "last_seen": profile_data.last_seen,
                "status": profile_data.status
            })
        return user
    
    @cached("user:contacts", ttl=settings.CACHE_USER_TTL)
    async def get_user_contacts(self, user_id: int) -> List[dict]:
        """Get user contacts with caching"""
        query = select(User).join(
            User.contacts
        ).where(User.id == user_id)
        result = await self.session.execute(query)
        contacts = result.scalars().all()
        return [contact.to_dict() for contact in contacts]
    
    async def update_user(self, user_id: int, user_data: UserUpdate) -> Optional[dict]:
        """Update user data and invalidate cache"""
        query = select(User).where(User.id == user_id)
        result = await self.session.execute(query)
        user = result.scalar_one_or_none()
        
        if not user:
            return None
            
        for field, value in user_data.dict(exclude_unset=True).items():
            setattr(user, field, value)
        
        await self.session.commit()
        
        # Инвалидируем кэш для обновленного пользователя
        await cache.delete(f"user:{user_id}")
        await cache.delete(f"user:profile:{user_id}")
        await cache.delete(f"user:contacts:{user_id}")
        
        return user.to_dict() 