from datetime import datetime
from typing import List, Optional, Dict, Any
from uuid import UUID, uuid4
import logging

from sqlalchemy import ForeignKey, String, DateTime, Integer, Boolean, JSON, BigInteger, func, LargeBinary
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.chat_system.db.base import Base
from src.chat_system.db.enums import MessageDirection

logger = logging.getLogger(__name__)

class User(Base):
    """User model"""
    __tablename__ = "users"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    full_name: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(50), default="user")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())

    # Relationships
    owned_workspaces: Mapped[List["Workspace"]] = relationship(back_populates="owner")
    workspaces: Mapped[List["Workspace"]] = relationship("Workspace", secondary="workspace_users", back_populates="users")

class Workspace(Base):
    """Workspace model"""
    __tablename__ = "workspaces"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    name: Mapped[str] = mapped_column(String(255))
    owner_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())

    # Relationships
    owner: Mapped[User] = relationship(back_populates="owned_workspaces")
    bots: Mapped[List["Bot"]] = relationship(back_populates="workspace", cascade="all, delete-orphan")
    chats: Mapped[List["Chat"]] = relationship(back_populates="workspace", cascade="all, delete-orphan")
    users: Mapped[List["User"]] = relationship("User", secondary="workspace_users", back_populates="workspaces")

class WorkspaceUser(Base):
    __tablename__ = "workspace_users"

    workspace_id: Mapped[UUID] = mapped_column(ForeignKey("workspaces.id"), primary_key=True)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

class Bot(Base):
    """Bot model"""
    __tablename__ = "bots"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    workspace_id: Mapped[UUID] = mapped_column(ForeignKey("workspaces.id"))
    token: Mapped[str] = mapped_column(String(255), unique=True)
    name: Mapped[str] = mapped_column(String(255))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())

    # Relationships
    workspace: Mapped[Workspace] = relationship(back_populates="bots")

class Chat(Base):
    """Chat model"""
    __tablename__ = "chats"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    workspace_id: Mapped[UUID] = mapped_column(ForeignKey("workspaces.id"))
    telegram_id: Mapped[int] = mapped_column(BigInteger)
    username: Mapped[str] = mapped_column(String(255))
    photo_url: Mapped[Optional[str]] = mapped_column(String(1024), nullable=True)
    photo_data: Mapped[Optional[bytes]] = mapped_column(LargeBinary, nullable=True)
    last_message_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())

    # Relationships
    workspace: Mapped[Workspace] = relationship(back_populates="chats")
    messages: Mapped[List["Message"]] = relationship(
        back_populates="chat",
        cascade="all, delete-orphan",
        order_by="Message.sent_at.desc()",
        overlaps="last_message"
    )
    last_message: Mapped[Optional["Message"]] = relationship(
        "Message",
        primaryjoin="and_(Chat.id == Message.chat_id, "
                   "Chat.last_message_at == Message.sent_at)",
        overlaps="messages"
    )

    def to_dict(self) -> Dict[str, Any]:
        """Convert chat to dictionary"""
        result = {
            "id": str(self.id),
            "workspace_id": str(self.workspace_id),
            "telegram_id": self.telegram_id,
            "username": self.username,
            "photo_url": None,  # Deprecated
            "photo_data": self.photo_data.hex() if self.photo_data else None,
            "last_message_at": self.last_message_at.isoformat() if self.last_message_at else None,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }
        
        if self.last_message:
            result["last_message"] = self.last_message.to_dict()
        
        return result

class Message(Base):
    """Message model"""
    __tablename__ = "messages"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    chat_id: Mapped[UUID] = mapped_column(ForeignKey("chats.id"))
    content: Mapped[str] = mapped_column(String)
    direction: Mapped[str] = mapped_column(String(50))
    sent_at: Mapped[datetime] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())

    # Relationships
    chat: Mapped[Chat] = relationship(back_populates="messages", overlaps="last_message")

    def to_dict(self) -> Dict[str, Any]:
        """Convert message to dictionary"""
        return {
            "id": str(self.id),
            "content": self.content,
            "sent_at": self.sent_at.isoformat(),
            "direction": self.direction,
            "chat_id": str(self.chat_id)
        } 