# config.py
import os
import logging
from dotenv import load_dotenv

load_dotenv()

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
DATABASE_URL = os.getenv("DATABASE_URL")
SCRAPERAPI_KEY = os.getenv("SCRAPERAPI_KEY")

CHECK_INTERVAL_SECONDS = int(os.getenv("CHECK_INTERVAL_SECONDS", 14400))
NOTIFY_COOLDOWN_HOURS = float(os.getenv("NOTIFY_COOLDOWN_HOURS", 4))
SCRAPE_TTL_MINUTES = float(os.getenv("SCRAPE_TTL_MINUTES", 240))
MAX_RETRIES_SCRAPER = int(os.getenv("MAX_RETRIES_SCRAPER", 3))
RETRY_DELAY_SCRAPER_SECONDS = int(os.getenv("RETRY_DELAY_SCRAPER_SECONDS", 5))
API_TIMEOUT_SECONDS = int(os.getenv("API_TIMEOUT_SECONDS", 30))
SCRAPER_MAX_COST = os.getenv("SCRAPER_MAX_COST", '1')

LOGGING_LEVEL_NAME = os.getenv("LOGGING_LEVEL", "INFO").upper()
LOGGING_HTTPX_LEVEL_NAME = os.getenv("LOGGING_HTTPX_LEVEL", "WARNING").upper()

LOGGING_LEVEL = getattr(logging, LOGGING_LEVEL_NAME, logging.INFO)
LOGGING_HTTPX_LEVEL = getattr(logging, LOGGING_HTTPX_LEVEL_NAME, logging.WARNING)

# Configuración básica de logging para este módulo si se importa antes que main
# main.py puede reconfigurar con un formato más detallado.
logging.basicConfig(level=LOGGING_LEVEL)  # Asegura que el logger esté configurado
logger = logging.getLogger(__name__)

if not TELEGRAM_TOKEN:
    logger.critical("No se encontró TELEGRAM_TOKEN en las variables de entorno.")
    raise ValueError("No se encontró TELEGRAM_TOKEN en las variables de entorno.")
if not DATABASE_URL:
    logger.critical("No se encontró DATABASE_URL en las variables de entorno.")
    raise ValueError("No se encontró DATABASE_URL en las variables de entorno.")
if not SCRAPERAPI_KEY:
    logger.warning("No se encontró SCRAPERAPI_KEY. El scraping podría no funcionar como se espera.")

# Logto SDK configuration
LOGTO_ENDPOINT = os.getenv("LOGTO_ENDPOINT")
LOGTO_APP_ID = os.getenv("LOGTO_APP_ID")
LOGTO_APP_SECRET = os.getenv("LOGTO_APP_SECRET")
SESSION_SECRET_KEY = os.getenv("SESSION_SECRET_KEY") # Para SessionMiddleware si se usa LogtoClient con storage

# Para validación de Bearer Tokens JWT de Logto (usado en security.py)
LOGTO_JWKS_URI = os.getenv("LOGTO_JWKS_URI") # Ej: https://<tu-dominio-logto>/oidc/jwks
LOGTO_AUDIENCE = os.getenv("LOGTO_AUDIENCE") # El identificador de tu API Resource en Logto
LOGTO_ISSUER = os.getenv("LOGTO_ISSUER")     # Ej: https://<tu-dominio-logto>/oidc

if not (LOGTO_ENDPOINT and LOGTO_APP_ID and LOGTO_APP_SECRET and SESSION_SECRET_KEY):
    logger.warning(
        "Faltan variables de configuración de Logto para el flujo OIDC server-side (LogtoClient con storage): "
        "LOGTO_ENDPOINT, LOGTO_APP_ID, LOGTO_APP_SECRET, SESSION_SECRET_KEY."
    )

if not (LOGTO_JWKS_URI and LOGTO_AUDIENCE and LOGTO_ISSUER):
    logger.warning(
        "Faltan variables de configuración de Logto para validación de Bearer Tokens JWT: "
        "LOGTO_JWKS_URI, LOGTO_AUDIENCE, LOGTO_ISSUER. La autenticación de API fallará."
    )
