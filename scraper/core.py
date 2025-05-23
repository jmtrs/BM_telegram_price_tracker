# scraper/core.py
import logging
import json
import asyncio

import requests
from bs4 import BeautifulSoup

import config
from db import queries as db_queries
from .utils import clean_url

logger = logging.getLogger(__name__)

def _parse_product_details(html_content: str, url_for_logging: str) -> dict:
    details = {
        "price": None, "availability": None, "condition": None,
        "name": None, "description": None, "image": None,
        "color": None, "storage": None, "brand_name": None
    }
    try:
        soup = BeautifulSoup(html_content, "html.parser")
        scripts = soup.find_all("script", type="application/ld+json")
        product_data_found = False
        for script in scripts:
            if not script.string:
                continue
            data = json.loads(script.string)
            if isinstance(data, list):
                for item in data:
                    if isinstance(item, dict) and item.get("@type") == "Product":
                        data = item
                        break
                else:
                    continue
            if isinstance(data, dict) and data.get("@type") == "Product":
                product_data_found = True
                details["name"] = data.get("name")
                details["description"] = data.get("description")
                image_data = data.get("image")
                if isinstance(image_data, list) and image_data:
                    details["image"] = image_data[0]
                elif isinstance(image_data, str):
                    details["image"] = image_data
                details["color"] = data.get("color")
                details["storage"] = data.get("storage")
                brand_data = data.get("brand")
                if isinstance(brand_data, dict):
                    details["brand_name"] = brand_data.get("name")
                elif isinstance(brand_data, str):
                    details["brand_name"] = brand_data
                offers_data = data.get("offers")
                if offers_data:
                    offer = None
                    if isinstance(offers_data, list):
                        if offers_data: offer = offers_data[0]
                    elif isinstance(offers_data, dict):
                        offer = offers_data
                    if offer and isinstance(offer, dict) and "price" in offer:
                        try:
                            details["price"] = float(offer["price"])
                        except (ValueError, TypeError):
                            logger.warning(f"Precio inválido '{offer['price']}' en {url_for_logging}")
                        details["availability"] = offer.get("availability", "").split("/")[-1]
                        item_condition_url = offer.get("itemCondition")
                        if isinstance(item_condition_url, str):
                            details["condition"] = item_condition_url.split("/")[-1]
                        logger.info(f"Detalles parseados (JSON-LD) para {url_for_logging}")
                        return details
        if not product_data_found:
             logger.info(f"No se encontró '@type': 'Product' en JSON-LD para {url_for_logging}")
        elif details["price"] is None:
            logger.info(f"'Product' hallado pero sin oferta/precio válido en JSON-LD para {url_for_logging}")
    except json.JSONDecodeError as e:
        logger.warning(f"JSONDecodeError para {url_for_logging}: {e}")
    except Exception as e:
        logger.error(f"Error procesando contenido para {url_for_logging}: {e}", exc_info=True)
    return details

def _fetch_url_content_attempt(full_url: str, use_api: bool) -> requests.Response:
    # Esta función es SÍNCRONA y será ejecutada en un hilo por asyncio.to_thread
    logger.info(f"SYNC_FETCH_ATTEMPT: Iniciando petición síncrona para {full_url}. Timeout={config.API_TIMEOUT_SECONDS}s. Usar API: {use_api}")
    response = None
    if use_api and config.SCRAPERAPI_KEY:
        payload = {'api_key': config.SCRAPERAPI_KEY, 'url': full_url, 'max_cost': config.SCRAPER_MAX_COST}
        response = requests.get("https://api.scraperapi.com/", params=payload, timeout=config.API_TIMEOUT_SECONDS)
    else:
        if not use_api:
            logger.debug(f"SYNC_FETCH_ATTEMPT: Usando petición directa (use_api=False) para {full_url}")
        else:
            logger.warning(f"SYNC_FETCH_ATTEMPT: SCRAPERAPI_KEY no configurado. Usando petición directa para {full_url}")
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'}
        response = requests.get(full_url, headers=headers, timeout=config.API_TIMEOUT_SECONDS)
    logger.info(f"SYNC_FETCH_ATTEMPT: Petición síncrona para {full_url} completada. Status: {response.status_code if response else 'No Response'}")
    if response:
        response.raise_for_status()
    elif not response :
        raise requests.exceptions.RequestException("No se obtuvo respuesta del servidor (variable response es None).")
    return response

async def fetch_product_details_from_url(full_url: str, use_api: bool = True) -> tuple[str | None, str | None]:
    response_text = None
    status = None
    for attempt in range(config.MAX_RETRIES_SCRAPER + 1):
        try:
            log_prefix = f"[API Intento {attempt + 1}]" if use_api and config.SCRAPERAPI_KEY else f"[Directo Intento {attempt + 1}]"
            logger.info(f"{log_prefix} Preparando para obtener {full_url}")
            # Ejecutar la función de red en un hilo separado
            # usando asyncio.to_thread para evitar bloquear el hilo principal
            response_object = await asyncio.to_thread(_fetch_url_content_attempt, full_url, use_api)
            response_text = response_object.text
            status = 'SUCCESS'
            break
        except requests.exceptions.Timeout:
            logger.warning(f"Timeout en intento {attempt + 1} para {full_url} (después de {config.API_TIMEOUT_SECONDS}s)")
            status = 'TIMEOUT_ERROR'
        except requests.exceptions.HTTPError as e:
            logger.warning(f"HTTPError intento {attempt + 1} para {full_url}: {e.response.status_code if e.response else 'Unknown status'}")
            status = 'API_ERROR' if use_api and config.SCRAPERAPI_KEY else 'REQUEST_ERROR'
            if e.response and e.response.status_code in [401, 403, 404] and attempt == config.MAX_RETRIES_SCRAPER:
                logger.error(f"Error cliente ({e.response.status_code}) para {full_url}. Sin más reintentos.")
                break
        except requests.exceptions.RequestException as e:
            logger.warning(f"RequestException intento {attempt + 1} para {full_url}: {e}")
            status = 'REQUEST_ERROR'
        except Exception as e_general:
            logger.error(f"Excepción general en intento {attempt + 1} para {full_url} originada en to_thread: {e_general}", exc_info=True)
            status = 'THREAD_EXECUTION_ERROR'
        if attempt < config.MAX_RETRIES_SCRAPER:
            logger.info(f"Reintentando en {config.RETRY_DELAY_SCRAPER_SECONDS}s...")
            await asyncio.sleep(config.RETRY_DELAY_SCRAPER_SECONDS)
        else:
            logger.error(f"Todos los {config.MAX_RETRIES_SCRAPER + 1} intentos fallaron para {full_url}.")
    if response_text is None and status != 'SUCCESS':
        status = 'NO_TEXT' if status is None else status
    return response_text, status

async def get_product_info(url_to_scrape: str) -> dict:
    cleaned_url_str = clean_url(url_to_scrape)
    logger.info(f"GET_PRODUCT_INFO: URL original: {url_to_scrape}, URL limpiada para caché: {cleaned_url_str}")
    cached_product_info = await asyncio.to_thread(db_queries.get_cached_price, cleaned_url_str)
    if cached_product_info:
        logger.info(f"Usando datos completos de caché para {cleaned_url_str}")
        cached_product_info["clean_url"] = cleaned_url_str
        cached_product_info["full_url"] = url_to_scrape
        cached_product_info["status"] = "CACHE_HIT"
        cached_product_info.setdefault("price", None)
        cached_product_info.setdefault("availability", "N/A (cache)")
        cached_product_info.setdefault("condition", cached_product_info.get("product_condition"))
        return cached_product_info
    logger.info(f"No hay caché válida para {cleaned_url_str}, procediendo a scrapear.")
    use_api_for_this_url = True 
    if not config.SCRAPERAPI_KEY:
        logger.warning(f"SCRAPERAPI_KEY no disponible. El scraping para {url_to_scrape} podría fallar.")
    html_content, fetch_status = await fetch_product_details_from_url(url_to_scrape, use_api=use_api_for_this_url)
    base_fail_response = {
        "price": None, "availability": None, "condition": None,
        "name": None, "description": None, "image": None,
        "color": None, "storage": None, "brand_name": None,
        "clean_url": cleaned_url_str, "full_url": url_to_scrape,
        "status": f"SCRAPE_FAILED_{fetch_status}"
    }
    if fetch_status == 'SUCCESS' and html_content:
        product_details = _parse_product_details(html_content, url_to_scrape)
        if product_details.get("price") is not None:
            await asyncio.to_thread(
                db_queries.save_scraped_price,
                cleaned_url_str,
                product_details
            )
        final_details = base_fail_response.copy()
        final_details.update(product_details)
        final_details["status"] = "SCRAPED_SUCCESS"
        return final_details
    else:
        logger.error(f"Fallo al obtener/parsear detalles para {url_to_scrape}. Estado final: {base_fail_response['status']}")
        return base_fail_response
