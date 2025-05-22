# tu_proyecto/bot/ui.py
import logging
from telegram import InlineKeyboardButton, InlineKeyboardMarkup

logger = logging.getLogger(__name__)

def format_product_info_message(product_info: dict, target_price: float | None = None) -> str:
    msg_parts = []
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
    if product_info.get("full_url"):
         msg_parts.append(f"\n🔗 {product_info['full_url']}")
    return "\n".join(msg_parts)

def format_alert_list_message(alerts: list[dict]) -> tuple[str, InlineKeyboardMarkup | None]:
    if not alerts:
        return "📭 No tienes alertas activas.", None

    keyboard_buttons = []
    text_parts = ["📌 Tus alertas activas (más recientes/actualizadas primero):"] # Usar una lista para construir el texto

    for i, alert_data in enumerate(alerts):
        full_url = alert_data.get('full_url', '') # Obtener la URL completa
        
        # Preparar el texto del enlace (URL truncada)
        link_text = full_url
        if len(link_text) > 45: # Un poco más corto para dejar espacio para [] y ()
            link_text = link_text[:42] + "..."
        
        # Escapar caracteres especiales de Markdown en el texto del enlace si es necesario
        # (para URLs truncadas simples, usualmente no es un gran problema, pero es buena práctica)
        # link_text_escaped = link_text.replace("[", "\\[").replace("]", "\\]")
        # Para este caso, como el link_text es una URL truncada, es poco probable que tenga '[' o ']'
        # que no sean parte de la propia URL, lo cual Telegram maneja bien dentro de [texto](enlace).

        line = f"\n{i+1}. "
        if full_url: # Solo crear enlace si hay URL
            # Crear el enlace Markdown: [texto_visible](URL_completa)
            line += f"[{link_text}]({full_url})"
        else:
            line += "URL Desconocida"
            
        line += f"\n    🎯 Objetivo: ≤{alert_data['target_price']}€"
        if alert_data.get('last_price') is not None:
            line += f" (Último: {alert_data['last_price']}€)"
        
        text_parts.append(line)
        
        alert_id_str = str(alert_data['id'])
        button = InlineKeyboardButton(f"🗑️ Eliminar {i+1}", callback_data=f"delete_alert_{alert_id_str}")
        keyboard_buttons.append([button])
    
    reply_markup = InlineKeyboardMarkup(keyboard_buttons) if keyboard_buttons else None
    return "\n".join(text_parts), reply_markup

def format_notification_message(alert_data: dict, product_info: dict) -> str:
    # (Esta función no muestra una lista de URLs, así que no necesita cambios para este issue)
    price_info_text = f"{product_info.get('price','Precio Desconocido')}€"
    previous_last_price = alert_data.get('last_price')

    if previous_last_price is not None and product_info.get('price') is not None and product_info['price'] < previous_last_price:
        price_info_text = f"de {previous_last_price}€ a {product_info['price']}€"
    
    message_parts = [
        f"📉 ¡Precio objetivo alcanzado/superado! {price_info_text}",
    ]
    # El nombre del producto, si está disponible, puede ser un buen candidato para ser el texto del enlace
    product_name = product_info.get("name")
    full_url = alert_data.get('full_url', '')

    if product_name and product_name != "N/A (cache)" and full_url:
        message_parts.append(f"🏷️ [{product_name}]({full_url})")
    elif full_url: # Si no hay nombre pero sí URL
         message_parts.append(f"🔗 {full_url}")


    message_parts.append(f"(Tu objetivo: ≤{alert_data['target_price']}€)")

    for key, prefix in [
        ("brand_name", "🏢 Marca"), ("color", "🎨 Color"), ("storage", "💾 Almacenamiento"),
    ]:
        value = product_info.get(key)
        if value and value != "N/A (cache)":
            message_parts.append(f"{prefix}: {value}")
    
    condition_value = product_info.get("condition") or product_info.get("product_condition")
    if condition_value and condition_value != "N/A (cache)":
        message_parts.append(f"✨ Condición: {condition_value}")
    
    return "\n".join(message_parts)

HELP_MESSAGE_MARKDOWN = (
    "🤖 *Comandos disponibles:*\n\n"
    "/track `<URL>` `<precio_objetivo>` – Añade o actualiza una alerta.\n"
    "/alerts – Lista tus alertas.\n"
    "/delete `<número>` – Elimina una alerta por su número de la lista.\n"
    "/help – Muestra este mensaje."
)
