import logging
from datetime import datetime
from typing import Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.chat_system.db.models import Chat, Message
from src.chat_system.db.enums import MessageDirection

logger = logging.getLogger(__name__)

class MessageProcessor:
    """Process incoming and outgoing Telegram messages"""

    def __init__(self, session: AsyncSession):
        self._session = session
        self._logger = logging.getLogger(__name__)

    async def process_message(self, workspace_id: UUID, message: Message) -> None:
        """Process incoming message"""
        try:
            # Import here to avoid circular imports
            from src.chat_system.telegram.manager import telegram_manager
            
            # Get bot info to check message ownership
            bot_info = await telegram_manager.get_bot_info(workspace_id)
            if not bot_info:
                logger.error(f"Bot info not found for workspace {workspace_id}")
                return

            # Process all messages in the chat where this bot is a participant
            # We don't need to check bot_info.id here as it's a different concept in Telegram
            logger.info(f"Processing message from chat {message.chat.id} in workspace {workspace_id}")

            # Get or create chat
            result = await self._session.execute(
                select(Chat).where(
                    Chat.workspace_id == workspace_id,
                    Chat.telegram_id == message.chat.id,
                )
            )
            chat = result.scalar_one_or_none()
            
            if not chat:
                chat = Chat(
                    workspace_id=workspace_id,
                    telegram_id=message.chat.id,
                    username=message.chat.username or "",
                )
                self._session.add(chat)
                await self._session.flush()
                logger.info(f"Created new chat: {chat.id} for telegram_id: {message.chat.id}")
            
            # Check if message already exists
            existing_message = await self._session.execute(
                select(Message).where(
                    Message.chat_id == chat.id,
                    Message.sent_at == message.date.replace(tzinfo=None),
                    Message.content == (message.text or "")
                )
            )
            if existing_message.scalar_one_or_none():
                logger.debug("Message already exists, skipping")
                return
            
            # Create message
            db_message = Message(
                chat_id=chat.id,
                content=message.text or "",
                sent_at=message.date.replace(tzinfo=None),
                direction=MessageDirection.INCOMING if message.from_user.id != bot_info.id else MessageDirection.OUTGOING,
            )
            self._session.add(db_message)
            
            # Update chat's last message time
            chat.last_message_at = message.date.replace(tzinfo=None)
            logger.info(f"Added message to chat {chat.id}: {message.text[:50] if message.text else ''}")
            
            await self._session.commit()
            
        except Exception as e:
            logger.error(f"Error processing message: {str(e)}", exc_info=True)
            await self._session.rollback()

    async def process_outgoing_message(
        self,
        workspace_id: UUID,
        telegram_id: int,
        text: str,
    ) -> None:
        """Process an outgoing message"""
        self._logger.info(f"Processing outgoing message for workspace {workspace_id} to chat {telegram_id}")
        
        try:
            # Get chat
            chat = await self._session.execute(
                select(Chat).where(
                    Chat.workspace_id == workspace_id,
                    Chat.telegram_id == telegram_id,
                )
            )
            chat = chat.scalar_one_or_none()
            
            if not chat:
                self._logger.error("Chat not found")
                return
            
            # Create message and update chat in one go
            sent_at = datetime.utcnow()
            message = Message(
                chat_id=chat.id,
                content=text,
                sent_at=sent_at,
                direction=MessageDirection.OUTGOING,
            )
            chat.last_message_at = sent_at
            
            self._session.add(message)
            await self._session.flush()
            
        except Exception as e:
            self._logger.error(f"Failed to process outgoing message: {str(e)}", exc_info=True)
            raise

    async def _get_or_create_chat(
        self, workspace_id: UUID, telegram_id: int, username: str
    ) -> Optional[Chat]:
        """Get existing chat or create new one"""
        try:
            # Try to get existing chat
            self._logger.info(f"Looking for existing chat with telegram_id {telegram_id}")
            chat = await self._session.execute(
                select(Chat).where(
                    Chat.workspace_id == workspace_id,
                    Chat.telegram_id == telegram_id,
                )
            )
            chat = chat.scalar_one_or_none()
            
            if chat:
                self._logger.info(f"Found existing chat: {chat.id}")
                # Update username if changed
                if chat.username != username:
                    self._logger.info(f"Updating username from {chat.username} to {username}")
                    chat.username = username
                    await self._session.flush()
                return chat
            
            # Create new chat
            self._logger.info("Creating new chat")
            chat = Chat(
                workspace_id=workspace_id,
                telegram_id=telegram_id,
                username=username,
            )
            self._session.add(chat)
            await self._session.flush()
            self._logger.info(f"Created new chat: {chat.id}")
            return chat
            
        except Exception as e:
            self._logger.error(f"Error in get_or_create_chat: {str(e)}", exc_info=True)
            return None

    async def _get_chat(
        self, workspace_id: UUID, telegram_id: int
    ) -> Optional[Chat]:
        """Get existing chat"""
        try:
            # Get chat
            self._logger.info(f"Looking for chat with telegram_id {telegram_id}")
            chat = await self._session.execute(
                select(Chat).where(
                    Chat.workspace_id == workspace_id,
                    Chat.telegram_id == telegram_id,
                )
            )
            chat = chat.scalar_one_or_none()
            
            if chat:
                self._logger.info(f"Found chat: {chat.id}")
                return chat
            
            self._logger.error("Chat not found")
            return None
            
        except Exception as e:
            self._logger.error(f"Error in get_chat: {str(e)}", exc_info=True)
            return None 