# application_core/ports/alert_repository_port.py
from abc import ABC, abstractmethod
from typing import Optional, List
from uuid import UUID
import asyncpg
from application_core.domain_models.alert_model import Alert


class AlertRepositoryPort(ABC):
    @abstractmethod
    async def get_by_id(self, alert_id: UUID) -> Optional[Alert]:
        pass

    @abstractmethod
    async def update_target_price(self, alert_id: UUID, target_price: float, full_url: str) -> None:
        pass

    @abstractmethod
    async def delete_alert(self, alert_id: UUID, user_id: UUID) -> bool:  # user_id for ownership check
        pass

    @abstractmethod
    async def update_last_price(self, alert_id: UUID, current_price: Optional[float]) -> None:
        pass

    @abstractmethod
    async def update_last_notified(self, alert_id: UUID) -> None:
        pass

    @abstractmethod
    async def get_all_alerts_for_checker(self) -> List[asyncpg.Record]:  # Or List[Alert]
        pass

    @abstractmethod
    async def upsert_alert(self, user_id: UUID, full_url: str, clean_url: str, target_price: float) -> Alert:
        """Insert or update an alert atomically and return the domain model."""
        pass

    @abstractmethod
    async def get_alerts_by_user_id(self, user_id: UUID) -> List[Alert]:
        pass
