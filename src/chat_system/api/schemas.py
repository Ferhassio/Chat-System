from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, EmailStr

# User schemas
class UserBase(BaseModel):
    """Base user schema"""
    email: EmailStr
    full_name: str

class UserCreate(UserBase):
    """User creation schema"""
    password: str

class UserLogin(BaseModel):
    """User login schema"""
    email: EmailStr
    password: str

class UserResponse(UserBase):
    """User response schema"""
    id: UUID
    role: str
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True

# Token schemas
class Token(BaseModel):
    """Token schema"""
    access_token: str
    token_type: str

# Workspace schemas
class WorkspaceBase(BaseModel):
    """Base workspace schema"""
    name: str

class WorkspaceCreate(WorkspaceBase):
    """Workspace creation schema"""
    pass

class WorkspaceResponse(WorkspaceBase):
    """Workspace response schema"""
    id: UUID
    owner_id: UUID
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True

# Bot schemas
class BotBase(BaseModel):
    """Base bot schema"""
    name: str
    token: str

class BotCreate(BotBase):
    """Bot creation schema"""
    pass

class BotResponse(BotBase):
    """Bot response schema"""
    id: UUID
    workspace_id: UUID
    is_active: bool
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True

# Chat schemas
class ChatResponse(BaseModel):
    """Chat response schema"""
    id: UUID
    workspace_id: UUID
    telegram_id: int
    username: str
    last_message_at: Optional[datetime]
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True

# Message schemas
class MessageCreate(BaseModel):
    """Message creation schema"""
    content: str

class MessageResponse(BaseModel):
    """Message response schema"""
    id: UUID
    chat_id: UUID
    content: str
    direction: str
    sent_at: datetime
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True 