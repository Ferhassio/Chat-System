import psycopg2
import asyncio
import logging
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT
from src.chat_system.db.session import engine
from src.chat_system.db.models import Base
from src.chat_system.core.cache import cache

logger = logging.getLogger(__name__)

async def recreate_database():
    """Drop and recreate the database"""
    try:
        # Connect to postgres database
        conn = psycopg2.connect(
            dbname="postgres",
            user="postgres",
            password="66666VetkaSotona666666",
            host="localhost",
            port="5432"
        )
        conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
        
        # Create cursor
        cur = conn.cursor()

        # Drop database if exists
        cur.execute("DROP DATABASE IF EXISTS chat_system")
        logger.info("Dropped existing database")

        # Create database
        cur.execute("CREATE DATABASE chat_system")
        logger.info("Created new database")
        
        # Close cursor and connection
        cur.close()
        conn.close()

        # Clear Redis cache
        await cache.clear_all()
        logger.info("Redis cache cleared")

        # Create tables
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
            logger.info("Database tables created successfully")

    except Exception as e:
        logger.error(f"Error recreating database: {e}")
        raise

if __name__ == "__main__":
    asyncio.run(recreate_database()) 
