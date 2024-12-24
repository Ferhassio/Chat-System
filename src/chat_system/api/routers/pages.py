from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from src.chat_system.api.deps import get_current_user
from src.chat_system.core.config import TEMPLATES_DIR
from src.chat_system.db.models import User

router = APIRouter()
templates = Jinja2Templates(directory=TEMPLATES_DIR)

@router.get("/", response_class=HTMLResponse)
async def index(request: Request) -> HTMLResponse:
    """Render index page"""
    return templates.TemplateResponse("index.html", {"request": request})

@router.get("/auth", response_class=HTMLResponse)
async def auth_page(request: Request) -> HTMLResponse:
    """Render auth page"""
    return templates.TemplateResponse("auth.html", {"request": request}) 