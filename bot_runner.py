import asyncio
import signal
import logging
import config
from db.connection import init_db_pool, close_db_pool
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler
from bot.handlers import (
    help_command,
    track_command,
    list_alerts_command,
    delete_alert_by_number_command,
    callback_query_handler
)

logger = logging.getLogger(__name__)


async def main():
    # Inicializar pool de BD
    await init_db_pool()
    logger.info("Bot runner: DB pool initialized.")

    # Construir aplicación de Telegram
    app = ApplicationBuilder().token(config.TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", help_command))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("track", track_command))
    app.add_handler(CommandHandler("alerts", list_alerts_command))
    app.add_handler(CommandHandler("delete", delete_alert_by_number_command))
    app.add_handler(CallbackQueryHandler(callback_query_handler))

    # Inicializar y arrancar bot según la guía de PTB para bucles asyncio existentes
    await app.initialize()
    await app.start()
    await app.updater.start_polling()
    logger.info("Bot de Telegram iniciado y haciendo polling.")

    # Esperar una señal para detener el bot
    stop_event = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, stop_event.set) # Establecer el evento al recibir la señal
    
    logger.info("El bot está en ejecución. Presiona Ctrl+C para detener.")
    await stop_event.wait() # Mantener la corrutina main viva hasta que se reciba la señal

    # Detener el bot
    logger.info("Señal de interrupción recibida, deteniendo el bot...")
    await app.updater.stop()
    await app.stop()
    await app.shutdown()
    
    await close_db_pool()
    logger.info("Bot runner: shutdown completo.")


if __name__ == "__main__":
    asyncio.run(main())
