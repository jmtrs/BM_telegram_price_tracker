# scraper/core.py
import logging
import json
import asyncio
import re
import time
from bs4 import BeautifulSoup
import urllib.parse

from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError
from prometheus_client import Counter, Histogram, Gauge

import config
from db import queries as db_queries
from .utils import clean_url

logger = logging.getLogger(__name__)

# Métricas de rendimiento
scraper_success_counter = Counter('scraper_success_total', 'Número total de scrapes exitosos')
scraper_failure_counter = Counter('scraper_failure_total', 'Número total de scrapes fallidos')

# Métricas adicionales
scraper_incomplete_counter = Counter('scraper_incomplete_total', 'Número total de scrapes con datos incompletos')
scraper_duration_seconds = Histogram(
    'scraper_duration_seconds',
    'Duración en segundos de la operación de scraping completo',
    buckets=[0.1, 0.5, 1, 2, 5, 10, 30, 60]
)

# Semáforo para limitar scrapes concurrentes
scraper_semaphore = asyncio.Semaphore(config.SCRAPER_MAX_CONCURRENT_SCRAPES)

# Pool de navegador Playwright reutilizable
global_playwright = None
global_browser = None

# Métrica de scrapes en curso
scraper_in_flight_gauge = Gauge('scraper_in_flight', 'Número de scrapes en curso')

# Métrica de scrapes perdidos y latencia de espera de semáforo
stale_products_counter = Counter('scrapes_perdidos_total', 'Número total de scrapes perdidos por semáforo saturado')
semaphore_wait_seconds = Histogram('semaphore_wait_seconds', 'Tiempo en segundos esperando semáforo', buckets=[0.1, 0.5, 1, 2, 5, 10])

# Diccionario de semáforos por host
host_semaphores: dict[str, asyncio.Semaphore] = {}

async def _get_browser():
    global global_playwright, global_browser
    if global_playwright is None or global_browser is None:
        global_playwright = await async_playwright().start()
        global_browser = await global_playwright.chromium.launch(headless=True)
    return global_browser

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
    
    # Fallback: descripción desde meta description y imagen desde og:image si no hay JSON-LD
    if not product_data.get('description'):
        meta_desc = soup.find('meta', attrs={'name': 'description'})
        if meta_desc and meta_desc.get('content'):
            product_data['description'] = meta_desc['content'].strip()
            source_parts.append('description_meta')
    if not product_data.get('image'):
        og_img = soup.find('meta', property='og:image')
        if og_img and og_img.get('content'):
            product_data['image'] = og_img['content'].strip()
            source_parts.append('image_og')
    # Fallback HTML para color y storage
    if not product_data.get('color'):
        color_tag = soup.find('span', class_='product-color')
        if color_tag:
            product_data['color'] = color_tag.get_text(strip=True)
            source_parts.append('color_html_fallback')
    if not product_data.get('storage'):
        storage_tag = soup.find('span', class_='product-storage')
        if storage_tag:
            product_data['storage'] = storage_tag.get_text(strip=True)
            source_parts.append('storage_html_fallback')

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


# Excepción personalizada para exceso de redirecciones
class TooManyRedirectsError(Exception):
    pass

async def get_html_from_url(url: str, timeout_seconds: int = config.API_TIMEOUT_SECONDS) -> str | None:
    # Semáforo por host
    host = urllib.parse.urlparse(url).netloc
    host_sem = host_semaphores.setdefault(host, asyncio.Semaphore(config.SCRAPER_MAX_CONCURRENT_SCRAPES_PER_HOST))
    # Intentar adquirir semáforo de host con timeout y medir latencia
    start_host_wait = time.monotonic()
    try:
        await asyncio.wait_for(host_sem.acquire(), timeout=config.SEMAPHORE_ACQUIRE_TIMEOUT_SECONDS)
    except asyncio.TimeoutError:
        stale_products_counter.inc()
        logger.warning(f"Semáforo por host ocupado >{config.SEMAPHORE_ACQUIRE_TIMEOUT_SECONDS}s para {host}, scrape perdido para {url}")
        return None
    host_wait_elapsed = time.monotonic() - start_host_wait
    semaphore_wait_seconds.observe(host_wait_elapsed)

    # Semáforo global
    start_global_wait = time.monotonic()
    try:
        await asyncio.wait_for(scraper_semaphore.acquire(), timeout=config.SEMAPHORE_ACQUIRE_TIMEOUT_SECONDS)
    except asyncio.TimeoutError:
        stale_products_counter.inc()
        # Liberar semáforo de host si falla acquire global
        host_sem.release()
        logger.warning(f"Semáforo global ocupado >{config.SEMAPHORE_ACQUIRE_TIMEOUT_SECONDS}s, scrape perdido para {url}")
        return None
    global_wait_elapsed = time.monotonic() - start_global_wait
    semaphore_wait_seconds.observe(global_wait_elapsed)
    # Ya adquiridos ambos semáforos, iniciar scraping
    scraper_in_flight_gauge.inc()
    try:
        logger.info(f"Iniciando scraping con Playwright para URL: {url}")
        browser = await _get_browser()
        # Crear un nuevo contexto y página para cada petición
        context = await browser.new_context(user_agent=config.PLAYWRIGHT_USER_AGENT)
        page = await context.new_page()
        try:
            # Intento original con query y fragmentos
            await page.goto(url, timeout=timeout_seconds * 1000, wait_until='domcontentloaded')
            html_content = await page.content()
            if not html_content or html_content.strip() == "<html><head></head><body></body></html>":
                logger.warning(f"Contenido HTML vacío o mínimo para {url}")
                return None
            return html_content
        except PlaywrightTimeoutError:
            logger.error(f"Timeout ({timeout_seconds}s) al obtener HTML para {url}")
            return None
        except Exception as e:
            # Manejo de demasiadas redirecciones: strip query y fragment y reintentar
            msg = str(e)
            if "net::ERR_TOO_MANY_REDIRECTS" in msg:
                logger.warning(f"Exceso de redirecciones para {url}, reintentando sin parámetros...")
                parsed = urllib.parse.urlparse(url)
                stripped = urllib.parse.urlunparse(parsed._replace(query='', fragment=''))
                try:
                    await page.goto(stripped, timeout=timeout_seconds * 1000, wait_until='domcontentloaded')
                    html_content = await page.content()
                    if not html_content or html_content.strip() == "<html><head></head><body></body></html>":
                        logger.warning(f"Contenido HTML vacío tras reintento para {stripped}")
                        return None
                    return html_content
                except Exception as e2:
                    logger.error(f"Reintento fallido para {stripped}: {e2}")
                    return None
            logger.error(f"Error general de Playwright/red al obtener HTML para {url}: {e}", exc_info=True)
            return None
        finally:
            await page.close()
            await context.close()
            logger.debug(f"Recursos de Playwright para {url} cerrados.")
    finally:
        scraper_in_flight_gauge.dec()
        # Liberar semáforos en orden inverso
        scraper_semaphore.release()
        host_sem.release()

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
        except TooManyRedirectsError as e:
            status = 'ERR_TOO_MANY_REDIRECTS'
            # No reintentar en caso de exceso de redirecciones
            break
        except Exception as e: # Captura errores inesperados directamente de get_html_from_url si los hubiera
            status = 'REQUEST_EXCEPTION' # Un error más genérico si la excepción no fue manejada dentro de get_html_from_url
        
        if attempt < config.MAX_RETRIES_SCRAPER:
            await asyncio.sleep(config.RETRY_DELAY_SCRAPER_SECONDS)
        else: # Último intento fallido
            logger.error(f"Todos los {config.MAX_RETRIES_SCRAPER + 1} intentos fallaron para {full_url}. Último estado: {status}")
            
    if not html_content and status not in ['SUCCESS', 'ERR_TOO_MANY_REDIRECTS']:
        status = status if status != 'INIT' else 'ALL_ATTEMPTS_FAILED'
        
    return html_content, status

async def get_product_info(url_to_scrape: str) -> dict:
    # Medir el tiempo total del scraping
    with scraper_duration_seconds.time():
        cleaned_url_str = clean_url(url_to_scrape)
        try:
            cached_product_info = await asyncio.to_thread(db_queries.get_cached_price, cleaned_url_str)
            if cached_product_info:
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
                if not final_cached_info["price"] or not final_cached_info["condition"]:
                    logger.warning(f"Datos incompletos en caché para {cleaned_url_str}, descartando caché.")
                else:
                    scraper_success_counter.inc()
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

                if not final_details['price'] or not final_details['condition']:
                    logger.error(f"Datos incompletos obtenidos para {cleaned_url_str}. No se guardarán en la base de datos.")
                    final_details['status'] = f"SCRAPED_INCOMPLETE_{fetch_status}"
                    scraper_incomplete_counter.inc()
                    return final_details

                final_details['status'] = f"SCRAPED_SUCCESS_{fetch_status}"

                try:
                    await asyncio.to_thread(
                        db_queries.save_scraped_price,
                        cleaned_url_str,
                        final_details
                    )
                except Exception as e:
                    logger.error(f"Error al guardar datos scrapeados en BD para {cleaned_url_str}: {e}", exc_info=True)
                    final_details["status"] += "_DB_SAVE_ERROR"

                scraper_success_counter.inc()
                return final_details
            except Exception as e:
                logger.error(f"Error al parsear HTML para {url_to_scrape} ({fetch_status}): {e}", exc_info=True)
                base_response["status"] = f"SCRAPE_FAILED_PARSE_ERROR_{fetch_status}"
                scraper_failure_counter.inc()
                return base_response
        else:
            logger.warning(f"No se guardarán datos para {cleaned_url_str} debido a fallo en obtención de HTML, estado: {base_response['status']}")
            scraper_failure_counter.inc()
            return base_response

async def get_product_info_with_retries(url_to_scrape: str) -> dict:
    """Intenta obtener información del producto con reintentos en caso de fallos."""
    retries = 0
    max_retries = config.MAX_RETRIES_SCRAPER
    delay = config.RETRY_DELAY_SCRAPER_SECONDS
    last_status = None

    while retries < max_retries:
        product_info = await get_product_info(url_to_scrape)
        last_status = product_info.get("status")

        if product_info.get("price") is not None and not last_status.startswith("SCRAPED_INCOMPLETE"):
            return product_info

        if last_status.startswith("SCRAPED_INCOMPLETE") or "ERR_TOO_MANY_REDIRECTS" in last_status:
            logger.warning(f"No se reintenta para URL {url_to_scrape}, estado no recuperable: {last_status}")
            return product_info

        retries += 1
        logger.warning(f"Reintento {retries}/{max_retries} para URL: {url_to_scrape}. Estado actual: {last_status}")
        await asyncio.sleep(delay * retries)

    logger.error(f"Fallaron todos los reintentos para URL: {url_to_scrape}, estado final: {last_status}")
    return {"status": last_status or "SCRAPE_FAILED_MAX_RETRIES"}

async def shutdown_playwright():
    """Cierra el navegador y detiene Playwright."""
    global global_browser, global_playwright
    try:
        if global_browser:
            await global_browser.close()
    except Exception:
        pass
    try:
        if global_playwright:
            await global_playwright.stop()
    except Exception:
        pass

