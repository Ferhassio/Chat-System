from datetime import datetime
from enum import Enum
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, EmailStr

class MessageDirection(str, Enum):
    INCOMING = "incoming"
    OUTGOING = "outgoing"

class UserBase(BaseModel):
    email: EmailStr
    full_name: str

class UserCreate(UserBase):
    password: str

class UserLogin(BaseModel):
    email: EmailStr
    password: str

class UserResponse(UserBase):
    id: UUID
    is_owner: Optional[bool] = False

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

class ChatResponse(ChatBase):
    id: UUID
    workspace_id: UUID
    last_message_at: Optional[datetime] = None

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