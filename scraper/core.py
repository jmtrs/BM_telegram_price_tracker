# scraper/core.py
import logging
import json
import asyncio
import re
from bs4 import BeautifulSoup

from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError

import config
from db import queries as db_queries
from .utils import clean_url

logger = logging.getLogger(__name__)


def _normalize_condition(condition_text: str | None) -> str | None:
    if not condition_text:
        return None
    
    text = condition_text.lower().strip()

    if text in ["prémium", "premium", "impecable"]:
        return "Prémium"
    if text == "excelente":
        return "Excelente"
    if text in ["muy bueno", "muy buen estado"]:
        return "Muy bueno"
    if text == "correcto":
        return "Correcto"
    
    if "schema.org/" in text:
        condition_part = text.split('/')[-1]
        if condition_part == "newcondition": return "Nuevo"
        if condition_part == "refurbishedcondition": return "Reacondicionado"
        if condition_part == "usedcondition": return "Reacondicionado" 
        if condition_part == "damagedcondition": return "Dañado"

    if "newcondition" in text: return "Nuevo"
    if "refurbishedcondition" in text: return "Reacondicionado"
    if "damagedcondition" in text: return "Dañado"

    if condition_text in ["Prémium", "Excelente", "Muy bueno", "Correcto", "Nuevo", "Reacondicionado", "Dañado"]:
       return condition_text

    return None


def _parse_product_details(html_content: str, url: str) -> dict:
    product_data = {
        'name': None, 'price': None, 'condition': None, 'availability': None,
        'sku': None, 'description': None, 'image': None, 'color': None, 
        'storage': None, 'brand_name': None, 'url': url, 'source': '' 
    }
    source_parts = ['initial'] 
    soup = BeautifulSoup(html_content, 'html.parser')

    name_from_html = None
    name_tag_specific = soup.find('h1', attrs={'data-test-id': 'product-title'})
    if name_tag_specific:
        name_from_html = name_tag_specific.get_text(strip=True)
    else:
        name_tag_generic = soup.find('h1')
        if name_tag_generic:
            name_from_html = name_tag_generic.get_text(strip=True)
    
    product_json_ld = None
    json_ld_scripts = soup.find_all('script', type='application/ld+json')
    for script_tag in json_ld_scripts:
        if script_tag.string:
            try:
                data = json.loads(script_tag.string)
                items_to_check = data if isinstance(data, list) else [data]
                for item in items_to_check:
                    if isinstance(item, dict) and 'Product' in item.get('@type', ''):
                        product_json_ld = item
                        break
                if product_json_ld: break
            except json.JSONDecodeError:
                logger.warning(f"Fallo al decodificar JSON-LD para {url}. Contenido: {script_tag.string[:200]}...", exc_info=False)
            except Exception as e:
                 logger.error(f"Error inesperado procesando JSON-LD para {url}: {e}. Contenido: {script_tag.string[:200]}...", exc_info=False)
    
    if product_json_ld:
        source_parts.append("jsonld_parsed")
        
        product_data['name'] = product_json_ld.get('name')
        product_data['description'] = product_json_ld.get('description')
        image_data = product_json_ld.get('image')
        if isinstance(image_data, list):
            product_data['image'] = image_data[0] if image_data else None
        elif isinstance(image_data, dict):
            product_data['image'] = image_data.get('url')
        else:
            product_data['image'] = image_data 
        
        product_data['sku'] = product_json_ld.get('sku')
        brand_data = product_json_ld.get('brand', {})
        if isinstance(brand_data, dict):
            product_data['brand_name'] = brand_data.get('name')

        # Extracción de Color desde JSON-LD (directamente como string)
        color_value_from_json_ld = product_json_ld.get('color')
        if isinstance(color_value_from_json_ld, str):
            product_data['color'] = color_value_from_json_ld.strip()
            source_parts.append("color_jsonld_direct")
        elif color_value_from_json_ld:
            source_parts.append("color_jsonld_type_mismatch")
        else:
            source_parts.append("color_jsonld_not_found")
        
        # Extracción de Storage desde JSON-LD (directamente como string)
        storage_value_from_json_ld = product_json_ld.get('storage')
        if isinstance(storage_value_from_json_ld, str):
            product_data['storage'] = storage_value_from_json_ld.strip()
            source_parts.append("storage_jsonld_direct")
        elif storage_value_from_json_ld:
            source_parts.append("storage_jsonld_type_mismatch")
        else:
            source_parts.append("storage_jsonld_not_found")

        offers_data = product_json_ld.get('offers', {})
        if isinstance(offers_data, list): 
            offers_data = offers_data[0] if offers_data else {}
        if not isinstance(offers_data, dict):
            offers_data = {}

        availability_raw_from_json_ld = offers_data.get('availability')
        normalized_availability = None
        if availability_raw_from_json_ld and isinstance(availability_raw_from_json_ld, str):
            availability_lower = availability_raw_from_json_ld.lower()
            if "instock" in availability_lower:
                normalized_availability = "InStock"
                source_parts.append("availability_jsonld_instock")
            elif "outofstock" in availability_lower:
                normalized_availability = "OutOfStock"
                source_parts.append("availability_jsonld_outofstock")
            elif "preorder" in availability_lower:
                normalized_availability = "PreOrder"
                source_parts.append("availability_jsonld_preorder")
            elif "soldout" in availability_lower:
                normalized_availability = "SoldOut"
                source_parts.append("availability_jsonld_soldout")
            elif "discontinued" in availability_lower:
                normalized_availability = "Discontinued"
                source_parts.append("availability_jsonld_discontinued")
            else: 
                if "schema.org/" in availability_raw_from_json_ld:
                    normalized_availability = availability_raw_from_json_ld.split('/')[-1]
                else:
                    normalized_availability = availability_raw_from_json_ld
                source_parts.append("availability_jsonld_other")
            product_data['availability'] = normalized_availability
        elif availability_raw_from_json_ld:
            product_data['availability'] = str(availability_raw_from_json_ld) 
            source_parts.append("availability_jsonld_raw_type_unexpected")
    else:
        product_json_ld = {}
        offers_data = {}

    if name_from_html:
        product_data['name'] = name_from_html
        source_parts.append("name_html")
    elif product_data['name']:
        source_parts.append("name_jsonld")

    price_from_html = None
    price_selectors = [
        {"attrs": {"data-qa": "productpage-product-price"}},
        {"attrs": {"data-test": "productpage-product-price"}},
        {"attrs": {"data-test": "price"}}
    ]
    for selector in price_selectors:
        price_tag = soup.find(**selector)
        if price_tag:
            price_text = price_tag.get_text(strip=True)
            if price_text:
                price_text_cleaned = price_text.replace('€', '').replace('\\xa0', '').replace('.', '').replace(',', '.').strip()
                try:
                    price_from_html = float(price_text_cleaned)
                    break 
                except ValueError:
                    logger.warning(f"No se pudo convertir precio HTML '{price_text_cleaned}' a float para {url}")
    
    price_from_json_ld = None
    price_from_json_ld_str = offers_data.get('price')
    if price_from_json_ld_str:
        try:
            price_from_json_ld = float(price_from_json_ld_str)
        except (ValueError, TypeError):
            logger.warning(f"No se pudo convertir precio JSON-LD '{price_from_json_ld_str}' a float para {url}")

    if price_from_html is not None:
        product_data['price'] = price_from_html
        source_parts.append("price_html")
    elif price_from_json_ld is not None:
        product_data['price'] = price_from_json_ld
        source_parts.append("price_jsonld")
    else:
        source_parts.append("price_unavailable")

    grade_condition_from_html = None
    raw_grade_text_final = None
    
    # Selectores CSS para elementos que indican el estado/grado seleccionado
    selected_elements_candidates = soup.select(
        '[aria-pressed="true"], [aria-checked="true"], [aria-selected="true"], '
        '.selected, .active, .is-selected, .is-active, .current, .activated, .selected_item, '
        '[class*="--selected"], [class*="-selected"], [class*="_selected"], '
        '[class*="--active"], [class*="-active"], [class*="_active"], '
        '[class*="--current"], [class*="-current"], [class*="_current"]'
    )
    
    common_non_condition_words = [
        "iphone", "ver detalles", "elegir", "estado", "color", "capacidad", 
        "wifi", "ipad", "air", "gb", "descuento", "ahorra", "disponible"
    ]

    for elem in selected_elements_candidates:
        temp_raw_text = None
        
        # Prioridad 1: Texto dentro de <span>
        spans = elem.find_all('span', recursive=True)
        for span_elem in spans:
            span_text = span_elem.get_text(strip=True)
            # Validar si el texto del span es una condición y cumple criterios básicos
            if _normalize_condition(span_text) and \
               (2 < len(span_text) < 30) and \
               not span_text.isdigit() and \
               "€" not in span_text and \
               not any(word in span_text.lower() for word in ["dct", "ahorra"]):
                temp_raw_text = span_text
                break 
        
        # Prioridad 2: Texto directo del elemento si no se encontró en <span>
        if not temp_raw_text:
            direct_text = elem.get_text(strip=True)
            if _normalize_condition(direct_text) and len(direct_text) < 30: 
                temp_raw_text = direct_text
            else:
                # Si el texto directo no es una condición, buscar partes que sí lo sean
                parts = re.findall(r'\b[A-Za-záéíóúÁÉÍÓÚüÜñÑ]{3,}(?:\s+[A-Za-záéíóúÁÉÍÓÚüÜñÑ]{2,})?\b', direct_text)
                for part in parts:
                    normalized_part_check = _normalize_condition(part)
                    if normalized_part_check:
                        # Filtrar palabras comunes que podrían normalizarse accidentalmente
                        if not part.isdigit() and "€" not in part and \
                           not any(word == part.lower() for word in common_non_condition_words):
                            temp_raw_text = part
                            break 
                            
        if temp_raw_text:
            normalized_condition_check = _normalize_condition(temp_raw_text)
            if normalized_condition_check:
                raw_grade_text_final = temp_raw_text
                break 

    if raw_grade_text_final:
        normalized_grade = _normalize_condition(raw_grade_text_final)
        if normalized_grade:
            grade_condition_from_html = normalized_grade

    # Condición de JSON-LD (fallback)
    condition_from_json_ld_schema = offers_data.get('itemCondition')
    normalized_json_ld_condition = None
    if condition_from_json_ld_schema:
        # Extraer el término de la condición (ej. "NewCondition" de "http://schema.org/NewCondition")
        raw_condition_str = str(condition_from_json_ld_schema).split('/')[-1] if "schema.org/" in str(condition_from_json_ld_schema) else str(condition_from_json_ld_schema)
        normalized_json_ld_condition = _normalize_condition(raw_condition_str)
        if normalized_json_ld_condition:
             logger.info(f"Condición JSON-LD normalizada: '{normalized_json_ld_condition}' (raw: '{raw_condition_str}') para {url}")
        else:
             logger.warning(f"Condición JSON-LD '{raw_condition_str}' no pudo ser normalizada para {url}.")

    # Asignación final de la condición con prioridad
    if grade_condition_from_html:
        product_data['condition'] = grade_condition_from_html
        source_parts.append("condition_html_grade")
    elif normalized_json_ld_condition:
        product_data['condition'] = normalized_json_ld_condition
        source_parts.append("condition_jsonld")
    else:
        source_parts.append("condition_unavailable")
        
    product_data['source'] = ",".join(list(dict.fromkeys(source_parts)))

    return product_data


async def get_html_from_url(url: str, timeout_seconds: int = config.API_TIMEOUT_SECONDS) -> str | None:
    logger.info(f"Iniciando scraping con Playwright para URL: {url}")
    browser = None
    context = None
    page = None
    effective_timeout_ms = timeout_seconds * 1000
    
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
            )
            page = await context.new_page()
            
            response = await page.goto(url, timeout=effective_timeout_ms, wait_until='domcontentloaded')

            if response and response.ok:
                html_content = await page.content()
                return html_content
            elif response:
                logger.error(f"Error al obtener HTML de {url}. Status: {response.status} {response.status_text}")
            else: # No response object
                logger.error(f"No se recibió respuesta HTTP válida de {url}.")
            return None # Explicitly return None on failure within try block
                
    except PlaywrightTimeoutError:
        logger.error(f"Timeout ({timeout_seconds}s) al obtener HTML para {url}")
        return None
    except Exception as e:
        logger.error(f"Error general al obtener HTML de {url} con Playwright: {e}", exc_info=True)
        return None
    finally:
        # Cerrar recursos de Playwright en orden inverso a su creación
        if page and not page.is_closed():
            try:
                await page.close()
            except Exception as e:
                logger.warning(f"Excepción al cerrar la página de Playwright para {url}: {e}")
        if context: # No hay método is_closed() estándar para context, intentar cerrar siempre
            try:
                await context.close()
            except Exception as e:
                if "Target page, context or browser has been closed" in str(e) or "context.close: Target closed" in str(e):
                    logger.warning(f"Contexto de Playwright para {url} ya estaba cerrado: {e}")
                else:
                    logger.error(f"Error al cerrar el contexto de Playwright para {url}: {e}", exc_info=False)
        if browser and browser.is_connected():
            try:
                await browser.close()
            except Exception as e:
                logger.error(f"Error al cerrar el navegador de Playwright para {url}: {e}", exc_info=False)

async def fetch_product_details_from_url(full_url: str) -> tuple[str | None, str | None]:
    """
    Intenta obtener el contenido HTML de una URL, con reintentos.
    Devuelve una tupla (html_content, status_string).
    """
    html_content = None
    status = 'INIT'

    for attempt in range(config.MAX_RETRIES_SCRAPER + 1): # +1 para incluir el intento inicial
        try:
            html_content = await get_html_from_url(full_url, config.API_TIMEOUT_SECONDS)
            
            if html_content:
                status = 'SUCCESS'
                logger.info(f"HTML obtenido para {full_url} en intento {attempt + 1}")
                break 
            else: # get_html_from_url devolvió None, el error ya fue logueado allí
                status = 'REQUEST_ERROR_NO_CONTENT' 
        except Exception as e: # Captura errores inesperados directamente de get_html_from_url si los hubiera
            status = 'REQUEST_EXCEPTION' # Un error más genérico si la excepción no fue manejada dentro de get_html_from_url
        
        if attempt < config.MAX_RETRIES_SCRAPER:
            await asyncio.sleep(config.RETRY_DELAY_SCRAPER_SECONDS)
        else: # Último intento fallido
            logger.error(f"Todos los {config.MAX_RETRIES_SCRAPER + 1} intentos fallaron para {full_url}. Último estado: {status}")
            
    if not html_content and status != 'SUCCESS':
        status = status if status != 'INIT' else 'ALL_ATTEMPTS_FAILED'
        
    return html_content, status

async def get_product_info(url_to_scrape: str) -> dict:
    cleaned_url_str = clean_url(url_to_scrape)
    # Intento de caché primero
    try:
        cached_product_info = await asyncio.to_thread(db_queries.get_cached_price, cleaned_url_str)
        if cached_product_info:
            # Asegurar que los campos esperados estén presentes, incluso si vienen de caché
            final_cached_info = {
                "price": cached_product_info.get("price"),
                "availability": cached_product_info.get("availability", "N/A (cache)"),
                "condition": cached_product_info.get("product_condition", cached_product_info.get("condition")),
                "name": cached_product_info.get("name", cached_product_info.get("product_name")),
                "description": cached_product_info.get("description"),
                "image": cached_product_info.get("image_url", cached_product_info.get("image")),
                "color": cached_product_info.get("color"),
                "storage": cached_product_info.get("storage"),
                "brand_name": cached_product_info.get("brand_name"),
                "clean_url": cleaned_url_str,
                "full_url": url_to_scrape,
                "status": "CACHE_HIT",
                "source": cached_product_info.get("source", "cache")
            }
            return final_cached_info
    except Exception as e:
        logger.error(f"Error al acceder a la caché para {cleaned_url_str}: {e}", exc_info=True)
    
    html_content, fetch_status = await fetch_product_details_from_url(url_to_scrape)
    
    base_response = {
        "price": None, "availability": None, "condition": None,
        "name": None, "description": None, "image": None,
        "color": None, "storage": None, "brand_name": None,
        "clean_url": cleaned_url_str, "full_url": url_to_scrape,
        "status": f"SCRAPE_FAILED_{fetch_status}",
        "source": "scrape_attempt"
    }
    
    if fetch_status == 'SUCCESS' and html_content:
        try:
            product_details = _parse_product_details(html_content, url_to_scrape)
            
            final_details = base_response.copy()
            final_details.update(product_details)

            missing_attributes = [
                key for key in ["price", "condition"]
                if not final_details.get(key)
            ]

            if missing_attributes:
                final_details["status"] = f"SCRAPED_INCOMPLETE_{fetch_status}"
            else:
                final_details["status"] = f"SCRAPED_SUCCESS_{fetch_status}"
            
            if not final_details["status"].startswith("SCRAPE_FAILED"):
                try:
                    await asyncio.to_thread(
                        db_queries.save_scraped_price,
                        cleaned_url_str,
                        final_details
                    )
                except Exception as e:
                    logger.error(f"Error al guardar datos scrapeados (éxito/incompleto) en BD para {cleaned_url_str}: {e}", exc_info=True)
                    final_details["status"] += "_DB_SAVE_ERROR"
            else:
                logger.info(f"No se guardan datos para {cleaned_url_str} porque el estado es {final_details['status']}")

            return final_details
        except Exception as e:
            logger.error(f"Error al parsear HTML para {url_to_scrape} ({fetch_status}): {e}", exc_info=True)
            base_response["status"] = f"SCRAPE_FAILED_PARSE_ERROR_{fetch_status}"
            logger.warning(f"No se guardarán datos para {cleaned_url_str} debido a error de parseo, estado: {base_response['status']}")
            return base_response
    else:
        logger.warning(f"No se guardarán datos para {cleaned_url_str} debido a fallo en obtención de HTML, estado: {base_response['status']}")
        return base_response

