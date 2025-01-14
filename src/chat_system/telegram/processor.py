import logging
from datetime import datetime
from uuid import UUID
import aiohttp
import base64
from typing import Optional

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import func

from src.chat_system.db.models import Chat, Message, Bot
from src.chat_system.db.enums import MessageDirection
from src.chat_system.api.services.chat_service import ChatService

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

    async def _update_chat_photo(self, chat: Chat, photo_url: Optional[str]) -> None:
        """Update chat photo if needed"""
        if not photo_url:
            return
            
        try:
            photo_data = await self._get_photo_data(photo_url)
            if photo_data:
                # Use chat service to update photo with proper caching
                chat_service = ChatService(self._session)
                await chat_service.update_chat_photo(chat.id, photo_data)
                logger.info(f"Updated photo for chat {chat.id}")
        except Exception as e:
            logger.error(f"Failed to update chat photo: {e}")
            # Don't raise the error to avoid breaking the main flow

    async def _get_or_create_chat(
        self,
        workspace_id: UUID,
        telegram_id: int,
        bot_id: UUID,
        username: str = None,
        photo_url: str = None
    ) -> Chat:
        """Get existing chat or create new one"""
        result = await self._session.execute(
            select(Chat).where(
                Chat.workspace_id == workspace_id,
                Chat.telegram_id == telegram_id,
                Chat.bot_id == bot_id,
            )
        )
        chat = result.scalar_one_or_none()
        
        if not chat:
            chat = Chat(
                workspace_id=workspace_id,
                telegram_id=telegram_id,
                bot_id=bot_id,
                username=username or "",
            )
            self._session.add(chat)
            await self._session.flush()
            self._logger.info(f"Created new chat: {chat.id} for telegram_id: {telegram_id} with bot: {bot_id}")
        elif username and chat.username != username:
            # Update username if changed
            chat.username = username
            await self._session.flush()
            self._logger.info(f"Updated username for chat {chat.id} to {username}")
        
        # Update photo if provided
        if photo_url:
            await self._update_chat_photo(chat, photo_url)
        
        return chat

    async def _save_message(self, chat_id: UUID, content: str, sent_at: datetime) -> Message:
        """Save new message"""
        # Get chat to check message ownership
        result = await self._session.execute(
            select(Chat).where(Chat.id == chat_id)
        )
        chat = result.scalar_one()
        
        message = Message(
            chat_id=chat_id,
            content=content,
            sent_at=sent_at.replace(tzinfo=None),
            direction=MessageDirection.INCOMING
        )
        
        # Update chat's last message and set unread flag
        chat.last_message_at = sent_at.replace(tzinfo=None)
        chat.has_unread = True
        
        self._session.add(message)
        await self._session.flush()
        
        return message

    async def process_message(self, workspace_id: UUID, message: Message, bot_id: UUID) -> None:
        """Process incoming message"""
        try:
            if not message or not message.chat:
                self._logger.error("Invalid message object")
                return
                
            self._logger.info(f"Processing message from chat {message.chat.id} in workspace {workspace_id}")
            
            # Get or create chat
            chat = await self._get_or_create_chat(
                workspace_id=workspace_id,
                telegram_id=message.chat.id,
                bot_id=bot_id,
                username=message.chat.username
            )
            
            # Get user photo if available
            try:
                if message.from_user:
                    self._logger.info(f"Getting photos for user {message.from_user.id}")
                    photos = await message.from_user.get_profile_photos()
                    if photos and photos.total_count > 0:
                        self._logger.info(f"Found {photos.total_count} photos")
                        photo = photos.photos[0][-1]  # Get the last (smallest) size of the first photo
                        file = await photo.get_file()
                        self._logger.info(f"Raw file path from Telegram: {file.file_path}")
                        
                        # Extract only the file path if it's a full URL
                        file_path = file.file_path
                        if file_path.startswith('https://'):
                            file_path = file_path.split('/photos/')[-1]
                        
                        # Get bot token for photo URL
                        result = await self._session.execute(
                            select(Bot).where(Bot.id == bot_id)
                        )
                        bot = result.scalar_one_or_none()
                        if bot:
                            # Generate clean photo URL
                            photo_url = f"https://api.telegram.org/file/bot{bot.token}/photos/{file_path}"
                            self._logger.info(f"Generated photo URL: {photo_url}")
                            
                            # Update chat with photo
                            await self._update_chat_photo(chat, photo_url)
                        else:
                            self._logger.error(f"Bot not found for id {bot_id}")
                    else:
                        self._logger.info("No photos found for user")
            except Exception as e:
                self._logger.error(f"Failed to get user photo: {str(e)}", exc_info=True)
            
            # Only save message if it has text content
            if message.text:
                await self._save_message(
                    chat_id=chat.id,
                    content=message.text,
                    sent_at=message.date
                )
                
                await self._session.commit()
                self._logger.info(f"Successfully saved message to chat {chat.id}")
            else:
                self._logger.info("Skipping message without text content")
            
        except Exception as e:
            self._logger.error(f"Error processing message: {str(e)}", exc_info=True)
            await self._session.rollback()
            raise

    async def process_outgoing_message(
        self,
        workspace_id: UUID,
        telegram_id: int,
        bot_id: UUID,
        text: str,
    ) -> None:
        """Process outgoing message"""
        try:
            if not text or not text.strip():
                logger.error("Empty message text")
                return

            # Get chat
            result = await self._session.execute(
                select(Chat).where(
                    Chat.workspace_id == workspace_id,
                    Chat.telegram_id == telegram_id,
                    Chat.bot_id == bot_id,
                )
            )
            chat = result.scalar_one_or_none()
            
            if not chat:
                logger.error(f"Chat not found for workspace_id={workspace_id}, telegram_id={telegram_id}, bot_id={bot_id}")
                return
            
            # Create message and update chat
            sent_at = datetime.utcnow()
            message = Message(
                chat_id=chat.id,
                content=text.strip(),
                sent_at=sent_at,
                direction=MessageDirection.OUTGOING,
            )
            chat.last_message_at = sent_at
            
            self._session.add(message)
            await self._session.commit()
            logger.info(f"Successfully saved outgoing message to chat {chat.id}")
            
        except Exception as e:
            logger.error(f"Error processing outgoing message: {str(e)}", exc_info=True)
            await self._session.rollback()
            raise 