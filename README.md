# Telegram Price Tracker Bot 📈

This Telegram bot allows users to track product prices from URLs. It periodically scrapes the product pages, checks if the current price is below a user-defined target price, and notifies the user of price drops or when the target is met.

## ✨ Features

* **Track Products**: Add products via URL and set a target price.
* **Price Scraping**: Fetches current price, availability, and condition from product pages using JSON-LD data.
* **Caching**: Scraped data is cached to reduce redundant requests.
* **Periodic Checks**: Automatically checks prices at defined intervals.
* **Notifications**: Sends Telegram messages for price drops or when target price is met.
* **Alert Management**: List and delete active alerts.
* **URL Cleaning**: Cleans URLs to use a canonical version for tracking.
* **ScraperAPI Integration**: Uses ScraperAPI for robust fetching.

## 🛠️ Prerequisites

* Python 3.8+
* PostgreSQL database
* Telegram Bot Token
* ScraperAPI Key

## ⚙️ Setup

1.  **Clone the repository (if applicable):**
    ```bash
    git clone <your-repo-url>
    cd <your-repo-directory>
    ```

2.  **Create a `.env` file:**
    Copy the example below and fill in your credentials.
    ```env
    TELEGRAM_TOKEN=your_telegram_bot_token_here
    DATABASE_URL=postgresql://user:password@host:port/database
    SCRAPERAPI_KEY=your_scraperapi_key_here

    # Optional: Adjust these parameters if needed
    # CHECK_INTERVAL_SECONDS=14400  # 4 hours
    # NOTIFY_COOLDOWN_HOURS=4
    # SCRAPE_TTL_MINUTES=240 # 4 hours
    ```

3.  **Install dependencies:**
    ```bash
    pip install -r requirements.txt
    ```

4.  **Database Setup:**
    Connect to your PostgreSQL database and execute the SQL commands from the `tables.sql` file provided. This will create the `alerts` and `scraped_prices` tables.

## 🚀 Running the Bot

To start the bot, run the `main.py` script:

```bash
python main.py
```

You should see "🤖 Bot running..." in your console.

## ✅ Running Tests

The project includes unit tests for URL cleaning and product detail parsing. Make sure your test file (e.g., `main_test.py` as per your code) is in the same directory or accessible.

To run the tests:

```bash
pytest tests/
```

Ensure that scraper.html (if used by tests for specific scenarios) is present or that tests have appropriate fallbacks.

## 🤖 Bot Commands

* `/start` - Shows the help message.
* `/help` - Shows the help message with available commands.
* `/track <URL> <precio>` - Adds a new product to track or updates the target price for an existing one.
    * Example: `/track https://www.example.com/product123 49.99`
* `/alerts` - Lists all your active price alerts with an option to delete them via inline buttons.
* `/delete <número>` - Deletes an alert based on its number in the `/alerts` list.

## ☁️ Deployment on Railway (Example)

Railway is a good platform for deploying applications like this. Here's a general guide:

1.  **Push your code to a GitHub repository.**
2.  **Create a new project on Railway and link it to your GitHub repository.**
3.  **Add a PostgreSQL service on Railway.** Railway will provide you with a connection string (`DATABASE_URL`).
4.  **Configure Environment Variables:**
    * In your Railway project settings, add the following environment variables:
        * `TELEGRAM_TOKEN`: Your Telegram bot token.
        * `DATABASE_URL`: Your PostgreSQL connection string.
        * `SCRAPERAPI_KEY`: Your ScraperAPI key.
        * You can also add `CHECK_INTERVAL_SECONDS`, etc., if you modify the script to read them from the environment.
5.  **Define a Start Command (Procfile):**
    Create a `Procfile` in the root of your repository with the following line:
    ```
    worker: python main.py
    ```
    Railway should detect this, or you might need to set the start command in the service settings. Using `worker` is appropriate for a bot that runs continuously.
6.  **Database Schema Migration:**
    You'll need to run the SQL from `tables.sql` on your Railway PostgreSQL database. You can do this by connecting to the database using a tool like `psql` or any GUI client, using the credentials provided by Railway. Some frameworks offer migration tools; for this script, manual execution is straightforward.
7.  **Deploy:** Railway will typically auto-deploy when you push to your connected branch. Monitor the deployment logs for any errors.
