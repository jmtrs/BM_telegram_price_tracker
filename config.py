# config.py
import os
import logging
from dotenv import load_dotenv

load_dotenv()

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
DATABASE_URL = os.getenv("DATABASE_URL")

CHECK_INTERVAL_SECONDS = int(os.getenv("CHECK_INTERVAL_SECONDS", 3700))
NOTIFY_COOLDOWN_HOURS = float(os.getenv("NOTIFY_COOLDOWN_HOURS", 1))
SCRAPE_TTL_MINUTES = float(os.getenv("SCRAPE_TTL_MINUTES", 60)) 
MAX_RETRIES_SCRAPER = int(os.getenv("MAX_RETRIES_SCRAPER", 3))
RETRY_DELAY_SCRAPER_SECONDS = int(os.getenv("RETRY_DELAY_SCRAPER_SECONDS", 5))
API_TIMEOUT_SECONDS = int(os.getenv("API_TIMEOUT_SECONDS", 20))

# Número máximo de scrapes concurrentes permitidos
SCRAPER_MAX_CONCURRENT_SCRAPES = int(os.getenv("SCRAPER_MAX_CONCURRENT_SCRAPES", 5))

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
if not DATABASE_URL:
    logger.critical("No se encontró DATABASE_URL en las variables de entorno.")
    raise ValueError("No se encontró DATABASE_URL en las variables de entorno.")

# User agent para Playwright
PLAYWRIGHT_USER_AGENT = os.getenv(
    "PLAYWRIGHT_USER_AGENT",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/100.0.4896.127 Safari/537.36"
)

# Tiempo en horas para reintentar un host tras demasiadas redirecciones
CIRCUIT_BREAKER_HOURS = float(os.getenv("CIRCUIT_BREAKER_HOURS", 1))
