# BM_telegram_price_tracker/test_request.py
import requests
import os
from dotenv import load_dotenv
import logging

# Configurar logging básico para este script de prueba
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

load_dotenv() # Carga .env del directorio actual

# Leer desde os.getenv, usando valores por defecto si es necesario
SCRAPERAPI_KEY = os.getenv("SCRAPERAPI_KEY")
# Usa el mismo timeout que tu config.py para consistencia en pruebas
API_TIMEOUT_SECONDS = int(os.getenv("API_TIMEOUT_SECONDS", 10)) 
SCRAPER_MAX_COST = os.getenv("SCRAPER_MAX_COST", '1')

# URL que está dando problemas en el log del bot
url_to_test = "https://www.backmarket.es/es-es/p/ipad-air-5-2022-109-256gb-purpura-sin-puerto-sim/dc35c628-76fc-42fc-92f1-f6cf8879c836?l=9&variantClicked=true#scroll=false"
# url_to_test_simple = "https://www.google.com" # Para una prueba rápida y confiable

logging.info(f"Probando URL: {url_to_test}")
logging.info(f"Timeout configurado: {API_TIMEOUT_SECONDS}s")

# --- Prueba directa ---
logging.info("\n--- Iniciando prueba directa ---")
try:
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
    }
    logging.info(f"Haciendo GET directo a: {url_to_test}")
    resp_direct = requests.get(url_to_test, headers=headers, timeout=API_TIMEOUT_SECONDS)
    logging.info(f"Prueba directa - Status: {resp_direct.status_code}")
    # logging.info(f"Prueba directa - Primeros 500 chars: {resp_direct.text[:500]}")
    resp_direct.raise_for_status()
    logging.info("Prueba directa completada con éxito.")
except requests.exceptions.Timeout:
    logging.error(f"Error en prueba directa: Timeout después de {API_TIMEOUT_SECONDS} segundos.")
except requests.exceptions.RequestException as e:
    logging.error(f"Error en prueba directa: {e}")
except Exception as e_gen:
    logging.error(f"Error general inesperado en prueba directa: {e_gen}", exc_info=True)


# --- Prueba con ScraperAPI ---
if SCRAPERAPI_KEY:
    logging.info("\n--- Iniciando prueba con ScraperAPI ---")
    try:
        payload = {
            'api_key': SCRAPERAPI_KEY,
            'url': url_to_test,
            'max_cost': SCRAPER_MAX_COST 
            # Podrías añadir más parámetros de ScraperAPI aquí si los usas, ej. 'render': 'true'
        }
        scraper_api_url = "https://api.scraperapi.com/"
        logging.info(f"Haciendo GET a ScraperAPI: {scraper_api_url} con payload para URL: {url_to_test}")
        resp_api = requests.get(scraper_api_url, params=payload, timeout=API_TIMEOUT_SECONDS)
        logging.info(f"Prueba ScraperAPI - Status: {resp_api.status_code}")
        # logging.info(f"Prueba ScraperAPI - Primeros 500 chars: {resp_api.text[:500]}")
        resp_api.raise_for_status()
        logging.info("Prueba ScraperAPI completada con éxito.")
    except requests.exceptions.Timeout:
        logging.error(f"Error en prueba ScraperAPI: Timeout después de {API_TIMEOUT_SECONDS} segundos.")
    except requests.exceptions.RequestException as e:
        logging.error(f"Error en prueba ScraperAPI: {e}")
    except Exception as e_gen:
        logging.error(f"Error general inesperado en prueba ScraperAPI: {e_gen}", exc_info=True)
else:
    logging.warning("\nSCRAPERAPI_KEY no encontrada en .env, saltando prueba con API.")

logging.info("\n--- Pruebas finalizadas ---")
