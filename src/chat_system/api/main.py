import logging
from pathlib import Path
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from src.chat_system.api.routers import auth, pages, workspaces
from src.chat_system.core.config import STATIC_DIR, TEMPLATES_DIR
from src.chat_system.db.base import Base
from src.chat_system.db.session import engine
from src.chat_system.telegram.manager import telegram_manager

# Configure logging
# logging.basicConfig(
#     level=logging.INFO,
#     format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
# )
logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan context manager for startup and shutdown events"""
    logger.info("Starting up application...")
    
    # Create database tables
    async with engine.begin() as conn:
        logger.info("Creating database tables...")
        await conn.run_sync(Base.metadata.create_all)
        logger.info("Database tables created successfully")

    # Initialize bots on startup
    await telegram_manager.initialize_from_db()
    
    yield
    
    # Cleanup on shutdown
    logger.info("Shutting down application...")
    await telegram_manager.cleanup()

# Create FastAPI application
app = FastAPI(title="Chat System", lifespan=lifespan)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount static files
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

# Setup templates
templates = Jinja2Templates(directory=TEMPLATES_DIR)

# Include routers
app.include_router(pages.router, tags=["pages"])
app.include_router(auth.router, prefix="/api/auth", tags=["auth"])
app.include_router(workspaces.router, prefix="/api/workspaces", tags=["workspaces"]) 