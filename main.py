# main.py
import nest_asyncio
nest_asyncio.apply()

import asyncio
import logging

import config

from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler

# Importar módulos como paquetes desde la raíz del proyecto
from bot import handlers as bot_handlers
from tasks import checker as tasks_checker
from db import connection as db_connection

# Configuración del logger principal de la aplicación
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - [%(module)s:%(lineno)d] - %(message)s',
    level=config.LOGGING_LEVEL
)
logging.getLogger("httpx").setLevel(config.LOGGING_HTTPX_LEVEL)
logging.getLogger("telegram.ext").setLevel(logging.INFO)

logger = logging.getLogger(__name__)


async def main_async_logic():
    logger.info("Iniciando el bot...")

    try:
        db_conn = await db_connection.get_db_connection()
        if db_conn is None or db_conn.closed:
            logger.critical("La conexión a la BD no se pudo establecer o está cerrada después del intento inicial.")
            return
        logger.info("Conexión inicial a la base de datos verificada.")
    except Exception as e:
        logger.critical(f"Fallo crítico al obtener conexión a la BD en main: {e}", exc_info=True)
        return

    application = (
        ApplicationBuilder()
        .token(config.TELEGRAM_TOKEN)
        .build()
    )

    application.add_handler(CommandHandler("start", bot_handlers.help_command))
    application.add_handler(CommandHandler("help", bot_handlers.help_command))
    application.add_handler(CommandHandler("track", bot_handlers.track_command))
    application.add_handler(CommandHandler("alerts", bot_handlers.list_alerts_command))
    application.add_handler(CommandHandler("delete", bot_handlers.delete_alert_by_number_command))
    application.add_handler(CallbackQueryHandler(bot_handlers.callback_query_handler))

    # Crear y programar la tarea del checker
    # Esta tarea se ejecutará en el mismo bucle de eventos que application.run_polling()
    checker_task = asyncio.create_task(tasks_checker.check_alerts_periodically(application))
    logger.info("Tarea del checker programada.")

    try:
        logger.info("🤖 Bot iniciado y escuchando actualizaciones...")
        # run_polling es una llamada bloqueante que maneja su propio ciclo de vida de inicialización/apagado.
        await application.run_polling()
    except KeyboardInterrupt:
        logger.info("Cerrando el bot por interrupción de teclado (Ctrl+C)...")
    except Exception as e:
        logger.critical(f"Error no capturado en el bucle principal de polling: {e}", exc_info=True)
    finally:
        logger.info("Iniciando proceso de apagado (desde el bloque finally de main_async_logic)...")

        if checker_task and not checker_task.done():
            logger.info("Cancelando la tarea del checker...")
            checker_task.cancel()
            try:
                await checker_task
                logger.info("Tarea del checker finalizada después de la cancelación.")
            except asyncio.CancelledError:
                logger.info("Tarea del checker explícitamente cancelada y finalizada.")
            except Exception as e_task:
                logger.error(f"Error durante la espera de la cancelación de la tarea del checker: {e_task}", exc_info=True)

        db_connection.close_db_connection()
        logger.info("🤖 Bot detenido (desde el bloque finally de main_async_logic).")


if __name__ == "__main__":
    asyncio.run(main_async_logic())
