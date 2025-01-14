import telegram
from telegram import Update
from telegram.ext import Application, ContextTypes, MessageHandler, filters
from telegram.error import TimedOut
from sqlalchemy import select

from uuid import UUID
import logging
import asyncio
from typing import Dict, Any, Optional

from src.chat_system.core.config import settings
from src.chat_system.telegram.processor import MessageProcessor
from src.chat_system.db.session import async_session_factory
from src.chat_system.db.models import Bot, Chat, Message
from src.chat_system.db.enums import MessageDirection

logger = logging.getLogger(__name__)

class TelegramManager:
    def __init__(self):
        self._bots: dict[tuple[UUID, UUID], Application] = {}  # (workspace_id, bot_id) -> Application
        self._workspace_by_token: dict[str, tuple[UUID, UUID]] = {}  # token -> (workspace_id, bot_id)
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
                    await self.initialize_bot(bot.workspace_id, bot.token, bot.id)
                    
                logger.info(f"Initialized {len(bots)} bots from database")
        except Exception as e:
            logger.error(f"Failed to initialize bots from database: {str(e)}", exc_info=True)

    async def initialize_bot(self, workspace_id: UUID, token: str, bot_id: UUID = None) -> bool:
        """Initialize a new bot for the workspace"""
        try:
            # If bot_id is not provided, get it from database
            if not bot_id:
                async with self._session_factory() as session:
                    result = await session.execute(
                        select(Bot).where(
                            Bot.workspace_id == workspace_id,
                            Bot.token == token
                        )
                    )
                    bot = result.scalar_one_or_none()
                    if not bot:
                        logger.error(f"Bot not found in database for workspace {workspace_id}")
                        return False
                    bot_id = bot.id

            # Check if bot already exists
            if (workspace_id, bot_id) in self._bots:
                logger.info(f"Bot already exists for workspace {workspace_id}, bot {bot_id}, cleaning up first")
                await self.cleanup_bot(workspace_id, bot_id)
            
            logger.info(f"Starting bot initialization for workspace {workspace_id}, bot {bot_id}")
            
            # Validate token by getting bot info
            try:
                bot = telegram.Bot(token)
                bot_info = await bot.get_me()
                if not bot_info:
                    logger.error(f"Invalid bot token for workspace {workspace_id}")
                    return False
                logger.info(f"Validated bot token for {bot_info.username}")
            except Exception as e:
                logger.error(f"Failed to validate bot token: {str(e)}", exc_info=True)
                return False
            
            # Create bot application
            application = (
                Application.builder()
                .token(token)
                .connect_timeout(settings.TELEGRAM_API_TIMEOUT)
                .pool_timeout(30.0)
                .connection_pool_size(8)
                .concurrent_updates(True)
                .read_timeout(30.0)
                .write_timeout(30.0)
                .build()
            )
            
            # Add message handlers
            application.add_handler(
                MessageHandler(
                    filters.TEXT & ~filters.COMMAND,
                    self._handle_message
                )
            )
            
            try:
                # Start the bot
                logger.info("Initializing bot application...")
                await application.initialize()
                logger.info("Starting bot application...")
                await application.start()
                logger.info("Starting polling...")
                await application.updater.start_polling(
                    allowed_updates=['message'],
                    drop_pending_updates=True,
                    timeout=30,
                    read_timeout=30,
                )
                
                # Store the bot and token mapping
                self._bots[(workspace_id, bot_id)] = application
                self._workspace_by_token[token] = (workspace_id, bot_id)
                
                logger.info(f"Bot successfully initialized for workspace {workspace_id}, bot {bot_id}")
                return True
                
            except Exception as e:
                logger.error(f"Failed to start bot: {str(e)}", exc_info=True)
                try:
                    if application:
                        await application.stop()
                        await application.shutdown()
                except Exception as cleanup_error:
                    logger.error(f"Error during cleanup: {str(cleanup_error)}", exc_info=True)
                return False
                
        except Exception as e:
            logger.error(f"Failed to initialize bot: {str(e)}", exc_info=True)
            return False

    async def cleanup_bot(self, workspace_id: UUID, bot_id: UUID) -> bool:
        """Cleanup and stop the bot"""
        try:
            key = (workspace_id, bot_id)
            if key in self._bots:
                logger.info(f"Starting cleanup for workspace {workspace_id}, bot {bot_id}")
                application = self._bots[key]
                
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
                del self._bots[key]
                
                logger.info(f"Bot successfully cleaned up for workspace {workspace_id}, bot {bot_id}")
                return True
            return False
        except Exception as e:
            logger.error(f"Failed to cleanup bot: {str(e)}", exc_info=True)
            return False

    async def cleanup(self) -> None:
        """Cleanup all bots"""
        for (workspace_id, bot_id) in list(self._bots.keys()):
            await self.cleanup_bot(workspace_id, bot_id)

    async def send_message(self, workspace_id: UUID, chat_id: int, bot_id: UUID, text: str) -> bool:
        """Send message to a chat"""
        if not text or not text.strip():
            logger.error("Empty message text")
            return False
            
        try:
            # Find the correct bot for this chat
            async with self._session_factory() as session:
                logger.info(f"Looking for chat: workspace_id={workspace_id}, telegram_id={chat_id}, bot_id={bot_id}")
                
                # Get the specific chat
                result = await session.execute(
                    select(Chat).where(
                        Chat.workspace_id == workspace_id,
                        Chat.telegram_id == chat_id,
                        Chat.bot_id == bot_id
                    )
                )
                chat = result.scalar_one_or_none()
                if not chat:
                    logger.error(f"Chat not found: workspace_id={workspace_id}, telegram_id={chat_id}, bot_id={bot_id}")
                    return False
                
                key = (workspace_id, bot_id)
                logger.info(f"Found chat with bot_id={bot_id}, looking for bot application")
                
                # Get bot application
                application = self._bots.get(key)
                if not application:
                    logger.error(f"No bot found for workspace {workspace_id}, bot {bot_id}")
                    return False
            
                try:
                    logger.info(f"Sending message to chat {chat_id} in workspace {workspace_id} using bot {bot_id}")
                    
                    # Send message first
                    sent_message = await application.bot.send_message(
                        chat_id=chat_id,
                        text=text.strip(),
                        disable_web_page_preview=True
                    )
                    
                    if not sent_message:
                        logger.error("Failed to send message via Telegram API")
                        return False
                        
                    logger.info(f"Message sent successfully via Telegram API to chat {chat_id}")
                    
                    # Then process it
                    processor = MessageProcessor(session)
                    await processor.process_outgoing_message(
                        workspace_id=workspace_id,
                        telegram_id=chat_id,
                        bot_id=bot_id,
                        text=text.strip(),
                    )
                    await session.commit()
                    logger.info(f"Message processed and saved to database for chat {chat_id}")
                    return True
                    
                except Exception as e:
                    logger.error(f"Failed to send or process message: {str(e)}", exc_info=True)
                    await session.rollback()
                    return False
                    
        except Exception as e:
            logger.error(f"Failed to send message: {str(e)}", exc_info=True)
            return False

    async def _handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle incoming message"""
        if not update.message or not update.message.text:
            logger.debug("Skipping non-message or non-text update")
            return

        message = update.message
        logger.info(f"Processing message: {message.text[:20]}... from chat {message.chat.id}")
        
        # Get workspace_id and bot_id for this bot using token
        token = context.bot.token
        workspace_info = self._workspace_by_token.get(token)
                
        if not workspace_info:
            logger.error(f"Could not find workspace for bot token {token}")
            return
            
        workspace_id, bot_id = workspace_info
            
        # Create session and process message
        async with async_session_factory() as session:
            processor = MessageProcessor(session)
            
            for attempt in range(1, 4):  # 3 attempts
                try:
                    await processor.process_message(
                        workspace_id=workspace_id,
                        message=message,
                        bot_id=bot_id  # Pass bot_id to process_message
                    )
                    logger.info(f"Successfully processed message for workspace {workspace_id}, bot {bot_id}, chat {message.chat.id}")
                    await session.commit()
                    break
                except Exception as e:
                    if attempt == 3:
                        logger.error(f"Session error (attempt {attempt}/3): {str(e)}", exc_info=True)
                        await session.rollback()
                    else:
                        logger.error(f"Failed to process message (attempt {attempt}/3): {str(e)}", exc_info=True)
                        await session.rollback()
                        await asyncio.sleep(1)

    async def get_bot_info(self, workspace_id: UUID, bot_id: UUID = None) -> Optional[Dict[str, Any]]:
        """Get bot info by workspace id and optionally bot_id"""
        try:
            async with self._session_factory() as session:
                query = select(Bot).where(
                    Bot.workspace_id == workspace_id,
                    Bot.is_active == True
                )
                if bot_id:
                    query = query.where(Bot.id == bot_id)
                    result = await session.execute(query)
                    bot = result.scalar_one_or_none()
                    if bot:
                        return {
                            'id': bot.id,
                            'token': bot.token,
                            'workspace_id': workspace_id
                        }
                else:
                    # If no bot_id specified, get the first active bot
                    result = await session.execute(query.order_by(Bot.created_at.desc()))
                    bot = result.scalar_one_or_none()
                    if bot:
                        return {
                            'id': bot.id,
                            'token': bot.token,
                            'workspace_id': workspace_id
                        }
                return None
        except Exception as e:
            logger.error(f"Failed to get bot info: {str(e)}", exc_info=True)
            return None

    async def get_bot_chats(self, workspace_id: UUID, bot_id: UUID = None):
        """Get all chats for the bot"""
        try:
            # Get the specific bot application
            key = (workspace_id, bot_id) if bot_id else None
            if not key or key not in self._bots:
                logger.error(f"No bot found for workspace {workspace_id}, bot {bot_id}")
                return []
            
            application = self._bots[key]
            
            # Get all updates to build chat list
            updates = []
            offset = 0
            
            async def get_updates():
                nonlocal updates, offset
                try:
                    # Get bot info first
                    bot_info = await application.bot.get_me()
                    if not bot_info:
                        logger.error("Failed to get bot info")
                        return
                        
                    logger.info(f"Getting updates for bot {bot_info.username}")
                    
                    for _ in range(3):  # Try up to 3 times
                        try:
                            new_updates = await application.bot.get_updates(
                                offset=offset,
                                timeout=5,  # 5 second timeout per request
                                allowed_updates=['message'],
                                read_timeout=10
                            )
                            
                            if not new_updates:
                                logger.info("No new updates found")
                                break
                                
                            updates.extend(new_updates)
                            offset = new_updates[-1].update_id + 1
                            logger.info(f"Got {len(new_updates)} new updates")
                            
                        except TimedOut:
                            logger.warning("Get updates timed out, retrying...")
                            await asyncio.sleep(1)
                            
                        except Exception as e:
                            logger.error(f"Error getting updates: {str(e)}", exc_info=True)
                            break
                            
                except Exception as e:
                    logger.error(f"Error in get_updates: {str(e)}", exc_info=True)
            
            # Use wait_for instead of timeout
            try:
                await asyncio.wait_for(get_updates(), timeout=15.0)  # 15 seconds total timeout
            except asyncio.TimeoutError:
                logger.error("Get bot chats timed out")
            except Exception as e:
                logger.error(f"Error during get_updates: {str(e)}", exc_info=True)
            
            # Extract unique chats
            chats = {}  # Use dict to maintain uniqueness
            try:
                async with self._session_factory() as session:
                    for update in updates:
                        if update.message and update.message.chat:
                            chat = update.message.chat
                            if chat.id not in chats:
                                chats[chat.id] = chat
                                
                                # Try to create chat in database if it doesn't exist
                                processor = MessageProcessor(session)
                                try:
                                    await processor.process_message(
                                        workspace_id=workspace_id,
                                        message=update.message,
                                        bot_id=bot_id
                                    )
                                    await session.commit()
                                except Exception as e:
                                    logger.error(f"Failed to process chat: {str(e)}", exc_info=True)
                                    await session.rollback()
                         
                logger.info(f"Found {len(chats)} unique chats")
                return list(chats.values())
                
            except Exception as e:
                logger.error(f"Error processing chats: {str(e)}", exc_info=True)
                return []
            
        except Exception as e:
            logger.error(f"Failed to get bot chats: {str(e)}", exc_info=True)
            return []

    async def get_chat_history(self, workspace_id: UUID, chat_id: int, bot_id: UUID = None, limit: int = 100):
        """Get chat message history"""
        try:
            # Get the specific bot application
            key = (workspace_id, bot_id) if bot_id else None
            if not key or key not in self._bots:
                logger.error(f"No bot found for workspace {workspace_id}, bot {bot_id}")
                return []
            
            application = self._bots[key]
            
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