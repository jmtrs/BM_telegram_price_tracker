# Usar una imagen oficial de Python.
# Se recomienda usar la misma versión de Python que usas en desarrollo.
# Python 3.11-slim es una buena opción general.
FROM python:3.11-slim

# Establecer variables de entorno para evitar preguntas interactivas durante la instalación de paquetes
ENV PYTHONUNBUFFERED=1 \
    DEBIAN_FRONTEND=noninteractive

# Instalar dependencias del sistema necesarias para Playwright (Chromium) y otras comunes.
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    # Dependencias para Playwright Chromium
    libnss3 libnspr4 libatk1.0-0 libatk-bridge2.0-0 libcups2 libdrm2 libxkbcommon0 libxcomposite1 libxdamage1 libxfixes3 libxrandr2 libgbm1 libasound2 \
    # Otros paquetes que pueden ser útiles
    curl \
    git \
    # Limpiar la caché de apt para reducir el tamaño de la imagen
    && apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Establecer el directorio de trabajo en /app
WORKDIR /app

# Copiar el archivo de requisitos primero para aprovechar el almacenamiento en caché de capas de Docker
COPY requirements.txt .

# Instalar las dependencias de Python
# --no-cache-dir reduce el tamaño de la imagen
RUN pip install --no-cache-dir -r requirements.txt

# Instalar los navegadores de Playwright.
# --with-deps se asegura de que las dependencias del navegador a nivel de SO estén instaladas.
# Aquí solo instalamos chromium para mantener la imagen más ligera.
RUN playwright install --with-deps chromium

# Copiar el resto del código de la aplicación al directorio de trabajo
COPY . .

# Comando para ejecutar la aplicación.
# Este comando debe ser el que inicia tu aplicación principal (el bot de Telegram y cualquier API si está integrada).
# Coincide con el comando de tu Procfile si lo estabas usando.
CMD ["python", "main.py"]
