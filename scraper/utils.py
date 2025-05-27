# scraper/utils.py
from urllib.parse import urlsplit, urlunsplit, parse_qs, urlencode
import logging

logger = logging.getLogger(__name__)


def clean_url(url: str) -> str:
    """Limpia la URL, manteniendo solo los parámetros esenciales (ej: 'l') y eliminando el fragmento."""
    try:
        scheme, netloc, path, query_string, fragment = urlsplit(url)

        query_params = parse_qs(query_string)

        # Mantener solo el parámetro 'l' si existe.
        # Esto es específico para BM.
        kept_query_params = {}
        if "l" in query_params:
            kept_query_params["l"] = query_params["l"]

        new_query_string = urlencode(kept_query_params, doseq=True)

        cleaned = urlunsplit((scheme, netloc, path, new_query_string, ''))
        return cleaned
    except Exception as e:
        logger.error(f"Error al limpiar la URL '{url}': {e}", exc_info=True)
        # Devolver la URL original o una cadena vacía podría ser más seguro que la URL parcialmente procesada
        return url
