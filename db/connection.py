# db/connection.py
import psycopg2
from psycopg2.extras import RealDictCursor
import logging
import config

logger = logging.getLogger(__name__)
conn = None


def get_db_connection():
    """Establece o retorna la conexión existente a la base de datos."""
    global conn
    if conn is None or conn.closed:
        try:
            conn = psycopg2.connect(config.DATABASE_URL, cursor_factory=RealDictCursor)
            conn.autocommit = True
            logger.info("Nueva conexión a la base de datos establecida.")
        except psycopg2.Error as e:
            logger.critical(f"Error CRÍTICO al conectar con la base de datos: {e}")
            raise
    return conn

def close_db_connection():
    """Cierra la conexión a la base de datos si está abierta."""
    global conn
    if conn and not conn.closed:
        conn.close()
        logger.info("Conexión a la base de datos cerrada.")
        conn = None
    else:
        logger.info("No hay conexión abierta a cerrar.")
