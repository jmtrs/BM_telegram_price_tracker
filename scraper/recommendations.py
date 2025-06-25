# scraper/recommendations.py
"""
Captura peticiones de recomendaciones de BackMarket ejecutando scroll completo en la ruta /good-deals.
"""
import asyncio
import time # Aunque time no se usa directamente, lo mantenemos por si se añade logging con timestamps
from typing import List, Dict
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError, Error as PlaywrightError
import config

# Considera añadir estas constantes a tu config.py para facilitar los ajustes
SCROLL_PAUSE_DURATION_S = getattr(config, 'SCROLL_PAUSE_DURATION_S', 3) # Aumentado de 2 a 3
NETWORK_IDLE_TIMEOUT_MS = getattr(config, 'NETWORK_IDLE_TIMEOUT_MS', 5000)
FINAL_WAIT_S = getattr(config, 'FINAL_WAIT_S', 5) # Aumentado ligeramente para dar más margen
MAX_NO_CHANGE_ATTEMPTS = getattr(config, 'MAX_NO_CHANGE_ATTEMPTS', 8) # Aumentado de 5 a 8
PAGE_GOTO_TIMEOUT_MS = getattr(config, 'PAGE_GOTO_TIMEOUT_MS', 60000)
SELECTOR_WAIT_TIMEOUT_MS = getattr(config, 'SELECTOR_WAIT_TIMEOUT_MS', 10000)


async def fetch_recommendation_responses(url: str) -> List[Dict]:
    """
    Abre la página, hace scroll hasta el final y devuelve los JSON de cada respuesta
    al endpoint /bm/recommendation/v2/recommendations/...
    Incluye paginación automática siguiendo nextPageCursor.
    """
    raw_responses: List[tuple[str, Dict]] = []
    collected_urls = set()
    response_tasks: list[asyncio.Task] = []

    browser = None
    context = None
    page = None
    request_ctx = None

    # Obtener el nombre de la categoría para logging
    current_category_name = next((key for key, val in config.RECOMMENDATION_URLS.items() if val == url), "Desconocida")
    print(f"[{current_category_name}] Iniciando fetch_recommendation_responses para URL: {url}")

    async with async_playwright() as p:
        try:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context(user_agent=config.PLAYWRIGHT_USER_AGENT)
            page = await context.new_page()

            page.on("response", lambda resp: response_tasks.append(
                asyncio.create_task(_handle_response(resp, raw_responses, collected_urls, current_category_name))
            ))

            await page.goto(url, timeout=PAGE_GOTO_TIMEOUT_MS)
            print(f"[{current_category_name}] Página cargada: {url}")

            category_key_from_config = next((key for key, val in config.RECOMMENDATION_URLS.items() if val == url), None)
            specific_selector = f'div[name="{category_key_from_config}"][type="universe-page"]' if category_key_from_config else None
            
            # La acción de scroll SIEMPRE es en document.body.
            log_scroll_action_description = "SIEMPRE en document.body (window.scrollTo(0, document.body.scrollHeight))"
            # La MEDICIÓN de altura AHORA también será SIEMPRE en document.body.
            log_height_measurement_target_description = "document.body"

            # La lógica para specific_selector se mantiene para logging o verificación de su presencia,
            # pero no para decidir dónde medir la altura del scroll.
            if specific_selector:
                print(f"[{current_category_name}] Selector específico de categoría definido: {specific_selector}.")
                try:
                    target_element_locator = page.locator(specific_selector)
                    if await target_element_locator.is_visible(timeout=SELECTOR_WAIT_TIMEOUT_MS):
                        print(f"[{current_category_name}] Selector específico '{specific_selector}' VISIBLE. Nota: La medición de altura y el scroll seguirán siendo en document.body.")
                    else:
                        print(f"[{current_category_name}] Selector específico '{specific_selector}' NO VISIBLE o no encontrado tras {SELECTOR_WAIT_TIMEOUT_MS}ms.")
                except PlaywrightTimeoutError:
                    print(f"[{current_category_name}] Timeout esperando visibilidad de '{specific_selector}'.")
                except PlaywrightError as e:
                    print(f"[{current_category_name}] Error al verificar selector específico '{specific_selector}': {e}.")
            else:
                print(f"[{current_category_name}] No hay selector específico de categoría definido.")
        
            print(f"[{current_category_name}] Estrategia de scroll y medición: Medida de altura en '{log_height_measurement_target_description}'. Acción de scroll {log_scroll_action_description}.")

            if page.is_closed():
                print(f"[{current_category_name}] La página se cerró antes de iniciar el scroll.")
                return []
                
            # Medición de altura SIEMPRE en document.body
            previous_height = await page.evaluate("() => document.body.scrollHeight")
            
            print(f"[{current_category_name}] Altura inicial (medida en '{log_height_measurement_target_description}'): {previous_height}.")
            
            scroll_attempts_no_change = 0

            while True:
                if page.is_closed():
                    print(f"[{current_category_name}] La página se cerró durante el bucle de scroll.")
                    break
                
                try:
                    # ACCIÓN DE SCROLL SIEMPRE EN DOCUMENT.BODY
                    print(f"[{current_category_name}] Realizando scroll en document.body (window.scrollTo(0, document.body.scrollHeight))")
                    await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                    
                    await asyncio.sleep(SCROLL_PAUSE_DURATION_S)

                    try:
                        await page.wait_for_load_state('networkidle', timeout=NETWORK_IDLE_TIMEOUT_MS)
                    except PlaywrightTimeoutError:
                        # print(f"[{current_category_name}] Timeout esperando networkidle, continuando scroll.")
                        pass 
                    except PlaywrightError as e:
                        print(f"[{current_category_name}] Error durante wait_for_load_state: {e}")
                        if page.is_closed(): break # Salir del bucle while si la página se cierra
                            
                    if page.is_closed(): break # Salir del bucle while si la página se cierra

                    # MEDICIÓN DE ALTURA SIEMPRE EN DOCUMENT.BODY
                    new_height = await page.evaluate("() => document.body.scrollHeight")
                    
                    # Usar log_height_measurement_target_description para consistencia en el log
                    print(f"[{current_category_name}] Alturas post-scroll: Nueva (medida en '{log_height_measurement_target_description}')={new_height}, Anterior={previous_height}. Acción de scroll fue en document.body.")

                    if new_height == previous_height:
                        scroll_attempts_no_change += 1
                        print(f"[{current_category_name}] La altura (medida en '{log_height_measurement_target_description}') no ha cambiado. Intentos sin cambio: {scroll_attempts_no_change}/{MAX_NO_CHANGE_ATTEMPTS}")
                        if scroll_attempts_no_change >= MAX_NO_CHANGE_ATTEMPTS:
                            print(f"[{current_category_name}] Altura de scroll (medida en '{log_height_measurement_target_description}') sin cambios por {MAX_NO_CHANGE_ATTEMPTS} intentos ({new_height}px). Finalizando scroll.")
                            break
                    else:
                        scroll_attempts_no_change = 0
                    previous_height = new_height
                
                except PlaywrightError as e:
                    print(f"[{current_category_name}] Error en el bucle de scroll: {e}")
                    # Comprobación explícita si el error indica que el target (página/contexto/navegador) se cerró.
                    if "Target page, context or browser has been closed" in str(e):
                        print(f"[{current_category_name}] La página, contexto o navegador se cerró (detectado en excepción de scroll).")
                    elif page.is_closed(): # Comprobación general por si la página se cerró por otra razón durante la operación.
                        print(f"[{current_category_name}] La página se cerró debido a un error o durante una operación en el bucle de scroll.")
                    break # Romper el bucle de scroll en caso de cualquier PlaywrightError.

            print(f"[{current_category_name}] Bucle de scroll finalizado. Esperando {FINAL_WAIT_S}s para respuestas finales.")
            await asyncio.sleep(FINAL_WAIT_S) 

            if response_tasks:
                gathered_results = await asyncio.gather(*response_tasks, return_exceptions=True)
                for i, res in enumerate(gathered_results):
                    if isinstance(res, Exception):
                        print(f"[{current_category_name}] Excepción en una tarea _handle_response ({i}): {res}")
            
            print(f"[{current_category_name}] Total respuestas XHR recolectadas inicialmente: {len(raw_responses)}")

            if raw_responses:
                request_ctx = await p.request.new_context() 
                idx = 0
                print(f"[{current_category_name}] Iniciando paginación si es necesario...")
                while idx < len(raw_responses):
                    api_url, data = raw_responses[idx]
                    idx += 1
                    cursor = data.get('nextPageCursor')
                    if cursor:
                        base_api_url = api_url.split('?')[0]
                        pag_url = f"{base_api_url}?cursor={cursor}"
                        if pag_url not in collected_urls:
                            collected_urls.add(pag_url)
                            # print(f"[{current_category_name}] Paginando: {pag_url}")
                            try:
                                resp = await request_ctx.get(pag_url)
                                if resp.ok:
                                    page_data = await resp.json()
                                    raw_responses.append((pag_url, page_data))
                                    # print(f"[{current_category_name}] Paginación exitosa para {pag_url}, {len(page_data.get('items',[]))} items.")
                                else:
                                    print(f"[{current_category_name}] Error en petición paginada {pag_url}: status {resp.status}")
                            except Exception as e:
                                print(f"[{current_category_name}] Excepción en petición paginada {pag_url}: {e}")
                                pass
    
        except PlaywrightError as e:
            print(f"[{current_category_name}] Error general de Playwright: {e}")
            pass
        except Exception as e:
            print(f"[{current_category_name}] Excepción inesperada: {e}")
            pass
        finally:
            print(f"[{current_category_name}] Bloque finally: cerrando recursos.")
            if request_ctx:
                await request_ctx.dispose()
            if page and not page.is_closed():
                await page.close()
            if context:
                await context.close()
            if browser:
                await browser.close()
            print(f"[{current_category_name}] Recursos cerrados.")
                
    print(f"[{current_category_name}] Retornando {len(raw_responses)} respuestas finales.")
    return [data for (_, data) in raw_responses]


async def _handle_response(resp, results: List[tuple[str, Dict]], seen: set, category_name_for_log: str = "Global"):
    try:
        url = resp.url
        if "backmarket.es/bm/recommendation/v2/recommendations" in url:
            if url in seen:
                return
            seen.add(url)
            
            if resp.ok and "application/json" in resp.headers.get("content-type", "").lower():
                data = await resp.json()
                results.append((url, data)) 
                # print(f"[{category_name_for_log}] _handle_response: Capturada respuesta de {url} con {len(data.get('items',[]))} items.")
            # else:
                # print(f"[{category_name_for_log}] _handle_response: Respuesta NO OK o NO JSON para {url}: status {resp.status}, type {resp.headers.get('content-type')}")
    except PlaywrightError as e: 
        print(f"[{category_name_for_log}] _handle_response: Error de Playwright al procesar respuesta para {resp.url if resp else 'N/A'}: {e}")
    except Exception as e: 
        print(f"[{category_name_for_log}] _handle_response: Error genérico al procesar respuesta para {resp.url if resp else 'N/A'}: {e}")


def get_recommendations_sync(url: str) -> List[Dict]:
    """
    Wrapper síncrono para fetch_recommendation_responses con URL parametrizada.
    Maneja la creación y cierre del bucle de eventos de asyncio.
    """
    created_loop = False
    loop = None
    current_category_name = next((key for key, val in config.RECOMMENDATION_URLS.items() if val == url), url)
    # print(f"[{current_category_name}] get_recommendations_sync: Iniciando.")

    try:
        loop = asyncio.get_running_loop()
        # print(f"[{current_category_name}] get_recommendations_sync: Usando bucle de eventos existente.")
        if loop.is_running():
            print(f"[{current_category_name}] ADVERTENCIA: get_recommendations_sync llamada mientras el bucle de eventos existente está en ejecución. "
                  f"Intentando asyncio.run_coroutine_threadsafe.")
            future = asyncio.run_coroutine_threadsafe(fetch_recommendation_responses(url), loop)
            try:
                # Estimar un timeout generoso para toda la operación de Playwright.
                playwright_timeout = (PAGE_GOTO_TIMEOUT_MS / 1000) + \
                                     (MAX_NO_CHANGE_ATTEMPTS * SCROLL_PAUSE_DURATION_S) + \
                                     FINAL_WAIT_S + 60  # 60s de buffer adicional
                # print(f"[{current_category_name}] get_recommendations_sync: Esperando resultado de future con timeout de {playwright_timeout}s.")
                return future.result(timeout=playwright_timeout)
            except asyncio.TimeoutError:
                print(f"[{current_category_name}] ERROR: Timeout ({playwright_timeout}s) esperando el resultado de fetch_recommendation_responses en el bucle existente.")
                return []
            except Exception as e_future:
                print(f"[{current_category_name}] ERROR: Excepción esperando el resultado de future en el bucle existente: {e_future}")
                return []
        else:
            # El bucle existe pero no está "running" (ej. se usó run_until_complete antes y no se cerró)
            # print(f"[{current_category_name}] get_recommendations_sync: Bucle existente no está 'running'. Usando run_until_complete.")
            # Proceder a loop.run_until_complete más abajo
            pass

    except RuntimeError: # No hay bucle de eventos en ejecución en este hilo.
        # print(f"[{current_category_name}] get_recommendations_sync: No hay bucle de eventos. Creando uno nuevo.")
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        created_loop = True
    
    result = []
    if loop is None: 
        print(f"[{current_category_name}] ERROR CRÍTICO: No se pudo obtener o crear un bucle de eventos.")
        return []

    try:
        result = loop.run_until_complete(fetch_recommendation_responses(url))
    except Exception as e_run:
        print(f"[{current_category_name}] ERROR: Excepción durante run_until_complete(fetch_recommendation_responses): {e_run}")
    finally:
        if created_loop:
            # print(f"[{current_category_name}] get_recommendations_sync: Bucle fue creado. Procediendo a cerrarlo.")
            try:
                loop.run_until_complete(asyncio.sleep(0.5)) # Dar tiempo para limpieza
            except Exception as e_sleep:
                print(f"[{current_category_name}] ERROR: Excepción durante el asyncio.sleep final en el bucle creado: {e_sleep}")
            finally:
                loop.close()
                # print(f"[{current_category_name}] get_recommendations_sync: Bucle creado y cerrado.")
        else:
            # print(f"[{current_category_name}] get_recommendations_sync: Usó bucle existente, no se cierra aquí.")
            pass
            
    # print(f"[{current_category_name}] get_recommendations_sync: Finalizado. Devolviendo {len(result)} respuestas.")
    return result
