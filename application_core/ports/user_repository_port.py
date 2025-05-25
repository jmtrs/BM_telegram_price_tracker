# application_core/ports/user_repository_port.py
from abc import ABC, abstractmethod
from typing import Optional
from uuid import UUID

from application_core.domain_models.user_model import User


class UserRepositoryPort(ABC):
    @abstractmethod
    async def get_by_id(self, user_id: UUID) -> Optional[User]:
        pass

    @abstractmethod
    async def get_by_telegram_id(self, telegram_chat_id: int) -> Optional[User]:
        pass

    @abstractmethod
    async def get_by_idp_id(self, idp_user_id: str) -> Optional[User]:
        pass

    @abstractmethod
    async def add(self, user: User) -> Optional[User]:  # Changed User to Optional[User]
        pass

    @abstractmethod
    async def update(self, user: User) -> Optional[User]:
        pass

    # Optional: A method to list users, could be useful for admin purposes
    # @abstractmethod
    # async def list_all(self) -> list[User]:
    # pass
