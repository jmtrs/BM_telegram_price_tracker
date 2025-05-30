# bot/handlers.py
import logging
import asyncio
from urllib.parse import urlsplit # Añadir urlsplit
from telegram import Update, InputMediaPhoto
from telegram.ext import ContextTypes
from telegram.constants import ParseMode
from telegram.error import TelegramError

from db import queries as db_queries
from scraper import core as scraper_core
from scraper import utils as scraper_utils
from .ui import (
    format_product_info_message,
    format_alert_list_message,
    HELP_MESSAGE_MARKDOWN
)

logger = logging.getLogger(__name__)

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(HELP_MESSAGE_MARKDOWN, parse_mode=ParseMode.MARKDOWN)

async def track_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.info(f"Comando /track recibido con args: {context.args}")
    chat_id = update.effective_chat.id
    if not context.args or len(context.args) != 2:
        logger.warning(f"/track: Argumentos inválidos: {context.args}")
        await update.message.reply_text("❌ Uso: /track <URL> <precio_objetivo>")
        return
    url, price_str = context.args

    # Validación del dominio de la URL
    try:
        parsed_url = urlsplit(url)
        if parsed_url.netloc.lower() != "www.backmarket.es":
            logger.warning(f"/track: URL no pertenece a www.backmarket.es: {url}")
            await update.message.reply_text("❌ Solo se admiten URLs de www.backmarket.es")
            return
    except Exception as e:
        logger.warning(f"/track: Error al parsear la URL para validación de dominio: {url}, error: {e}")
        await update.message.reply_text("❌ URL inválida.")
        return

    try:
        target_price = float(price_str)
        if target_price <= 0:
            logger.warning(f"/track: Precio objetivo no positivo: {target_price}")
            await update.message.reply_text("❌ El precio objetivo debe ser un número positivo.")
            return
    except ValueError:
        logger.warning(f"/track: Precio objetivo no es un número: {price_str}")
        await update.message.reply_text("❌ El precio objetivo debe ser un número.")
        return
    
    cleaned_url = scraper_utils.clean_url(url)
    if not cleaned_url:
        logger.warning(f"/track: URL inválida o no se pudo procesar: {url}")
        await update.message.reply_text("❌ URL inválida o no se pudo procesar.")
        return

    processing_message = await update.message.reply_text("⚙️ Procesando tu solicitud...")

    try:
        product_info = await scraper_core.get_product_info(url)
        logger.info(f"/track: product_info obtenido: {product_info}")

        raw_status_check = product_info.get('status', 'UNKNOWN_STATUS')
        product_name_check = product_info.get('name')
        product_price_check = product_info.get('price')

        if raw_status_check.startswith("SCRAPE_FAILED"):
            await context.bot.edit_message_text(
                chat_id=chat_id,
                message_id=processing_message.message_id,
                text=f"❌ No se pudo obtener información del producto desde la URL proporcionada. La alerta no ha sido creada/actualizada."
            )
            return

    except Exception as e:
        logger.error(f"/track: Excepción al obtener product_info para {url}: {e}", exc_info=True)
        await context.bot.edit_message_text(
            chat_id=chat_id,
            message_id=processing_message.message_id,
            text="❌ Error crítico al obtener información del producto. Inténtalo de nuevo más tarde."
        )
        return
        
    product_name_for_db = product_info.get("name")
    
    base_response_text = "" 
    try:
        existing_alert = await asyncio.to_thread(db_queries.get_alert_by_chat_and_clean_url, chat_id, cleaned_url)

        if existing_alert:
            await asyncio.to_thread(db_queries.update_alert_target_price, str(existing_alert['id']), target_price, url)
            base_response_text = "🔁 Alerta actualizada."
            logger.info(f"/track: Alerta actualizada ID {existing_alert['id']} para chat {chat_id}")
        else:
            await asyncio.to_thread(db_queries.create_alert, chat_id, url, cleaned_url, target_price, product_name_for_db)
            base_response_text = "✅ Alerta creada correctamente."
            logger.info(f"/track: Nueva alerta creada para chat {chat_id}, URL: {cleaned_url}")
    except Exception as e:
        logger.error(f"/track: Excepción durante operaciones de base de datos: {e}", exc_info=True)
        await context.bot.edit_message_text(
            chat_id=chat_id,
            message_id=processing_message.message_id,
            text="❌ Error crítico al guardar la alerta en la base de datos."
        )
        return

    message_text_body, _ = format_product_info_message(product_info, target_price)
    
    raw_status = product_info.get('status', 'UNKNOWN_STATUS')
    
    status_display = raw_status 

    full_response_message = ""
    if raw_status == "CACHE_HIT" or raw_status.startswith("SCRAPED_SUCCESS"):
        full_response_message = f"{base_response_text}\n{message_text_body}"
    elif raw_status.startswith("SCRAPED_INCOMPLETE"):
        full_response_message = (f"{base_response_text}\n{message_text_body}\n"
                                 f"⚠️ _Algunos detalles del producto no pudieron ser obtenidos (Estado: {status_display})_")
    else:
        full_response_message = (f"{base_response_text}\n"
                                 f"❓ Estado del producto desconocido o inesperado (Estado: {status_display}).\n"
                                 f"Alerta creada/actualizada con objetivo {str(target_price)}€ para:\n🔗 {url}")

    image_url = product_info.get("image")
    sent_with_photo = False
    if image_url and image_url != "N/A (cache)" and \
       (raw_status == "CACHE_HIT" or
        raw_status.startswith("SCRAPED_SUCCESS") or
        raw_status.startswith("SCRAPED_INCOMPLETE")):
        try:
            if processing_message:
                 await context.bot.delete_message(chat_id=chat_id, message_id=processing_message.message_id)
                 processing_message = None
            
            await context.bot.send_photo(
                chat_id=chat_id,
                photo=image_url,
                caption=full_response_message,
                parse_mode=ParseMode.MARKDOWN
            )
            sent_with_photo = True
        except TelegramError as e:
            logger.warning(f"/track: No se pudo enviar foto para /track ({image_url}): {e}. Enviando solo texto.", exc_info=True)
        except Exception as e_gen:
            logger.error(f"/track: Error inesperado al intentar enviar foto para /track: {e_gen}", exc_info=True)
    else:
        logger.info(f"/track: No se intentará enviar foto. Image URL: {image_url}, Raw Status: {raw_status}")


    if not sent_with_photo:
        logger.info(f"/track: Enviando mensaje de solo texto.")
        try:
            if processing_message:
                await context.bot.edit_message_text(
                    chat_id=chat_id,
                    message_id=processing_message.message_id,
                    text=full_response_message,
                    parse_mode=ParseMode.MARKDOWN
                )
            else:
                await update.message.reply_text(full_response_message, parse_mode=ParseMode.MARKDOWN)
            logger.info(f"/track: Mensaje de texto enviado/editado exitosamente a chat {chat_id}")
        except TelegramError as e:
            logger.error(f"/track: TelegramError al enviar/editar mensaje de texto: {e}", exc_info=True)
            try:
                await update.message.reply_text("⚠️ Ocurrió un error al formatear la respuesta. Tu alerta ha sido procesada.")
            except Exception as e_fallback:
                logger.error(f"/track: Error en el mensaje de fallback: {e_fallback}", exc_info=True)
        except Exception as e_gen:
            logger.error(f"/track: Error inesperado al enviar/editar mensaje de texto: {e_gen}", exc_info=True)

async def list_alerts_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user_alerts = await asyncio.to_thread(db_queries.get_user_alerts, chat_id)
    message_text, reply_markup = format_alert_list_message(user_alerts)
    await update.message.reply_text(message_text, reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN) # Ya estaba en MARKDOWN, se mantiene

async def delete_alert_by_number_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if not context.args or len(context.args) != 1:
        await update.message.reply_text("❌ Uso: /delete <número de alerta>")
        return
    try:
        idx_to_delete = int(context.args[0]) - 1
    except ValueError:
        await update.message.reply_text("❌ El número debe ser un entero.")
        return
    alerts_ordered = await asyncio.to_thread(db_queries.get_user_alerts, chat_id)
    if not (0 <= idx_to_delete < len(alerts_ordered)):
        await update.message.reply_text("❌ Número de alerta inválido.")
        return
    alert_id_to_delete = str(alerts_ordered[idx_to_delete]['id'])
    deleted = await asyncio.to_thread(db_queries.delete_alert_by_id, alert_id_to_delete, chat_id)
    if deleted:
        await update.message.reply_text(f"🗑️ Alerta eliminada.")
    else:
        await update.message.reply_text("⚠️ No se pudo eliminar.")


async def handle_refresh_alert(update: Update, context: ContextTypes.DEFAULT_TYPE, alert_id_str: str):
    """Maneja la acción de refrescar una alerta específica."""
    query = update.callback_query
    chat_id = query.message.chat_id
    
    await query.edit_message_text(text=f"🔄 Actualizando información para alerta ID {alert_id_str[-6:]}...", reply_markup=None)

    alert_data = await asyncio.to_thread(db_queries.get_alert_by_id, alert_id_str)
    if not alert_data or alert_data['chat_id'] != chat_id:
        await query.edit_message_text("⚠️ Error: Alerta no encontrada o no te pertenece.")
        return

    product_info = await scraper_core.get_product_info(alert_data['full_url'])
    
    if product_info.get("price") is not None:
        await asyncio.to_thread(db_queries.update_alert_last_price, alert_id_str, product_info["price"])
        feedback_msg_text, _ = format_product_info_message(product_info, alert_data['target_price'])
        
        product_name_for_link = product_info.get('name', 'Producto')
        if not product_name_for_link or product_name_for_link == "N/A (cache)":
            product_name_for_link = "Producto"

        final_message = f"✅ Información actualizada para [{product_name_for_link}]({alert_data['full_url']}):\n{feedback_msg_text}"
        
        user_alerts = await asyncio.to_thread(db_queries.get_user_alerts, chat_id)
        list_text, list_markup = format_alert_list_message(user_alerts)

        await query.edit_message_text(text=final_message, parse_mode=ParseMode.MARKDOWN, reply_markup=None)
        await context.bot.send_message(chat_id=chat_id, text=list_text, reply_markup=list_markup, parse_mode=ParseMode.MARKDOWN)

    else:
        await query.edit_message_text(f"⚠️ No se pudo actualizar el precio para la alerta. Estado: {product_info.get('status')}")


async def callback_query_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    action_data = query.data
    chat_id = query.message.chat_id

    if action_data.startswith("delete_alert_"):
        try:
            alert_id_str = action_data.replace("delete_alert_", "")
        except Exception as e:
            logger.error(f"Error parseando alert_id desde callback '{action_data}': {e}")
            await query.edit_message_text(text="❌ Error: ID de alerta inválido.")
            return
        
        deleted = await asyncio.to_thread(db_queries.delete_alert_by_id, alert_id_str, chat_id)
        if deleted:
            await query.edit_message_text(text="🗑️ Alerta eliminada.")
            # Actualizar la lista de alertas después de eliminar
            user_alerts = await asyncio.to_thread(db_queries.get_user_alerts, chat_id)
            message_text, reply_markup = format_alert_list_message(user_alerts)
