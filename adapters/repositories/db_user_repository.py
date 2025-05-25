# adapters/repositories/db_user_repository.py
from typing import Optional
from uuid import UUID
import logging

from application_core.domain_models.user_model import User
from application_core.ports.user_repository_port import UserRepositoryPort
from db import queries as db_queries
from db.connection import get_db_pool  # Import get_db_pool

logger = logging.getLogger(__name__)


class DbUserRepository(UserRepositoryPort):
    async def get_by_id(self, user_id: UUID) -> Optional[User]:
        logger.debug(f"Attempting to get user by id: {user_id}")
        pool = await get_db_pool()
        async with pool.acquire() as conn:
            user_data = await db_queries.get_user_by_id(conn, user_id)
        if user_data:
            return User(**user_data)
        return None

    async def get_by_telegram_id(self, telegram_chat_id: int) -> Optional[User]:
        logger.debug(f"Attempting to get user by telegram_chat_id: {telegram_chat_id}")
        pool = await get_db_pool()
        async with pool.acquire() as conn:
            user_data = await db_queries.get_user_by_telegram_id(conn, telegram_chat_id)
        if user_data:
            return User(**user_data)
        return None

    async def get_by_idp_id(self, idp_user_id: str) -> Optional[User]:
        logger.debug(f"Attempting to get user by idp_user_id: {idp_user_id}")
        pool = await get_db_pool()
        async with pool.acquire() as conn:
            user_data = await db_queries.get_user_by_idp_id(conn, idp_user_id)
        if user_data:
            return User(**user_data)
        return None

    async def add(self, user: User) -> Optional[User]:
        logger.debug(f"Attempting to add user: {user.idp_user_id or user.telegram_chat_id}")
        pool = await get_db_pool()
        async with pool.acquire() as conn:
            async with conn.transaction():
                user_data = await db_queries.add_user(
                    conn,
                    telegram_chat_id=user.telegram_chat_id,
                    idp_user_id=user.idp_user_id,
                    username=user.username,
                    is_active=user.is_active
                )
        if user_data:
            return User(**user_data)
        logger.error(f"Failed to add user ({user.idp_user_id or user.telegram_chat_id}) to the database.")
        return None

    async def update(self, user: User) -> Optional[User]:
        logger.debug(f"Attempting to update user: {user.id}")
        pool = await get_db_pool()
        async with pool.acquire() as conn:
            async with conn.transaction():
                updated_user_data = await db_queries.update_user(
                    conn,
                    user_id=user.id,
                    username=user.username,
                    is_active=user.is_active
                )
        if updated_user_data:
            return User(**updated_user_data)
        return None
