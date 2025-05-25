# application_core/ports/alert_repository_port.py
from abc import ABC, abstractmethod
from typing import Optional, List
from uuid import UUID
import asyncpg # For type hinting asyncpg.Record or a custom Alert domain model

# It would be better to define an Alert domain model in domain_models/
# and have repository methods return that instead of raw asyncpg.Record.
# For now, we'll use asyncpg.Record or dict for simplicity, aligning with db_queries.
# from ..domain_models.alert_model import Alert # Assuming you create this

class AlertRepositoryPort(ABC):
    @abstractmethod
    async def get_by_id(self, alert_id: UUID) -> Optional[asyncpg.Record]: # Or Optional[Alert]
        pass

    @abstractmethod
    async def get_by_chat_and_clean_url(self, chat_id: int, clean_url: str) -> Optional[asyncpg.Record]: # Or Optional[Alert]
        pass

    @abstractmethod
    async def get_alerts_by_chat_id(self, chat_id: int) -> List[asyncpg.Record]: # Or List[Alert]
        pass

    @abstractmethod
    async def create_alert(
        self,
        chat_id: int,
        full_url: str,
        clean_url: str,
        target_price: float,
        product_name: Optional[str]
    ) -> UUID: # Returns new alert ID
        pass

    @abstractmethod
    async def update_target_price(self, alert_id: UUID, target_price: float, full_url: str) -> None:
        pass

    @abstractmethod
    async def delete_alert(self, alert_id: UUID, chat_id: int) -> bool: # chat_id for ownership check
        pass

    @abstractmethod
    async def update_last_price(self, alert_id: UUID, current_price: Optional[float]) -> None:
        pass

    @abstractmethod
    async def update_last_notified(self, alert_id: UUID) -> None:
        pass

    @abstractmethod
    async def get_all_alerts_for_checker(self) -> List[asyncpg.Record]: # Or List[Alert]
        pass
