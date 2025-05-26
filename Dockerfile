# Dockerfile for Price Tracker (API, Bot, Checker)
FROM python:3.11-slim AS builder
WORKDIR /app

# Install build dependencies
RUN apt-get update \
    && apt-get install -y --no-install-recommends gcc libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
FROM python:3.11-slim AS runtime
WORKDIR /app
COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY . .

ENV PYTHONUNBUFFERED=1

# Default command: run API; override in Railway or Docker Compose for bot/checker
CMD ["uvicorn", "adapters.api.main:app", "--host=0.0.0.0", "--port", "${PORT:-8000}"]
