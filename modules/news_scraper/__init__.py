"""
modules/news_scraper/__init__.py

Flask Blueprint registration and shared configuration for the news scraper module.
"""

import json
import os
import threading
from datetime import datetime

from flask import Blueprint

# ---------------------------------------------------------------------------
# Blueprint
# ---------------------------------------------------------------------------

news_scraper_bp = Blueprint('news_scraper', __name__)

# ---------------------------------------------------------------------------
# Scraper roles
# ---------------------------------------------------------------------------

SCRAPER_ROLES = (
    'it_sby', 'it_hu', 'it_jkt2', 'it_bdg', 'it_smg',
    'it_mlg', 'it_mdn', 'it_bjm', 'it_plm', 'it_lpg', 'admin',
)

# ---------------------------------------------------------------------------
# Data file paths (persistent on server)
# ---------------------------------------------------------------------------

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 'data', 'news_scraper')
os.makedirs(DATA_DIR, exist_ok=True)

WP_SITES_FILE = os.path.join(DATA_DIR, 'wp_sites.json')
BACKLINKS_FILE = os.path.join(DATA_DIR, 'financial_backlinks.json')
HYPERLINKS_FILE = os.path.join(DATA_DIR, 'hyperlink_map.json')
SCRAPER_LOG_FILE = os.path.join(DATA_DIR, 'scraper_log.json')
UPLOAD_HISTORY_FILE = os.path.join(DATA_DIR, 'upload_history.json')
SETTINGS_FILE = os.path.join(DATA_DIR, 'scraper_settings.json')

# ---------------------------------------------------------------------------
# Financial Authority Backlinks (default dataset)
# ---------------------------------------------------------------------------

DEFAULT_AUTHORITY_SITES = {
    "Otoritas Jasa Keuangan (OJK)": "https://www.ojk.go.id/",
    "Bank Indonesia (BI)": "https://www.bi.go.id/",
    "Bursa Efek Indonesia (BEI)": "https://www.idx.co.id/",
    "International Monetary Fund (IMF)": "https://www.imf.org/",
    "World Bank": "https://www.worldbank.org/",
    "Bank for International Settlements (BIS)": "https://www.bis.org/",
    "Asian Development Bank (ADB)": "https://www.adb.org/",
    "Bloomberg": "https://www.bloomberg.com/",
    "Reuters Finance": "https://www.reuters.com/finance",
    "Financial Times": "https://www.ft.com/",
    "Wall Street Journal": "https://www.wsj.com/",
    "CNBC": "https://www.cnbc.com/",
    "Investing.com": "https://www.investing.com/",
    "Yahoo Finance": "https://finance.yahoo.com/",
    "Chicago Mercantile Exchange (CME)": "https://www.cmegroup.com/",
    "London Metal Exchange (LME)": "https://www.lme.com/",
    "Kontan": "https://www.kontan.co.id/",
    "Bisnis.com": "https://www.bisnis.com/",
    "Investor Daily": "https://www.investor.id/",
    "TradingView": "https://www.tradingview.com/",
    "Investopedia": "https://www.investopedia.com/",
    "Badan Pusat Statistik (BPS)": "https://www.bps.go.id/",
    "Kementerian Keuangan RI": "https://www.kemenkeu.go.id/",
}

DEFAULT_KEYWORD_MAPPING = {
    "OJK": "Otoritas Jasa Keuangan (OJK)",
    "Bank Indonesia": "Bank Indonesia (BI)",
    "BI": "Bank Indonesia (BI)",
    "BEI": "Bursa Efek Indonesia (BEI)",
    "Bursa Efek": "Bursa Efek Indonesia (BEI)",
    "IMF": "International Monetary Fund (IMF)",
    "World Bank": "World Bank",
    "Bank Dunia": "World Bank",
    "Bloomberg": "Bloomberg",
    "Reuters": "Reuters Finance",
    "TradingView": "TradingView",
    "Investopedia": "Investopedia",
    "BPS": "Badan Pusat Statistik (BPS)",
    "Kemenkeu": "Kementerian Keuangan RI",
    "emas": "London Metal Exchange (LME)",
    "inflasi": "Bank Indonesia (BI)",
    "suku bunga": "Bank Indonesia (BI)",
    "trading": "TradingView",
    "investasi": "Investopedia",
    "forex": "Investopedia",
    "komoditas": "Chicago Mercantile Exchange (CME)",
    "saham": "Bursa Efek Indonesia (BEI)",
    "minyak": "Chicago Mercantile Exchange (CME)",
}

MAX_LOG_ENTRIES = 500
_log_lock = threading.Lock()


# ---------------------------------------------------------------------------
# Logging helper
# ---------------------------------------------------------------------------

def _log_scraper(message: str, user: str = "system") -> None:
    """Append a timestamped entry to the scraper JSON log (keep last 500)."""
    entry = {
        "timestamp": datetime.now().isoformat(),
        "user": user,
        "message": message,
    }
    with _log_lock:
        try:
            with open(SCRAPER_LOG_FILE, 'r', encoding='utf-8') as f:
                logs = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            logs = []

        logs.append(entry)
        logs = logs[-MAX_LOG_ENTRIES:]

        with open(SCRAPER_LOG_FILE, 'w', encoding='utf-8') as f:
            json.dump(logs, f, indent=2, ensure_ascii=False)


# ---------------------------------------------------------------------------
# Route registration
# ---------------------------------------------------------------------------

def register_news_scraper_routes(app) -> None:
    """Register the news scraper blueprint and its routes with the Flask app."""
    from . import routes  # noqa: F401 (registers views on the blueprint)

    app.register_blueprint(news_scraper_bp)
    _log_scraper("News scraper blueprint registered.", user="system")
