import telegram
from telegram import Update
from telegram.ext import Application, ContextTypes, MessageHandler, filters
from telegram.error import TimedOut
from sqlalchemy import select

from uuid import UUID
import logging
import asyncio

from src.chat_system.core.config import settings
from src.chat_system.telegram.processor import MessageProcessor
from src.chat_system.db.session import async_session_factory
from src.chat_system.db.models import Bot

logger = logging.getLogger(__name__)

class TelegramManager:
    def __init__(self):
        self._bots: dict[UUID, Application] = {}
        self._workspace_by_token: dict[str, UUID] = {}
        self._session_factory = async_session_factory

    async def initialize_from_db(self):
        """Initialize bots from database"""
        try:
            async with self._session_factory() as session:
                # Get all active bots
                result = await session.execute(
                    select(Bot).where(Bot.is_active == True)
                )
                bots = result.scalars().all()
                
                # Initialize each bot
                for bot in bots:
                    await self.initialize_bot(bot.workspace_id, bot.token)
                    
                logger.info(f"Initialized {len(bots)} bots from database")
        except Exception as e:
            logger.error(f"Failed to initialize bots from database: {str(e)}", exc_info=True)

    async def initialize_bot(self, workspace_id: UUID, token: str) -> bool:
        """Initialize a new bot for the workspace"""
        try:
            logger.info(f"Starting bot initialization for workspace {workspace_id}")
            
            # Create bot application with adjusted connection pool settings
            application = (
                Application.builder()
                .token(token)
                .connect_timeout(settings.TELEGRAM_API_TIMEOUT)
                .pool_timeout(30.0)  # Increase pool timeout
                .connection_pool_size(8)  # Increase pool size
                .concurrent_updates(True)
                .build()
            )
            
            # Add message handlers
            application.add_handler(
                MessageHandler(
                    filters.TEXT,
                    self._handle_message
                )
            )
            
            # Start the bot
            logger.info("Initializing bot application...")
            await application.initialize()
            logger.info("Starting bot application...")
            await application.start()
            logger.info("Starting polling...")
            await application.updater.start_polling(
                allowed_updates=['message'],
                drop_pending_updates=True,
            )
            
            # Store the bot and token mapping
            self._bots[workspace_id] = application
            self._workspace_by_token[token] = workspace_id
            
            logger.info(f"Bot successfully initialized for workspace {workspace_id}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to initialize bot for workspace {workspace_id}: {str(e)}", exc_info=True)
            return False
    
    async def cleanup_bot(self, workspace_id: UUID) -> bool:
        """Cleanup and stop the bot for the workspace"""
        try:
            if workspace_id in self._bots:
                logger.info(f"Starting cleanup for workspace {workspace_id}")
                application = self._bots[workspace_id]
                
                # Remove token mapping
                token = application.bot.token
                if token in self._workspace_by_token:
                    del self._workspace_by_token[token]
                
                # Stop bot
                logger.info("Stopping bot polling...")
                await application.updater.stop()
                logger.info("Stopping bot application...")
                await application.stop()
                logger.info("Shutting down bot...")
                await application.shutdown()
                del self._bots[workspace_id]
                
                logger.info(f"Bot successfully cleaned up for workspace {workspace_id}")
                return True
            return False
        except Exception as e:
            logger.error(f"Failed to cleanup bot for workspace {workspace_id}: {str(e)}", exc_info=True)
            return False
    
    async def cleanup(self) -> None:
        """Cleanup all bots"""
        for workspace_id in list(self._bots.keys()):
            await self.cleanup_bot(workspace_id)

    async def send_message(self, workspace_id: UUID, chat_id: int, text: str) -> bool:
        """Send message to a chat"""
        try:
            # Get bot application
            application = self._bots.get(workspace_id)
            if not application:
                logger.error(f"No bot found for workspace {workspace_id}")
                return False
            
            # Send message and process it
            async with self._session_factory() as session:
                try:
                    # Send message first
                    await application.bot.send_message(chat_id=chat_id, text=text)
                    
                    # Then process it
                    processor = MessageProcessor(session)
                    await processor.process_outgoing_message(
                        workspace_id=workspace_id,
                        telegram_id=chat_id,
                        text=text,
                    )
                    await session.commit()
                    return True
                except Exception as e:
                    logger.error(f"Failed to send or process message: {str(e)}", exc_info=True)
                    await session.rollback()
                    return False
                    
        except Exception as e:
            logger.error(f"Failed to send message: {str(e)}", exc_info=True)
            return False
    
    async def _handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle incoming messages"""
        try:
            # Skip non-message updates
            if not update.message:
                logger.debug("Skipping non-message update")
                return
                
            # Skip non-text messages
            if not update.message.text:
                logger.debug("Skipping non-text message")
                return

            # Get workspace ID from bot token
            token = context.bot.token
            workspace_id = self._workspace_by_token.get(token)
            
            if not workspace_id:
                logger.error(f"No workspace found for bot token {token}")
                return
            
            logger.info(f"Processing message: {update.message.text[:50]}... from chat {update.message.chat.id}")
            
            # Process message with retries
            max_retries = 3
            for attempt in range(max_retries):
                try:
                    async with self._session_factory() as session:
                        try:
                            processor = MessageProcessor(session)
                            await processor.process_message(
                                workspace_id=workspace_id,
                                telegram_id=update.message.chat.id,
                                username=update.message.from_user.username or "",
                                text=update.message.text,
                                sent_at=update.message.date,
                            )
                            await session.commit()
                            logger.info(f"Successfully processed message from chat {update.message.chat.id}")
                            return
                        except Exception as e:
                            logger.error(f"Failed to process message (attempt {attempt + 1}/{max_retries}): {str(e)}", exc_info=True)
                            await session.rollback()
                            if attempt == max_retries - 1:  # Last attempt
                                raise
                except Exception as e:
                    logger.error(f"Session error (attempt {attempt + 1}/{max_retries}): {str(e)}", exc_info=True)
                    if attempt == max_retries - 1:  # Last attempt
                        raise
                
                # Wait before retry
                await asyncio.sleep(1)
                
        except Exception as e:
            logger.error(f"Error handling message: {str(e)}", exc_info=True)

    async def get_bot_info(self, workspace_id: UUID):
        """Get bot information"""
        try:
            application = self._bots.get(workspace_id)
            if not application:
                return None
            
            return await application.bot.get_me()
        except Exception as e:
            logger.error(f"Failed to get bot info: {str(e)}", exc_info=True)
            return None

    async def get_bot_chats(self, workspace_id: UUID):
        """Get all chats for the bot"""
        try:
            application = self._bots.get(workspace_id)
            if not application:
                logger.error(f"No bot found for workspace {workspace_id}")
                return []
            
            # Get all updates to build chat list
            updates = []
            offset = 0
            
            async def get_updates():
                nonlocal updates, offset
                for _ in range(3):  # Try up to 3 times
                    try:
                        new_updates = await application.bot.get_updates(
                            offset=offset,
                            timeout=1,  # 1 second timeout per request
                            allowed_updates=['message']
                        )
                        if not new_updates:
                            break
                        updates.extend(new_updates)
                        offset = new_updates[-1].update_id + 1
                    except TimedOut:
                        logger.warning("Get updates timed out, retrying...")
                        continue
            
            # Use wait_for instead of timeout
            try:
                await asyncio.wait_for(get_updates(), timeout=5.0)
            except asyncio.TimeoutError:
                logger.error("Get bot chats timed out")
            
            # Extract unique chats
            chats = {}  # Use dict to maintain uniqueness
            for update in updates:
                if update.message and update.message.chat:
                    chat = update.message.chat
                    chats[chat.id] = chat
            
            return list(chats.values())
            
        except Exception as e:
            logger.error(f"Failed to get bot chats: {str(e)}", exc_info=True)
            return []

    async def get_chat_history(self, workspace_id: UUID, chat_id: int, limit: int = 100):
        """Get chat message history"""
        try:
            application = self._bots.get(workspace_id)
            if not application:
                return []
            
            messages = []
            try:
                # Get chat first
                chat = await application.bot.get_chat(chat_id)
                if not chat:
                    return []
                
                # Then get history
                async for message in chat.get_history(limit=limit):
                    if message.text:  # Only store text messages for now
                        messages.append(message)
                
                return messages
            except Exception as e:
                logger.error(f"Failed to get chat history: {str(e)}", exc_info=True)
                return []
                
        except Exception as e:
            logger.error(f"Failed to get chat history: {str(e)}", exc_info=True)
            return []

# Create global instance
telegram_manager = TelegramManager() 