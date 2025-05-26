# db/connection.py
import asyncpg
import logging
import config
from typing import Optional

logger = logging.getLogger(__name__)
db_pool: Optional[asyncpg.Pool] = None 


async def init_db_pool():
    """Initializes the asynchronous database connection pool."""
    global db_pool
    if db_pool is None:
        try:
            db_pool = await asyncpg.create_pool(
                dsn=config.DATABASE_URL,
                min_size=5,  # Default is 10
                max_size=20  # Default is 10
            )
            logger.info("Database connection pool initialized successfully.")
        except (asyncpg.exceptions.PostgresError, OSError) as e:
            logger.critical(f"CRITICAL error initializing database connection pool: {e}")
            raise
    return db_pool


async def get_db_pool() -> asyncpg.Pool:
    """Returns the initialized database connection pool.
    Ensures the pool is initialized before returning.
    """
    if db_pool is None:
        # This ensures that if something tries to get the pool before explicit initialization,
        # it attempts to initialize it. However, explicit initialization at startup is preferred.
        logger.warning("DB pool accessed before explicit initialization. Attempting to initialize now.")
        await init_db_pool()

    assert db_pool is not None, "Database pool is not initialized and initialization failed."
    return db_pool


async def close_db_pool():
    """Closes the asynchronous database connection pool."""
    global db_pool
    if db_pool:
        try:
            await db_pool.close()
            logger.info("Database connection pool closed.")
            db_pool = None
        except Exception as e:
            logger.error(f"Error closing database connection pool: {e}")
    else:
        logger.info("No database connection pool to close.")
