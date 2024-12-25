from datetime import datetime
from enum import Enum
from typing import Optional, Dict, List
from uuid import UUID

from pydantic import BaseModel, EmailStr

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
    photos: Optional[UserPhotos] = None

class ChatCreate(ChatBase):
    workspace_id: UUID

class ChatUpdate(ChatBase):
    pass

class ChatResponse(ChatBase):
    id: UUID
    workspace_id: UUID
    last_message: Optional[Dict] = None

    class Config:
        from_attributes = True

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