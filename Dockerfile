# ============================================================
# Stage 1 — Build SPA Vue 3 (Vite)
# ============================================================
FROM node:24-alpine AS frontend-build
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

# Install MySQL client (untuk mysqldump) + cron (untuk auto-cleanup foto OT).
# apt-get upgrade -y: tarik fix keamanan paket OS dari base image (gerbang Trivy
# HIGH/CRITICAL di CI — A.8.8; gagal build bila ada CVE yg sudah punya fix).
RUN apt-get update && apt-get upgrade -y && apt-get install -y --no-install-recommends \
    default-mysql-client \
    cron \
    poppler-utils \
    tesseract-ocr \
    tesseract-ocr-ind \
    ffmpeg \
    ghostscript \
    qpdf \
    && rm -rf /var/lib/apt/lists/*
# v2.47.0: ghostscript + qpdf = mesin kompres PDF (modul PDF Kit, role IT).
# Ghostscript = lossy bertingkat (pdfwrite); qpdf = lossless struktural.
# poppler-utils (pdfinfo/pdfsig/pdftotext) dipakai untuk memeriksa sifat PDF
# & mendeteksi dokumen bertanda tangan sebelum dikompres.

# Setup cron: cleanup foto overtime > 6 bulan + retensi KTP FirstWork (v2.85.0,
# UU PDP: foto KTP dihapus 90 hari setelah keputusan verifikasi, tercatat audit)
COPY scripts/overtime-cleanup.sh /app/scripts/overtime-cleanup.sh
COPY scripts/first_work_ktp_retention.py /app/scripts/first_work_ktp_retention.py
RUN chmod +x /app/scripts/overtime-cleanup.sh && \
    echo '*/30 * * * * /bin/sh /app/scripts/overtime-cleanup.sh >> /var/log/overtime-cleanup.log 2>&1' > /etc/cron.d/overtime-cleanup && \
    echo '10 4 * * * python3 /app/scripts/first_work_ktp_retention.py >> /var/log/first-work-ktp-retention.log 2>&1' >> /etc/cron.d/overtime-cleanup && \
    chmod 0644 /etc/cron.d/overtime-cleanup && \
    crontab /etc/cron.d/overtime-cleanup && \
    touch /var/log/overtime-cleanup.log /var/log/first-work-ktp-retention.log

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt \
    && pip uninstall -y pip setuptools wheel jaraco.context 2>/dev/null || true
COPY . .
COPY static/ /app/static/

# Fonts untuk PDF generator (DejaVuSans)
COPY fonts/ /app/fonts/

# Data directory untuk news_scraper (wp_sites.json, logs, dll)
RUN mkdir -p /app/data/news_scraper

# Auto-scrape cron: scrape + upload tiap jam 6,10,14,18 WIB.
# v2.45.1: wrapper mengekspor PATH dgn /usr/local/bin — python3 image slim
# ada di sana, di luar PATH default cron (auto_scrape.log: 'python3: not found').
#
# v2.45.2: cron DIMATIKAN sementara (batch catch-up 278 artikel backdate
# di-rollback dari BPF Bandung). v2.45.3: DIAKTIFKAN KEMBALI dgn filter usia
# — auto_scrape.py hanya meng-upload artikel maksimal AUTO_SCRAPE_MAX_AGE_DAYS
# hari (default 1, bisa dioverride di baris cron) sehingga backlog lama tidak
# pernah diterjunkan ke site. Mode aman utk uji: --dry-run.
# Nonaktifkan lagi: komentari echo+crontab di bawah lalu rebuild.
RUN chmod +x /app/scripts/auto_scrape.sh /app/scripts/auto_scrape.py && \
    echo '0 6,10,14,18 * * * AUTO_SCRAPE_MAX_AGE_DAYS=1 /bin/bash /app/scripts/auto_scrape.sh >> /app/data/news_scraper/auto_scrape.log 2>&1' >> /etc/cron.d/overtime-cleanup && \
    crontab /etc/cron.d/overtime-cleanup && \
    touch /app/data/news_scraper/auto_scrape.log

# SPA bundle hasil build Vue (harus paling akhir agar tidak tertimpa COPY static/)
COPY --from=frontend-build /build/dist/ /app/static/app/

EXPOSE 5000

# Start cron + Flask app via Gunicorn (production WSGI server).
# - Worker gevent (v2.38.0): dibutuhkan flask-socketio async_mode=gevent;
#   eventlet deprecated & dihapus dari worker bawaan gunicorn 26.
# - -w 1: room SocketIO in-memory per-proses; gevent menangani konkurensi
#   via greenlet (bukan multi-proses), jadi 1 worker sudah benar.
# - --timeout 300: request berat (PDF/excel/upload/scraper) butuh waktu lama.
# - access log JSON sudah dicetak app (after_request) — gunicorn access log
#   dimatikan agar tidak dobel; error log tetap ke stdout (docker logs).
CMD service cron start && exec gunicorn --worker-class gevent -w 1 \
    --bind 0.0.0.0:5000 --timeout 300 --graceful-timeout 60 \
    --access-logfile /dev/null --error-logfile - --capture-output \
    app:app
