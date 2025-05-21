import os
import asyncio
import json
import logging
from urllib.parse import urlsplit, urlunsplit, parse_qs, urlencode
from datetime import datetime, timedelta

import psycopg2
from psycopg2.extras import RealDictCursor
import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

# Configuración inicial
load_dotenv()
logging.basicConfig(level=logging.INFO)

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

def fetch_or_cache_price(clean_url: str, full_url: str) -> tuple[float | None, str | None]:
    with conn.cursor() as cur:
        cur.execute("""
            SELECT price, scraped_at FROM scraped_prices
            WHERE clean_url = %s
            ORDER BY scraped_at DESC LIMIT 1
        """, (clean_url,))
        row = cur.fetchone()

        if row and datetime.utcnow() - row['scraped_at'] < timedelta(minutes=SCRAPE_TTL_MINUTES):
            logging.info(f"[CACHE] Using cached price for {clean_url}")
            return row['price'], None

    try:
        payload = {
            'api_key': SCRAPERAPI_KEY,
            'url': full_url,
            'max_cost': '1'
        }
        response = requests.get("https://api.scraperapi.com/", params=payload, timeout=60)
        soup = BeautifulSoup(response.text, "html.parser")

        scripts = soup.find_all("script", type="application/ld+json")
        for script in scripts:
            data = json.loads(script.string)
            if isinstance(data, dict) and "offers" in data:
                offer = data["offers"]
                if isinstance(offer, dict) and "price" in offer:
                    price = float(offer["price"])
                    availability = offer.get("availability", "").split("/")[-1]  # e.g. InStock
                    with conn.cursor() as cur:
                        cur.execute("""
                            INSERT INTO scraped_prices (clean_url, price, scraped_at)
                            VALUES (%s, %s, now())
                            ON CONFLICT (clean_url) DO UPDATE SET
                                price = EXCLUDED.price,
                                scraped_at = EXCLUDED.scraped_at
                        """, (clean_url, price))
                    return price, availability
    except Exception as e:
        logging.warning(f"[fetch_price] Error: {e}")
    return None, None

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
    current_price, availability = fetch_or_cache_price(cleaned, url)

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
    if availability:
        estado = "✅ En stock" if availability.lower() == "instock" else "❌ Sin stock"
        msg += f"\n📦 Disponibilidad: {estado}"

    await update.message.reply_text(msg)

async def list_alerts(update: Update, context: ContextTypes.DEFAULT_TYPE):
    with conn.cursor() as cur:
        cur.execute("SELECT * FROM alerts WHERE chat_id=%s ORDER BY inserted_at", (update.effective_chat.id,))
        rows = cur.fetchall()
        if not rows:
            await update.message.reply_text("📭 No tienes alertas activas.")
        else:
            text = "\n".join([f"{i+1}. {r['full_url']} ≤ {r['target_price']}€" for i, r in enumerate(rows)])
            await update.message.reply_text(f"📌 Alertas activas:\n{text}")

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

            current_price, _ = fetch_or_cache_price(alert['clean_url'], alert['full_url'])
            if current_price is None:
                logging.warning(f"❌ No se pudo obtener precio para {alert['full_url']}")
                continue

            if alert['last_price'] is not None and current_price == alert['last_price']:
                logging.info(f"🔁 Precio sin cambios: {current_price}€")
                continue

            with conn.cursor() as cur:
                cur.execute("UPDATE alerts SET last_price=%s, inserted_at=now() WHERE id=%s", (current_price, alert['id']))

            if current_price <= alert['target_price']:
                text = f"📉 ¡Bajada de precio!\n{current_price}€ ≤ {alert['target_price']}€\n{alert['full_url']}"
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

    asyncio.create_task(checker(app))
    print("🤖 Bot running...")
    await app.run_polling()

if __name__ == "__main__":
    import nest_asyncio
    nest_asyncio.apply()
    asyncio.run(main())
