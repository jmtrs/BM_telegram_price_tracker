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
        logger.debug(f"Intentando obtener usuario por idp_user_id: {idp_user_id}")
        pool = await get_db_pool()
        async with pool.acquire() as conn:
            user_data = await db_queries.get_user_by_idp_id(conn, idp_user_id)
        if user_data:
            logger.debug(f"Usuario encontrado por idp_user_id {idp_user_id}: {user_data['id']}")
            return User(**user_data)
        logger.debug(f"Usuario no encontrado por idp_user_id: {idp_user_id}")
        return None

    async def add(self, user: User) -> Optional[User]:
        """Añade un usuario a la base de datos usando el objeto User del dominio."""
        logger.debug(f"Intentando añadir usuario (modelo): idp_id={user.idp_user_id}, tg_id={user.telegram_chat_id}")
        pool = await get_db_pool()
        async with pool.acquire() as conn:
            async with conn.transaction():
                # El ID del usuario es generado por la BD, no se pasa aquí.
                user_data = await db_queries.add_user(
                    conn,
                    telegram_chat_id=user.telegram_chat_id,
                    idp_user_id=user.idp_user_id,
                    username=user.username,
                    is_active=user.is_active
                )
        if user_data:
            logger.info(f"Usuario añadido exitosamente con ID: {user_data['id']}")
            # Actualizar el ID del objeto user con el generado por la BD
            user_with_id = user.model_copy(update={"id": user_data['id'], "created_at": user_data['created_at']})
            return user_with_id
        logger.error(f"Fallo al añadir usuario (modelo): idp_id={user.idp_user_id}, tg_id={user.telegram_chat_id}")
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

    async def add_user(self, telegram_chat_id: int | None, idp_user_id: str | None,
                       username: str | None, is_active: bool) -> Optional[User]:
        """Crea un nuevo usuario en la BD con identificadores proporcionados. (Método legado, preferir add)."""
        logger.debug(f"Intentando añadir usuario vía add_user (legado): chat_id={telegram_chat_id}, idp_id={idp_user_id}")
        
        pool = await get_db_pool()
        async with pool.acquire() as conn:
            async with conn.transaction():
                # El ID es generado por la BD.
                user_data = await db_queries.add_user(
                    conn,
                    telegram_chat_id=telegram_chat_id,
                    idp_user_id=idp_user_id,
                    username=username,
                    is_active=is_active
                )
        if user_data:
            logger.info(f"Usuario añadido (legado) con ID: {user_data['id']}")
            return User(**user_data)
        logger.error(f"Fallo al añadir usuario (legado): chat_id={telegram_chat_id}, idp_id={idp_user_id}")
        return None

