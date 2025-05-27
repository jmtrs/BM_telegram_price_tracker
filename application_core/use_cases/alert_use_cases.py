# application_core/use_cases/alert_use_cases.py
import logging
from typing import List, Tuple
from uuid import UUID
from application_core.domain_models.alert_model import Alert

from ..ports.alert_repository_port import AlertRepositoryPort
from ..ports.user_repository_port import UserRepositoryPort
from ..ports.scraped_price_repository_port import ScrapedPriceRepositoryPort

from scraper import core as scraper_core
from scraper import utils as scraper_utils
from db.connection import get_db_pool
from db import queries as db_queries

from application_core.domain_models.product_info_model import ProductInfo
import config

logger = logging.getLogger(__name__)


class CreateOrUpdateAlertUseCase:
    def __init__(self, alert_repository: AlertRepositoryPort, user_repository: UserRepositoryPort,
                 scraped_price_repository: ScrapedPriceRepositoryPort):
        self.alert_repository = alert_repository
        self.user_repository = user_repository
        self.scraped_price_repository = scraped_price_repository

    async def execute(self, idp_user_id: str, url: str, target_price: float) -> Tuple[
        Alert, ProductInfo, str]:
        user = await self.user_repository.get_by_idp_id(idp_user_id)
        if not user:
            logger.info(
                f"User with idp_user_id {idp_user_id} not found. API should ensure user exists or handle creation.")
            raise ValueError(
                f"User with idp_user_id {idp_user_id} not found. Creation logic not implemented in this specific use case path.")

        cleaned_url = scraper_utils.clean_url(url)
        if not cleaned_url:
            raise ValueError("Invalid or unprocessable product URL.")

        # Siempre intentar usar ScraperAPI; scraper_core manejará si la clave no está.
        product_info_dict = await scraper_core.get_product_info(url, use_api=True)
        # Build domain model for product info
        product_info = ProductInfo(
            name=product_info_dict.get("name"),
            price=product_info_dict.get("price"),
            product_condition=product_info_dict.get("condition"),
            image_url=product_info_dict.get("image"),
            description=product_info_dict.get("description"),
            availability=product_info_dict.get("availability"),
            color=product_info_dict.get("color"),
            storage=product_info_dict.get("storage"),
            brand_name=product_info_dict.get("brand_name"),
            clean_url=cleaned_url, 
            full_url=url,
            status=product_info_dict.get("status", "UNKNOWN_SCRAPE_STATUS")
        )

        try:
            await self.scraped_price_repository.save_or_update_scraped_product(product_info)
            logger.info(f"Successfully recorded scraped product info for {cleaned_url} in scraped_prices table via async use case.")
        except Exception as e:
            logger.error(f"Failed to record scraped product info for {cleaned_url} in CreateOrUpdateAlertUseCase (async): {e}")

        alert = await self.alert_repository.upsert_alert(
            user_id=user.id,
            full_url=url,
            clean_url=cleaned_url,
            target_price=target_price
        )
        status_message = "Alert created or updated successfully."
        return alert, product_info, status_message


class ListUserAlertsUseCase:
    def __init__(self, alert_repository: AlertRepositoryPort, user_repository: UserRepositoryPort):
        self.alert_repository = alert_repository
        self.user_repository = user_repository

    async def execute(self, idp_user_id: str) -> List[Alert]:
        user = await self.user_repository.get_by_idp_id(idp_user_id)
        if not user:
            raise ValueError(f"User with idp_user_id {idp_user_id} not found.")
        alerts = await self.alert_repository.get_alerts_by_user_id(user.id)
        return alerts


class DeleteAlertUseCase:
    def __init__(self, alert_repository: AlertRepositoryPort, user_repository: UserRepositoryPort):
        self.alert_repository = alert_repository
        self.user_repository = user_repository

    async def execute(self, idp_user_id: str, alert_id_to_delete: UUID) -> bool:
        user = await self.user_repository.get_by_idp_id(idp_user_id)
        if not user:
            raise ValueError(f"User with idp_user_id {idp_user_id} not found.")
        # Verify ownership by user_id
        alert = await self.alert_repository.get_by_id(alert_id_to_delete)
        if not alert:
            raise ValueError("Alert not found.")
        if alert.user_id != user.id:
            raise PermissionError("User does not have permission to delete this alert.")
        return await self.alert_repository.delete_alert(alert_id_to_delete, user.id)


class GetProductInfoUseCase:
    @staticmethod
    async def execute(url: str) -> ProductInfo:
        if not url:
            raise ValueError("URL query parameter is required.")
        cleaned_url = scraper_utils.clean_url(url)
        if not cleaned_url:
            raise ValueError("Invalid or unprocessable product URL.")

        should_use_scraper_api = bool(config.SCRAPERAPI_KEY)

        # Intentar cache
        pool = await get_db_pool()
        async with pool.acquire() as conn:
            cached = await db_queries.get_cached_price(conn, cleaned_url)
        if cached:
            return ProductInfo(
                name=cached.get('name'),
                price=cached.get('price'),
                product_condition=cached.get('condition'),
                image_url=cached.get('image'),
                description=cached.get('description'),
                availability=cached.get('availability'),
                color=cached.get('color'),
                storage=cached.get('storage'),
                brand_name=cached.get('brand_name'),
                clean_url=cleaned_url,
                full_url=url,
                status="CACHE_HIT"
            )

        product_info_dict = await scraper_core.get_product_info(url, use_api=True)
        # Guardar en cache
        async with pool.acquire() as conn:
            await db_queries.save_scraped_price(conn, cleaned_url, product_info_dict)
        # Return domain model
        return ProductInfo(
            name=product_info_dict.get("name"),
            price=product_info_dict.get("price"),
            product_condition=product_info_dict.get("condition"),
            image_url=product_info_dict.get("image"),
            description=product_info_dict.get("description"),
            availability=product_info_dict.get("availability"),
            color=product_info_dict.get("color"),
            storage=product_info_dict.get("storage"),
            brand_name=product_info_dict.get("brand_name"),
            clean_url=cleaned_url,
            full_url=url,
            status=product_info_dict.get("status", "UNKNOWN_SCRAPE_STATUS")
        )
