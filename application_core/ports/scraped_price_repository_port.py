from abc import ABC, abstractmethod
from typing import Optional
from application_core.domain_models.product_info_model import ProductInfo
import asyncpg # MODIFIED: Import asyncpg

class ScrapedPriceRepositoryPort(ABC):
    """Port for interacting with the storage of scraped product prices."""

    @abstractmethod
    async def save_or_update_scraped_product(self, product_info: ProductInfo, db_conn: Optional[asyncpg.Connection] = None) -> None: # MODIFIED: Made async, changed db_conn type
        """
        Saves a new scraped product's information or updates it if it already exists
        based on the clean_url.
        """
        pass
