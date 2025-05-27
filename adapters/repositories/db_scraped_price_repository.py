import logging
from typing import Optional
import asyncpg

from application_core.domain_models.product_info_model import ProductInfo
from application_core.ports.scraped_price_repository_port import ScrapedPriceRepositoryPort
from db.connection import get_db_pool
from db import queries as db_queries

logger = logging.getLogger(__name__)

class DBScrapedPriceRepository(ScrapedPriceRepositoryPort):
    """Adapter for interacting with the scraped_prices table using asyncpg, delegating SQL to db.queries."""

    async def save_or_update_scraped_product(self, product_info: ProductInfo, db_conn_provided: Optional[asyncpg.Connection] = None) -> None: # MODIFIED: Made async, changed db_conn type
        """
        Saves a new scraped product's information or updates it if it already exists,
        by calling an async query function from db.queries.
        """
        
        conn_was_provided = db_conn_provided is not None
        conn = db_conn_provided
        pool = None

        if not conn_was_provided:
            pool = await get_db_pool()
            conn = await pool.acquire()

        try:
            # Prepare product_details dict for the existing save_scraped_price query
            # Ensure HttpUrl fields are converted to strings if your query expects strings
            image_url_str = str(product_info.image_url) if product_info.image_url else None

            product_details_for_query = {
                'price': product_info.price,
                'condition': product_info.product_condition,
                'name': product_info.name,
                'description': product_info.description,
                'image': image_url_str,
                'color': product_info.color,
                'storage': product_info.storage,
                'brand_name': product_info.brand_name,
                'availability': product_info.availability
            }
            
            # Call the existing async save_scraped_price from db_queries
            await db_queries.save_scraped_price(conn, product_info.clean_url, product_details_for_query)
            
            logger.info(f"Successfully saved/updated scraped product info via async repository for: {product_info.clean_url}")
        except asyncpg.PostgresError as e:
            logger.error(f"Asyncpg database error while saving/updating scraped product {product_info.clean_url}: {e}")
        
            raise
        except Exception as e:
            logger.error(f"Unexpected async error while saving/updating scraped product {product_info.clean_url}: {e}")
            raise
        finally:
            if not conn_was_provided and conn:
                await pool.release(conn)
