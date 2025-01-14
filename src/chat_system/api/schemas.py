from datetime import datetime
from enum import Enum
from typing import Optional, Dict, List
from uuid import UUID
import base64

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
    photo_data: Optional[str] = None  # Base64 encoded photo data
    photo_url: Optional[str] = None  # Deprecated, kept for backward compatibility
    bot_id: UUID  # Add bot_id field

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
        
    @classmethod
    def from_orm(cls, obj):
        # Convert photo_data bytes to base64 string if present
        if hasattr(obj, 'photo_data') and obj.photo_data:
            # Create a copy of the object to avoid modifying the original
            obj_dict = {
                'id': obj.id,
                'workspace_id': obj.workspace_id,
                'bot_id': obj.bot_id,  # Add bot_id field
                'telegram_id': obj.telegram_id,
                'username': obj.username,
                'last_message_at': obj.last_message_at,
                'photo_url': obj.photo_url,
                'photo_data': base64.b64encode(obj.photo_data).decode('utf-8'),
                'last_message': None
            }
            # Add last_message if it exists
            if hasattr(obj, 'last_message') and obj.last_message:
                obj_dict['last_message'] = {
                    'id': obj.last_message.id,
                    'content': obj.last_message.content,
                    'direction': obj.last_message.direction,
                    'sent_at': obj.last_message.sent_at
                }
            return cls(**obj_dict)
        return super().from_orm(obj)

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