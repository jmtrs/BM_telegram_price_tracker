import asyncio
import signal
import logging
import config
from db.connection import init_db_pool, close_db_pool
from telegram.ext import ApplicationBuilder
from tasks.checker import check_alerts_periodically

logger = logging.getLogger(__name__)


async def main():
    # Inicializar pool de BD
    await init_db_pool()
    logger.info("Checker runner: DB pool initialized.")

    # Construir aplicación de Telegram solo para enviar notificaciones
    app = ApplicationBuilder().token(config.TELEGRAM_TOKEN).build()
    await app.initialize()
    bot = app.bot

    # Iniciar proceso de chequeo
    checker_task = asyncio.create_task(check_alerts_periodically(app))
    logger.info("Checker de alertas iniciado.")

    # Manejo de señales para shutdown
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, checker_task.cancel)

    try:
        await checker_task
    except asyncio.CancelledError:
        pass

    # Shutdown ordenado
    await app.shutdown()
    await close_db_pool()
    logger.info("Checker runner: shutdown completo.")


if __name__ == "__main__":
    asyncio.run(main())
