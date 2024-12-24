import logging
from typing import List
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.chat_system.api.deps import get_current_user, get_session
from src.chat_system.api.schemas import (
    BotCreate,
    BotResponse,
    ChatResponse,
    MessageCreate,
    MessageResponse,
    WorkspaceCreate,
    WorkspaceResponse,
)
from src.chat_system.db.models import Bot, Chat, Message, User, Workspace
from src.chat_system.telegram.manager import telegram_manager

router = APIRouter()
logger = logging.getLogger(__name__)

@router.post("/", response_model=WorkspaceResponse)
async def create_workspace(
    workspace: WorkspaceCreate,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> Workspace:
    """Create a new workspace"""
    db_workspace = Workspace(
        name=workspace.name,
        owner_id=current_user.id,
    )
    session.add(db_workspace)
    await session.commit()
    return db_workspace

@router.get("/", response_model=List[WorkspaceResponse])
async def get_workspaces(
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> List[Workspace]:
    """Get all workspaces for current user"""
    result = await session.execute(
        select(Workspace).where(Workspace.owner_id == current_user.id)
    )
    return result.scalars().all()

@router.post("/{workspace_id}/bots", response_model=BotResponse)
async def add_bot(
    workspace_id: UUID,
    bot: BotCreate,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> Bot:
    """Add a new bot to workspace"""
    try:
        # Check workspace exists and belongs to user
        workspace = await session.execute(
            select(Workspace).where(
                Workspace.id == workspace_id,
                Workspace.owner_id == current_user.id,
            )
        )
        workspace = workspace.scalar_one_or_none()
        if not workspace:
            raise HTTPException(status_code=404, detail="Workspace not found")
            
        # Check if bot with this token already exists
        existing_bot = await session.execute(
            select(Bot).where(Bot.token == bot.token)
        )
        existing_bot = existing_bot.scalar_one_or_none()
        if existing_bot:
            raise HTTPException(
                status_code=400, 
                detail="Бот с таким токеном уже зарегистрирован в другом рабочем пространстве. Пожалуйста, используйте другой токен бота."
            )

        # Initialize bot first to validate token
        if not await telegram_manager.initialize_bot(workspace_id, bot.token):
            raise HTTPException(status_code=400, detail="Failed to initialize bot")

        # Create bot record
        db_bot = Bot(
            workspace_id=workspace_id,
            name=bot.name,
            token=bot.token,
        )
        session.add(db_bot)
        await session.flush()
        
        # Get existing chats and messages for this bot
        bot_info = await telegram_manager.get_bot_info(workspace_id)
        if bot_info:
            logger.info(f"Got bot info: {bot_info.id} ({bot_info.username})")
            
            # Get all chats for this bot
            chats = await telegram_manager.get_bot_chats(workspace_id)
            logger.info(f"Found {len(chats)} chats")
            
            for chat in chats:
                logger.info(f"Processing chat: {chat.id} ({chat.username})")
                
                # Create chat record if not exists
                result = await session.execute(
                    select(Chat).where(
                        Chat.workspace_id == workspace_id,
                        Chat.telegram_id == chat.id,
                    )
                )
                db_chat = result.scalar_one_or_none()
                if not db_chat:
                    db_chat = Chat(
                        workspace_id=workspace_id,
                        telegram_id=chat.id,
                        username=chat.username or "",
                    )
                    session.add(db_chat)
                    await session.flush()
                    logger.info(f"Created new chat record: {db_chat.id}")
                else:
                    logger.info(f"Using existing chat record: {db_chat.id}")
                
                # Get chat history
                messages = await telegram_manager.get_chat_history(workspace_id, chat.id)
                logger.info(f"Got {len(messages)} messages from history")
                
                for msg in messages:
                    if not msg.text:  # Skip non-text messages
                        continue
                        
                    # Check if message already exists
                    result = await session.execute(
                        select(Message).where(
                            Message.chat_id == db_chat.id,
                            Message.sent_at == msg.date,
                        )
                    )
                    if result.scalar_one_or_none():
                        continue
                    
                    db_message = Message(
                        chat_id=db_chat.id,
                        content=msg.text,
                        sent_at=msg.date.replace(tzinfo=None),  # Remove timezone info
                        direction=MessageDirection.INCOMING if msg.from_user.id != bot_info.id else MessageDirection.OUTGOING,
                    )
                    session.add(db_message)
                    logger.info(f"Added message: {msg.text[:50]}...")
                
                # Update last message time
                if messages:
                    db_chat.last_message_at = messages[-1].date.replace(tzinfo=None)  # Remove timezone info
                    logger.info(f"Updated chat last_message_at to {db_chat.last_message_at}")
        
        await session.commit()
        logger.info("Successfully added bot and imported history")
        return db_bot
        
    except Exception as e:
        await session.rollback()
        # Cleanup bot if it was initialized
        await telegram_manager.cleanup_bot(workspace_id)
        logger.error(f"Failed to add bot: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to add bot")

@router.get("/{workspace_id}/bots", response_model=List[BotResponse])
async def get_bots(
    workspace_id: UUID,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> List[Bot]:
    """Get all bots in workspace"""
    result = await session.execute(
        select(Bot).where(
            Bot.workspace_id == workspace_id,
            Workspace.id == workspace_id,
            Workspace.owner_id == current_user.id,
        )
    )
    return result.scalars().all()

@router.get("/{workspace_id}/chats", response_model=List[ChatResponse])
async def get_chats(
    workspace_id: UUID,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> List[Chat]:
    """Get all chats in workspace"""
    result = await session.execute(
        select(Chat)
        .join(Workspace, Chat.workspace_id == Workspace.id)
        .where(
            Chat.workspace_id == workspace_id,
            Workspace.owner_id == current_user.id,
        )
        .order_by(Chat.last_message_at.desc())
    )
    return result.scalars().all()

@router.get("/{workspace_id}/chats/{chat_id}/messages", response_model=List[MessageResponse])
async def get_messages(
    workspace_id: UUID,
    chat_id: UUID,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> List[Message]:
    """Get all messages in chat"""
    result = await session.execute(
        select(Message)
        .join(Chat, Message.chat_id == Chat.id)
        .join(Workspace, Chat.workspace_id == Workspace.id)
        .where(
            Message.chat_id == chat_id,
            Chat.workspace_id == workspace_id,
            Workspace.owner_id == current_user.id,
        )
        .order_by(Message.sent_at.asc())
    )
    return result.scalars().all()

@router.post("/{workspace_id}/chats/{chat_id}/messages", response_model=MessageResponse)
async def send_message(
    workspace_id: UUID,
    chat_id: UUID,
    message: MessageCreate,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> Message:
    """Send message to chat"""
    # Check chat exists and belongs to user's workspace
    result = await session.execute(
        select(Chat).where(
            Chat.id == chat_id,
            Chat.workspace_id == workspace_id,
            Workspace.id == workspace_id,
            Workspace.owner_id == current_user.id,
        )
    )
    chat = result.scalar_one_or_none()
    if not chat:
        raise HTTPException(status_code=404, detail="Chat not found")
    
    # Send message via Telegram
    success = await telegram_manager.send_message(
        workspace_id=workspace_id,
        chat_id=chat.telegram_id,
        text=message.content,
    )
    if not success:
        raise HTTPException(status_code=500, detail="Failed to send message")
    
    # Get the saved message (get the latest one)
    result = await session.execute(
        select(Message)
        .where(Message.chat_id == chat_id)
        .order_by(Message.sent_at.desc())
        .limit(1)
    )
    return result.scalar_one() 