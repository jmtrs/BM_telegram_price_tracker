# adapters/repositories/db_alert_repository.py
from typing import Optional, List
from uuid import UUID
import asyncpg
import logging

from application_core.ports.alert_repository_port import AlertRepositoryPort
# from application_core.domain_models.alert_model import Alert # If you create an Alert domain model
from db import queries as db_queries
from db.connection import get_db_pool

logger = logging.getLogger(__name__)


class DbAlertRepository(AlertRepositoryPort):
    async def get_by_id(self, alert_id: UUID) -> Optional[asyncpg.Record]:
        pool = await get_db_pool()
        async with pool.acquire() as conn:
            return await db_queries.get_alert_by_id(conn, str(alert_id))

    async def get_by_chat_and_clean_url(self, chat_id: int, clean_url: str) -> Optional[asyncpg.Record]:
        pool = await get_db_pool()
        async with pool.acquire() as conn:
            return await db_queries.get_alert_by_chat_and_clean_url(conn, chat_id, clean_url)

    async def get_alerts_by_chat_id(self, chat_id: int) -> List[asyncpg.Record]:
        pool = await get_db_pool()
        async with pool.acquire() as conn:
            return await db_queries.get_user_alerts(conn, chat_id)

    async def create_alert(
            self,
            chat_id: int,
            full_url: str,
            clean_url: str,
            target_price: float,
            product_name: Optional[str]
    ) -> UUID:
        pool = await get_db_pool()
        async with pool.acquire() as conn:
            async with conn.transaction():  # create_alert in queries.py returns the ID
                new_alert_id = await db_queries.create_alert(
                    conn, chat_id, full_url, clean_url, target_price, product_name
                )
                return new_alert_id

    async def update_target_price(self, alert_id: UUID, target_price: float, full_url: str) -> None:
        pool = await get_db_pool()
        async with pool.acquire() as conn:
            async with conn.transaction():
                await db_queries.update_alert_target_price(conn, str(alert_id), target_price, full_url)

    async def delete_alert(self, alert_id: UUID, chat_id: int) -> bool:
        pool = await get_db_pool()
        async with pool.acquire() as conn:
            async with conn.transaction():
                return await db_queries.delete_alert_by_id(conn, str(alert_id), chat_id)

    async def update_last_price(self, alert_id: UUID, current_price: Optional[float]) -> None:
        pool = await get_db_pool()
        async with pool.acquire() as conn:
            async with conn.transaction():
                await db_queries.update_alert_last_price(conn, str(alert_id), current_price)

    async def update_last_notified(self, alert_id: UUID) -> None:
        pool = await get_db_pool()
        async with pool.acquire() as conn:
            async with conn.transaction():
                await db_queries.update_alert_last_notified(conn, str(alert_id))

    async def get_all_alerts_for_checker(self) -> List[asyncpg.Record]:
        pool = await get_db_pool()
        async with pool.acquire() as conn:
            return await db_queries.get_all_alerts(conn)
