# scraper/core.py
import logging
import json
import aiohttp
from bs4 import BeautifulSoup
import asyncio

import config

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
                        
                        raw_availability = offer.get("availability")
                        if isinstance(raw_availability, str) and "/" in raw_availability:
                            details["availability"] = raw_availability.split("/")[-1]
                        elif isinstance(raw_availability, str): 
                            details["availability"] = raw_availability
                        else:
                            details["availability"] = None

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


async def _fetch_url_content_attempt_async(session: aiohttp.ClientSession, full_url: str, use_api: bool) -> str:
    logger.info(
        f"ASYNC_FETCH_ATTEMPT: Iniciando petición asíncrona para {full_url}. Timeout={config.API_TIMEOUT_SECONDS}s. Usar API: {use_api}")

    target_url = full_url
    params = None
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'}

    if use_api and config.SCRAPERAPI_KEY:
        target_url = "https://api.scraperapi.com/"
        params = {'api_key': config.SCRAPERAPI_KEY, 'url': full_url, 'max_cost': config.SCRAPER_MAX_COST}
        headers = None  # ScraperAPI manages headers
    elif use_api and not config.SCRAPERAPI_KEY:
        logger.warning(f"ASYNC_FETCH_ATTEMPT: SCRAPERAPI_KEY no configurado. Usando petición directa para {full_url}")
        # Fall through to use default target_url and headers for direct request
    else:  # Direct request (use_api=False or fallback from previous elif)
        logger.debug(f"ASYNC_FETCH_ATTEMPT: Usando petición directa para {full_url}")
        # Default target_url and headers are already set

    timeout = aiohttp.ClientTimeout(total=config.API_TIMEOUT_SECONDS)
    async with session.get(target_url, params=params, headers=headers, timeout=timeout) as response:
        logger.info(f"ASYNC_FETCH_ATTEMPT: Petición asíncrona para {full_url} completada. Status: {response.status}")
        response.raise_for_status()
        return await response.text()


async def get_product_info(full_url: str, use_api: bool = False) -> dict:
    """Obtiene la información del producto: hace peticiones async, reintenta, parsea y devuelve un dict con status."""
    
    effective_use_api = use_api
    if not use_api and config.SCRAPERAPI_KEY:
        logger.info(f"get_product_info: use_api era False para {full_url}, pero SCRAPERAPI_KEY está disponible. Forzando use_api=True.")
        effective_use_api = True
    elif use_api and not config.SCRAPERAPI_KEY:
        logger.warning(f"get_product_info: use_api era True para {full_url}, pero SCRAPERAPI_KEY no está disponible. Forzando use_api=False.")
        effective_use_api = False
    elif not config.SCRAPERAPI_KEY and not use_api:
        logger.info(f"get_product_info: ni use_api=True ni SCRAPERAPI_KEY disponible para {full_url}. Procediendo con petición directa.")
        effective_use_api = False


    async with aiohttp.ClientSession() as session:
        for attempt in range(config.MAX_RETRIES_SCRAPER):
            try:
                html = await _fetch_url_content_attempt_async(session, full_url, effective_use_api)
                details = _parse_product_details(html, full_url)
                if details.get('price') is not None:
                    return {**details, 'status': 'SCRAPED_SUCCESS'}
                return {**details, 'status': 'SCRAPED_NO_PRICE'}
            except Exception as e:
                logger.warning(f"SCRAPE attempt {attempt + 1}/{config.MAX_RETRIES_SCRAPER} failed for {full_url}: {e}")
                if attempt < config.MAX_RETRIES_SCRAPER - 1:
                    await asyncio.sleep(config.RETRY_DELAY_SCRAPER_SECONDS)
                    continue
                # último intento fallido
                empty = {k: None for k in
                         ['price', 'availability', 'condition', 'name', 'description', 'image', 'color', 'storage',
                          'brand_name']}
                return {**empty, 'status': f'SCRAPE_FAILED_{type(e).__name__}'}
