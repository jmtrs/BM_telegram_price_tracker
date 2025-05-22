import os
import asyncio
import json
import logging
import time # Added for retry delay
from urllib.parse import urlsplit, urlunsplit, parse_qs, urlencode
from datetime import datetime, timedelta

import psycopg2
from psycopg2.extras import RealDictCursor
import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes, CallbackQueryHandler

# Configuración inicial
load_dotenv()
logging.basicConfig(level=logging.INFO)
logging.getLogger("httpx").setLevel(logging.WARNING)

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
SUPABASE_PG_URI = os.getenv("SUPABASE_PG_URI")
SCRAPERAPI_KEY = os.getenv("SCRAPERAPI_KEY")

CHECK_INTERVAL_SECONDS = 14400  # 4h
NOTIFY_COOLDOWN_HOURS = 8
SCRAPE_TTL_MINUTES = 240  # 4h

conn = psycopg2.connect(SUPABASE_PG_URI, cursor_factory=RealDictCursor)
conn.autocommit = True

def clean_url(url: str) -> str:
    parts = urlsplit(url)
    query = parse_qs(parts.query)
    kept_query = {"l": query["l"]} if "l" in query else {}
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(kept_query, doseq=True), ''))

def fetch_or_cache_price(clean_url: str, full_url: str) -> tuple[float | None, str | None, str | None]:
    with conn.cursor() as cur:
        try:
            cur.execute("""
                SELECT price, scraped_at, product_condition FROM scraped_prices
                WHERE clean_url = %s
                ORDER BY scraped_at DESC LIMIT 1
            """, (clean_url,))
            row = cur.fetchone()

            if row and datetime.utcnow() - row['scraped_at'] < timedelta(minutes=SCRAPE_TTL_MINUTES):
                logging.info(f"[CACHE] Using cached price and condition for {clean_url}")
                return row['price'], "N/A", row.get('product_condition')
        except psycopg2.Error as e:
            logging.warning(f"[CACHE_READ_ERROR] Error reading product_condition: {e}. Assuming column might not exist.")
            # Fallback to old query if product_condition column doesn't exist
            cur.execute("""
                SELECT price, scraped_at FROM scraped_prices
                WHERE clean_url = %s
                ORDER BY scraped_at DESC LIMIT 1
            """, (clean_url,))
            row = cur.fetchone()
            if row and datetime.utcnow() - row['scraped_at'] < timedelta(minutes=SCRAPE_TTL_MINUTES):
                logging.info(f"[CACHE] Using cached price for {clean_url} (condition column likely missing).")
                return row['price'], "N/A", None

    # Scraping part
    max_retries = 2
    retry_delay_seconds = 5
    response_text = None

    for attempt in range(max_retries + 1):
        try:
            payload = {
                'api_key': SCRAPERAPI_KEY,
                'url': full_url,
                'max_cost': '1'
            }
            response = requests.get("https://api.scraperapi.com/", params=payload, timeout=60)
            response.raise_for_status() # Check for HTTP errors (4xx or 5xx)
            response_text = response.text
            logging.info(f"[fetch_price] Successfully fetched on attempt {attempt + 1} for {clean_url}")
            break # Success, exit retry loop
        except requests.exceptions.RequestException as e:
            logging.warning(f"[fetch_price] Attempt {attempt + 1}/{max_retries + 1} failed for {clean_url}: {e}")
            if attempt < max_retries:
                time.sleep(retry_delay_seconds)
            else:
                logging.error(f"[fetch_price] All attempts failed for {clean_url} after {max_retries + 1} tries.")
                return None, None, None # All retries failed

    if response_text is None:
        # This case should ideally be covered by the retry loop's return, but acts as a safeguard.
        logging.error(f"[fetch_price] response_text is None after retry loop for {clean_url}, this should not happen.")
        return None, None, None

    # Parsing part (if fetch was successful)
    price, availability, condition = _parse_product_details(response_text, full_url)

    if price is not None:
        # Database update/insert logic
        try:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO scraped_prices (clean_url, price, product_condition, scraped_at)
                    VALUES (%s, %s, %s, now())
                    ON CONFLICT (clean_url) DO UPDATE SET
                        price = EXCLUDED.price,
                        product_condition = EXCLUDED.product_condition,
                        scraped_at = EXCLUDED.scraped_at
                """, (clean_url, price, condition))
        except psycopg2.Error as db_error:
            logging.warning(f"[DB_WRITE_ERROR] Error writing product_condition for {clean_url}: {db_error}. Column might be missing. Proceeding without condition for this write.")
            # Fallback: try inserting/updating without product_condition
            with conn.cursor() as cur_fallback:
                 cur_fallback.execute("""
                    INSERT INTO scraped_prices (clean_url, price, scraped_at)
                    VALUES (%s, %s, now())
                    ON CONFLICT (clean_url) DO UPDATE SET
                        price = EXCLUDED.price,
                        scraped_at = EXCLUDED.scraped_at
                """, (clean_url, price))
        
        return price, availability, condition # SUCCESSFUL RETURN
    
    # If parsing failed (price is None)
    logging.info(f"[fetch_price] Parsing failed for {clean_url}, returning None for product details.")
    return None, None, None # Fallback if parsing fails

def _parse_product_details(html_content: str, url_for_logging: str) -> tuple[float | None, str | None, str | None]:
    """
    Parses HTML content to extract price, availability, and product condition using BeautifulSoup and JSON-LD.
    """
    try:
        soup = BeautifulSoup(html_content, "html.parser")
        scripts = soup.find_all("script", type="application/ld+json")
        for script in scripts:
            if script.string: # Ensure script.string is not None
                data = json.loads(script.string)
                if isinstance(data, dict) and "offers" in data:
                    offer = data["offers"]
                    if isinstance(offer, list): # Handle cases where offers is a list
                        if not offer: # Empty list
                            continue
                        offer = offer[0] # Take the first offer

                    if isinstance(offer, dict) and "price" in offer:
                        price = float(offer["price"])
                        availability = offer.get("availability", "").split("/")[-1]  # e.g. InStock
                        condition_text = None
                        if "itemCondition" in offer:
                            condition_url = offer["itemCondition"]
                            if isinstance(condition_url, str):
                                # E.g., "https://schema.org/NewCondition" -> "NewCondition"
                                condition_text = condition_url.split("/")[-1] 
                        
                        logging.info(f"[_parse_product_details] Successfully parsed product details for {url_for_logging}")
                        return price, availability, condition_text
        
        logging.info(f"[_parse_product_details] No offer found in JSON-LD for {url_for_logging} after parsing all script tags.")
    except json.JSONDecodeError as e:
        logging.warning(f"[_parse_product_details] JSONDecodeError while parsing content for {url_for_logging}: {e}")
    except Exception as e:
        # This catches other errors in parsing the response
        logging.warning(f"[_parse_product_details] Error processing content for {url_for_logging}: {e}")
    
    return None, None, None


async def track(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if len(context.args) != 2:
        await update.message.reply_text("❌ Uso: /track <URL> <precio>")
        return
    url, price_str = context.args
    try:
        price = float(price_str)
    except ValueError:
        await update.message.reply_text("❌ El precio debe ser un número.")
        return

    cleaned = clean_url(url)
    current_price, availability, current_condition = fetch_or_cache_price(cleaned, url)

    with conn.cursor() as cur:
        cur.execute("SELECT * FROM alerts WHERE chat_id=%s AND clean_url=%s", (update.effective_chat.id, cleaned))
        existing = cur.fetchone()
        if existing:
            cur.execute("UPDATE alerts SET target_price=%s, inserted_at=now() WHERE id=%s", (price, existing['id']))
            msg = "🔁 Alerta actualizada."
        else:
            cur.execute("""
                INSERT INTO alerts (chat_id, full_url, clean_url, target_price)
                VALUES (%s, %s, %s, %s)
            """, (update.effective_chat.id, url, cleaned, price))
            msg = "✅ Alerta creada correctamente."

    if current_price:
        msg += f"\n\n🔍 Precio actual: {current_price}€"
    if availability and availability != "N/A": # Don't show N/A for availability
        estado = "✅ En stock" if availability.lower() == "instock" else "❌ Sin stock"
        msg += f"\n📦 Disponibilidad: {estado}"
    if current_condition:
        msg += f"\n✨ Condición: {current_condition}"
    
    await update.message.reply_text(msg)

async def list_alerts(update: Update, context: ContextTypes.DEFAULT_TYPE):
    with conn.cursor() as cur:
        cur.execute("SELECT * FROM alerts WHERE chat_id=%s ORDER BY inserted_at", (update.effective_chat.id,))
        rows = cur.fetchall()
        if not rows:
            await update.message.reply_text("📭 No tienes alertas activas.")
        else:
            keyboard = []
            text = "📌 Alertas activas:\n"
            for i, r in enumerate(rows):
                text += f"{i+1}. {r['full_url']} ≤ {r['target_price']}€\n"
                button = InlineKeyboardButton(f"🗑️ Eliminar {i+1}", callback_data=f"delete_alert_{r['id']}")
                keyboard.append([button])
            reply_markup = InlineKeyboardMarkup(keyboard)
            await update.message.reply_text(text, reply_markup=reply_markup)

async def button_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()  # Acknowledge callback query

    if query.data.startswith("delete_alert_"):
        alert_id = query.data.split("_")[-1]
        chat_id = query.message.chat_id
        
        try:
            alert_id = int(alert_id) # Ensure alert_id is an integer
        except ValueError:
            logging.error(f"Invalid alert_id format: {alert_id}")
            await query.edit_message_text(text="❌ Error: ID de alerta inválido.")
            return

        with conn.cursor() as cur:
            # Verify the alert belongs to the user before deleting
            cur.execute("DELETE FROM alerts WHERE id=%s AND chat_id=%s RETURNING id", (alert_id, chat_id))
            deleted_row = cur.fetchone()
        
        if deleted_row:
            await query.edit_message_text(text="🗑️ Alerta eliminada.")
            # Optionally, re-list alerts or update the message more dynamically
            # For simplicity, we just confirm deletion.
            # To re-list, you could call a modified list_alerts or send a new message.
        else:
            # This case handles if the alert was already deleted or doesn't belong to the user.
            await query.edit_message_text(text="⚠️ No se pudo eliminar la alerta. Puede que ya haya sido eliminada o no te pertenezca.")


async def delete_alert(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("❌ Uso: /delete <número>")
        return
    try:
        idx = int(context.args[0]) - 1
    except ValueError:
        await update.message.reply_text("❌ Número inválido.")
        return

    with conn.cursor() as cur:
        cur.execute("SELECT id FROM alerts WHERE chat_id=%s ORDER BY inserted_at", (update.effective_chat.id,))
        rows = cur.fetchall()
        if idx < 0 or idx >= len(rows):
            await update.message.reply_text("❌ No hay ninguna alerta con ese número.")
            return
        alert_id = rows[idx]['id']
        cur.execute("DELETE FROM alerts WHERE id=%s", (alert_id,))
        await update.message.reply_text("🗑 Alerta eliminada.")

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🤖 *Comandos disponibles:*\n"
        "/track <URL> <precio> – Añade o actualiza una alerta\n"
        "/alerts – Lista tus alertas activas\n"
        "/delete <n> – Elimina una alerta por número\n"
        "/help – Muestra este mensaje",
        parse_mode="Markdown"
    )

async def checker(app):
    while True:
        logging.info(f"[Checker] Ejecutando a las {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM alerts")
            alerts = cur.fetchall()

        for i, alert in enumerate(alerts):
            await asyncio.sleep(i * 2)  # Escalonar consultas
            now = datetime.utcnow()
            last_notified = alert['last_notified']
            if last_notified and now - last_notified < timedelta(hours=NOTIFY_COOLDOWN_HOURS):
                logging.info(f"⏳ Saltando (cooldown): {alert['clean_url']}")
                continue

            current_price, _, current_condition = fetch_or_cache_price(alert['clean_url'], alert['full_url']) # Use _ for availability if not used
            if current_price is None:
                logging.warning(f"❌ No se pudo obtener precio para {alert['full_url']}")
                continue

            # The 'alert' dictionary holds the state from *before* the last_price update for this cycle.
            previous_last_price = alert['last_price'] 

            # Update last_price in the database for the current alert *before* notification decision
            with conn.cursor() as cur:
                cur.execute("UPDATE alerts SET last_price=%s, inserted_at=now() WHERE id=%s", (current_price, alert['id']))

            notification_triggered = False
            if current_price <= alert['target_price']:
                if previous_last_price is None: # First time seeing price below target
                    notification_triggered = True
                    logging.info(f"📉 Price {current_price}€ meets target (no prior last_price) for {alert['clean_url']}.")
                elif current_price < previous_last_price: # Actual price drop
                    notification_triggered = True
                    logging.info(f"📉 Price dropped from {previous_last_price}€ to {current_price}€ for {alert['clean_url']}.")
                else:
                    logging.info(f"📝 Price {current_price}€ for {alert['clean_url']} meets target {alert['target_price']}€, but not lower than last known price {previous_last_price}€.")
            else:
                logging.info(f"📝 Price {current_price}€ for {alert['clean_url']} is above target {alert['target_price']}€ (last: {previous_last_price}€).")

            if notification_triggered:
                price_info = f"{current_price}€"
                if previous_last_price is not None: # If there was a previous price, show the drop
                    price_info = f"de {previous_last_price}€ a {current_price}€"
                
                text = f"📉 ¡Bajada de precio! {price_info}\n{alert['full_url']}"
                text += f"\n(Objetivo: ≤{alert['target_price']}€)"

                if current_condition: # current_condition is from fetch_or_cache_price
                    text += f"\n✨ Condición: {current_condition}"
                
                try:
                    await app.bot.send_message(chat_id=alert['chat_id'], text=text)
                    with conn.cursor() as cur:
                        cur.execute("UPDATE alerts SET last_notified=now() WHERE id=%s", (alert['id'],))
                    logging.info(f"[✅] Alerta enviada a {alert['chat_id']}")
                except Exception as e:
                    logging.warning(f"[Telegram Error] {e}")

        # Limpieza de caché antigua (más de 2 días)
        with conn.cursor() as cur:
            cur.execute("DELETE FROM scraped_prices WHERE scraped_at < now() - interval '2 days'")
            logging.info("🧼 Limpieza de caché completada.")

        await asyncio.sleep(CHECK_INTERVAL_SECONDS)

async def main():
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", help_command))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("alerts", list_alerts))
    app.add_handler(CommandHandler("delete", delete_alert))
    app.add_handler(CommandHandler("track", track))
    app.add_handler(CallbackQueryHandler(button_callback_handler))

    asyncio.create_task(checker(app))
    print("🤖 Bot running...")
    await app.run_polling()

if __name__ == "__main__":
    import nest_asyncio
    nest_asyncio.apply()
    asyncio.run(main())
