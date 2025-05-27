# Dockerfile for Price Tracker (API, Bot, Checker)
FROM python:3.11-slim AS builder
WORKDIR /app

# Install build dependencies
RUN apt-get update \
    && apt-get install -y --no-install-recommends gcc libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
# Instalar dependencias en una ubicación que también incluya los scripts ejecutables
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
FROM python:3.11-slim AS runtime
WORKDIR /app

# Copiar los site-packages Y los ejecutables instalados
COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

COPY . .

ENV PYTHONUNBUFFERED=1
ENV PATH="/usr/local/bin:${PATH}"

# Default command: run API; override in Railway or Docker Compose for bot/checker
CMD uvicorn adapters.api.main:app --host=0.0.0.0 --port ${PORT:-8000}
