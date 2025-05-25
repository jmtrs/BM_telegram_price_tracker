# application_core/use_cases/user_use_cases.py
import logging
from typing import Optional
from uuid import uuid4  # For generating new user IDs

from application_core.domain_models.user_model import User
from application_core.ports.user_repository_port import UserRepositoryPort

logger = logging.getLogger(__name__)

class GetOrCreateUserByTelegramIdUseCase:
    def __init__(self, user_repository: UserRepositoryPort):
        self.user_repository = user_repository

    async def execute(self, telegram_chat_id: int, username: Optional[str] = None) -> Optional[User]:
        logger.debug(f"Executing GetOrCreateUserByTelegramIdUseCase for telegram_chat_id: {telegram_chat_id}")
        user = await self.user_repository.get_by_telegram_id(telegram_chat_id)
        if user:
            logger.info(f"User found by telegram_chat_id {telegram_chat_id}: {user.id}")
            # Optionally update username if it has changed or is now provided
            if username and user.username != username:
                user.username = username
                updated_user = await self.user_repository.update(user)
                if updated_user:
                    logger.info(f"Username updated for user {user.id}")
                    return updated_user
                else:
                    logger.warning(f"Failed to update username for user {user.id}")
                    return user  # Return original user if update fails
            return user

        logger.info(f"User not found by telegram_chat_id {telegram_chat_id}. Creating new user.")
        new_user_domain = User(
            id=uuid4(),  # Generate a new UUID for the user
            telegram_chat_id=telegram_chat_id,
            idp_user_id=None,
            username=username,
            is_active=True
        )
        created_user = await self.user_repository.add(new_user_domain)
        if created_user:
            logger.info(f"New user created with telegram_chat_id {telegram_chat_id}: {created_user.id}")
            return created_user
        else:
            logger.error(f"Failed to create new user for telegram_chat_id {telegram_chat_id}")
            return None

class GetOrCreateUserByIdpIdUseCase:
    def __init__(self, user_repository: UserRepositoryPort):
        self.user_repository = user_repository

    async def execute(self, idp_user_id: str, username: Optional[str] = None) -> Optional[User]:
        logger.debug(f"Executing GetOrCreateUserByIdpIdUseCase for idp_user_id: {idp_user_id}")
        user = await self.user_repository.get_by_idp_id(idp_user_id)
        if user:
            logger.info(f"User found by idp_user_id {idp_user_id}: {user.id}")
            # Optionally update username if it has changed or is now provided
            if username and user.username != username:
                user.username = username
                updated_user = await self.user_repository.update(user)
                if updated_user:
                    logger.info(f"Username updated for user {user.id}")
                    return updated_user
                else:
                    logger.warning(f"Failed to update username for user {user.id}")
                    return user  # Return original user if update fails
            return user

        logger.info(f"User not found by idp_user_id {idp_user_id}. Creating new user.")
        new_user_domain = User(
            id=uuid4(),  # Generate a new UUID for the user
            telegram_chat_id=None,
            idp_user_id=idp_user_id,
            username=username,
            is_active=True
        )
        created_user = await self.user_repository.add(new_user_domain)
        if created_user:
            logger.info(f"New user created with idp_user_id {idp_user_id}: {created_user.id}")
            return created_user
        else:
            logger.error(f"Failed to create new user for idp_user_id {idp_user_id}")
            return None
