# db/queries.py
import logging
from datetime import datetime, timedelta
from .connection import get_db_connection
import config
import psycopg2
import time

logger = logging.getLogger(__name__)

# --- Scraped Prices Queries ---

def get_cached_price(clean_url: str) -> dict | None:
    conn = get_db_connection()
    if not conn:
        logger.error("Failed to get DB connection in get_cached_price")
        return None
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT price, product_condition, scraped_at,
                       product_name, description, image_url,
                       color, storage, brand_name
                FROM scraped_prices
                WHERE clean_url = %s
                ORDER BY scraped_at DESC LIMIT 1
            """, (clean_url,))
            row = cur.fetchone()
        if row and datetime.utcnow() - row['scraped_at'] < timedelta(minutes=config.SCRAPE_TTL_MINUTES):
            logger.info(f"Usando datos completos de caché para {clean_url}")
            return dict(row)
        return None
    except Exception as e:
        logger.error(f"Error in get_cached_price for {clean_url}: {e}")
        return None
    finally:
        if conn:
            conn.close()

def save_scraped_price(clean_url: str, product_details: dict):
    """Guarda o actualiza todos los detalles scrapeados del producto."""
    conn = get_db_connection()
    if not conn:
        logger.error("Failed to get DB connection in save_scraped_price")
        return
    
    params_for_query = {
        'clean_url': clean_url,
        'price': product_details.get('price'),
        'product_condition': product_details.get('condition'),
        'name': product_details.get('name'),
        'description': product_details.get('description'),
        'image_url': product_details.get('image'),
        'color': product_details.get('color'),
        'storage': product_details.get('storage'),
        'brand_name': product_details.get('brand_name'),
        'availability': product_details.get('availability')
    }

    try:
        with conn.cursor() as cur:
            sql = """
            INSERT INTO scraped_prices (
                clean_url, price, product_condition, scraped_at,
                product_name, description, image_url, color, storage, brand_name,
                availability  -- Añadir columna availability
            )
            VALUES (
                %(clean_url)s, %(price)s, %(product_condition)s, now(),
                %(name)s, %(description)s, %(image_url)s, %(color)s, %(storage)s, %(brand_name)s,
                %(availability)s  -- Añadir valor para availability
            )
            ON CONFLICT (clean_url) DO UPDATE SET
                price = EXCLUDED.price,
                product_condition = EXCLUDED.product_condition,
                scraped_at = EXCLUDED.scraped_at,
                product_name = EXCLUDED.product_name,
                description = EXCLUDED.description,
                image_url = EXCLUDED.image_url,
                color = EXCLUDED.color,
                storage = EXCLUDED.storage,
                brand_name = EXCLUDED.brand_name,
                availability = EXCLUDED.availability  -- Actualizar availability en conflicto
            """
            cur.execute(sql, params_for_query)
        conn.commit()
        logger.info(f"Datos completos del producto guardados/actualizados para {clean_url}")
    except Exception as e:
        logger.error(f"Error in save_scraped_price for {clean_url}: {e}")
        if conn:
            conn.rollback()
    finally:
        if conn:
            conn.close()

def cleanup_old_scraped_prices():
    conn = get_db_connection()
    with conn.cursor() as cur:
        cur.execute("DELETE FROM scraped_prices WHERE scraped_at < now() - interval '2 days'")
        deleted_count = cur.rowcount
    if deleted_count > 0:
        logger.info(f"Limpieza de caché: {deleted_count} registros eliminados.")
    return deleted_count

# --- Alerts Queries ---

def get_alert_by_chat_and_clean_url(chat_id: int, clean_url: str) -> dict | None:
    conn = get_db_connection()
    if not conn:
        logger.error("Failed to get DB connection in get_alert_by_chat_and_clean_url")
        return None
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM alerts WHERE chat_id=%s AND clean_url=%s", (chat_id, clean_url))
            return cur.fetchone()
    except Exception as e:
        logger.error(f"Error in get_alert_by_chat_and_clean_url for chat {chat_id}, url {clean_url}: {e}")
        return None
    finally:
        if conn:
            conn.close()

def get_alert_by_id(alert_id: str) -> dict | None:
    """Obtiene una alerta específica por su ID (UUID como string)."""
    conn = get_db_connection()
    if not conn:
        logger.error(f"Failed to get DB connection in get_alert_by_id for alert {alert_id}")
        return None
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM alerts WHERE id::text = %s", (alert_id,))
            return cur.fetchone()
    except Exception as e:
        logger.error(f"Error in get_alert_by_id for alert {alert_id}: {e}")
        return None
    finally:
        if conn:
            conn.close()

def update_alert_target_price(alert_id: str, target_price: float, full_url: str): # Renombrado
    conn = get_db_connection()
    if not conn:
        logger.error("Failed to get DB connection in update_alert_target_price")
        raise Exception("Database connection failed")
    try:
        rows_affected = 0
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE alerts SET target_price=%s, inserted_at=now(), full_url=%s WHERE id::text=%s",
                (target_price, full_url, alert_id)
            )
            rows_affected = cur.rowcount
        conn.commit()
        if rows_affected > 0:
            logger.info(f"Alerta {alert_id} actualizada. Nuevo objetivo: {target_price}€")
        else:
            logger.warning(f"Alerta {alert_id} no encontrada o no actualizada en update_alert_target_price.")
    except Exception as e:
        logger.error(f"Error in update_alert_target_price for alert {alert_id}: {e}")
        if conn:
            conn.rollback()
        raise # Re-raise the exception
    finally:
        if conn:
            conn.close()

def create_alert(chat_id: int, full_url: str, clean_url: str, target_price: float, product_name: str | None = None):
    conn = get_db_connection()
    if not conn:
        logger.error("Failed to get DB connection in create_alert")
        raise Exception("Database connection failed") 

    new_alert_id = None
    max_retries = 3  # Número máximo de reintentos
    retry_delay = 2  # Retraso entre reintentos en segundos

    for attempt in range(max_retries):
        try:
            with conn.cursor() as cur:
                # Configurar nivel de aislamiento
                cur.execute("SET TRANSACTION ISOLATION LEVEL READ COMMITTED")

                cur.execute(
                    """
                    INSERT INTO alerts (chat_id, full_url, clean_url, target_price) 
                    VALUES (%s, %s, %s, %s) RETURNING id
                    """,
                    (chat_id, full_url, clean_url, target_price)
                )
                result = cur.fetchone()
                if result:
                    new_alert_id = result['id']
                else:
                    raise Exception("Failed to retrieve ID after insert in create_alert")
            conn.commit()
            if new_alert_id:
                logger.info(f"Nueva alerta ID {new_alert_id} creada para chat_id {chat_id}, URL: {clean_url}, Objetivo: {target_price}€")
            return new_alert_id
        except psycopg2.OperationalError as e:
            logger.warning(f"Intento {attempt + 1} de {max_retries} fallido en create_alert debido a bloqueo: {e}")
            if attempt < max_retries - 1:
                time.sleep(retry_delay)
                continue
            else:
                logger.error(f"Error en create_alert tras {max_retries} intentos: {e}")
                if conn:
                    conn.rollback()
                raise
        except Exception as e:
            logger.error(f"Error en create_alert para chat {chat_id}, url {clean_url}: {e}")
            if conn:
                conn.rollback()
            raise
        finally:
            if conn:
                conn.close()

def get_user_alerts(chat_id: int, sort_by: str = "date_desc") -> list[dict]:
    conn = get_db_connection()
    if not conn:
        logger.error(f"Failed to get DB connection in get_user_alerts for chat {chat_id}")
        return [] # Return empty list on connection failure
    try:
        with conn.cursor() as cur:
            sql_base = """
                SELECT 
                    a.*, 
                    sp.product_name, 
                    sp.product_condition
                FROM alerts a
                LEFT JOIN (
                    SELECT 
                        clean_url, 
                        product_name, 
                        product_condition, 
                        ROW_NUMBER() OVER(PARTITION BY clean_url ORDER BY scraped_at DESC) as rn
                    FROM scraped_prices
                ) sp ON a.clean_url = sp.clean_url AND sp.rn = 1
                WHERE a.chat_id = %s
            """

            if sort_by == "price_asc":
                sql_query = sql_base + " ORDER BY a.last_price ASC NULLS LAST, a.inserted_at DESC"
            else:
                sql_query = sql_base + " ORDER BY a.inserted_at DESC"
                
            cur.execute(sql_query, (chat_id,))
            return cur.fetchall()
    except Exception as e:
        logger.error(f"Error in get_user_alerts for chat {chat_id}: {e}")
        return []
    finally:
        if conn:
            conn.close()

def delete_alert_by_id(alert_id: str, chat_id: int) -> bool:
    conn = get_db_connection()
    if not conn:
        logger.error("Failed to get DB connection in delete_alert_by_id")
        return False
    deleted = False
    try:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM alerts WHERE id::text=%s AND chat_id=%s RETURNING id", (alert_id, chat_id))
            deleted_row = cur.fetchone()
        conn.commit()
        if deleted_row:
            logger.info(f"Alerta {alert_id} eliminada para chat_id {chat_id}.")
            deleted = True
        else:
            logger.warning(f"Intento de eliminar alerta {alert_id} (chat_id {chat_id}) fallido (no encontrada o no pertenece)." )
    except Exception as e:
        logger.error(f"Error in delete_alert_by_id for alert {alert_id}, chat {chat_id}: {e}")
        if conn:
            conn.rollback()
    finally:
        if conn:
            conn.close()
    return deleted

def get_all_alerts() -> list[dict]:
    conn = get_db_connection()
    if not conn:
        logger.error("Failed to get DB connection in get_all_alerts")
        return []
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM alerts")
            return cur.fetchall()
    except Exception as e:
        logger.error(f"Error in get_all_alerts: {e}")
        return []
    finally:
        if conn:
            conn.close()

def update_alert_target_price_by_id(alert_id: str, new_target_price: float, chat_id: int) -> bool:
    """
    Actualiza el precio objetivo de una alerta por su ID y chat_id.
    """
    conn = get_db_connection()
    if not conn:
        return False
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE alerts
                SET target_price = %s, inserted_at = CURRENT_TIMESTAMP
                WHERE id = %s AND chat_id = %s
                RETURNING id;
                """,
                (new_target_price, alert_id, chat_id)
            )
            updated_alert = cur.fetchone()
            conn.commit()
            if updated_alert:
                return True
            else:
                logger.warning(f"Alert {alert_id} not found or does not belong to chat {chat_id} for price update.")
                return False
    except Exception as e:
        logger.error(f"Error updating alert target price by ID {alert_id} for chat {chat_id}: {e}")
        if conn:
            conn.rollback()
        return False
    finally:
        if conn:
            conn.close()

def update_alert_last_price(alert_id: str, current_price: float | None):
    if current_price is None:
        logger.warning(f"Intento de actualizar precio con None para alerta {alert_id}. Operación ignorada.")
        return
    conn = get_db_connection()
    if not conn:
        logger.error("Failed to get DB connection in update_alert_last_price")
        return
    try:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE alerts SET last_price=%s WHERE id::text=%s",
                (current_price, alert_id)
            )
        conn.commit()
    except Exception as e:
        logger.error(f"Error in update_alert_last_price for alert {alert_id}: {e}")
        if conn:
            conn.rollback()
    finally:
        if conn:
            conn.close()

def update_alert_last_notified(alert_id: str):
    conn = get_db_connection()
    if not conn:
        logger.error("Failed to get DB connection in update_alert_last_notified")
        return
    try:
        with conn.cursor() as cur:
            cur.execute("UPDATE alerts SET last_notified=now() WHERE id::text=%s", (alert_id,))
        conn.commit()
    except Exception as e:
        logger.error(f"Error in update_alert_last_notified for alert {alert_id}: {e}")
        if conn:
            conn.rollback()
    finally:
        if conn:
            conn.close()

# --- Circuit Breaker / Host Failures Queries ---

# Implementación en memoria
host_failures_state: dict[str, datetime] = {}

def set_host_circuit_break(host: str, until_ts: datetime):
    """Guarda o actualiza el estado del circuito rompedor para un host en memoria."""
    host_failures_state[host] = until_ts

def get_active_host_circuits() -> dict:
    """Obtiene los hosts con circuito rompedor activo (hasta until_ts > ahora)."""
    now = datetime.utcnow()
    return {host: until_ts for host, until_ts in host_failures_state.items() if until_ts > now}

def cleanup_expired_host_circuits() -> int:
    """Elimina hosts expirados del circuito rompedor y retorna cantidad eliminada."""
    now = datetime.utcnow()
    expired = [host for host, until_ts in host_failures_state.items() if until_ts <= now]
    for host in expired:
        del host_failures_state[host]
    return len(expired)

def get_recent_recommendation_requests(limit: int = 10) -> list[dict]:
    """Devuelve las últimas `limit` peticiones de recomendaciones."""
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, recommendation_request_id, widget_id, requested_at
                FROM public.recommendation_requests
                ORDER BY requested_at DESC
                LIMIT %s
                """,
                (limit,)
            )
            return cur.fetchall()
    except Exception as e:
        logger.error(f"Error en get_recent_recommendation_requests: {e}")
        return []
    finally:
        conn.close()


def get_recommended_products_by_request(request_id: str) -> list[dict]:
    """Devuelve todos los productos asociados a una petición de recomendación."""
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT product_id, listing_id, title, name, price_amount, price_currency, raw_data
                FROM public.recommended_products
                WHERE request_id = %s
                ORDER BY id
                """,
                (request_id,)
            )
            return cur.fetchall()
    except Exception as e:
        logger.error(f"Error en get_recommended_products_by_request: {e}")
        return []
    finally:
        conn.close()
