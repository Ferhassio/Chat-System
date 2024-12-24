import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.chat_system.api.deps import get_session
from src.chat_system.api.schemas import Token, UserCreate, UserLogin, UserResponse
from src.chat_system.core.config import TEMPLATES_DIR
from src.chat_system.core.security import (
    create_access_token,
    get_password_hash,
    verify_password,
)
from src.chat_system.db.models import User

router = APIRouter()
logger = logging.getLogger(__name__)
templates = Jinja2Templates(directory=TEMPLATES_DIR)

@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request) -> HTMLResponse:
    """Render login page"""
    return templates.TemplateResponse("auth.html", {"request": request})

@router.post("/register", response_model=UserResponse)
async def register(
    user: UserCreate,
    session: AsyncSession = Depends(get_session),
) -> User:
    """Register new user"""
    # Check if user exists
    result = await session.execute(
        select(User).where(User.email == user.email)
    )
    if result.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Email already registered")
    
    # Create user
    db_user = User(
        email=user.email,
        password_hash=get_password_hash(user.password),
        full_name=user.full_name,
    )
    session.add(db_user)
    await session.commit()
    return db_user

@router.post("/login", response_model=Token)
async def login(
    user: UserLogin,
    response: Response,
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Login user"""
    # Get user
    result = await session.execute(
        select(User).where(User.email == user.email)
    )
    db_user = result.scalar_one_or_none()
    
    # Verify user and password
    if not db_user or not verify_password(user.password, db_user.password_hash):
        raise HTTPException(
            status_code=401,
            detail="Invalid email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    # Create access token
    access_token = create_access_token(user_id=db_user.id)
    
    # Set CORS headers
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Credentials"] = "true"
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, DELETE, OPTIONS"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization"
    
    return {"access_token": access_token, "token_type": "bearer"} 