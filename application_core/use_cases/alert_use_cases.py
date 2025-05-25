# application_core/use_cases/alert_use_cases.py
import logging
from typing import Optional, List, Tuple
from uuid import UUID
import asyncpg # For type hinting if returning records directly

from ..ports.alert_repository_port import AlertRepositoryPort
from ..ports.user_repository_port import UserRepositoryPort
from ..domain_models.user_model import User
# from ..domain_models.alert_model import Alert # If you create an Alert domain model

from scraper import core as scraper_core
from scraper import utils as scraper_utils

# For API responses, we might need to define specific DTOs (Data Transfer Objects)
# or use the Pydantic schemas defined in adapters/api/schemas.py if appropriate for use cases.
# For now, use cases might return repository data or simple structures.
from adapters.api import schemas as api_schemas # For structuring responses, be mindful of hexagonal layers

logger = logging.getLogger(__name__)

class CreateOrUpdateAlertUseCase:
    def __init__(self, alert_repository: AlertRepositoryPort, user_repository: UserRepositoryPort):
        self.alert_repository = alert_repository
        self.user_repository = user_repository
        # Potentially inject scraper service/port here too if its logic becomes more complex

    async def execute(self, idp_user_id: str, url: str, target_price: float) -> Tuple[Optional[asyncpg.Record], api_schemas.ScrapedProductInfo, str]:
        # 1. Get or create user
        # This part might be handled by a dedicated GetOrCreateUserByIdpIdUseCase instance
        # For now, directly using user_repository for simplicity in this combined use case.
        user = await self.user_repository.get_by_idp_id(idp_user_id)
        if not user:
            # Logic for creating user if not found (simplified here, ideally from GetOrCreateUserByIdpIdUseCase)
            logger.info(f"User with idp_user_id {idp_user_id} not found. API should ensure user exists or handle creation.")
            # This use case might assume user exists or be part of a larger flow where user is created first.
            # For now, let's raise an error or return a specific status if user creation is not in scope here.
            raise ValueError(f"User with idp_user_id {idp_user_id} not found. Creation logic not implemented in this specific use case path.")

        if not user.telegram_chat_id:
            logger.warning(f"User {user.id} (idp_user_id: {idp_user_id}) has no associated telegram_chat_id.")
            raise ValueError("User profile is not associated with a Telegram chat.")

        chat_id = user.telegram_chat_id

        # 2. Clean URL
        cleaned_url = scraper_utils.clean_url(url)
        if not cleaned_url:
            raise ValueError("Invalid or unprocessable product URL.")

        # 3. Scrape product info
        product_info_dict = await scraper_core.get_product_info(url)
        scraped_product_info_schema = api_schemas.ScrapedProductInfo(
            name=product_info_dict.get("name"),
            price=product_info_dict.get("price"),
            condition=product_info_dict.get("condition") or product_info_dict.get("product_condition"),
            image=product_info_dict.get("image"),
            description=product_info_dict.get("description"),
            availability=product_info_dict.get("availability"),
            color=product_info_dict.get("color"),
            storage=product_info_dict.get("storage"),
            brand_name=product_info_dict.get("brand_name"),
            clean_url=product_info_dict.get("clean_url", cleaned_url),
            full_url=product_info_dict.get("full_url", url),
            status=product_info_dict.get("status", "UNKNOWN_SCRAPE_STATUS")
        )

        # 4. Create or Update Alert in DB
        status_message = ""
        alert_record = None
        product_name_for_db = product_info_dict.get("name") if scraped_product_info_schema.status == "SCRAPED_SUCCESS" else None

        existing_alert = await self.alert_repository.get_by_chat_and_clean_url(chat_id, cleaned_url)

        if existing_alert:
            alert_id = existing_alert['id']
            await self.alert_repository.update_target_price(alert_id, target_price, url)
            status_message = "Alert updated successfully."
            alert_record = await self.alert_repository.get_by_id(alert_id)
        else:
            new_alert_id = await self.alert_repository.create_alert(
                chat_id=chat_id,
                full_url=url,
                clean_url=cleaned_url,
                target_price=target_price,
                product_name=product_name_for_db
            )
            status_message = "Alert created successfully."
            alert_record = await self.alert_repository.get_by_id(new_alert_id)

        if not alert_record:
            # This implies an issue after creation/update, e.g., get_by_id failed
            raise Exception("Failed to retrieve alert details after database operation.")

        return alert_record, scraped_product_info_schema, status_message

class ListUserAlertsUseCase:
    def __init__(self, alert_repository: AlertRepositoryPort, user_repository: UserRepositoryPort):
        self.alert_repository = alert_repository
        self.user_repository = user_repository

    async def execute(self, idp_user_id: str) -> List[asyncpg.Record]: # Or List[Alert]
        user = await self.user_repository.get_by_idp_id(idp_user_id)
        if not user:
            raise ValueError(f"User with idp_user_id {idp_user_id} not found.")
        if not user.telegram_chat_id:
            raise ValueError("User profile is not associated with a Telegram chat.")

        return await self.alert_repository.get_alerts_by_chat_id(user.telegram_chat_id)

class DeleteAlertUseCase:
    def __init__(self, alert_repository: AlertRepositoryPort, user_repository: UserRepositoryPort):
        self.alert_repository = alert_repository
        self.user_repository = user_repository

    async def execute(self, idp_user_id: str, alert_id_to_delete: UUID) -> bool:
        user = await self.user_repository.get_by_idp_id(idp_user_id)
        if not user:
            raise ValueError(f"User with idp_user_id {idp_user_id} not found.")
        if not user.telegram_chat_id:
            raise ValueError("User profile is not associated with a Telegram chat for ownership verification.")

        chat_id_of_requesting_user = user.telegram_chat_id

        alert_to_verify = await self.alert_repository.get_by_id(alert_id_to_delete)
        if not alert_to_verify:
            raise ValueError("Alert not found.") # Or a custom NotFoundError

        if alert_to_verify['chat_id'] != chat_id_of_requesting_user:
            # Forbidden access
            raise PermissionError("User does not have permission to delete this alert.")

        return await self.alert_repository.delete_alert(alert_id_to_delete, chat_id_of_requesting_user)

class GetProductInfoUseCase:
    # This use case might not need a repository if it only uses the scraper
    def __init__(self): # Potentially inject a scraper port/service
        pass

    async def execute(self, url: str) -> api_schemas.ScrapedProductInfo:
        if not url:
            raise ValueError("URL query parameter is required.")
        cleaned_url = scraper_utils.clean_url(url)
        if not cleaned_url:
            raise ValueError("Invalid or unprocessable product URL.")

        product_info_dict = await scraper_core.get_product_info(url)
        return api_schemas.ScrapedProductInfo(
            name=product_info_dict.get("name"),
            price=product_info_dict.get("price"),
            condition=product_info_dict.get("condition") or product_info_dict.get("product_condition"),
            image=product_info_dict.get("image"),
            description=product_info_dict.get("description"),
            availability=product_info_dict.get("availability"),
            color=product_info_dict.get("color"),
            storage=product_info_dict.get("storage"),
            brand_name=product_info_dict.get("brand_name"),
            clean_url=product_info_dict.get("clean_url", cleaned_url),
            full_url=product_info_dict.get("full_url", url),
            status=product_info_dict.get("status", "UNKNOWN_SCRAPE_STATUS")
        )

