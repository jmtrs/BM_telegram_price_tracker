# tu_proyecto/bot/handlers.py
import logging
import asyncio
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
    chat_id = update.effective_chat.id
    if not context.args or len(context.args) != 2:
        await update.message.reply_text("❌ Uso: /track <URL> <precio_objetivo>")
        return
    url, price_str = context.args
    try:
        target_price = float(price_str)
        if target_price <= 0:
            await update.message.reply_text("❌ El precio objetivo debe ser un número positivo.")
            return
    except ValueError:
        await update.message.reply_text("❌ El precio objetivo debe ser un número.")
        return
    
    cleaned_url = scraper_utils.clean_url(url)
    if not cleaned_url:
        await update.message.reply_text("❌ URL inválida o no se pudo procesar.")
        return

    processing_message = await update.message.reply_text("⚙️ Procesando tu solicitud...")

    product_info = await scraper_core.get_product_info(url)
    product_name_for_db = product_info.get("name") if product_info.get("status") == "SCRAPED_SUCCESS" else None
    
    # Usar la función renombrada y la lógica de creación/actualización
    existing_alert = await asyncio.to_thread(db_queries.get_alert_by_chat_and_clean_url, chat_id, cleaned_url)
    response_key_part = ""

    if existing_alert:
        await asyncio.to_thread(db_queries.update_alert_target_price, str(existing_alert['id']), target_price, url)
        response_key_part = "🔁 Alerta actualizada."
    else:
        # Pasar product_name a create_alert si se quiere guardar en tabla alerts en el futuro
        await asyncio.to_thread(db_queries.create_alert, chat_id, url, cleaned_url, target_price, product_name_for_db)
        response_key_part = "✅ Alerta creada correctamente."

    # Formatear el mensaje de respuesta
    # format_product_info_message ahora devuelve (texto, teclado), pero para /track no necesitamos teclado aquí.
    message_text_body, _ = format_product_info_message(product_info, target_price)
    
    if product_info['status'] in ["CACHE_HIT", "SCRAPED_SUCCESS"]:
        full_response_message = f"{response_key_part}\n\n{message_text_body}"
    elif product_info['status'].startswith("SCRAPE_FAILED"):
        full_response_message = (f"{response_key_part}\n\n"
                                 f"⚠️ No se pudo obtener la información completa del producto (Estado: {product_info['status']}).\n"
                                 f"La alerta ha sido creada/actualizada con objetivo {target_price}€ para:\n🔗 {url}")
    else:
        full_response_message = (f"{response_key_part}\n\n"
                                 f"❓ Estado desconocido al obtener info del producto.\n"
                                 f"Alerta creada/actualizada con objetivo {target_price}€ para:\n🔗 {url}")

    # Intentar enviar con foto si está disponible y es un scrapeo exitoso
    image_url = product_info.get("image")
    sent_with_photo = False
    if image_url and image_url != "N/A (cache)" and product_info['status'] == "SCRAPED_SUCCESS":
        try:
            if processing_message: # Editar el mensaje "Procesando..." para que sea la foto
                 await context.bot.delete_message(chat_id=chat_id, message_id=processing_message.message_id)
                 # No se puede editar un mensaje de texto a foto, se envía uno nuevo.
            await context.bot.send_photo(
                chat_id=chat_id,
                photo=image_url,
                caption=full_response_message,
                parse_mode=ParseMode.MARKDOWN
            )
            sent_with_photo = True
        except TelegramError as e:
            logger.warning(f"No se pudo enviar foto para /track ({image_url}): {e}. Enviando solo texto.")
        except Exception as e_gen: # Captura otras excepciones por si acaso
            logger.error(f"Error inesperado al intentar enviar foto para /track: {e_gen}", exc_info=True)


    if not sent_with_photo: # Si no se envió foto (o falló)
        if processing_message:
            await context.bot.edit_message_text(
                chat_id=chat_id,
                message_id=processing_message.message_id,
                text=full_response_message,
                parse_mode=ParseMode.MARKDOWN
            )
        else:
            await update.message.reply_text(full_response_message, parse_mode=ParseMode.MARKDOWN)


async def list_alerts_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user_alerts = await asyncio.to_thread(db_queries.get_user_alerts, chat_id)
    message_text, reply_markup = format_alert_list_message(user_alerts)
    await update.message.reply_text(message_text, reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN)

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
        # Obtener nombre del producto para mensaje de confirmación (opcional)
        # alert_name = alerts_ordered[idx_to_delete].get('product_name', 'la alerta seleccionada')
        await update.message.reply_text(f"🗑️ Alerta eliminada.") # Podrías añadir `para {alert_name}`
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
        final_message = f"✅ Información actualizada para [{product_info.get('name', 'Producto')}]({alert_data['full_url']}):\n{feedback_msg_text}"
        
        # Re-enviar la lista de alertas actualizada
        user_alerts = await asyncio.to_thread(db_queries.get_user_alerts, chat_id)
        list_text, list_markup = format_alert_list_message(user_alerts)

        # Primero editar el mensaje de "actualizando" para quitarlo
        await query.edit_message_text(text=final_message, parse_mode=ParseMode.MARKDOWN, reply_markup=None)
        # Luego enviar la nueva lista (o editar el mensaje original de la lista si se pudiera identificar)
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
