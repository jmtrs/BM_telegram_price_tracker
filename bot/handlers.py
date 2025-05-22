# tu_proyecto/bot/handlers.py
import logging
import asyncio
from telegram import Update
from telegram.ext import ContextTypes
from telegram.constants import ParseMode

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
    existing_alert = await asyncio.to_thread(db_queries.get_alert, chat_id, cleaned_url)
    response_key_part = ""
    if existing_alert:
        await asyncio.to_thread(db_queries.update_alert, str(existing_alert['id']), target_price, url)
        response_key_part = "🔁 Alerta actualizada."
    else:
        await asyncio.to_thread(db_queries.create_alert, chat_id, url, cleaned_url, target_price)
        response_key_part = "✅ Alerta creada correctamente."
    if product_info['status'] in ["CACHE_HIT", "SCRAPED_SUCCESS"]:
        full_response = f"{response_key_part}\n\n{format_product_info_message(product_info, target_price)}"
    elif product_info['status'].startswith("SCRAPE_FAILED"):
        full_response = (f"{response_key_part}\n\n"
                         f"⚠️ No se pudo obtener información del producto (Estado: {product_info['status']}). "
                         f"Alerta creada/actualizada igualmente.")
    else:
        full_response = (f"{response_key_part}\n\n"
                         f"❓ Estado desconocido al obtener info del producto. Alerta creada/actualizada.")
    if processing_message:
        await context.bot.edit_message_text(chat_id=chat_id, message_id=processing_message.message_id,
                                            text=full_response, parse_mode=ParseMode.MARKDOWN)
    else:
        await update.message.reply_text(full_response, parse_mode=ParseMode.MARKDOWN)

async def list_alerts_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user_alerts = await asyncio.to_thread(db_queries.get_user_alerts, chat_id)
    message_text, reply_markup = format_alert_list_message(user_alerts)
    await update.message.reply_text(
        message_text,
        reply_markup=reply_markup,
        parse_mode=ParseMode.MARKDOWN
    )

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
        await update.message.reply_text("🗑️ Alerta eliminada.")
    else:
        await update.message.reply_text("⚠️ No se pudo eliminar.")

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
        else:
            await query.edit_message_text(text="⚠️ No se pudo eliminar.")
    else:
        logger.warning(f"Callback query no reconocido: {action_data}")
        await query.edit_message_text(text="❓ Acción no reconocida.")
