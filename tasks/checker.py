# tasks/checker.py
import asyncio
import logging
from datetime import datetime, timedelta

from telegram.ext import Application
from telegram.constants import ParseMode
from telegram.error import TelegramError

import config
from db import queries as db_queries
from scraper import core as scraper_core
from bot import ui as bot_ui

logger = logging.getLogger(__name__)

async def check_alerts_periodically(application: Application):
    bot = application.bot
    while True:
        logger.info(f"[Checker] Ejecutando ciclo a las {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        try:
            alerts_to_check = await asyncio.to_thread(db_queries.get_all_alerts)
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

            now_utc = datetime.utcnow()
            last_notified_utc = alert_data.get('last_notified')

            if last_notified_utc and now_utc - last_notified_utc < timedelta(hours=config.NOTIFY_COOLDOWN_HOURS):
                logger.info(f"Saltando alerta ID {alert_data['id']} (cooldown).")
                continue
            
            product_info = await scraper_core.get_product_info(alert_data['full_url'])
            current_price = product_info.get("price")

            if current_price is None:
                logger.warning(f"No se pudo obtener precio para alerta ID {alert_data['id']}. Estado: {product_info.get('status')}")
                await asyncio.to_thread(db_queries.update_alert_last_price, str(alert_data['id']), None) # Marcar que falló
                continue

            previous_last_price = alert_data.get('last_price')
            await asyncio.to_thread(db_queries.update_alert_last_price, str(alert_data['id']), current_price)
            
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
                    logger.info(f"{log_msg_notif_base} sigue cumpliendo (igual que anterior), cooldown permite.")
                else: 
                    notification_triggered = True
                    logger.info(f"{log_msg_notif_base} (subió de {previous_last_price}€) pero sigue en objetivo, cooldown permite.")
            
            if notification_triggered:
                alert_data_for_msg = alert_data.copy()
                alert_data_for_msg['last_price'] = previous_last_price 
                
                # Obtener texto, teclado y URL de imagen para la notificación
                message_text, inline_keyboard, image_url = bot_ui.format_notification_content(alert_data_for_msg, product_info)
                
                try:
                    if image_url: # Si hay URL de imagen, enviar como foto con caption
                        await bot.send_photo(
                            chat_id=alert_data['chat_id'],
                            photo=image_url,
                            caption=message_text,
                            parse_mode=ParseMode.MARKDOWN,
                            reply_markup=inline_keyboard
                        )
                    else: # Si no hay imagen, enviar como mensaje de texto
                        await bot.send_message(
                            chat_id=alert_data['chat_id'],
                            text=message_text,
                            parse_mode=ParseMode.MARKDOWN,
                            reply_markup=inline_keyboard
                        )
                    
                    await asyncio.to_thread(db_queries.update_alert_last_notified, str(alert_data['id']))
                    logger.info(f"Notificación enviada a chat_id {alert_data['chat_id']} por alerta ID {alert_data['id']}.")
                except TelegramError as e: # Capturar errores específicos de Telegram
                    logger.error(f"Error Telegram al enviar notificación a {alert_data['chat_id']} (alerta {alert_data['id']}): {e}")
                    if "bot was blocked by the user" in str(e).lower() or "chat not found" in str(e).lower():
                        logger.warning(f"Bot bloqueado o chat no encontrado para {alert_data['chat_id']}. Considerar eliminar/desactivar alertas.")
                        # Aquí podrías añadir lógica para eliminar/desactivar alertas para este chat_id
                except Exception as e: # Otros errores
                    logger.error(f"Error general al enviar notificación a {alert_data['chat_id']} (alerta {alert_data['id']}): {e}", exc_info=True)
            else:
                logger.info(f"Alerta ID {alert_data['id']}: Precio {current_price}€ (Obj:{target_price}€, Prev:{previous_last_price}€). No requiere notificación.")
        
        try:
            await asyncio.to_thread(db_queries.cleanup_old_scraped_prices)
        except Exception as e:
            logger.error(f"[Checker] Error durante limpieza de caché: {e}", exc_info=True)

        logger.info(f"[Checker] Ciclo completado. Durmiendo por {config.CHECK_INTERVAL_SECONDS}s.")
        await asyncio.sleep(config.CHECK_INTERVAL_SECONDS)
