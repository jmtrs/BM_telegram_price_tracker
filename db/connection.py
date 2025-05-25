# db/connection.py
import asyncpg
import logging
import config
from typing import Optional # Import Optional

logger = logging.getLogger(__name__)
db_pool: Optional[asyncpg.Pool] = None # Explicitly type hint db_pool

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
        except (asyncpg.exceptions.PostgresError, OSError) as e: # OSError for connection issues
            logger.critical(f"CRITICAL error initializing database connection pool: {e}")
            # Depending on application design, you might want to re-raise or exit
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

# Example of how to acquire a connection (to be used in repositories/use_cases):
# async def example_usage():
#     pool = await get_db_pool()
#     async with pool.acquire() as connection:
#         # Use the connection for queries
#         # e.g., await connection.fetchval('SELECT 1')
#         pass

# Note: The original get_db_connection() and close_db_connection() using psycopg2
# are removed as they are replaced by the async pool mechanism.
