# db/queries.py
import logging
from datetime import datetime, timedelta, timezone
from uuid import UUID
from .connection import get_db_connection
import config
import asyncpg

logger = logging.getLogger(__name__)

# --- Scraped Prices Queries ---

async def get_cached_price(conn: asyncpg.Connection, clean_url: str) -> asyncpg.Record | None:
    row = await conn.fetchrow("""
        SELECT price, product_condition, scraped_at,
               product_name, description, image_url,
               color, storage, brand_name
        FROM scraped_prices
        WHERE clean_url = $1
        ORDER BY scraped_at DESC LIMIT 1
    """, clean_url)

    if row and datetime.now(timezone.utc) - row['scraped_at'] < timedelta(minutes=config.SCRAPE_TTL_MINUTES):
        logger.info(f"Usando datos completos de caché para {clean_url}")
        return row
    return None

async def save_scraped_price(conn: asyncpg.Connection, clean_url: str, product_details: dict):
    params_for_query = {
        'clean_url': clean_url,
        'price': product_details.get('price'),
        'product_condition': product_details.get('condition'),
        'product_name': product_details.get('name'),
        'description': product_details.get('description'),
        'image_url': product_details.get('image'),
        'color': product_details.get('color'),
        'storage': product_details.get('storage'),
        'brand_name': product_details.get('brand_name')
    }
    await conn.execute("""
        INSERT INTO scraped_prices (clean_url, price, product_condition, product_name, description, image_url, color, storage, brand_name)
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
        ON CONFLICT (clean_url) DO UPDATE SET
            price = EXCLUDED.price,
            product_condition = EXCLUDED.product_condition,
            product_name = EXCLUDED.product_name,
            description = EXCLUDED.description,
            image_url = EXCLUDED.image_url,
            color = EXCLUDED.color,
            storage = EXCLUDED.storage,
            brand_name = EXCLUDED.brand_name,
            scraped_at = now()
    """, clean_url, params_for_query['price'], params_for_query['product_condition'],
         params_for_query['product_name'], params_for_query['description'], params_for_query['image_url'],
         params_for_query['color'], params_for_query['storage'], params_for_query['brand_name'])

async def cleanup_old_scraped_prices(conn: asyncpg.Connection) -> int:
    result = await conn.execute("DELETE FROM scraped_prices WHERE scraped_at < now() - interval '2 days'")
    deleted_count = int(result.split(" ")[1]) if result and result.startswith("DELETE ") else 0
    if deleted_count > 0:
        logger.info(f"Limpieza de caché: {deleted_count} registros eliminados.")
    return deleted_count

# --- Alerts Queries ---

async def get_alert_by_chat_and_clean_url(conn: asyncpg.Connection, chat_id: int, clean_url: str) -> asyncpg.Record | None:
    return await conn.fetchrow("SELECT * FROM alerts WHERE chat_id=$1 AND clean_url=$2", chat_id, clean_url)

async def get_alert_by_id(conn: asyncpg.Connection, alert_id: str) -> asyncpg.Record | None:
    return await conn.fetchrow("SELECT * FROM alerts WHERE id::text = $1", alert_id)

async def update_alert_target_price(conn: asyncpg.Connection, alert_id: str, target_price: float, full_url: str):
    await conn.execute(
        "UPDATE alerts SET target_price=$1, inserted_at=now(), full_url=$2 WHERE id::text=$3",
        target_price, full_url, alert_id
    )
    logger.info(f"Alerta {alert_id} actualizada. Nuevo objetivo: {target_price}€")

async def create_alert(conn: asyncpg.Connection, chat_id: int, full_url: str, clean_url: str, target_price: float, product_name: str | None = None) -> UUID:
    row = await conn.fetchrow("""
        INSERT INTO alerts (chat_id, full_url, clean_url, target_price) 
        VALUES ($1, $2, $3, $4) RETURNING id
    """, chat_id, full_url, clean_url, target_price)
    new_alert_id = row['id']
    logger.info(f"Nueva alerta ID {new_alert_id} creada para chat_id {chat_id}, URL: {clean_url}, Objetivo: {target_price}€")
    return new_alert_id

async def get_user_alerts(conn: asyncpg.Connection, chat_id: int) -> list[asyncpg.Record]:
    return await conn.fetch("SELECT * FROM alerts WHERE chat_id=$1 ORDER BY inserted_at DESC", chat_id)

async def delete_alert_by_id(conn: asyncpg.Connection, alert_id: str, chat_id: int) -> bool:
    deleted_row = await conn.fetchrow("DELETE FROM alerts WHERE id::text=$1 AND chat_id=$2 RETURNING id", alert_id, chat_id)
    if deleted_row:
        logger.info(f"Alerta {alert_id} eliminada para chat_id {chat_id}.")
        return True
    logger.warning(f"Intento de eliminar alerta {alert_id} (chat_id {chat_id}) fallido.")
    return False

async def get_all_alerts(conn: asyncpg.Connection) -> list[asyncpg.Record]:
    return await conn.fetch("SELECT * FROM alerts")

async def update_alert_last_price(conn: asyncpg.Connection, alert_id: str, current_price: float | None):
    await conn.execute(
        "UPDATE alerts SET last_price=$1, inserted_at=now() WHERE id::text=$2",
        current_price, alert_id
    )

async def update_alert_last_notified(conn: asyncpg.Connection, alert_id: str):
    await conn.execute("UPDATE alerts SET last_notified=now() WHERE id::text=$1", alert_id)

# --- User Queries ---

async def get_user_by_id(conn: asyncpg.Connection, user_id: UUID) -> asyncpg.Record | None:
    return await conn.fetchrow("SELECT * FROM users WHERE id = $1", user_id)

async def get_user_by_telegram_id(conn: asyncpg.Connection, telegram_chat_id: int) -> asyncpg.Record | None:
    return await conn.fetchrow("SELECT * FROM users WHERE telegram_chat_id = $1", telegram_chat_id)

async def get_user_by_idp_id(conn: asyncpg.Connection, idp_user_id: str) -> asyncpg.Record | None:
    return await conn.fetchrow("SELECT * FROM users WHERE idp_user_id = $1", idp_user_id)

async def add_user(conn: asyncpg.Connection, telegram_chat_id: int | None, idp_user_id: str | None, username: str | None, is_active: bool) -> asyncpg.Record | None:
    return await conn.fetchrow("""
        INSERT INTO users (telegram_chat_id, idp_user_id, username, is_active)
        VALUES ($1, $2, $3, $4)
        RETURNING *
    """, telegram_chat_id, idp_user_id, username, is_active)

async def update_user(conn: asyncpg.Connection, user_id: UUID, username: str | None, is_active: bool) -> asyncpg.Record | None:
    return await conn.fetchrow("""
        UPDATE users
        SET username = $1, is_active = $2
        WHERE id = $3
        RETURNING *
    """, username, is_active, user_id)
