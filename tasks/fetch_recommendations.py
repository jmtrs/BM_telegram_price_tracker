# tasks/fetch_recommendations.py
"""
Task para obtener recomendaciones de BackMarket y almacenarlas en la BD.
"""
import asyncio
import logging
import random

from scraper.recommendations import get_recommendations_sync
from use_cases.store_recommendations import store_recommendations

import config

logger = logging.getLogger(__name__)


def run_fetch_recommendations() -> None:
    """Ejecuta el scraper de recomendaciones y persiste los resultados."""
    try:
        # Eliminar datos antiguos antes de cada ejecución
        from repositories.recommendation_repository import delete_all_recommendations
        delete_all_recommendations()
        # Iterar por cada categoría y URL configurada
        from config import RECOMMENDATION_URLS
        for category, url in RECOMMENDATION_URLS.items():
            try:
                logger.info(f"Iniciando scraping de recomendaciones para categoria '{category}'")
                responses = get_recommendations_sync(url)
                logger.info(f"Obtenidas {len(responses)} respuestas para categoria '{category}'")
                for resp in responses:
                    # Sobrescribir widgetId con la categoria legible
                    resp['widgetId'] = category
                    req_id = resp.get('recommendationRequestId')
                    try:
                        store_recommendations(resp)
                        logger.info(f"Recomendaciones procesadas [{category}] para request {req_id}.")
                    except Exception as e:
                        logger.error(f"Error al guardar recomendaciones [{category}] {req_id}: {e}")
            except Exception as e:
                logger.error(f"Error en scraping categoría '{category}': {e}")
                continue
    except Exception as e:
        logger.error(f"Error en fetch_recommendations task: {e}")


async def fetch_recommendations_periodically(shutdown_event: asyncio.Event):
    """Ejecuta periódicamente la tarea de fetch_recommendations hasta que se señale shutdown_event."""
    # Intervalo base y jitter definidos en config
    interval = config.CHECK_INTERVAL_SECONDS
    jitter = config.JITTER_MAX_SECONDS
    while not shutdown_event.is_set():
        try:
            await asyncio.to_thread(run_fetch_recommendations)
        except Exception as e:
            logger.error(f"Error periódico en fetch_recommendations: {e}")
        # Esperar intervalo con jitter
        sleep_time = interval + random.uniform(0, jitter)
        await asyncio.wait([shutdown_event.wait()], timeout=sleep_time)


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    run_fetch_recommendations()
