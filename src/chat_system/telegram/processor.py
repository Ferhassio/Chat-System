import logging
from datetime import datetime
from uuid import UUID
import aiohttp
import base64
from typing import Optional

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import func

from src.chat_system.db.models import Chat, Message
from src.chat_system.db.enums import MessageDirection

logger = logging.getLogger(__name__)

class MessageProcessor:
    def __init__(self, session: AsyncSession):
        self._session = session
        self._logger = logging.getLogger(__name__)

    async def _get_photo_data(self, photo_url: str) -> Optional[bytes]:
        """Download photo from Telegram and convert to bytes"""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(photo_url) as response:
                    if response.status == 200:
                        return await response.read()
        except Exception as e:
            self._logger.error(f"Failed to download photo: {str(e)}")
        return None

    async def _update_chat_photo(self, chat_id: UUID, photo_url: str) -> None:
        """Update chat's photo data"""
        try:
            photo_data = await self._get_photo_data(photo_url)
            if photo_data:
                await self._session.execute(
                    update(Chat)
                    .where(Chat.id == chat_id)
                    .values(
                        photo_url=photo_url,
                        photo_data=photo_data,
                        updated_at=func.now()
                    )
                )
                await self._session.commit()
                self._logger.info(f"Updated chat photo data for chat {chat_id}")
            else:
                self._logger.error(f"Failed to download photo data from {photo_url}")
        except Exception as e:
            self._logger.error(f"Error updating chat photo: {str(e)}")
            await self._session.rollback()

    async def _get_or_create_chat(
        self,
        workspace_id: UUID,
        telegram_id: int,
        username: str = None,
        photo_url: str = None
    ) -> Chat:
        """Get existing chat or create new one"""
        result = await self._session.execute(
            select(Chat).where(
                Chat.workspace_id == workspace_id,
                Chat.telegram_id == telegram_id,
            )
        )
        chat = result.scalar_one_or_none()
        
        if not chat:
            chat = Chat(
                workspace_id=workspace_id,
                telegram_id=telegram_id,
                username=username or "",
            )
            self._session.add(chat)
            await self._session.flush()
            self._logger.info(f"Created new chat: {chat.id} for telegram_id: {telegram_id}")
        
        # Update photo if provided
        if photo_url:
            await self._update_chat_photo(chat.id, photo_url)
        
        return chat

    async def _save_message(self, chat_id: UUID, content: str, sent_at: datetime) -> Message:
        """Save new message"""
        # Import here to avoid circular imports
        from src.chat_system.telegram.manager import telegram_manager
        
        # Get bot info to check message ownership
        workspace_id = None
        result = await self._session.execute(
            select(Chat.workspace_id).where(Chat.id == chat_id)
        )
        workspace_id = result.scalar_one()
        
        bot_info = await telegram_manager.get_bot_info(workspace_id)
        if not bot_info:
            raise ValueError(f"Bot info not found for workspace {workspace_id}")

        message = Message(
            chat_id=chat_id,
            content=content,
            sent_at=sent_at.replace(tzinfo=None),
            direction=MessageDirection.INCOMING
        )
        
        # Update chat's last message
        result = await self._session.execute(
            select(Chat).where(Chat.id == chat_id)
        )
        chat = result.scalar_one()
        chat.last_message_at = sent_at.replace(tzinfo=None)
        
        self._session.add(message)
        await self._session.flush()
        
        return message

    async def process_message(self, workspace_id: UUID, message: Message) -> None:
        """Process incoming message"""
        try:
            # Import here to avoid circular imports
            from src.chat_system.telegram.manager import telegram_manager
            
            self._logger.info(f"Processing message from chat {message.chat.id} in workspace {workspace_id}")
            
            # Get or create chat
            chat = await self._get_or_create_chat(workspace_id, message.chat.id, message.chat.username)
            
            # Get user photo if available
            try:
                self._logger.info(f"Getting photos for user {message.from_user.id}")
                photos = await message.from_user.get_profile_photos()
                if photos and photos.total_count > 0:
                    self._logger.info(f"Found {photos.total_count} photos")
                    photo = photos.photos[0][-1]  # Get the last (smallest) size of the first photo
                    file = await photo.get_file()
                    self._logger.info(f"Raw file path from Telegram: {file.file_path}")
                    
                    # Get bot info to get token
                    bot_info = await telegram_manager.get_bot_info(workspace_id)
                    if not bot_info:
                        raise ValueError(f"Bot info not found for workspace {workspace_id}")
                    
                    # Extract only the file path if it's a full URL
                    file_path = file.file_path
                    if file_path.startswith('https://'):
                        file_path = file_path.split('/photos/')[-1]
                    
                    # Generate clean photo URL
                    photo_url = f"https://api.telegram.org/file/bot{bot_info['token']}/photos/{file_path}"
                    self._logger.info(f"Generated photo URL: {photo_url}")
                    
                    # Update chat with photo
                    await self._update_chat_photo(chat.id, photo_url)
                else:
                    self._logger.info("No photos found for user")
            except Exception as e:
                self._logger.error(f"Failed to get user photo: {str(e)}", exc_info=True)
            
            # Save message
            await self._save_message(
                chat_id=chat.id,
                content=message.text or "",
                sent_at=message.date
            )
            
            await self._session.commit()
            self._logger.info(f"Successfully saved message to chat {chat.id}")
            
        except Exception as e:
            self._logger.error(f"Error processing message: {str(e)}")
            raise

    async def process_outgoing_message(
        self,
        workspace_id: UUID,
        telegram_id: int,
        text: str,
    ) -> None:
        """Process outgoing message"""
        try:
            # Get chat
            result = await self._session.execute(
                select(Chat).where(
                    Chat.workspace_id == workspace_id,
                    Chat.telegram_id == telegram_id,
                )
            )
            chat = result.scalar_one_or_none()
            
            if not chat:
                logger.error("Chat not found")
                return
            
            # Create message and update chat
            sent_at = datetime.utcnow()
            message = Message(
                chat_id=chat.id,
                content=text,
                sent_at=sent_at,
                direction=MessageDirection.OUTGOING,
            )
            chat.last_message_at = sent_at
            
            self._session.add(message)
            await self._session.commit()
            
        except Exception as e:
            logger.error(f"Error processing outgoing message: {str(e)}")
            raise 