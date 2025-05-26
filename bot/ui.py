# bot/ui.py
import logging
from telegram import InlineKeyboardButton, InlineKeyboardMarkup

logger = logging.getLogger(__name__)


def format_product_info_message(product_info: dict, target_price: float | None = None,
                                for_notification: bool = False) -> tuple[str, InlineKeyboardMarkup | None]:
    """Formatea un mensaje con la información del producto y botones opcionales para notificaciones."""
    msg_parts = []
    keyboard_buttons = []

    image_url = product_info.get("image")

    name = product_info.get("name", "Producto Desconocido")
    if name and name != "N/A (cache)":
        msg_parts.append(f"🏷️ *{name}*")

    if product_info.get("price") is not None:
        msg_parts.append(f"💲 Precio actual: {product_info['price']}€")
    else:
        msg_parts.append("⚠️ No se pudo obtener el precio actual.")

    if target_price is not None:
        msg_parts.append(f"🎯 Tu objetivo: ≤{target_price}€")

    for key, prefix in [
        ("brand_name", "🏢 Marca"), ("color", "🎨 Color"), ("storage", "💾 Almacenamiento"),
    ]:
        value = product_info.get(key)
        if value and value != "N/A (cache)":
            msg_parts.append(f"{prefix}: {value}")

    if product_info.get("availability") and product_info["availability"] != "N/A (cache)":
        status_text = "✅ En stock" if product_info["availability"].lower() == "instock" else "❌ Sin stock"
        msg_parts.append(f"📦 Disponibilidad: {status_text}")

    condition_value = product_info.get("condition") or product_info.get("product_condition")
    if condition_value and condition_value != "N/A (cache)":
        msg_parts.append(f"✨ Condición: {condition_value}")

    full_url = product_info.get("full_url", "")
    if full_url:
        msg_parts.append(f"\n🔗 [{name if name and name != 'N/A (cache)' else 'Ver en la web'}]({full_url})")

    # Botones para notificaciones
    if for_notification and full_url:
        alert_id = product_info.get("alert_id_for_button")  # Necesitaremos pasar el alert_id aquí
        if alert_id:
            keyboard_buttons.append(InlineKeyboardButton("🛒 Ver Oferta", url=full_url))
            keyboard_buttons.append(
                InlineKeyboardButton("🗑️ Eliminar Alerta", callback_data=f"delete_alert_{alert_id}"))

    reply_markup = InlineKeyboardMarkup([keyboard_buttons]) if keyboard_buttons else None
    return "\n".join(msg_parts), reply_markup


def format_alert_list_message(alerts: list[dict]) -> tuple[str, InlineKeyboardMarkup | None]:
    if not alerts:
        return "📭 No tienes alertas activas.", None

    main_text_parts = ["📌 Tus alertas activas (más recientes/actualizadas primero):"]
    keyboard_layout = []  # Lista de listas de botones

    for i, alert_data in enumerate(alerts):
        full_url = alert_data.get('full_url', '')
        alert_id_str = str(alert_data['id'])

        item_number = i + 1  # Número del ítem en la lista

        link_text = str(full_url)  # Convertir HttpUrl a cadena
        if len(link_text) > 40:
            link_text = link_text[:37] + "..."

        line = f"\n{i + 1}. "
        if full_url:
            line += f"[{link_text if link_text else 'Producto'}]({full_url})"
        else:
            line += "URL Desconocida"

        line += f"\n    🎯 Objetivo: ≤{alert_data['target_price']}€"
        if alert_data.get('last_price') is not None:
            line += f" (Último: {alert_data['last_price']}€)"
        else:
            line += f" (Aún no verificado)"

        main_text_parts.append(line)

        # Botones para cada alerta
        buttons_for_alert = [
            InlineKeyboardButton(f"🗑️ Eliminar {item_number}", callback_data=f"delete_alert_{alert_id_str}")
        ]
        keyboard_layout.append(buttons_for_alert)

    reply_markup = InlineKeyboardMarkup(keyboard_layout) if keyboard_layout else None
    return "\n".join(main_text_parts), reply_markup


# Esta función ahora devuelve texto y teclado, y asume que product_info tiene 'alert_id_for_button'
def format_notification_content(alert_data: dict, product_info: dict) -> tuple[
    str, InlineKeyboardMarkup | None, str | None]:
    """Prepara el contenido para una notificación: texto, teclado y URL de imagen."""
    product_info_for_msg = product_info.copy()
    product_info_for_msg["alert_id_for_button"] = str(alert_data.get("id"))

    price_info_text = f"{product_info.get('price', 'Precio Desconocido')}€"
    previous_last_price = alert_data.get('last_price')

    if previous_last_price is not None and product_info.get('price') is not None and product_info[
        'price'] < previous_last_price:
        price_info_text = f"de {previous_last_price}€ a {product_info['price']}€"

    # Usar la función genérica format_product_info_message
    # El título principal de la notificación
    title = f"📉 ¡Precio objetivo alcanzado/superado! {price_info_text}"

    # Formatear el cuerpo del mensaje usando la función existente
    # Pasamos for_notification=True para que genere los botones "Ver Oferta" y "Eliminar"
    message_body_text, inline_keyboard = format_product_info_message(
        product_info_for_msg,
        target_price=alert_data['target_price'],
        for_notification=True
    )

    full_message_text = f"{title}\n{message_body_text}"

    image_url_to_send = product_info.get("image")
    if image_url_to_send == "N/A (cache)":
        image_url_to_send = None

    return full_message_text, inline_keyboard, image_url_to_send


HELP_MESSAGE_MARKDOWN = (
    "🤖 *Comandos disponibles:*\n\n"
    "/track `<URL>` `<precio_objetivo>` – Añade o actualiza una alerta.\n"
    "/alerts – Lista tus alertas y permite eliminarlas.\n"
    "/delete `<número>` – Elimina una alerta por su número de la lista.\n"
    "/help – Muestra este mensaje."
)
