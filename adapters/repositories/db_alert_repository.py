# adapters/repositories/db_alert_repository.py
from typing import Optional, List
from uuid import UUID
import asyncpg
import logging

from application_core.ports.alert_repository_port import AlertRepositoryPort
from application_core.domain_models.alert_model import Alert
from db import queries as db_queries
from db.connection import get_db_pool

logger = logging.getLogger(__name__)


class DbAlertRepository(AlertRepositoryPort):
    async def get_by_id(self, alert_id: UUID) -> Optional[Alert]:
        pool = await get_db_pool()
        async with pool.acquire() as conn:
            record = await db_queries.get_alert_by_id(conn, str(alert_id))
        return Alert(**dict(record)) if record else None

    async def update_target_price(self, alert_id: UUID, target_price: float, full_url: str) -> None:
        pool = await get_db_pool()
        async with pool.acquire() as conn:
            async with conn.transaction():
                await db_queries.update_alert_target_price(conn, str(alert_id), target_price, full_url)

    async def delete_alert(self, alert_id: UUID, user_id: UUID) -> bool:
        pool = await get_db_pool()
        async with pool.acquire() as conn:
            async with conn.transaction():
                return await db_queries.delete_alert_by_id(conn, str(alert_id), user_id)

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

    async def upsert_alert(self, user_id: UUID, full_url: str, clean_url: str, target_price: float) -> UUID:
        """Insert or update an alert atomically based on user_id and clean_url."""
        pool = await get_db_pool()
        async with pool.acquire() as conn:
            async with conn.transaction():
                new_id = await db_queries.upsert_alert(conn, user_id, full_url, clean_url, target_price)
        return await self.get_by_id(new_id)

    async def get_alerts_by_user_id(self, user_id: UUID) -> List[Alert]:
        """Get all alerts belonging to a user by internal user_id."""
        pool = await get_db_pool()
        async with pool.acquire() as conn:
            records = await db_queries.get_user_alerts(conn, user_id)
        return [Alert(**dict(r)) for r in records]
