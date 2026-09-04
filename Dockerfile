# ============================================================
# Stage 1 — Build SPA Vue 3 (Vite)
# ============================================================
FROM node:20-alpine AS frontend-build
WORKDIR /build
COPY frontend/package*.json ./
RUN npm install --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

# ============================================================
# Stage 2 — Python runtime (Flask + SocketIO)
# ============================================================
FROM python:3.11-slim
ENV TZ=Asia/Jakarta
RUN ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ > /etc/timezone

WORKDIR /app

# Install MySQL client (untuk mysqldump) + cron (untuk auto-cleanup foto OT)
RUN apt-get update && apt-get install -y --no-install-recommends \
    default-mysql-client \
    cron \
    && rm -rf /var/lib/apt/lists/*

# Setup cron: cleanup foto overtime > 6 bulan
COPY scripts/overtime-cleanup.sh /app/scripts/overtime-cleanup.sh
RUN chmod +x /app/scripts/overtime-cleanup.sh && \
    echo '*/30 * * * * /bin/sh /app/scripts/overtime-cleanup.sh >> /var/log/overtime-cleanup.log 2>&1' > /etc/cron.d/overtime-cleanup && \
    chmod 0644 /etc/cron.d/overtime-cleanup && \
    crontab /etc/cron.d/overtime-cleanup && \
    touch /var/log/overtime-cleanup.log

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
COPY static/ /app/static/

# Fonts untuk PDF generator (DejaVuSans)
COPY fonts/ /app/fonts/

# Data directory untuk news_scraper (wp_sites.json, logs, dll)
RUN mkdir -p /app/data/news_scraper

# Auto-scrape cron: scrape + upload tiap jam 6,10,14,18 WIB
RUN chmod +x /app/scripts/auto_scrape.sh && \
    echo '0 6,10,14,18 * * * /bin/sh /app/scripts/auto_scrape.sh >> /app/data/news_scraper/auto_scrape.log 2>&1' >> /etc/cron.d/overtime-cleanup && \
    crontab /etc/cron.d/overtime-cleanup && \
    touch /app/data/news_scraper/auto_scrape.log

# SPA bundle hasil build Vue (harus paling akhir agar tidak tertimpa COPY static/)
COPY --from=frontend-build /build/dist/ /app/static/app/

EXPOSE 5000

# Start cron + Flask app via Gunicorn (production WSGI server).
# - Worker eventlet: dibutuhkan flask-socketio async_mode=eventlet.
# - -w 1: room SocketIO in-memory per-proses; eventlet menangani konkurensi
#   via green thread (bukan multi-proses), jadi 1 worker sudah benar.
# - --timeout 300: request berat (PDF/excel/upload/scraper) butuh waktu lama.
# - access log JSON sudah dicetak app (after_request) — gunicorn access log
#   dimatikan agar tidak dobel; error log tetap ke stdout (docker logs).
CMD service cron start && exec gunicorn --worker-class eventlet -w 1 \
    --bind 0.0.0.0:5000 --timeout 300 --graceful-timeout 60 \
    --access-logfile /dev/null --error-logfile - --capture-output \
    app:app
