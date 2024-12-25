from typing import Optional, List
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.chat_system.core.decorators import cached
from src.chat_system.core.config import settings
from src.chat_system.db.models import Chat, Message, User
from src.chat_system.core.cache import cache

class ChatService:
    def __init__(self, session: AsyncSession):
        self.session = session
    
    @cached("chat", ttl=settings.CACHE_CHAT_TTL)
    async def get_chat(self, chat_id: int) -> Optional[dict]:
        """Get chat by ID with caching"""
        query = select(Chat).where(Chat.id == chat_id)
        result = await self.session.execute(query)
        chat = result.scalar_one_or_none()
        return chat.to_dict() if chat else None
    
    @cached("chat:messages", ttl=settings.CACHE_MESSAGE_TTL)
    async def get_chat_messages(
        self, 
        chat_id: int, 
        limit: int = 50, 
        offset: int = 0
    ) -> List[dict]:
        """Get chat messages with pagination and caching"""
        query = select(Message).where(
            Message.chat_id == chat_id
        ).order_by(
            Message.created_at.desc()
        ).limit(limit).offset(offset)
        
        result = await self.session.execute(query)
        messages = result.scalars().all()
        return [msg.to_dict() for msg in messages]
    
    @cached("user:chats", ttl=settings.CACHE_CHAT_TTL)
    async def get_user_chats(self, user_id: int) -> List[dict]:
        """Get user chats with caching"""
        query = select(Chat).join(
            Chat.participants
        ).where(User.id == user_id)
        result = await self.session.execute(query)
        chats = result.scalars().all()
        return [chat.to_dict() for chat in chats]
    
    async def add_message(self, chat_id: int, user_id: int, content: str) -> dict:
        """Add new message and invalidate relevant caches"""
        message = Message(
            chat_id=chat_id,
            user_id=user_id,
            content=content
        )
        self.session.add(message)
        await self.session.commit()
        
        # Инвалидируем кэш сообщений чата
        await cache.delete(f"chat:messages:{chat_id}")
        
        # Обновляем last_message в чате
        chat = await self.session.get(Chat, chat_id)
        if chat:
            chat.last_message = message
            chat.last_message_at = message.created_at
            await self.session.commit()
            await cache.delete(f"chat:{chat_id}")
        
        return message.to_dict()
    
    @cached("chat:unread", ttl=settings.CACHE_MESSAGE_TTL)
    async def get_unread_messages_count(self, chat_id: int, user_id: int) -> int:
        """Get number of unread messages for user in chat"""
        query = select(Message).where(
            Message.chat_id == chat_id,
            Message.user_id != user_id,
            Message.is_read == False
        )
        result = await self.session.execute(query)
        return len(result.scalars().all())
    
    async def mark_messages_read(self, chat_id: int, user_id: int) -> None:
        """Mark messages as read and invalidate cache"""
        query = select(Message).where(
            Message.chat_id == chat_id,
            Message.user_id != user_id,
            Message.is_read == False
        )
        result = await self.session.execute(query)
        messages = result.scalars().all()
        
        for message in messages:
            message.is_read = True
        
        await self.session.commit()
        
        # Инвалидируем кэш непрочитанных сообщений
        await cache.delete(f"chat:unread:{chat_id}:{user_id}")
        # Инвалидируем кэш сообщений чата
        await cache.delete(f"chat:messages:{chat_id}") 