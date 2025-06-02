# bot/handlers.py
import logging
import asyncio
from urllib.parse import urlsplit
from telegram import Update, InputMediaPhoto, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from telegram.constants import ParseMode
from telegram.error import TelegramError
from uuid import UUID

from db import queries as db_queries
from scraper import core as scraper_core
from scraper import utils as scraper_utils
from .ui import (
    format_product_info_message,
    format_alert_list_message,
    HELP_MESSAGE_MARKDOWN
)

logger = logging.getLogger(__name__)

MAX_MESSAGE_LENGTH = 4096  # Límite de caracteres de Telegram por mensaje

async def _send_message_potentially_chunked(bot, chat_id: int, text_content: str, reply_markup: InlineKeyboardMarkup | None = None):
    """Envía un mensaje, dividiéndolo en fragmentos si excede la longitud máxima."""
    if len(text_content) <= MAX_MESSAGE_LENGTH:
        await bot.send_message(chat_id, text_content, reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN)
    else:
        lines = text_content.split('\n')
        chunks = []
        current_chunk = ""
        for line in lines:
            potential_length = len(current_chunk) + len(line) + (1 if current_chunk else 0)
            if potential_length > MAX_MESSAGE_LENGTH and current_chunk:
                chunks.append(current_chunk)
                current_chunk = line
            else:
                if current_chunk:
                    current_chunk += "\n" + line
                else:
                    current_chunk = line
        
        if current_chunk:
            chunks.append(current_chunk)

        for i, chunk in enumerate(chunks):
            is_last_chunk = (i == len(chunks) - 1)
            try:
                await bot.send_message(
                    chat_id,
                    chunk, 
                    reply_markup=reply_markup if is_last_chunk else None, 
                    parse_mode=ParseMode.MARKDOWN
                )
            except TelegramError as e:
                logger.error(f"Error al enviar chunk {i+1}/{len(chunks)} para chat {chat_id}: {e}")
                if i == 0:
                     await bot.send_message(chat_id, "❌ Error al mostrar las alertas: el mensaje es demasiado extenso y no se pudo dividir correctamente.")
                break 

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(HELP_MESSAGE_MARKDOWN, parse_mode=ParseMode.MARKDOWN)

async def track_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if not context.args or len(context.args) != 2:
        logger.warning(f"/track: Argumentos inválidos: {context.args}")
        await update.message.reply_text("❌ Uso: /track <URL o ID_Alerta> <precio_objetivo>")
        return
    
    first_arg, price_str = context.args

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

    # Intentar interpretar el primer argumento como UUID (ID de alerta)
    try:
        alert_uuid = UUID(first_arg)
        processing_message = await update.message.reply_text(f"⚙️ Actualizando alerta ID {str(alert_uuid)[:8]}...")
        
        updated_count = await asyncio.to_thread(
            db_queries.update_alert_target_price_by_id, 
            str(alert_uuid), 
            target_price,
            chat_id
        )

        if updated_count and updated_count > 0:
            await context.bot.edit_message_text(
                chat_id=chat_id,
                message_id=processing_message.message_id,
                text=f"✅ Alerta ID {str(alert_uuid)[:8]} actualizada. Nuevo precio objetivo: {target_price}€."
            )
            logger.info(f"/track: Alerta {alert_uuid} actualizada para chat {chat_id} con nuevo precio {target_price}")
        else:
            await context.bot.edit_message_text(
                chat_id=chat_id,
                message_id=processing_message.message_id,
                text=f"❌ No se encontró una alerta con ID {str(alert_uuid)[:8]} o no te pertenece."
            )
            logger.warning(f"/track: Intento de actualizar alerta inexistente o no perteneciente {alert_uuid} para chat {chat_id}")
        return
    except ValueError:
        # No es un UUID, asumimos que es una URL y continuamos con la lógica original
        logger.info(f"/track: El primer argumento no es un UUID, se tratará como URL: {first_arg}")
        url = first_arg
    
    cleaned_url = scraper_utils.clean_url(url)
    if not cleaned_url:
        logger.warning(f"/track: URL inválida o no se pudo procesar: {url}")
        await update.message.reply_text("❌ URL inválida o no se pudo procesar.")
        return

    # Validación del dominio de la URL (solo si no era un UUID)
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
    sort_by = context.user_data.get('alert_sort_preference', 'date_desc')
    
    user_alerts = await asyncio.to_thread(db_queries.get_user_alerts, chat_id, sort_by)
    message_text, reply_markup = format_alert_list_message(user_alerts, sort_by=sort_by)

    await _send_message_potentially_chunked(context.bot, chat_id, message_text, reply_markup)

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

    sort_by = context.user_data.get('alert_sort_preference', 'date_desc')
    alerts_ordered = await asyncio.to_thread(db_queries.get_user_alerts, chat_id, sort_by)

    if not (0 <= idx_to_delete < len(alerts_ordered)):
        await update.message.reply_text("❌ Número de alerta inválido.")
        return
    alert_id_to_delete = str(alerts_ordered[idx_to_delete]['id'])
    deleted = await asyncio.to_thread(db_queries.delete_alert_by_id, alert_id_to_delete, chat_id)
    if deleted:
        await update.message.reply_text("🗑️ Alerta eliminada.")
    else:
        await update.message.reply_text("⚠️ No se pudo eliminar.")


async def handle_refresh_alert(update: Update, context: ContextTypes.DEFAULT_TYPE, alert_id_str: str):
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
        
        sort_by = context.user_data.get('alert_sort_preference', 'date_desc')
        user_alerts = await asyncio.to_thread(db_queries.get_user_alerts, chat_id, sort_by)
        list_text, list_markup = format_alert_list_message(user_alerts, sort_by=sort_by)

        await query.edit_message_text(text=final_message, parse_mode=ParseMode.MARKDOWN, reply_markup=None)
        await context.bot.send_message(chat_id=chat_id, text=list_text, reply_markup=list_markup, parse_mode=ParseMode.MARKDOWN)

    else:
        await query.edit_message_text(f"⚠️ No se pudo actualizar el precio para la alerta. Estado: {product_info.get('status')}")


async def callback_query_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    action_data = query.data
    chat_id = query.message.chat_id
    message_id = query.message.message_id 

    new_sort_by = None
    if action_data == "sort_alerts_price_asc":
        new_sort_by = "price_asc"
        context.user_data['alert_sort_preference'] = new_sort_by
        logger.info(f"Callback: Usuario {chat_id} cambió ordenación a 'price_asc'")
    elif action_data == "sort_alerts_date_desc":
        new_sort_by = "date_desc"
        context.user_data['alert_sort_preference'] = new_sort_by
        logger.info(f"Callback: Usuario {chat_id} cambió ordenación a 'date_desc'")

    if new_sort_by:
        user_alerts = await asyncio.to_thread(db_queries.get_user_alerts, chat_id, new_sort_by)
        new_message_text, new_reply_markup = format_alert_list_message(user_alerts, sort_by=new_sort_by)

        if len(new_message_text) > MAX_MESSAGE_LENGTH:
            try:
                await query.delete_message()
            except TelegramError as e:
                logger.error(f"Error al eliminar mensaje original antes de reenviar lista reordenada: {e}")
            await _send_message_potentially_chunked(context.bot, chat_id, new_message_text, new_reply_markup)
        else:
            try:
                await query.edit_message_text(
                    text=new_message_text,
                    reply_markup=new_reply_markup,
                    parse_mode=ParseMode.MARKDOWN
                )
            except TelegramError as e:
                logger.error(f"Error al editar mensaje para cambio de ordenación: {e}")
                if "Message is not modified" in str(e).lower():
                    await query.answer("ℹ️ La lista ya está ordenada de esta manera.")
                elif "message_too_long" not in str(e).lower(): 
                    await query.answer("⚠️ Error al actualizar la lista.")
        return

    if action_data.startswith("delete_alert_"):
        try:
            alert_id_str = action_data.replace("delete_alert_", "")
        except Exception as e:
            logger.error(f"Error parseando alert_id desde callback '{action_data}': {e}")
            await query.edit_message_text(text="❌ Error: ID de alerta inválido.")
            return
        
        deleted = await asyncio.to_thread(db_queries.delete_alert_by_id, alert_id_str, chat_id)
        if deleted:
            await query.edit_message_text(text="🗑️ Alerta eliminada de tus notificaciones.")
            logger.info(f"Alerta {alert_id_str} eliminada para el chat {chat_id} mediante callback.")
        else:
            await query.edit_message_text(text="⚠️ No se pudo eliminar la alerta.")
            logger.warning(f"No se pudo eliminar la alerta {alert_id_str} para el chat {chat_id} mediante callback.")
        return
        
    if action_data.startswith("refresh_alert_"):
        alert_id_str = action_data.replace("refresh_alert_", "")
        await handle_refresh_alert(update, context, alert_id_str)
        return

    logger.warning(f"Callback no manejado recibido: {action_data} por usuario {chat_id}")
