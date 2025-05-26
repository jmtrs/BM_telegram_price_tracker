# tasks/checker.py
import asyncio
import logging
from datetime import datetime, timedelta, timezone

from telegram.ext import Application
from telegram.constants import ParseMode
from telegram.error import TelegramError

import config
from db import queries as db_queries
from db.connection import get_db_pool
from scraper import core as scraper_core
from bot import ui as bot_ui

logger = logging.getLogger(__name__)


async def check_alerts_periodically(application: Application):
    bot = application.bot
    while True:
        logger.info(f"[Checker] Ejecutando ciclo a las {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S %Z')}")
        alerts_to_check = []
        pool = await get_db_pool()
        try:
            async with pool.acquire() as conn:
                alerts_to_check = await db_queries.get_all_alerts(conn)
        except Exception as e:
            logger.error(f"[Checker] Error obteniendo alertas de BD: {e}", exc_info=True)
            await asyncio.sleep(config.CHECK_INTERVAL_SECONDS)
            continue

        if not alerts_to_check:
            logger.info("[Checker] No hay alertas activas.")
        else:
            logger.info(f"[Checker] Verificando {len(alerts_to_check)} alerta(s).")

        for i, alert_data in enumerate(alerts_to_check):
            logger.debug(f"[Checker] Procesando alerta ID {alert_data['id']} para URL: {alert_data['clean_url']}")
            if i > 0: await asyncio.sleep(1)

            now_utc = datetime.now(timezone.utc)
            last_notified_db = alert_data.get('last_notified')
            last_notified_utc = None
            if last_notified_db:
                if last_notified_db.tzinfo is None:
                    last_notified_utc = last_notified_db.replace(tzinfo=timezone.utc)
                else:
                    last_notified_utc = last_notified_db.astimezone(timezone.utc)

            if last_notified_utc and now_utc - last_notified_utc < timedelta(hours=config.NOTIFY_COOLDOWN_HOURS):
                logger.info(f"Saltando alerta ID {alert_data['id']} (cooldown).")
                continue

            product_info = await scraper_core.get_product_info(alert_data['full_url'], use_api=True)
            current_price = product_info.get("price")

            async with pool.acquire() as conn_update:
                async with conn_update.transaction():
                    if current_price is None:
                        logger.warning(
                            f"No se pudo obtener precio para alerta ID {alert_data['id']}. Estado: {product_info.get('status')}")
                        await db_queries.update_alert_last_price(conn_update, str(alert_data['id']), None)
                        continue

                    previous_last_price = alert_data.get('last_price')
                    await db_queries.update_alert_last_price(conn_update, str(alert_data['id']), current_price)

                    notification_triggered = False
                    target_price = alert_data['target_price']

                    if current_price <= target_price:
                        log_msg_notif_base = f"Alerta ID {alert_data['id']}: Precio {current_price}€"
                        if previous_last_price is None:
                            notification_triggered = True
                            logger.info(f"{log_msg_notif_base} alcanza objetivo (sin precio anterior).")
                        elif current_price < previous_last_price:
                            notification_triggered = True
                            logger.info(f"{log_msg_notif_base} bajó de {previous_last_price}€.")
                        elif current_price == previous_last_price:
                            notification_triggered = True
                            logger.info(
                                f"{log_msg_notif_base} sigue cumpliendo (igual que anterior), cooldown permite.")
                        else:
                            notification_triggered = True
                            logger.info(
                                f"{log_msg_notif_base} (subió de {previous_last_price}€) pero sigue en objetivo, cooldown permite.")

                    if notification_triggered:
                        alert_data_for_msg = dict(alert_data).copy()
                        alert_data_for_msg['last_price'] = previous_last_price

                        message_text, inline_keyboard, image_url = bot_ui.format_notification_content(
                            alert_data_for_msg, product_info)

                        try:
                            chat_id_to_notify = alert_data.get('telegram_chat_id')
                            if not chat_id_to_notify:
                                logger.error(f"No se puede enviar notificación para alerta ID {alert_data['id']} porque telegram_chat_id es None.")
                                continue # Saltar al siguiente ciclo de la alerta o manejar de otra forma

                            if image_url:
                                await bot.send_photo(
                                    chat_id=chat_id_to_notify,
                                    photo=image_url,
                                    caption=message_text,
                                    parse_mode=ParseMode.MARKDOWN,
                                    reply_markup=inline_keyboard
                                )
                            else:
                                await bot.send_message(
                                    chat_id=chat_id_to_notify,
                                    text=message_text,
                                    parse_mode=ParseMode.MARKDOWN,
                                    reply_markup=inline_keyboard
                                )

                            await db_queries.update_alert_last_notified(conn_update, str(alert_data['id']))
                            logger.info(
                                f"Notificación enviada a chat_id {chat_id_to_notify} por alerta ID {alert_data['id']}.")
                        except TelegramError as e:
                            # El chat_id_to_notify ya fue validado arriba, pero lo mantenemos en el log por consistencia
                            logger.error(
                                f"Error Telegram al enviar notificación a {chat_id_to_notify} (alerta {alert_data['id']}): {e}")
                            if chat_id_to_notify and ("bot was blocked by the user" in str(e).lower() or "chat not found" in str(e).lower()):
                                logger.warning(
                                    f"Bot bloqueado o chat no encontrado para {chat_id_to_notify}. Considerar eliminar/desactivar alertas.")
                        except Exception as e:
                            logger.error(
                                f"Error general al enviar notificación a {chat_id_to_notify if chat_id_to_notify else 'ID de chat desconocido'} (alerta {alert_data['id']}): {e}",
                                exc_info=True)
                    else:
                        logger.info(
                            f"Alerta ID {alert_data['id']}: Precio {current_price}€ (Obj:{target_price}€, Prev:{previous_last_price}€). No requiere notificación.")

        try:
            async with pool.acquire() as conn_cleanup:
                async with conn_cleanup.transaction():
                    await db_queries.cleanup_old_scraped_prices(conn_cleanup)
        except Exception as e:
            logger.error(f"[Checker] Error durante limpieza de caché: {e}", exc_info=True)

        logger.info(f"[Checker] Ciclo completado. Durmiendo por {config.CHECK_INTERVAL_SECONDS}s.")
        await asyncio.sleep(config.CHECK_INTERVAL_SECONDS)
