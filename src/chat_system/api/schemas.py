from datetime import datetime
from enum import Enum
from typing import Optional, Dict, List
from uuid import UUID
import base64

from pydantic import BaseModel, EmailStr

from src.chat_system.db.models import Chat

class MessageDirection(str, Enum):
    INCOMING = "incoming"
    OUTGOING = "outgoing"

class UserPhotos(BaseModel):
    small: str
    medium: str
    large: str

class UserBase(BaseModel):
    email: EmailStr
    full_name: str
    photos: Optional[UserPhotos] = None

class UserCreate(UserBase):
    password: str

class UserLogin(BaseModel):
    email: EmailStr
    password: str

class UserUpdate(UserBase):
    password: Optional[str] = None
    email: Optional[EmailStr] = None
    full_name: Optional[str] = None

class UserResponse(UserBase):
    id: UUID
    is_active: bool
    is_owner: bool = False

    class Config:
        from_attributes = True

class WorkspaceUserCreate(BaseModel):
    email: EmailStr

class Token(BaseModel):
    access_token: str
    token_type: str

class TokenData(BaseModel):
    email: str

class WorkspaceBase(BaseModel):
    name: str

class WorkspaceCreate(WorkspaceBase):
    pass

class WorkspaceResponse(WorkspaceBase):
    id: UUID
    owner_id: UUID

    class Config:
        from_attributes = True

class BotBase(BaseModel):
    name: str
    token: str

class BotCreate(BotBase):
    pass

class BotResponse(BotBase):
    id: UUID
    workspace_id: UUID

    class Config:
        from_attributes = True

class ChatBase(BaseModel):
    telegram_id: int
    username: str
    last_message_at: Optional[datetime] = None
    photo_data: Optional[str] = None
    bot_id: UUID

class ChatCreate(ChatBase):
    workspace_id: UUID

class ChatUpdate(ChatBase):
    pass

class MessageBase(BaseModel):
    content: str

class MessageCreate(MessageBase):
    pass

class MessageResponse(MessageBase):
    id: UUID
    chat_id: UUID
    sent_at: datetime
    direction: MessageDirection

    class Config:
        from_attributes = True

class ChatResponse(BaseModel):
    """Chat response schema"""
    id: UUID
    workspace_id: UUID
    bot_id: UUID
    telegram_id: int
    username: str
    photo_data: Optional[str] = None
    has_unread: bool = False
    last_message_at: Optional[datetime] = None
    last_message: Optional[MessageResponse] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True

    @classmethod
    def from_orm(cls, obj: Chat) -> "ChatResponse":
        """Convert Chat model to ChatResponse"""
        return cls(
            id=obj.id,
            workspace_id=obj.workspace_id,
            bot_id=obj.bot_id,
            telegram_id=obj.telegram_id,
            username=obj.username,
            photo_data=obj.photo_data.hex() if obj.photo_data else None,
            has_unread=obj.has_unread,
            last_message_at=obj.last_message_at,
            last_message=MessageResponse.from_orm(obj.last_message) if obj.last_message else None,
            created_at=obj.created_at,
            updated_at=obj.updated_at
        ) 