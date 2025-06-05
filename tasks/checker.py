# tasks/checker.py
import asyncio
import logging
from datetime import datetime, timedelta
import urllib.parse
import random

from telegram.ext import Application
from telegram.constants import ParseMode
from telegram.error import TelegramError

import config
from db.queries import cleanup_old_scraped_prices  # ya solo se limpia caché, no circuit breakers en BD
from db import queries as db_queries
from scraper import core as scraper_core
from bot import ui as bot_ui

logger = logging.getLogger(__name__)

async def check_alerts_periodically(application: Application, shutdown_event: asyncio.Event):
    bot = application.bot
    retry_attempt = 0  # Contador para intentos de reintento
    # Circuit breaker por URL en memoria
    url_failures: dict[str, datetime] = {}

    while not shutdown_event.is_set():
        # Podar circuit breakers expirados
        now = datetime.utcnow()
        for u, until in list(url_failures.items()):
            if until <= now:
                del url_failures[u]
        logger.info(f"[Checker] Ejecutando ciclo a las {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        try:
            alerts_to_check = await asyncio.to_thread(db_queries.get_all_alerts)
            retry_attempt = 0  # Reiniciar contador de reintentos si es exitoso
        except Exception as e:
            logger.error(f"[Checker] Error obteniendo alertas de BD: {e}", exc_info=True)
            retry_attempt += 1
            backoff_delay = min(config.CHECK_INTERVAL_SECONDS * (2 ** retry_attempt), 3600)  # Máximo 1 hora
            logger.info(f"[Checker] Reintentando en {backoff_delay} segundos.")
            await asyncio.sleep(backoff_delay)
            continue

        if not alerts_to_check:
            logger.info("[Checker] No hay alertas activas.")
        else:
            logger.info(f"[Checker] Verificando {len(alerts_to_check)} alerta(s).")

        batch_size = 10  # Tamaño del lote para procesar alertas
        for batch_start in range(0, len(alerts_to_check), batch_size):
            batch = alerts_to_check[batch_start:batch_start + batch_size]

            for i, alert_data in enumerate(batch):
                if i > 0: await asyncio.sleep(1)

                now_utc = datetime.utcnow()
                last_notified_utc = alert_data.get('last_notified')

                if last_notified_utc and now_utc - last_notified_utc < timedelta(hours=config.NOTIFY_COOLDOWN_HOURS):
                    logger.info(f"Saltando alerta ID {alert_data['id']} (cooldown).")
                    continue
                # Ubicar y unificar URL de alerta
                full_url = alert_data['full_url']
                # Verificar circuito por URL antes de fetch o cache
                if full_url in url_failures and datetime.utcnow() < url_failures[full_url]:
                    logger.warning(f"Circuit breaker activo para URL {full_url}, saltando alerta ID {alert_data['id']}")
                    continue

                # Scrape usando lógica interna de semáforos y timeout
                try:
                    product_info = await asyncio.wait_for(
                        scraper_core.get_product_info_with_retries(full_url),
                        timeout=config.SCRAPE_TTL_MINUTES * 60
                    )
                except asyncio.TimeoutError:
                    logger.error(f"[Checker] Timeout al scrapear {alert_data['full_url']} (> {config.SCRAPE_TTL_MINUTES} minutos).")
                    continue

                current_price = product_info.get("price")

                if current_price is None or product_info.get("status", "").startswith("SCRAPED_INCOMPLETE") or "ERR_TOO_MANY_REDIRECTS" in product_info.get("status", ""):
                    logger.warning(f"No se pudo obtener precio o datos incompletos para alerta ID {alert_data['id']}. Estado: {product_info.get('status')}")
                    if "ERR_TOO_MANY_REDIRECTS" in product_info.get("status", ""):
                        # Registrar circuito por URL en memoria
                        until_ts = datetime.utcnow() + timedelta(hours=config.CIRCUIT_BREAKER_HOURS)
                        url_failures[full_url] = until_ts
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
                    except Exception as e: # Otros errores
                        logger.error(f"Error general al enviar notificación a {alert_data['chat_id']} (alerta {alert_data['id']}): {e}", exc_info=True)
                else:
                    logger.info(f"Alerta ID {alert_data['id']}: Precio {current_price}€ (Obj:{target_price}€, Prev:{previous_last_price}€). No requiere notificación.")

        try:
            await asyncio.to_thread(db_queries.cleanup_old_scraped_prices)
        except Exception as e:
            logger.error(f"[Checker] Error durante limpieza de caché: {e}", exc_info=True)

        # Calcular tiempo de sueño: intervalo base + jitter
        jitter = random.uniform(0, config.JITTER_MAX_SECONDS)
        sleep_time = config.CHECK_INTERVAL_SECONDS + jitter
        logger.info(f"[Checker] Ciclo completado. Durmiendo {sleep_time:.2f}s (incluye {jitter:.2f}s de jitter) para el próximo ciclo.")
        await asyncio.sleep(sleep_time)
