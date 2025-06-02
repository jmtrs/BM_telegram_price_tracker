# BM_telegram_price_tracker/test_request.py
import logging
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError
import json
import re
from bs4 import BeautifulSoup

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

API_TIMEOUT_SECONDS = 60  # Aumentado para pruebas más largas

# --- Definiciones de funciones copiadas y adaptadas de scraper/core.py ---

def _normalize_condition(condition_text: str | None) -> str | None:
    if not condition_text:
        return None
    
    text = condition_text.lower().strip()

    # Estados principales de BackMarket (y sinónimos comunes)
    if text in ["prémium", "premium", "impecable"]: # "impecable" es un sinónimo para Prémium
        return "Prémium"
    if text == "excelente":
        return "Excelente"
    if text in ["muy bueno", "muy buen estado"]:
        return "Muy bueno"
    if text == "correcto":
        return "Correcto"
    
    # Estados de schema.org y otros genéricos (si no coincidieron con los de arriba)
    if "schema.org/" in text:
        condition_part = text.split('/')[-1]
        if condition_part == "newcondition": return "Nuevo"
        if condition_part == "refurbishedcondition": return "Reacondicionado"
        # UsedCondition es amplio. Mapeado a "Reacondicionado" por consistencia con JSON-LD observado.
        if condition_part == "usedcondition": return "Reacondicionado" 
        if condition_part == "damagedcondition": return "Dañado"
        # Si hay otras condiciones de schema.org no mapeadas, se registrará al final.

    # Mapeos genéricos (si no son de schema.org y no coincidieron antes)
    # Estos son para casos donde el texto podría venir sin el path completo de schema.org
    if "newcondition" in text: return "Nuevo"
    if "refurbishedcondition" in text: return "Reacondicionado" # Cubre "refurbished" también
    if "damagedcondition" in text: return "Dañado"

    # Si el texto original es uno de los estados deseados (ya capitalizado), devolverlo.
    # Esto es útil si el texto ya viene bien y no necesita normalización de minúsculas.
    # No es estrictamente necesario si la entrada siempre se espera en minúsculas o mixta,
    # pero no hace daño y puede capturar algunos casos borde.
    if condition_text in ["Prémium", "Excelente", "Muy bueno", "Correcto", "Nuevo", "Reacondicionado", "Dañado"]:
       return condition_text

    logger.info(f"Condición '{condition_text}' no normalizada a un valor conocido de BackMarket.")
    return None

def _parse_product_details(html_content: str, url: str) -> dict:
    product_data = {
        'name': None, 'price': None, 'condition': None, 'availability': None,
        'sku': None, 'description': None, 'image': None, 'color': None,
        'storage': None, 'brand_name': None, 'url': url, 'source': 'initial_test'
    }
    soup = BeautifulSoup(html_content, 'html.parser')

    name_from_html = None
    name_tag_specific = soup.find('h1', attrs={'data-test-id': 'product-title'})
    if name_tag_specific:
        name_from_html = name_tag_specific.get_text(strip=True)
    else:
        name_tag_generic = soup.find('h1')
        if name_tag_generic:
            name_from_html = name_tag_generic.get_text(strip=True)
    product_data['name'] = name_from_html
    if name_from_html: product_data['source'] += ",name_html"


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
                logger.warning(f"Fallo al decodificar JSON-LD para {url}", exc_info=False) # Reducir verbosidad
            except Exception as e:
                 logger.error(f"Error inesperado procesando JSON-LD para {url}: {e}", exc_info=False) # Reducir verbosidad
    
    if not product_json_ld: product_json_ld = {}

    # Price from HTML
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
                price_text_cleaned = price_text.replace('€', '').replace('\xa0', '').replace('.', '').replace(',', '.').strip()
                try:
                    price_from_html = float(price_text_cleaned)
                    logger.info(f"Precio HTML: {price_from_html} (selector: {selector})")
                    break 
                except ValueError:
                    logger.warning(f"No se pudo convertir precio HTML '{price_text_cleaned}' a float para {url}")
    
    # Price from JSON-LD (fallback)
    price_from_json_ld = None
    offers_data = product_json_ld.get('offers', {})
    if isinstance(offers_data, list): offers_data = offers_data[0] if offers_data else {}
    # Asegurarse de que offers_data es un diccionario antes de usar .get()
    if not isinstance(offers_data, dict):
        offers_data = {} # Prevenir error si offers_data no es un dict
    price_from_json_ld_str = offers_data.get('price')
    if price_from_json_ld_str:
        try:
            price_from_json_ld = float(price_from_json_ld_str)
        except (ValueError, TypeError):
            logger.warning(f"No se pudo convertir precio JSON-LD '{price_from_json_ld_str}' a float para {url}")

    if price_from_html is not None:
        product_data['price'] = price_from_html
        product_data['source'] += ",price_html"
    elif price_from_json_ld is not None:
        product_data['price'] = price_from_json_ld
        product_data['source'] += ",price_jsonld"
    else:
        product_data['source'] += ",price_unavailable"

    # Condition from HTML (Grade selected) - Revised Strategy
    grade_condition_from_html = None
    raw_grade_text_final = None
    logger.info(f"COND_HTML Revised Strategy: Searching for selected elements for {url}")

    selected_elements_candidates = soup.select(
        '[aria-pressed="true"], [aria-checked="true"], [aria-selected="true"], '
        '.selected, .active, .is-selected, .is-active, .current, .activated, .selected_item, '
        '[class*="--selected"], [class*="-selected"], [class*="_selected"], '
        '[class*="--active"], [class*="-active"], [class*="_active"], '
        '[class*="--current"], [class*="-current"], [class*="_current"]'
    )

    found_condition_element = False

    for elem in selected_elements_candidates:
        temp_raw_text = None
        
        # Prioridad 1: Spans (often contain clean text)
        spans = elem.find_all('span', recursive=True)
        for span in spans:
            span_text = span.get_text(strip=True)
            # Check if this span's text is a direct condition & passes sanity checks
            if _normalize_condition(span_text) and 2 < len(span_text) < 30 and not span_text.isdigit() and "€" not in span_text and "dct" not in span_text.lower() and "ahorra" not in span_text.lower():
                temp_raw_text = span_text
                logger.info(f"COND_HTML Revised Strategy: Accepted text from SPAN: '{temp_raw_text}'")
                break 
        
        # Prioridad 2: Direct text of the element if no suitable span found
        if not temp_raw_text:
            direct_text = elem.get_text(strip=True)
            if _normalize_condition(direct_text) and len(direct_text) < 30: # Check if the whole direct text is a condition
                temp_raw_text = direct_text
                logger.info(f"COND_HTML Revised Strategy: Accepted DIRECT text: '{temp_raw_text}'")
            else:
                # If direct text is not a condition itself, check parts of it
                parts = re.findall(r'\b[A-Za-záéíóúÁÉÍÓÚüÜñÑ]{3,}(?:\s+[A-Za-záéíóúÁÉÍÓÚüÜñÑ]{3,})?\b', direct_text) # Corrected regex
                for part in parts:
                    if _normalize_condition(part):
                        # Filter out common words that might accidentally normalize but aren't conditions
                        if part.lower() not in ["iphone", "ver detalles", "elegir", "estado", "color", "capacidad", "wifi", "ipad", "air", "gb"] and not part.isdigit() and "€" not in part:
                            temp_raw_text = part
                            logger.info(f"COND_HTML Revised Strategy: Accepted PART of direct text: '{temp_raw_text}'")
                            break 
                            
        if temp_raw_text:
            # Final validation: ensure the extracted text is indeed a normalizable condition
            normalized_condition_check = _normalize_condition(temp_raw_text)
            if normalized_condition_check:
                raw_grade_text_final = temp_raw_text
                found_condition_element = True
                break # Exit loop once a suitable element and text are found
            else:
                logger.debug(f"COND_HTML Revised Strategy: Text '{temp_raw_text}' from selected element was not a normalizable condition (final check).")
        else:
            logger.debug(f"COND_HTML Revised Strategy: Element {str(elem)[:70]}... did not yield a recognizable condition text.")
            
    if not found_condition_element:
        logger.info(f"COND_HTML Revised Strategy: No selected element found whose text could be normalized to a known condition.")

    # Normalización final del texto crudo obtenido
    if raw_grade_text_final:
        logger.info(f"COND_HTML: Texto crudo final para normalizar: '{raw_grade_text_final}'")
        normalized_grade = _normalize_condition(raw_grade_text_final)
        if normalized_grade:
            grade_condition_from_html = normalized_grade
            logger.info(f"COND_HTML: Condición normalizada: '{grade_condition_from_html}' (raw: '{raw_grade_text_final}')")
        else:
            logger.warning(f"COND_HTML: Texto crudo final '{raw_grade_text_final}' NO PUDO SER NORMALIZADO.")
    else:
        logger.info(f"COND_HTML: No se obtuvo ningún texto de grado crudo de HTML.")

    # Condition from JSON-LD (fallback)
    condition_from_json_ld_schema = offers_data.get('itemCondition')
    normalized_json_ld_condition = None
    if condition_from_json_ld_schema:
        raw_condition_str = str(condition_from_json_ld_schema).split('/')[-1] if "schema.org/" in str(condition_from_json_ld_schema) else str(condition_from_json_ld_schema)
        normalized_json_ld_condition = _normalize_condition(raw_condition_str)

    if grade_condition_from_html:
        product_data['condition'] = grade_condition_from_html
        product_data['source'] += ",condition_html_grade"
    elif normalized_json_ld_condition:
        product_data['condition'] = normalized_json_ld_condition
        product_data['source'] += ",condition_jsonld"
    else:
        product_data['source'] += ",condition_unavailable"
        
    logger.info(f"Parse finalizado para {url}. Datos: Precio={product_data['price']}, Condición='{product_data['condition']}', Fuente='{product_data['source']}'")
    return product_data

def get_html_from_url_sync(p_instance, url: str, timeout_seconds: int) -> str | None:
    browser = None
    page = None
    html_content = None
    logger.info(f"Obteniendo HTML síncrono para: {url}")
    try:
        browser = p_instance.chromium.launch(headless=True)
        page = browser.new_page()
        page.set_extra_http_headers({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        })
        response = page.goto(url, timeout=timeout_seconds * 1000, wait_until='domcontentloaded')
        if response and response.ok:
            html_content = page.content()
            logger.info(f"HTML obtenido con éxito para {url}")
        else:
            logger.error(f"Error al cargar la página {url}. Status: {response.status if response else 'No response'}")
    except PlaywrightTimeoutError:
        logger.error(f"Timeout ({timeout_seconds}s) al obtener HTML para {url}")
    except Exception as e:
        logger.error(f"Error inesperado al obtener HTML para {url}: {e}", exc_info=True)
    finally:
        if page: page.close()
        if browser: browser.close()
    return html_content

def get_product_details_from_url_sync(p_instance, url: str, timeout_seconds: int) -> dict | None:
    html_content = get_html_from_url_sync(p_instance, url, timeout_seconds)
    if html_content:
        return _parse_product_details(html_content, url)
    return None

# --- Lógica de Pruebas ---
test_cases = [
    {
        "url": "https://www.backmarket.es/es-es/p/ipad-air-m2-11-2024-6a-generacion-256-gb-wifi-purpura/0517a26a-9352-4361-b52c-e43b072c5e41?l=10",
        "expected_price": 568.00,
        "expected_condition": "Excelente"
    },
    {
        "url": "https://www.backmarket.es/es-es/p/ipad-air-m2-11-2024-6a-generacion-256-gb-wifi-blanco-estrella/99f61ab3-4cef-4f30-8672-057feb10d8df?l=9",
        "expected_price": 599.00,
        "expected_condition": "Prémium" 
    },
    {
        "url": "https://www.backmarket.es/es-es/p/ipad-air-5-2022-109-256gb-purpura-sin-puerto-sim/dc35c628-76fc-42fc-92f1-f6cf8879c836?l=9&variantClicked=true#scroll=false",
        "expected_price": None, # No se proporciona, se mostrará lo extraído
        "expected_condition": None # No se proporciona, se mostrará lo extraído
    }
]

if __name__ == "__main__":
    logger.info("--- Iniciando pruebas de scraping autónomas ---")
    all_tests_passed = True
    
    with sync_playwright() as p: # Iniciar Playwright una vez para todas las pruebas
        for i, case in enumerate(test_cases):
            logger.info(f"--- Caso de prueba {i+1} --- URL: {case['url']}")
            logger.info(f"Esperado: Precio={case['expected_price']}, Condición='{case['expected_condition']}'")
            
            product_details = get_product_details_from_url_sync(p, case['url'], API_TIMEOUT_SECONDS)

            if product_details:
                # Si no hay valores esperados, el test se considera "informativo" para este caso
                if case['expected_price'] is None and case['expected_condition'] is None:
                    logger.info(f"CASO {i+1} (Informativo): Obtenido Precio={product_details.get('price')}, Condición='{product_details.get('condition')}', Fuente='{product_details.get('source')}'")
                    # No se marca como fallo si no hay valores esperados
                    price_ok = True 
                    condition_ok = True
                else:
                    price_ok = product_details.get('price') == case['expected_price']
                    condition_ok = product_details.get('condition') == case['expected_condition']
                
                    logger.info(f"Obtenido: Precio={product_details.get('price')}, Condición='{product_details.get('condition')}', Fuente='{product_details.get('source')}'")
                
                    if price_ok and condition_ok:
                        logger.info(f"CASO {i+1} PASÓ.")
                    else:
                        all_tests_passed = False
                        logger.error(f"CASO {i+1} FALLÓ.")
                        if not price_ok:
                            logger.error(f"  PRECIO: Esperado={case['expected_price']}, Obtenido={product_details.get('price')}")
                        if not condition_ok:
                            logger.error(f"  CONDICIÓN: Esperada='{case['expected_condition']}', Obtenida='{product_details.get('condition')}'")
            else:
                all_tests_passed = False
                logger.error(f"CASO {i+1} FALLÓ: No se pudieron obtener detalles del producto.")
            logger.info("--- Fin caso de prueba ---")

    if all_tests_passed:
        logger.info("TODAS LAS PRUEBAS PASARON CON ÉXITO.")
    else:
        logger.error("ALGUNAS PRUEBAS FALLARON. Un gatito está triste.")

    logger.info("--- Pruebas de scraping autónomas finalizadas ---")

# El código original de test_request.py que solo guardaba un scraper.html ha sido reemplazado.
