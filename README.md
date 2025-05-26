# Telegram Price Tracker Bot & API 📈

This project provides a Telegram bot and a FastAPI backend to track product prices from URLs. It periodically scrapes product pages, checks if the current price is below a user-defined target, and notifies the user. The API supports user authentication via Logto.

## ✨ Features

- **Track Products**: Add products via URL and set a target price (Telegram Bot & API).
- **User Authentication**: Secure API endpoints using Logto (OIDC).
- **Web Interface (via API)**:
  - Sign in/Sign out.
  - Create, list, and delete price alerts.
- **Telegram Bot Interface**:
  - Commands to manage alerts (`/track`, `/alerts`, `/delete`).
- **Price Scraping**: Fetches current price, availability, name, image, etc., from product pages (primarily using JSON-LD).
- **Caching**: Scraped data is cached to reduce redundant requests and API usage.
- **Periodic Checks**: A background service (`checker_runner.py`) automatically checks prices at defined intervals.
- **Notifications**: Sends Telegram messages for price drops or when a target price is met.
- **URL Cleaning**: Cleans URLs to use a canonical version for tracking.
- **ScraperAPI Integration**: Uses ScraperAPI for robust web fetching.
- **Database**: PostgreSQL for storing user data, alerts, and scraped prices.

## 🛠️ Prerequisites

- Python 3.8+
- PostgreSQL database
- Telegram Bot Token
- ScraperAPI Key
- Logto Account and Application configured for OIDC.

## ⚙️ Setup

1.  **Clone the repository:**

    ```bash
    git clone <your-repo-url>
    cd <your-repo-directory>
    ```

2.  **Create and configure Logto Application:**

    - Sign up/in to [Logto](https://logto.io/).
    - Create a new "Traditional Web Application".
    - Note down the **Issuer Base URL** (e.g., `https://<your-tenant-id>.logto.app/oidc`).
    - Note down the **App ID** and **App Secret**.
    - Configure Redirect URIs (e.g., `http://localhost:8000/api/v1/auth/callback` for local development).
    - Configure Post Logout Redirect URIs (e.g., `http://localhost:8000/` for local development).
    - Under API Resources, ensure you have one defined (e.g., `http://localhost:8000/api`). This will be your `LOGTO_AUDIENCE`.

3.  **Create a `.env` file:**
    Copy `.env.example` to `.env` and fill in your credentials.

    ```env
    TELEGRAM_TOKEN="your_telegram_bot_token"
    SCRAPERAPI_KEY="your_scraperapi_key"
    DATABASE_URL="postgresql://user:password@host:port/database"

    # Logto OIDC variables (for API token validation)
    LOGTO_ISSUER="https://<your-logto-tenant-id>.logto.app/oidc"
    LOGTO_AUDIENCE="http://localhost:8000/api" # Or your production API audience
    LOGTO_JWKS_URI="https://<your-logto-tenant-id>.logto.app/oidc/jwks" # Automatically derived from issuer

    # Logto SDK variables (for web authentication flow, e.g., sign-in page)
    LOGTO_ENDPOINT="https://<your-logto-tenant-id>.logto.app/" # Note the trailing slash
    LOGTO_APP_ID="your_logto_app_id"
    LOGTO_APP_SECRET="your_logto_app_secret"

    # Session secret key for Logto SDK (and potentially other session management)
    SESSION_SECRET_KEY="generate_a_strong_random_secret_key_here" # e.g., openssl rand -hex 32

    # Optional: Scraper settings
    # SCRAPE_TTL_MINUTES=60
    # CHECK_INTERVAL_SECONDS=300
    # NOTIFICATION_COOLDOWN_MINUTES=1440
    ```

4.  **Install dependencies:**

    ```bash
    pip install -r requirements.txt
    ```

5.  **Database Setup:**
    Connect to your PostgreSQL database and execute the SQL commands from `tables.sql`. This will create the necessary tables (`users`, `alerts`, `scraped_prices`).

## 🏃‍♀️ Running Locally

Ensure your `.env` file is correctly set up.

1.  **Start the FastAPI application (includes API and Logto auth routes):**

    ```bash
    uvicorn main:app --reload --host 0.0.0.0 --port 8000
    ```

    - API docs will be available at `http://localhost:8000/docs` and `http://localhost:8000/redoc`.
    - Logto sign-in can be initiated at `http://localhost:8000/api/v1/auth/signin`.

2.  **Start the Telegram Bot (in a separate terminal):**

    ```bash
    python bot_runner.py
    ```

3.  **Start the Alerts Checker (in a separate terminal):**
    ```bash
    python checker_runner.py
    ```

## 🐳 Docker (TODO: Update Dockerfile and instructions if necessary)

Build the image:

```bash
docker build -t price-tracker .
```

Run the API (port 8000):

```bash
docker run --env-file .env -p 8000:8000 price-tracker uvicorn main:app --host 0.0.0.0 --port 8000
```

Run the Bot:

```bash
docker run --env-file .env price-tracker python bot_runner.py
```

Run the Checker:

```bash
docker run --env-file .env price-tracker python checker_runner.py
```

_Note: The `Procfile` is designed for platforms like Heroku/Railway and might need adjustments for a single Docker container running multiple processes, or you might run each process in its own container._

## ☁️ Deployment on Railway (Example)

1.  **Push your code to a GitHub repository.**
2.  **Create a new project on Railway and link it to your GitHub repository.**
3.  **Add a PostgreSQL service on Railway.** Railway will provide `DATABASE_URL`.
4.  **Configure Environment Variables in Railway:**
    - Add all variables from your `.env` file (especially `TELEGRAM_TOKEN`, `DATABASE_URL`, `SCRAPERAPI_KEY`, and all `LOGTO_*` variables, `SESSION_SECRET_KEY`).
    - **Important for Logto on Railway/Production:**
      - Update `LOGTO_AUDIENCE` to your production API URL.
      - Update Redirect URIs and Post Logout Redirect URIs in your Logto application settings to use your production URLs.
5.  **Define Start Commands (Procfile):**
    The existing `Procfile` defines three process types:
    ```text
    web: uvicorn main:app --host=0.0.0.0 --port=${PORT}
    bot: python bot_runner.py
    checker: python checker_runner.py
    ```
    Railway will use these to run your services.
6.  **Database Schema Migration:**
    Run the SQL from `tables.sql` on your Railway PostgreSQL database (e.g., via `psql` or a GUI client).

## ✅ Tests (TODO)

- Implement comprehensive unit and integration tests for:
  - API endpoints and authentication.
  - Telegram bot handlers and commands.
  - Alert creation, checking, and notification logic.
  - Database interactions.
  - Scraping logic (mocking external services).

To run existing tests (if any):

```bash
pytest tests/
```

## 🤖 Telegram Bot Commands

- `/start` & `/help` - Shows help message.
- `/track <URL> <precio>` - Adds/updates an alert. Example: `/track https://www.example.com/product123 49.99`
- `/alerts` - Lists active alerts with delete options.
- `/delete <número>` - Deletes an alert by its number from the `/alerts` list.

## 🌐 API Endpoints

Refer to the auto-generated documentation at `/docs` or `/redoc` when the API is running. Key endpoints include:

- `/api/v1/auth/signin` - Initiates Logto sign-in.
- `/api/v1/auth/callback` - Logto callback URL.
- `/api/v1/auth/signout` - Signs out the user.
- `/api/v1/auth/me` - (Protected) Gets current user info.
- `/api/v1/alerts` - (Protected) GET to list alerts, POST to create an alert.
- `/api/v1/alerts/{alert_id}` - (Protected) DELETE to remove an alert.

## 📄 Project Structure

(A brief overview of the main directories and their purpose)

- `adapters/`: Handles external interfaces (API, database repositories).
  - `api/`: FastAPI application, routes, authentication.
  - `repositories/`: Database interaction logic.
- `application_core/`: Core business logic and domain models.
  - `domain_models/`: Pydantic models for entities.
  - `ports/`: Abstract interfaces for repositories.
  - `use_cases/`: Application-specific business logic.
- `bot/`: Telegram bot handlers and UI formatting.
- `db/`: Database connection and query execution.
- `scraper/`: Web scraping utilities.
- `tasks/`: Background tasks (e.g., `checker.py`).
- `main.py`: Entry point for the FastAPI application.
- `bot_runner.py`: Entry point for the Telegram bot.
- `checker_runner.py`: Entry point for the alert checking service.
- `config.py`: Configuration loading from environment variables.
- `tables.sql`: SQL schema for the database.
- `.env.example`: Template for environment variables.
- `requirements.txt`: Python dependencies.
- `Procfile`: For PaaS deployments like Railway/Heroku.
