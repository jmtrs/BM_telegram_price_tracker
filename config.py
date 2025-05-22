# tu_proyecto/config.py
import os
import logging
from dotenv import load_dotenv

load_dotenv()

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
SUPABASE_PG_URI = os.getenv("SUPABASE_PG_URI")
SCRAPERAPI_KEY = os.getenv("SCRAPERAPI_KEY")

CHECK_INTERVAL_SECONDS = int(os.getenv("CHECK_INTERVAL_SECONDS", 14400))
NOTIFY_COOLDOWN_HOURS = float(os.getenv("NOTIFY_COOLDOWN_HOURS", 4))
SCRAPE_TTL_MINUTES = float(os.getenv("SCRAPE_TTL_MINUTES", 240))
MAX_RETRIES_SCRAPER = int(os.getenv("MAX_RETRIES_SCRAPER", 2))
RETRY_DELAY_SCRAPER_SECONDS = int(os.getenv("RETRY_DELAY_SCRAPER_SECONDS", 5))
API_TIMEOUT_SECONDS = int(os.getenv("API_TIMEOUT_SECONDS", 60))
SCRAPER_MAX_COST = os.getenv("SCRAPER_MAX_COST", '1')

LOGGING_LEVEL_NAME = os.getenv("LOGGING_LEVEL", "INFO").upper()
LOGGING_HTTPX_LEVEL_NAME = os.getenv("LOGGING_HTTPX_LEVEL", "WARNING").upper()

LOGGING_LEVEL = getattr(logging, LOGGING_LEVEL_NAME, logging.INFO)
LOGGING_HTTPX_LEVEL = getattr(logging, LOGGING_HTTPX_LEVEL_NAME, logging.WARNING)

# Configuración básica de logging para este módulo si se importa antes que main
# main.py puede reconfigurar con un formato más detallado.
logging.basicConfig(level=LOGGING_LEVEL) # Asegura que el logger esté configurado
logger = logging.getLogger(__name__)

if not TELEGRAM_TOKEN:
    logger.critical("No se encontró TELEGRAM_TOKEN en las variables de entorno.")
    raise ValueError("No se encontró TELEGRAM_TOKEN en las variables de entorno.")
if not SUPABASE_PG_URI:
    logger.critical("No se encontró SUPABASE_PG_URI en las variables de entorno.")
    raise ValueError("No se encontró SUPABASE_PG_URI en las variables de entorno.")
if not SCRAPERAPI_KEY:
    logger.warning("No se encontró SCRAPERAPI_KEY. El scraping podría no funcionar como se espera.")
