# repositories/recommendation_repository.py
"""
Repositorio para persistir peticiones y productos de recomendaciones.
"""
import logging
import json
from db.connection import get_db_connection

logger = logging.getLogger(__name__)


def create_recommendation_request(recommendation_request_id: str, widget_id: str, response_json: dict) -> str:
    """Inserta o actualiza un registro en recommendation_requests y devuelve el UUID."""
    conn = get_db_connection()
    if not conn:
        logger.error("No hay conexión para create_recommendation_request")
        raise Exception("DB connection failed")
    new_id = None
    try:
        with conn.cursor() as cur:
            # Insertar o actualizar si ya existe el mismo recommendation_request_id
            cur.execute(
                """
                INSERT INTO public.recommendation_requests 
                    (recommendation_request_id, widget_id, response)
                VALUES (%s, %s, %s)
                ON CONFLICT (recommendation_request_id) DO UPDATE
                  SET widget_id = EXCLUDED.widget_id,
                      response = EXCLUDED.response
                RETURNING id
                """,
                (recommendation_request_id, widget_id, json.dumps(response_json))
            )
            result = cur.fetchone()
            new_id = result['id'] if result else None
        conn.commit()
        logger.info(f"Recommendation request saved: {recommendation_request_id} -> {new_id}")
        return new_id
    except Exception as e:
        conn.rollback()
        logger.error(f"Error en create_recommendation_request: {e}")
        raise
    finally:
        conn.close()


def bulk_insert_recommended_products(request_id: str, products: list[dict]) -> int:
    """Inserta múltiples productos asociados a una petición de recomendación, evitando duplicados."""
    conn = get_db_connection()
    if not conn:
        logger.error("No hay conexión para bulk_insert_recommended_products")
        raise Exception("DB connection failed")
    try:
        with conn.cursor() as cur:
            # Evitar duplicados por (product_id, listing_id)
            cur.execute(
                "SELECT product_id, listing_id FROM public.recommended_products WHERE request_id = %s",
                (request_id,)
            )
            existing = {(row['product_id'], row['listing_id']) for row in cur.fetchall()}

            count = 0
            for p in products:
                pid = p.get('id')
                lid = p.get('listing', {}).get('id')
                key = (pid, lid)
                if key in existing:
                    logger.debug(f"Producto duplicado omitido: {pid} para request {request_id}")
                    continue
                cur.execute(
                    """
                    INSERT INTO public.recommended_products
                        (request_id, product_id, listing_id, title, name, price_amount, price_currency, raw_data)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        request_id,
                        p.get('id'),
                        p.get('listing', {}).get('id'),
                        p.get('title'),
                        p.get('name'),
                        p.get('listing', {}).get('price', {}).get('amount'),
                        p.get('listing', {}).get('price', {}).get('currency'),
                        json.dumps(p)
                    )
                )
                existing.add(key)
                count += 1
        conn.commit()
        logger.info(f"Inserted {count} recommended products for request {request_id}")
        return count
    except Exception as e:
        conn.rollback()
        logger.error(f"Error en bulk_insert_recommended_products: {e}")
        raise
    finally:
        conn.close()


def delete_all_recommendations() -> None:
    """Elimina todos los registros de recommendation_requests y recommended_products."""
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM public.recommended_products;")
            cur.execute("DELETE FROM public.recommendation_requests;")
        conn.commit()
        logger.info("Todas las recomendaciones y productos han sido eliminados.")
    except Exception as e:
        conn.rollback()
        logger.error(f"Error en delete_all_recommendations: {e}")
        raise
    finally:
        conn.close()
