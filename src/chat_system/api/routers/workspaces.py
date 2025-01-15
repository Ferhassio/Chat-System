import logging
from typing import List
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload, selectinload, contains_eager

from src.chat_system.api.deps import get_current_user, get_session
from src.chat_system.api.schemas import (
    BotCreate,
    BotResponse,
    ChatResponse,
    MessageCreate,
    MessageResponse,
    WorkspaceCreate,
    WorkspaceResponse,
    UserResponse,
    WorkspaceUserCreate,
)
from src.chat_system.db.models import Bot, Chat, Message, User, Workspace, WorkspaceUser, AnalysisResult
from src.chat_system.telegram.manager import telegram_manager

router = APIRouter()
logging.basicConfig()

logging.getLogger('sqlalchemy.engine.Engine').disabled = True


async def get_workspace_or_404(session: AsyncSession, workspace_id: UUID, current_user: User) -> Workspace:
    """Get workspace by id or raise 404 if not found or no access"""
    workspace_access = await session.execute(
        select(Workspace).where(
            Workspace.id == workspace_id,
        ).where(
            (Workspace.owner_id == current_user.id) | 
            (Workspace.id.in_(
                select(WorkspaceUser.workspace_id).where(
                    WorkspaceUser.user_id == current_user.id
                )
            ))
        )
    )
    
    workspace = workspace_access.scalar_one_or_none()
    if not workspace:
        raise HTTPException(
            status_code=404, 
            detail="Рабочее пространство не найдено или у вас нет к нему доступа"
        )
    return workspace

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
    """Get all workspaces for current user (both owned and member of)"""
    result = await session.execute(
        select(Workspace).where(
            (Workspace.owner_id == current_user.id) | 
            (Workspace.id.in_(
                select(WorkspaceUser.workspace_id).where(
                    WorkspaceUser.user_id == current_user.id
                )
            ))
        )
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

        # Create bot record first to get bot_id
        db_bot = Bot(
            workspace_id=workspace_id,
            name=bot.name,
            token=bot.token,
        )
        session.add(db_bot)
        await session.flush()

        # Initialize bot with bot_id
        if not await telegram_manager.initialize_bot(workspace_id, bot.token, db_bot.id):
            # Cleanup on failure
            await session.rollback()
            raise HTTPException(status_code=400, detail="Failed to initialize bot")

        # Get existing chats and messages for this bot
        bot_info = await telegram_manager.get_bot_info(workspace_id, db_bot.id)
        if bot_info:
            logging.info(f"Got bot info: {bot_info['id']}")
            
            # Get all chats for this bot
            chats = await telegram_manager.get_bot_chats(workspace_id, db_bot.id)
            logging.info(f"Found {len(chats)} chats")
            
            for chat in chats:
                logging.info(f"Processing chat: {chat.id} ({chat.username})")
                
                # Create chat record if not exists
                result = await session.execute(
                    select(Chat).where(
                        Chat.workspace_id == workspace_id,
                        Chat.telegram_id == chat.id,
                        Chat.bot_id == db_bot.id
                    )
                )
                db_chat = result.scalar_one_or_none()
                if not db_chat:
                    db_chat = Chat(
                        workspace_id=workspace_id,
                        telegram_id=chat.id,
                        username=chat.username or "",
                        bot_id=db_bot.id
                    )
                    session.add(db_chat)
                    await session.flush()
                    logging.info(f"Created new chat record: {db_chat.id}")
                else:
                    logging.info(f"Using existing chat record: {db_chat.id}")

                # Get chat history
                messages = await telegram_manager.get_chat_history(workspace_id, chat.id, db_bot.id)
                logging.info(f"Got {len(messages)} messages from history")
                
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
                    
                    # Determine message direction based on sender
                    is_outgoing = msg.from_user and msg.from_user.is_bot
                    
                    db_message = Message(
                        chat_id=db_chat.id,
                        content=msg.text,
                        sent_at=msg.date.replace(tzinfo=None),  # Remove timezone info
                        direction=MessageDirection.OUTGOING if is_outgoing else MessageDirection.INCOMING,
                    )
                    session.add(db_message)
                    logging.info(f"Added message: {msg.text[:50]}...")
                
                # Update last message time
                if messages:
                    db_chat.last_message_at = messages[-1].date.replace(tzinfo=None)  # Remove timezone info
                    logging.info(f"Updated chat last_message_at to {db_chat.last_message_at}")
        
        await session.commit()
        logging.info("Successfully added bot and imported history")
        return db_bot
        
    except Exception as e:
        await session.rollback()
        # Cleanup bot if it was initialized
        if 'db_bot' in locals() and db_bot.id:
            await telegram_manager.cleanup_bot(workspace_id, db_bot.id)
        logging.error(f"Failed to add bot: {str(e)}", exc_info=True)
        if isinstance(e, HTTPException):
            raise
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/{workspace_id}/bots", response_model=List[BotResponse])
async def get_workspace_bots(
    workspace_id: UUID,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> List[Bot]:
    """Get all bots in workspace"""
    # Check if current user has access to workspace
    workspace = await session.execute(
        select(Workspace).where(
            Workspace.id == workspace_id,
            Workspace.owner_id == current_user.id,
        )
    )
    workspace = workspace.scalar_one_or_none()
    if not workspace:
        raise HTTPException(status_code=404, detail="Workspace not found")

    # Get all bots in workspace
    result = await session.execute(
        select(Bot).where(Bot.workspace_id == workspace_id)
    )
    bots = result.scalars().all()
    return bots

@router.delete("/{workspace_id}/bots/{bot_id}")
async def remove_workspace_bot(
    workspace_id: UUID,
    bot_id: UUID,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Remove bot from workspace"""
    # Check if current user is workspace owner
    workspace = await session.execute(
        select(Workspace).where(
            Workspace.id == workspace_id,
            Workspace.owner_id == current_user.id,
        )
    )
    workspace = workspace.scalar_one_or_none()
    if not workspace:
        raise HTTPException(status_code=404, detail="Workspace not found or you don't have permission")

    # Check if bot exists in the workspace
    result = await session.execute(
        select(Bot).where(
            Bot.workspace_id == workspace_id,
            Bot.id == bot_id
        )
    )
    bot = result.scalar_one_or_none()
    if not bot:
        raise HTTPException(status_code=404, detail="Bot not found in workspace")

    # Delete all messages associated with the bot
    await session.execute(delete(Message).where(Message.chat_id.in_(
        select(Chat.id).where(Chat.bot_id == bot.id)
    )))

    # Delete all analysis results associated with the bot
    await session.execute(delete(AnalysisResult).where(AnalysisResult.chat_id.in_(
        select(Chat.id).where(Chat.bot_id == bot.id)
    )))

    # Delete the bot
    await session.delete(bot)
    await session.commit()

    return {"status": "success"}

@router.get("/{workspace_id}/chats", response_model=List[ChatResponse])
async def get_chats(
    workspace_id: UUID,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> List[ChatResponse]:
    """Get all chats in workspace"""
    # Check workspace access
    workspace = await get_workspace_or_404(session, workspace_id, current_user)
    
    # Get chats with telegram profiles, bots and last messages
    result = await session.execute(
        select(Chat)
        .outerjoin(Chat.last_message)
        .options(
            contains_eager(Chat.last_message),
            joinedload(Chat.bot)
        )
        .where(Chat.workspace_id == workspace_id)
        .order_by(Chat.last_message_at.desc())
    )
    chats = result.unique().scalars().all()
    logging.info(f"Found {len(chats)} chats")
    
    # Convert to ChatResponse objects using from_orm
    chat_list = []
    for chat in chats:
        chat_response = ChatResponse.from_orm(chat)
        logging.info(f"Chat {chat.id} for bot {chat.bot.name} ({chat.bot_id})")
        chat_list.append(chat_response)
    
    return chat_list

@router.get("/{workspace_id}/chats/{chat_id}/bots/{bot_id}/messages", response_model=List[MessageResponse])
async def get_messages(
    workspace_id: UUID,
    chat_id: UUID,
    bot_id: UUID,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> List[Message]:
    """Get all messages in chat for a specific bot"""
    # Check if user has access to workspace (either owner or member)
    workspace_access = await session.execute(
        select(Workspace).where(
            Workspace.id == workspace_id,
        ).where(
            (Workspace.owner_id == current_user.id) | 
            (Workspace.id.in_(
                select(WorkspaceUser.workspace_id).where(
                    WorkspaceUser.user_id == current_user.id
                )
            ))
        )
    )
    
    workspace = workspace_access.scalar_one_or_none()
    if not workspace:
        raise HTTPException(
            status_code=404, 
            detail="Рабочее пространство не найдено или у вас нет к нему доступа"
        )

    # Get all messages for the chat and bot
    result = await session.execute(
        select(Message)
        .join(Chat, Message.chat_id == Chat.id)
        .where(
            Message.chat_id == chat_id,
            Chat.workspace_id == workspace_id,
            Chat.bot_id == bot_id,
        )
        .order_by(Message.sent_at.asc())
    )
    return result.scalars().all()

@router.post("/{workspace_id}/chats/{chat_id}/bots/{bot_id}/messages", response_model=MessageResponse)
async def send_message(
    workspace_id: UUID,
    chat_id: UUID,
    bot_id: UUID,
    message: MessageCreate,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> Message:
    """Send message to chat using a specific bot"""
    # Check if user has access to workspace (either owner or member)
    workspace_access = await session.execute(
        select(Workspace).where(
            Workspace.id == workspace_id,
        ).where(
            (Workspace.owner_id == current_user.id) | 
            (Workspace.id.in_(
                select(WorkspaceUser.workspace_id).where(
                    WorkspaceUser.user_id == current_user.id
                )
            ))
        )
    )
    
    workspace = workspace_access.scalar_one_or_none()
    if not workspace:
        raise HTTPException(
            status_code=404, 
            detail="Рабочее пространство не найдено или у вас нет к нему доступа"
        )

    # Check if chat exists and belongs to workspace
    result = await session.execute(
        select(Chat).where(
            Chat.id == chat_id,
            Chat.workspace_id == workspace_id,
            Chat.bot_id == bot_id  # Ensure the chat is associated with the correct bot
        )
    )
    chat = result.scalar_one_or_none()
    if not chat:
        raise HTTPException(status_code=404, detail="Чат не найден")
    
    # Send message via Telegram
    success = await telegram_manager.send_message(
        workspace_id=workspace_id,
        chat_id=chat.telegram_id,
        bot_id=bot_id,
        text=message.content,
    )
    if not success:
        raise HTTPException(status_code=500, detail="Не удалось отправить сообщение")
    
    # Get the saved message (get the latest one)
    result = await session.execute(
        select(Message)
        .where(Message.chat_id == chat_id)
        .order_by(Message.sent_at.desc())
        .limit(1)
    )
    return result.scalar_one()

@router.get("/{workspace_id}/users", response_model=List[UserResponse])
async def get_workspace_users(
    workspace_id: UUID,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> List[User]:
    """Get all users in workspace"""
    # Check if current user has access to workspace
    workspace = await session.execute(
        select(Workspace).where(
            Workspace.id == workspace_id,
            Workspace.owner_id == current_user.id,
        )
    )
    workspace = workspace.scalar_one_or_none()
    if not workspace:
        raise HTTPException(status_code=404, detail="Workspace not found")

    # Get all users in workspace
    result = await session.execute(
        select(User)
        .join(WorkspaceUser, WorkspaceUser.user_id == User.id)
        .where(WorkspaceUser.workspace_id == workspace_id)
    )
    users = result.scalars().all()
    
    # Add owner to the list if not already included
    owner_in_list = any(user.id == workspace.owner_id for user in users)
    if not owner_in_list:
        owner = await session.get(User, workspace.owner_id)
        if owner:
            users.append(owner)
    
    # Add is_owner flag to each user
    for user in users:
        user.is_owner = user.id == workspace.owner_id
    
    return users

@router.post("/{workspace_id}/users", response_model=UserResponse)
async def add_workspace_user(
    workspace_id: UUID,
    user_data: WorkspaceUserCreate,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> User:
    """Add user to workspace"""
    # Check if current user is workspace owner
    workspace = await session.execute(
        select(Workspace).where(
            Workspace.id == workspace_id,
            Workspace.owner_id == current_user.id,
        )
    )
    workspace = workspace.scalar_one_or_none()
    if not workspace:
        raise HTTPException(status_code=404, detail="Workspace not found or you don't have permission")

    # Find user by email
    result = await session.execute(
        select(User).where(User.email == user_data.email)
    )
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # Check if user is already in workspace
    result = await session.execute(
        select(WorkspaceUser).where(
            WorkspaceUser.workspace_id == workspace_id,
            WorkspaceUser.user_id == user.id,
        )
    )
    if result.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="User is already in workspace")

    # Add user to workspace
    workspace_user = WorkspaceUser(
        workspace_id=workspace_id,
        user_id=user.id,
    )
    session.add(workspace_user)
    await session.commit()

    return user

@router.delete("/{workspace_id}/users/{user_id}")
async def remove_workspace_user(
    workspace_id: UUID,
    user_id: UUID,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Remove user from workspace"""
    # Check if current user is workspace owner
    workspace = await session.execute(
        select(Workspace).where(
            Workspace.id == workspace_id,
            Workspace.owner_id == current_user.id,
        )
    )
    workspace = workspace.scalar_one_or_none()
    if not workspace:
        raise HTTPException(status_code=404, detail="Workspace not found or you don't have permission")

    # Cannot remove workspace owner
    if user_id == workspace.owner_id:
        raise HTTPException(status_code=400, detail="Cannot remove workspace owner")

    # Remove user from workspace
    result = await session.execute(
        select(WorkspaceUser).where(
            WorkspaceUser.workspace_id == workspace_id,
            WorkspaceUser.user_id == user_id,
        )
    )
    workspace_user = result.scalar_one_or_none()
    if not workspace_user:
        raise HTTPException(status_code=404, detail="User not found in workspace")

    await session.delete(workspace_user)
    await session.commit()

    return {"status": "success"}

@router.post("/{workspace_id}/chats/{chat_id}/mark_read", response_model=ChatResponse)
async def mark_chat_read(
    workspace_id: UUID,
    chat_id: UUID,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> ChatResponse:
    """Mark chat as read"""
    # Check workspace access
    workspace = await get_workspace_or_404(session, workspace_id, current_user)
    
    # Get chat with last message
    result = await session.execute(
        select(Chat)
        .outerjoin(Chat.last_message)
        .options(
            contains_eager(Chat.last_message),
            joinedload(Chat.bot)
        )
        .where(
            Chat.id == chat_id,
            Chat.workspace_id == workspace_id
        )
    )
    chat = result.unique().scalar_one_or_none()
    if not chat:
        raise HTTPException(status_code=404, detail="Chat not found")
    
    # Mark as read and prepare response before commit
    chat.has_unread = False
    response = ChatResponse.from_orm(chat)
    
    # Commit changes
    await session.commit()
    
    return response 

@router.get("/{workspace_id}/chats/{chat_id}/bots/{bot_id}/analysis")
async def get_chat_analysis(
    workspace_id: UUID,
    chat_id: UUID,
    bot_id: UUID,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Get analysis data for a specific chat and bot"""
    logging.debug(f"Fetching analysis for workspace_id: {workspace_id}, chat_id: {chat_id}, bot_id: {bot_id}")

    # Check if user has access to workspace (either owner or member)
    workspace_access = await session.execute(
        select(Workspace).where(
            Workspace.id == workspace_id,
        ).where(
            (Workspace.owner_id == current_user.id) | 
            (Workspace.id.in_(
                select(WorkspaceUser.workspace_id).where(
                    WorkspaceUser.user_id == current_user.id
                )
            ))
        )
    )
    
    workspace = workspace_access.scalar_one_or_none()
    if not workspace:
        logging.error("Workspace not found or access denied")
        raise HTTPException(
            status_code=404, 
            detail="Рабочее пространство не найдено или у вас нет к нему доступа"
        )

    # Check if chat exists and belongs to workspace
    result = await session.execute(
        select(Chat).where(
            Chat.id == chat_id,
            Chat.workspace_id == workspace_id,
            Chat.bot_id == bot_id  # Ensure the chat is associated with the correct bot
        )
    )
    chat = result.scalar_one_or_none()
    if not chat:
        logging.error(f"Chat not found for chat_id: {chat_id}, workspace_id: {workspace_id}, bot_id: {bot_id}")
        raise HTTPException(status_code=404, detail="Чат не найден")

    # Fetch analysis data from the database
    result = await session.execute(
        select(AnalysisResult).where(
            AnalysisResult.chat_id == chat_id,
            AnalysisResult.workspace_id == workspace_id
        )
    )
    analysis = result.scalar_one_or_none()
    if not analysis:
        logging.error(f"Analysis not found for chat_id: {chat_id}, workspace_id: {workspace_id}")
        raise HTTPException(status_code=404, detail="Анализ не найден")

    logging.info("Analysis data retrieved successfully")
    return {"analysis_data": analysis.analysis_data} 

@router.put("/{workspace_id}/bots/{bot_id}", response_model=BotResponse)
async def update_bot_key(
    workspace_id: UUID,
    bot_id: UUID,
    bot: BotCreate,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> Bot:
    """Update bot key in workspace"""
    # Check if current user is workspace owner
    workspace = await session.execute(
        select(Workspace).where(
            Workspace.id == workspace_id,
            Workspace.owner_id == current_user.id,
        )
    )
    workspace = workspace.scalar_one_or_none()
    if not workspace:
        raise HTTPException(status_code=404, detail="Workspace not found or you don't have permission")

    # Check if bot exists in the workspace
    result = await session.execute(
        select(Bot).where(
            Bot.workspace_id == workspace_id,
            Bot.id == bot_id
        )
    )
    bot_to_update = result.scalar_one_or_none()
    if not bot_to_update:
        raise HTTPException(status_code=404, detail="Bot not found in workspace")

    
    # Initialize bot with bot_id
    if not await telegram_manager.initialize_bot(workspace_id, bot.token, bot_id):
        raise HTTPException(status_code=400, detail="Failed to initialize bot")

    # Обновление токена
    bot_to_update.token = bot.token
    await session.commit()

    return bot_to_update 