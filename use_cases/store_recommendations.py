# use_cases/store_recommendations.py
"""
Caso de uso para persistir recomendaciones obtenidas desde BackMarket.
"""
import logging
from repositories.recommendation_repository import (
    create_recommendation_request,
    bulk_insert_recommended_products,
)

logger = logging.getLogger(__name__)

def store_recommendations(response_json: dict) -> str:
    """
    Guarda la petición de recomendación y sus productos en la BD.
    Returns: UUID interno de la petición guardada.
    """
    recommendation_request_id = response_json.get("recommendationRequestId")
    widget_id = response_json.get("widgetId")
    products = response_json.get("products", [])

    # Crear registro de petición
    request_uuid = create_recommendation_request(
        recommendation_request_id,
        widget_id,
        response_json,
    )
    logger.info(f"Stored recommendation request {recommendation_request_id} as {request_uuid}")

    # Guardar productos asociados
    count = bulk_insert_recommended_products(request_uuid, products)
    logger.info(f"Inserted {count} products for request {request_uuid}")

    return request_uuid
