# bot/handlers.py
import logging
from telegram import Update
from telegram.ext import ContextTypes
from telegram.constants import ParseMode
from telegram.error import TelegramError

from adapters.repositories.db_user_repository import DbUserRepository
from adapters.repositories.db_alert_repository import DbAlertRepository
from adapters.repositories.db_scraped_price_repository import DBScrapedPriceRepository
from application_core.ports.user_repository_port import UserRepositoryPort
from application_core.ports.alert_repository_port import AlertRepositoryPort
from application_core.domain_models.product_info_model import ProductInfo
from scraper import utils as scraper_utils
from scraper import core as scraper_core
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
    # Ensure User exists for this Telegram chat
    user_repo: UserRepositoryPort = DbUserRepository()
    user = await user_repo.get_by_telegram_id(chat_id)
    if not user:
        username = update.effective_user.username if update.effective_user else None
        user = await user_repo.add_user(telegram_chat_id=chat_id, idp_user_id=None, username=username, is_active=True)
    user_id = user.id

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

    product_info_dict = await scraper_core.get_product_info(url, use_api=True)
    
    # Construir el modelo de dominio ProductInfo
    domain_product_info = ProductInfo(
        name=product_info_dict.get("name"),
        price=product_info_dict.get("price"),
        product_condition=product_info_dict.get("condition"),
        image_url=product_info_dict.get("image"),
        description=product_info_dict.get("description"),
        availability=product_info_dict.get("availability"),
        color=product_info_dict.get("color"),
        storage=product_info_dict.get("storage"),
        brand_name=product_info_dict.get("brand_name"),
        clean_url=cleaned_url,
        full_url=url,
        status=product_info_dict.get("status", "UNKNOWN_SCRAPE_STATUS")
    )

    # Guardar en scraped_prices
    try:
        scraped_price_repo = DBScrapedPriceRepository()
        await scraped_price_repo.save_or_update_scraped_product(domain_product_info)
        logger.info(f"Successfully recorded scraped product info for {cleaned_url} in scraped_prices table via bot handler.")
    except Exception as e:
        logger.error(f"Failed to record scraped product info for {cleaned_url} in bot handler: {e}", exc_info=True)

    alert_repo: AlertRepositoryPort = DbAlertRepository()
    # Create or update alert atomically
    await alert_repo.upsert_alert(user_id=user_id, full_url=url, clean_url=cleaned_url, target_price=target_price)
    response_key_part = "✅ Alerta creada o actualizada correctamente."

    message_text_body, _ = format_product_info_message(product_info_dict, target_price)

    if product_info_dict['status'] in ["CACHE_HIT", "SCRAPED_SUCCESS"]:
        full_response_message = f"{response_key_part}\\n\\n{message_text_body}"
    elif product_info_dict['status'].startswith("SCRAPE_FAILED"):
        full_response_message = (f"{response_key_part}\\n\\n"
                                 f"⚠️ No se pudo obtener la información completa del producto (Estado: {product_info_dict['status']}).\\n"
                                 f"La alerta ha sido creada/actualizada con objetivo {target_price}€ para:\\n🔗 {url}")
    else:
        full_response_message = (f"{response_key_part}\\n\\n"
                                 f"❓ Estado desconocido al obtener info del producto.\\n"
                                 f"Alerta creada/actualizada con objetivo {target_price}€ para:\\n🔗 {url}")

    image_url = product_info_dict.get("image")
    sent_with_photo = False
    if image_url and image_url != "N/A (cache)" and product_info_dict['status'] == "SCRAPED_SUCCESS":
        try:
            if processing_message:
                await context.bot.delete_message(chat_id=chat_id, message_id=processing_message.message_id)
            await context.bot.send_photo(
                chat_id=chat_id,
                photo=image_url,
                caption=full_response_message,
                parse_mode=ParseMode.MARKDOWN
            )
            sent_with_photo = True
        except TelegramError as e:
            logger.warning(f"No se pudo enviar foto para /track ({image_url}): {e}. Enviando solo texto.")
        except Exception as e_gen:
            logger.error(f"Error inesperado al intentar enviar foto para /track: {e_gen}", exc_info=True)

    if not sent_with_photo:
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
    # Ensure user exists
    user_repo = DbUserRepository()
    user = await user_repo.get_by_telegram_id(chat_id)
    if not user:
        username = update.effective_user.username if update.effective_user else None
        user = await user_repo.add_user(telegram_chat_id=chat_id, idp_user_id=None, username=username, is_active=True)
    user_id = user.id
    # Fetch alerts for user
    alert_repo = DbAlertRepository()
    user_alerts_records = await alert_repo.get_alerts_by_user_id(user_id)
    user_alerts = [record.dict() for record in user_alerts_records]
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

    # Ensure user exists
    user_repo = DbUserRepository()
    user = await user_repo.get_by_telegram_id(chat_id)
    if not user:
        await update.message.reply_text("⚠️ Usuario no encontrado.")
        return
    user_id = user.id
    # Fetch and delete
    alert_repo = DbAlertRepository()
    alerts_ordered = await alert_repo.get_alerts_by_user_id(user_id)
    if not (0 <= idx_to_delete < len(alerts_ordered)):
        await update.message.reply_text("❌ Número de alerta inválido.")
        return
    alert_id_to_delete = alerts_ordered[idx_to_delete].id
    deleted = await alert_repo.delete_alert(alert_id_to_delete, user_id)

    if deleted:
        await update.message.reply_text("🗑️ Alerta eliminada.")
    else:
        await update.message.reply_text("⚠️ No se pudo eliminar.")


async def handle_refresh_alert(update: Update, context: ContextTypes.DEFAULT_TYPE, alert_id_str: str):
    query = update.callback_query
    chat_id = query.message.chat_id
    # Ensure user exists
    user_repo = DbUserRepository()
    user = await user_repo.get_by_telegram_id(chat_id)
    if not user:
        await query.edit_message_text("⚠️ Usuario no encontrado.")
        return
    user_id = user.id

    await query.edit_message_text(text=f"🔄 Actualizando información para alerta ID {alert_id_str[-6:]}...", reply_markup=None)

    # Load alert and verify ownership
    alert_repo = DbAlertRepository()
    alert_record = await alert_repo.get_by_id(alert_id_str)
    if not alert_record or alert_record.user_id != user_id:
        await query.edit_message_text("⚠️ Error: Alerta no encontrada o no te pertenece.")
        return
    alert_data = alert_record.dict()

    # Fetch latest product info
    product_info = await scraper_core.get_product_info(alert_data['full_url'], use_api=True)

    if product_info.get("price") is not None:
        # Update last price
        await alert_repo.update_last_price(alert_id_str, product_info["price"])
        feedback_msg_text, _ = format_product_info_message(product_info, alert_data['target_price'])
        final_message = f"✅ Información actualizada para [{product_info.get('name', 'Producto')}]({alert_data['full_url']}):\n{feedback_msg_text}"

        # Fetch updated alerts list
        user_alerts_records = await alert_repo.get_alerts_by_user_id(user_id)
        user_alerts = [record.dict() for record in user_alerts_records]
        list_text, list_markup = format_alert_list_message(user_alerts)

        # Reply updated info and list
        await query.edit_message_text(text=final_message, parse_mode=ParseMode.MARKDOWN, reply_markup=None)
        await context.bot.send_message(chat_id=chat_id, text=list_text, reply_markup=list_markup,
                                       parse_mode=ParseMode.MARKDOWN)
    else:
        await query.edit_message_text(
            f"⚠️ No se pudo actualizar el precio para la alerta. Estado: {product_info.get('status')}"
        )


async def callback_query_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    action_data = query.data
    chat_id = query.message.chat_id
    user_repo = DbUserRepository()
    user = await user_repo.get_by_telegram_id(chat_id)
    if not user:
        await query.edit_message_text("⚠️ Usuario no encontrado.")
        return
    user_id = user.id

    if action_data.startswith("delete_alert_"):
        try:
            alert_id_str = action_data.replace("delete_alert_", "")
        except Exception as e:
            logger.error(f"Error parseando alert_id desde callback '{action_data}': {e}")
            await query.edit_message_text(text="❌ Error: ID de alerta inválido.")
            return

        # Delete alert via repository
        alert_repo = DbAlertRepository()
        deleted = await alert_repo.delete_alert(alert_id_str, user_id)
        if deleted:
            await query.edit_message_text(text="🗑️ Alerta eliminada.")
            # Send updated list
            user_alerts_records = await alert_repo.get_alerts_by_user_id(user_id)
            user_alerts = [rec.dict() for rec in user_alerts_records]
            message_text, reply_markup = format_alert_list_message(user_alerts)
            await context.bot.send_message(chat_id=chat_id, text=message_text, reply_markup=reply_markup,
                                           parse_mode=ParseMode.MARKDOWN)
        else:
            await query.edit_message_text(
                text="❌ No se pudo eliminar la alerta (quizás ya fue eliminada o no te pertenece)."
            )

    elif action_data.startswith("refresh_alert_"):
        try:
            alert_id_str = action_data.replace("refresh_alert_", "")
            await handle_refresh_alert(update, context, alert_id_str)
        except Exception as e:
            logger.error(f"Error parseando alert_id para refrescar desde callback '{action_data}': {e}")
            await query.edit_message_text(text="❌ Error: ID de alerta inválido para refrescar.")
            return
