# tu_proyecto/db/queries.py
import logging
from datetime import datetime, timedelta
from .connection import get_db_connection
import config

logger = logging.getLogger(__name__)

# --- Scraped Prices Queries ---

def get_cached_price(clean_url: str) -> dict | None:
    conn = get_db_connection()
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

def save_scraped_price(clean_url: str, product_details: dict):
    """Guarda o actualiza todos los detalles scrapeados del producto."""
    conn = get_db_connection()
    
    # Crear un diccionario para los parámetros de la query,
    # combinando clean_url con product_details.
    params_for_query = {
        'clean_url': clean_url, # Añadir clean_url explícitamente
        'price': product_details.get('price'),
        'condition': product_details.get('condition'), # Asegúrate que 'condition' es la clave correcta
                                                     # en product_details, o usa 'product_condition'
                                                     # si así lo devuelve _parse_product_details y lo
                                                     # espera la tabla.
                                                     # La tabla tiene 'product_condition'.
                                                     # _parse_product_details devuelve 'condition'.
                                                     # Vamos a estandarizar.
        'product_condition': product_details.get('condition'), # Usar la clave que _parse devuelve
        'name': product_details.get('name'),
        'description': product_details.get('description'),
        'image_url': product_details.get('image'), # La columna es image_url, el detalle es 'image'
        'color': product_details.get('color'),
        'storage': product_details.get('storage'),
        'brand_name': product_details.get('brand_name')
    }

    with conn.cursor() as cur:
        sql = """
            INSERT INTO scraped_prices (
                clean_url, price, product_condition, scraped_at,
                product_name, description, image_url, color, storage, brand_name
            )
            VALUES (
                %(clean_url)s, %(price)s, %(product_condition)s, now(),
                %(name)s, %(description)s, %(image_url)s, %(color)s, %(storage)s, %(brand_name)s
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
                brand_name = EXCLUDED.brand_name
        """
        cur.execute(sql, params_for_query)
    logger.info(f"Datos completos del producto guardados/actualizados para {clean_url}")


def cleanup_old_scraped_prices():
    conn = get_db_connection()
    with conn.cursor() as cur:
        # El intervalo para limpieza podría ir a config.py
        cur.execute("DELETE FROM scraped_prices WHERE scraped_at < now() - interval '2 days'")
        deleted_count = cur.rowcount
    if deleted_count > 0:
        logger.info(f"Limpieza de caché: {deleted_count} registros eliminados.")
    # else: # Loguear solo si algo se borró para reducir ruido
    #     logger.info("Limpieza de caché: No hay registros antiguos que eliminar.")
    return deleted_count

# --- Alerts Queries ---

def get_alert_by_chat_and_clean_url(chat_id: int, clean_url: str) -> dict | None: # Renombrado
    conn = get_db_connection()
    with conn.cursor() as cur:
        cur.execute("SELECT * FROM alerts WHERE chat_id=%s AND clean_url=%s", (chat_id, clean_url))
        return cur.fetchone()

# NUEVA FUNCIÓN para obtener una alerta por su ID
def get_alert_by_id(alert_id: str) -> dict | None:
    """Obtiene una alerta específica por su ID (UUID como string)."""
    conn = get_db_connection()
    with conn.cursor() as cur:
        cur.execute("SELECT * FROM alerts WHERE id::text = %s", (alert_id,))
        return cur.fetchone()

def update_alert_target_price(alert_id: str, target_price: float, full_url: str): # Renombrado
    conn = get_db_connection()
    with conn.cursor() as cur:
        cur.execute(
            "UPDATE alerts SET target_price=%s, inserted_at=now(), full_url=%s WHERE id::text=%s",
            (target_price, full_url, alert_id)
        )
    logger.info(f"Alerta {alert_id} actualizada. Nuevo objetivo: {target_price}€")

def create_alert(chat_id: int, full_url: str, clean_url: str, target_price: float, product_name: str | None = None):
    conn = get_db_connection()
    with conn.cursor() as cur:
        # Podríamos considerar añadir product_name a la tabla alerts si queremos mostrarlo en /alerts sin joins
        cur.execute("""
            INSERT INTO alerts (chat_id, full_url, clean_url, target_price) 
            VALUES (%s, %s, %s, %s) RETURNING id
        """, (chat_id, full_url, clean_url, target_price))
        new_alert_id = cur.fetchone()['id']
    logger.info(f"Nueva alerta ID {new_alert_id} creada para chat_id {chat_id}, URL: {clean_url}, Objetivo: {target_price}€")
    return new_alert_id


def get_user_alerts(chat_id: int) -> list[dict]:
    conn = get_db_connection()
    with conn.cursor() as cur:
        cur.execute("SELECT * FROM alerts WHERE chat_id=%s ORDER BY inserted_at DESC", (chat_id,))
        return cur.fetchall()

def delete_alert_by_id(alert_id: str, chat_id: int) -> bool:
    conn = get_db_connection()
    with conn.cursor() as cur:
        cur.execute("DELETE FROM alerts WHERE id::text=%s AND chat_id=%s RETURNING id", (alert_id, chat_id))
        deleted_row = cur.fetchone()
    if deleted_row:
        logger.info(f"Alerta {alert_id} eliminada para chat_id {chat_id}.")
        return True
    logger.warning(f"Intento de eliminar alerta {alert_id} (chat_id {chat_id}) fallido.")
    return False

def get_all_alerts() -> list[dict]:
    conn = get_db_connection()
    with conn.cursor() as cur:
        cur.execute("SELECT * FROM alerts")
        return cur.fetchall()

def update_alert_last_price(alert_id: str, current_price: float | None):
    conn = get_db_connection()
    with conn.cursor() as cur:
        # Si current_price es None, guardamos NULL en la BD
        cur.execute(
            "UPDATE alerts SET last_price=%s, inserted_at=now() WHERE id::text=%s",
            (current_price, alert_id)
        )

def update_alert_last_notified(alert_id: str):
    conn = get_db_connection()
    with conn.cursor() as cur:
        cur.execute("UPDATE alerts SET last_notified=now() WHERE id::text=%s", (alert_id,))
