# bot/ui.py
import logging
from telegram import InlineKeyboardButton, InlineKeyboardMarkup

logger = logging.getLogger(__name__)

def format_product_info_message(product_info: dict, target_price: float | None = None, for_notification: bool = False) -> tuple[str, InlineKeyboardMarkup | None]:
    """Formatea un mensaje con la información del producto y botones opcionales para notificaciones."""
    msg_parts = []
    keyboard_buttons = []
    
    name = product_info.get("name", "Producto Desconocido")
    if name and name != "N/A (cache)":
        msg_parts.append(f"🏷️ *{name}*")
    
    price_value = product_info.get("price")
    if price_value is not None:
        msg_parts.append(f"💲 Precio actual: {str(price_value)}€")
    else:
        msg_parts.append("⚠️ No se pudo obtener el precio actual.")

    if target_price is not None:
        msg_parts.append(f"🎯 Tu objetivo: ≤{str(target_price)}€")

    for key, prefix in [
        ("brand_name", "🏢 Marca"), ("color", "🎨 Color"), ("storage", "💾 Almacenamiento"),
    ]:
        value = product_info.get(key)
        if value and value != "N/A (cache)":
            msg_parts.append(f"{prefix}: {value}")

    availability_value = product_info.get("availability")
    if availability_value and availability_value != "N/A (cache)":
        status_text = "✅ En stock" if availability_value.lower() == "instock" else "❌ Sin stock"
        msg_parts.append(f"📦 Disponibilidad: {status_text}")
    
    condition_value = product_info.get("condition") or product_info.get("product_condition")
    if condition_value and condition_value != "N/A (cache)":
        msg_parts.append(f"✨ Condición: {condition_value}")
    
    full_url = product_info.get("full_url", "")
    if full_url:
         link_display_text = name if name and name != 'N/A (cache)' else 'Ver en la web'
         msg_parts.append(f"\n🔗 [{link_display_text}]({full_url})")

    if for_notification and full_url:
        alert_id = product_info.get("alert_id_for_button")
        if alert_id:
            keyboard_buttons.append(InlineKeyboardButton("🛒 Ver Oferta", url=full_url))
            keyboard_buttons.append(InlineKeyboardButton("🗑️ Eliminar Alerta", callback_data=f"delete_alert_{alert_id}"))
    
    reply_markup = InlineKeyboardMarkup([keyboard_buttons]) if keyboard_buttons else None
    return "\n".join(msg_parts), reply_markup


def format_alert_list_message(alerts: list[dict], sort_by: str = "date_desc") -> tuple[str, InlineKeyboardMarkup | None]:
    if not alerts:
        return "📭 No tienes alertas activas.", None

    sort_criteria_text = {
        "date_desc": "Más recientes primero",
        "price_asc": "Precio actual (ascendente)"
    }
    current_sort_text = sort_criteria_text.get(sort_by, "Desconocido")

    main_text_parts = [f"📌 Tus alertas activas (Orden: {current_sort_text}):"]

    for i, alert_data in enumerate(alerts):
        item_number = i + 1
        alert_id = alert_data.get("id")
        
        product_name = alert_data.get('product_name', 'Producto Desconocido')
        if not product_name or product_name == "N/A (cache)":
            product_name = "Producto (nombre no disponible)"

        line = f"\n{item_number}. *{product_name}*"
        if alert_id:
            line += f" (ID: `{alert_id}`)"


        product_condition = alert_data.get('product_condition')
        if product_condition and product_condition != "N/A (cache)":
            line += f"\n    ✨ Condición: {product_condition}"
            
        target_price_str = str(alert_data['target_price'])
        line += f"\n    🎯 Objetivo: ≤{target_price_str}€" 
        
        last_price_val = alert_data.get('last_price')
        if last_price_val is not None:
            last_price_str = str(last_price_val)
            line += f" (Último: {last_price_str}€)"
        else:
            line += " (Aún no verificado)"
        
        full_url = alert_data.get('full_url', '')
        if full_url:
            line += f"\n    🔗 [Ver producto]({full_url})"
        
        main_text_parts.append(line)
        
    # Botones de ordenación
    keyboard_layout = [
        [
            InlineKeyboardButton("Ordenar por Precio Actual (asc)", callback_data="sort_alerts_price_asc"),
            InlineKeyboardButton("Ordenar por Fecha (recientes)", callback_data="sort_alerts_date_desc")
        ]
    ]
    
    reply_markup = InlineKeyboardMarkup(keyboard_layout)
    return "\n".join(main_text_parts), reply_markup

def format_notification_content(alert_data: dict, product_info: dict) -> tuple[str, InlineKeyboardMarkup | None, str | None]:
    product_info_for_msg = product_info.copy()
    product_info_for_msg["alert_id_for_button"] = str(alert_data.get("id"))

    current_price_val = product_info.get('price')
    previous_last_price_val = alert_data.get('last_price')

    price_desc_for_title_raw = ""
    if current_price_val is not None:
        if previous_last_price_val is not None and current_price_val < previous_last_price_val:
            price_desc_for_title_raw = f"de {str(previous_last_price_val)}€ a {str(current_price_val)}€"
        else:
            price_desc_for_title_raw = f"{str(current_price_val)}€"
    else:
        price_desc_for_title_raw = "Precio Desconocido"
    
    title = f"📉 ¡Precio objetivo alcanzado/superado! {price_desc_for_title_raw}"
    
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


def format_recommendations_message(requests: list[dict], products_map: dict[str, list[dict]]) -> str:
    """
    Formatea un mensaje con las últimas peticiones de recomendaciones y sus productos.
    """
    if not requests:
        return "📭 No hay recomendaciones disponibles."

    lines = ["📣 *Recomendaciones recientes*\n"]
    for req in requests:
        req_id = req.get('recommendation_request_id')
        widget_id = req.get('widget_id')
        timestamp = req.get('requested_at')
        # Cabecera de cada lote
        lines.append(f"🔔 *{req_id}* (widget: {widget_id}) — {timestamp}")
        # Categoría legible (opcional)
        # lines.append(f"🗂 Categoría: {widget_id}")
        prods = products_map.get(str(req.get('id')), [])
        for p in prods:
            raw = p.get('raw_data', {})
            # Preferir nombre completo y enlace clicable
            name = raw.get('name') or raw.get('displayTitle') or p.get('title') or 'Sin título'
            link = raw.get('link', {}).get('href')
            if link:
                title_md = f"[{name}]({link})"
            else:
                title_md = name
            amount = p.get('price_amount')
            currency = p.get('price_currency') or ''
            # Línea principal con precio
            lines.append(f"  • {title_md} — {amount}{currency}")
            # Detalles adicionales cuando existan
            extras = []
            if raw.get('brand'):
                extras.append(raw['brand'])
            grade = raw.get('listing', {}).get('grade', {}).get('name')
            if grade:
                extras.append(grade)
            rating = raw.get('reviewRating', {}).get('average')
            if rating:
                extras.append(f"⭐{rating}")
            ref_price = raw.get('referencePrice', {}).get('amount')
            if ref_price:
                extras.append(f"ref: {ref_price}{currency}")
            if extras:
                lines.append(f"     ({' • '.join(extras)})")
        lines.append("")
    return "\n".join(lines)

HELP_MESSAGE_MARKDOWN = (
    "🤖 *Comandos disponibles:*\n\n"
    "/track `<URL>` `<precio_objetivo>` – Añade o actualiza una alerta.\n"
    "/alerts – Lista tus alertas y permite eliminarlas.\n"
    "/delete `<número>` – Elimina una alerta por su número de la lista.\n"
    "/recommendations `<n>` – Muestra las últimas n recomendaciones (por defecto 10).\n"
    "/help – Muestra este mensaje."
)
