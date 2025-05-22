# tu_proyecto/scraper/utils.py
from urllib.parse import urlsplit, urlunsplit, parse_qs, urlencode
import logging

logger = logging.getLogger(__name__)

def clean_url(url: str) -> str:
    """Limpia la URL, manteniendo solo los parámetros esenciales (ej: 'l')."""
    try:
        parts = urlsplit(url)
        query = parse_qs(parts.query)
        # Mantener solo el parámetro 'l' si existe.
        # Esto es específico para BM.
        kept_query = {"l": query["l"]} if "l" in query else {}
        
        # Reconstruir la URL sin parámetros innecesarios y sin fragmento
        # El fragmento (después de #) raramente es necesario para identificar el producto.
        cleaned = urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(kept_query, doseq=True), ''))
        logger.debug(f"URL original: {url}, URL limpiada: {cleaned}")
        return cleaned
    except Exception as e:
        logger.error(f"Error al limpiar la URL '{url}': {e}")
        return url
