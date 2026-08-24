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

# Setup cron: cleanup foto overtime > 6 bulan, tiap 30 menit
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

# SPA bundle hasil build Vue (harus paling akhir agar tidak tertimpa COPY static/)
COPY --from=frontend-build /build/dist/ /app/static/app/

EXPOSE 5000

# Start cron + Flask app
# cron dijalankan di background, Flask di foreground
CMD service cron start && python3 -u app.py
