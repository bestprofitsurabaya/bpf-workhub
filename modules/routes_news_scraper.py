"""
routes_news_scraper.py — News Scraper & Content Management API
v2.23 — Adapted from NewsScraper_V1.5.1.py desktop app for BPF WorkHub.

Features:
  - WordPress site management (CRUD, test connection)
  - Article scraping from newsmaker.id
  - Article upload to WordPress with SEO optimization
  - Financial authority backlinks management
  - Duplicate article checking
  - Hyperlink management
  - Activity log
"""

import os
import re
import json
import time
import base64
import random
from datetime import datetime
from collections import Counter
from concurrent.futures import ThreadPoolExecutor

import requests
try:
    from bs4 import BeautifulSoup
except ImportError:
    BeautifulSoup = None
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from flask import Blueprint, request, jsonify, session

from modules.helpers import role_required, log_activity_async

# ---------------------------------------------------------------------------
# Blueprint
# ---------------------------------------------------------------------------
news_scraper_bp = Blueprint('news_scraper', __name__)

# Data directory (persistent on server)
DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'data', 'news_scraper')
os.makedirs(DATA_DIR, exist_ok=True)

WP_SITES_FILE = os.path.join(DATA_DIR, 'wp_sites.json')
BACKLINKS_FILE = os.path.join(DATA_DIR, 'financial_backlinks.json')
HYPERLINKS_FILE = os.path.join(DATA_DIR, 'hyperlink_map.json')
SCRAPER_LOG_FILE = os.path.join(DATA_DIR, 'scraper_log.json')
UPLOAD_HISTORY_FILE = os.path.join(DATA_DIR, 'upload_history.json')

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

ANCHOR_TEXT_VARIATIONS = {
    "emas": ["Harga Emas", "Pasar Emas", "Komoditas Emas", "Investasi Emas"],
    "inflasi": ["Tingkat Inflasi", "Data Inflasi", "Kebijakan Inflasi"],
    "suku bunga": ["Suku Bunga BI", "Kebijakan Suku Bunga", "BI Rate"],
    "trading": ["Platform Trading", "Analisis Trading"],
    "investasi": ["Strategi Investasi", "Instrumen Investasi"],
    "forex": ["Pasar Forex", "Trading Valas"],
    "komoditas": ["Pasar Komoditas", "Commodity Trading"],
    "saham": ["Pasar Saham", "Bursa Efek"],
    "minyak": ["Harga Minyak", "Crude Oil"],
}

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
SCRAPER_ROLES = ('it_ef', 'admin')


def _load_json(path, default=None):
    if default is None:
        default = {}
    if os.path.exists(path):
        try:
            with open(path, 'r') as f:
                return json.load(f)
        except Exception:
            pass
    return default


def _save_json(path, data):
    with open(path, 'w') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def _log_scraper(message, user='system'):
    logs = _load_json(SCRAPER_LOG_FILE, [])
    logs.append({
        'timestamp': datetime.now().isoformat(),
        'message': message,
        'user': user,
    })
    # Keep last 500 entries
    if len(logs) > 500:
        logs = logs[-500:]
    _save_json(SCRAPER_LOG_FILE, logs)


# ---------------------------------------------------------------------------
# Upload History
# ---------------------------------------------------------------------------
def _save_upload_history(entry):
    """Save upload/scrape history entry."""
    history = _load_json(UPLOAD_HISTORY_FILE, [])
    history.append(entry)
    # Keep last 1000 entries
    if len(history) > 1000:
        history = history[-1000:]
    _save_json(UPLOAD_HISTORY_FILE, history)


def _get_upload_history(date_from=None, date_to=None, action=None):
    """Get filtered upload history."""
    history = _load_json(UPLOAD_HISTORY_FILE, [])
    if date_from:
        history = [h for h in history if h.get('date', '') >= date_from]
    if date_to:
        history = [h for h in history if h.get('date', '') <= date_to]
    if action:
        history = [h for h in history if h.get('action') == action]
    return history


# ---------------------------------------------------------------------------
# SSE Progress Tracker
# ---------------------------------------------------------------------------
import threading
_progress_store = {}
_progress_lock = threading.Lock()


def _set_progress(task_id, data):
    with _progress_lock:
        _progress_store[task_id] = data


def _get_progress(task_id):
    with _progress_lock:
        return _progress_store.get(task_id, {})


def _clear_progress(task_id):
    with _progress_lock:
        _progress_store.pop(task_id, None)


def check_bs4():
    if BeautifulSoup is None:
        raise RuntimeError('beautifulsoup4 belum terinstall. Jalankan: pip install beautifulsoup4')


# Default server-level Basic Auth (shared hosting protection)
_WP_SERVER_AUTH = ('human', 'password')


def _get_wp_session():
    """Create requests session with retry strategy."""
    session = requests.Session()
    retry = Retry(total=3, backoff_factor=1, status_forcelist=[500, 502, 503, 504])
    adapter = HTTPAdapter(max_retries=retry, pool_connections=10, pool_maxsize=10)
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    return session


def _wp_auth_headers(username, app_password):
    creds = f"{username}:{app_password}"
    token = base64.b64encode(creds.encode()).decode('utf-8')
    return {'Authorization': f'Basic {token}', 'User-Agent': 'BPFWorkHub-Scraper/2.0'}


def _wp_login(session, wp_url, username, password):
    """Login ke WordPress via wp-login.php dengan dual auth:
    1. Basic Auth server (human:password) untuk bypass hosting protection
    2. WordPress credentials untuk session login
    Returns: (success, nonce_or_error)
    """
    try:
        base_url = wp_url.split('/wp-json')[0]
        login_url = f'{base_url}/wp-login.php'
        admin_url = f'{base_url}/wp-admin/'

        # Step 1: Set server Basic Auth
        session.auth = _WP_SERVER_AUTH
        session.headers.update({'User-Agent': 'BPFWorkHub-Scraper/2.0'})

        # Step 2: GET login page
        session.get(login_url, timeout=10)

        # Step 3: POST WordPress login
        r = session.post(login_url, data={
            'log': username, 'pwd': password,
            'wp-submit': 'Log In', 'redirect_to': '/wp-admin/', 'testcookie': '1',
        }, timeout=10)

        # Cookie name ada suffix hash (wordpress_logged_in_xxxxx)
        has_cookie = any(c.name.startswith('wordpress_logged_in') for c in session.cookies)
        if not has_cookie:
            return False, 'Login WordPress gagal — periksa username & password'

        # Step 4: Ambil WP REST nonce dari admin page
        r2 = session.get(admin_url, timeout=10)
        import re
        m = re.search(r'wpApiSettings.*?"nonce":"([a-f0-9]+)"', r2.text)
        nonce = m.group(1) if m else None

        # Step 5: Hapus Basic Auth (REST API pakai cookie, bukan Basic Auth)
        session.auth = None

        return True, nonce
    except Exception as e:
        session.auth = None
        return False, str(e)


def _wp_request(session, method, url, nonce=None, **kwargs):
    """Helper untuk REST API request dengan cookie + nonce."""
    headers = kwargs.pop('headers', {})
    if nonce:
        headers['X-WP-Nonce'] = nonce
    headers.setdefault('User-Agent', 'BPFWorkHub-Scraper/2.0')
    return session.request(method, url, headers=headers, **kwargs)


def _upload_image_to_wp(session, wp_url, nonce, image_url):
    """Download image from source and upload to WordPress media library.
    Returns: {'id': media_id, 'html': '<img ...>'} or None on failure.
    """
    try:
        # Download image from source
        r = session.get(image_url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=15, stream=True)
        if r.status_code != 200:
            return None

        content_type = r.headers.get('Content-Type', 'image/jpeg')
        if 'png' in image_url.lower():
            ext = 'png'
        elif 'gif' in image_url.lower():
            ext = 'gif'
        elif 'webp' in image_url.lower():
            ext = 'webp'
        else:
            ext = 'jpg'

        # Generate filename
        slug = re.sub(r'[^a-z0-9]', '-', image_url.split('/')[-1].lower())[:50]
        if not slug or slug == '-':
            slug = f"article-{int(time.time())}"
        filename = f"{slug}.{ext}"

        # Upload to WordPress media library
        media_url = wp_url.replace('/posts', '/media')
        headers = {
            'X-WP-Nonce': nonce,
            'Content-Disposition': f'attachment; filename="{filename}"',
            'Content-Type': content_type,
            'User-Agent': 'BPFWorkHub-Scraper/2.0',
        }
        # Remove Basic Auth for REST API
        session.auth = None
        r2 = session.post(media_url, data=r.content, headers=headers, timeout=30)
        session.auth = None  # Ensure stays clean

        if r2.status_code in (200, 201):
            media = r2.json()
            media_id = media.get('id', 0)
            # source_url = direct file URL, link = attachment page URL
            media_link = media.get('source_url', '') or media.get('link', '')
            return {
                'id': media_id,
                'html': f'<figure class="wp-block-image"><img src="{media_link}" alt="" class="wp-image-{media_id}" /></figure>\n',
                'link': media_link,
            }
    except Exception:
        pass
    return None


def _get_anchor_text(keyword):
    kw = keyword.lower()
    for base, variations in ANCHOR_TEXT_VARIATIONS.items():
        if base in kw:
            return random.choice(variations)
    return keyword


def _apply_backlinks(content, title, authority_sites, keyword_mapping, max_backlinks=3):
    """Add financial authority backlinks to content."""
    used = []
    combined = (title + " " + content).lower()
    matched = [(kw, site) for kw, site in keyword_mapping.items() if kw.lower() in combined]
    random.shuffle(matched)
    matched = matched[:max_backlinks]
    for kw, site_name in matched:
        if site_name in authority_sites:
            url = authority_sites[site_name]
            anchor = _get_anchor_text(kw)
            pattern = r'\b' + re.escape(kw) + r'\b(?![^<]*>)'
            replacement = f'<a href="{url}" target="_blank" rel="nofollow">{anchor}</a>'
            content = re.sub(pattern, replacement, content, count=1, flags=re.IGNORECASE)
            used.append(f"{anchor} → {site_name}")
    return content, used


def _seo_analyze(content, title):
    """Simple SEO analysis."""
    text = re.sub(r'<[^>]+>', '', content)
    word_count = len(text.split())
    h2 = len(re.findall(r'<h2', content, re.IGNORECASE))
    h3 = len(re.findall(r'<h3', content, re.IGNORECASE))
    headings = h2 + h3
    links = len(re.findall(r'<a href', content, re.IGNORECASE))
    images = len(re.findall(r'<img', content, re.IGNORECASE))
    link_density = links / max(word_count, 1)

    score = 0
    score += 40 if word_count >= 800 else (30 if word_count >= 500 else (20 if word_count >= 300 else 10))
    score += 20 if headings >= 3 else (15 if headings >= 2 else (10 if headings >= 1 else 5))
    score += 20 if link_density <= 0.15 else (15 if link_density <= 0.25 else 5)
    score += 20 if images >= 1 else 10

    recs = []
    if word_count < 800:
        recs.append(f"Tambah konten ({word_count}/800 kata)")
    if headings < 3:
        recs.append(f"Tambah heading H2/H3 ({headings}/3)")
    if link_density > 0.15:
        recs.append(f"Kurangi link ({link_density*100:.1f}%)")
    if images < 1:
        recs.append("Tambah gambar relevan")

    return {
        'word_count': word_count, 'headings': headings,
        'link_density': round(link_density, 3), 'images': images,
        'seo_score': score, 'recommendations': recs,
    }


# ===================================================================
# ROUTES
# ===================================================================

@news_scraper_bp.route('/api/scraper/sites', methods=['GET'])
@role_required(SCRAPER_ROLES)
def list_wp_sites():
    """List all WordPress sites."""
    sites = _load_json(WP_SITES_FILE, {})
    result = []
    for name, data in sites.items():
        result.append({
            'name': name,
            'wp_url': data.get('wp_url', ''),
            'wp_media_url': data.get('wp_media_url', ''),
            'username': data.get('username', ''),
            # Never expose app_password in list
        })
    return jsonify(result)


@news_scraper_bp.route('/api/scraper/sites', methods=['POST'])
@role_required(SCRAPER_ROLES)
def save_wp_site():
    """Add or update a WordPress site."""
    d = request.get_json(force=True)
    name = (d.get('name') or '').strip()
    wp_url = (d.get('wp_url') or '').strip()
    username = (d.get('username') or '').strip()
    app_password = (d.get('app_password') or '').strip()

    if not all([name, wp_url, username]):
        return jsonify({'error': 'name, wp_url, username wajib diisi'}), 400
    if not wp_url.startswith('http'):
        return jsonify({'error': 'wp_url harus diawali http:// atau https://'}), 400

    wp_media_url = (d.get('wp_media_url') or '').strip()
    if not wp_media_url:
        wp_media_url = wp_url.replace('/posts', '/media')

    sites = _load_json(WP_SITES_FILE, {})
    old = sites.get(name)
    if old and not app_password:
        app_password = old.get('app_password', '')

    sites[name] = {
        'wp_url': wp_url,
        'wp_media_url': wp_media_url,
        'username': username,
        'app_password': app_password,
    }
    _save_json(WP_SITES_FILE, sites)
    _log_scraper(f"WordPress site saved: {name}", session.get('user_name', 'unknown'))
    return jsonify({'ok': True, 'message': f'Site "{name}" berhasil disimpan'})


@news_scraper_bp.route('/api/scraper/sites/<name>', methods=['DELETE'])
@role_required(SCRAPER_ROLES)
def delete_wp_site(name):
    """Delete a WordPress site."""
    sites = _load_json(WP_SITES_FILE, {})
    if name not in sites:
        return jsonify({'error': f'Site "{name}" tidak ditemukan'}), 404
    del sites[name]
    _save_json(WP_SITES_FILE, sites)
    _log_scraper(f"WordPress site deleted: {name}", session.get('user_name', 'unknown'))
    return jsonify({'ok': True, 'message': f'Site "{name}" dihapus'})


@news_scraper_bp.route('/api/scraper/test-connection', methods=['POST'])
@role_required(SCRAPER_ROLES)
def test_connection():
    """Test WordPress API connection."""
    d = request.get_json(force=True)
    wp_url = (d.get('wp_url') or '').strip()
    username = (d.get('username') or '').strip()
    app_password = (d.get('app_password') or '').strip()

    if not all([wp_url, username, app_password]):
        return jsonify({'error': 'wp_url, username, app_password wajib'}), 400

    try:
        wp_session = _get_wp_session()
        login_ok, nonce = _wp_login(wp_session, wp_url, username, app_password)
        if not login_ok:
            return jsonify({'ok': False, 'message': f'Login gagal: {nonce}'}), 200
        r = _wp_request(wp_session, 'GET', wp_url, nonce=nonce, params={"per_page": 1}, timeout=10)
        if r.status_code == 200:
            data = r.json()
            post_count = len(data) if isinstance(data, list) else 1
            return jsonify({'ok': True, 'message': f'Koneksi berhasil! ({post_count} post ditemukan)'})
        else:
            return jsonify({'ok': False, 'message': f'Gagal — status {r.status_code}'}), 200
    except Exception as e:
        return jsonify({'ok': False, 'message': f'Error: {str(e)}'}), 200


# ----- SCRAPE ARTICLES -----

@news_scraper_bp.route('/api/scraper/check', methods=['POST'])
@role_required(SCRAPER_ROLES)
def check_articles():
    """Scrape articles from newsmaker.id."""
    try:
        check_bs4()
    except RuntimeError as e:
        return jsonify({'ok': False, 'error': str(e)}), 500
    try:
        d = request.get_json(force=True)
        pages = int(d.get('pages', 1))
        pages = max(1, min(pages, 20))
    except (ValueError, TypeError):
        pages = 1

    try:
        scrape_url = "https://www.newsmaker.id/id/news/commodity"
        allowed_categories = [
            "GOLD", "OIL", "SILVER", "Crude Oil",
            "USD/JPY", "US DOLLAR", "EUR/USD",
            "AUD/USD", "GBP/USD", "USD/CHF",
        ]

        # Indonesian month mapping for date parsing (full + abbreviation)
        _ID_MONTHS = {
            'januari': '01', 'jan': '01',
            'februari': '02', 'feb': '02',
            'maret': '03', 'mar': '03',
            'april': '04', 'apr': '04',
            'mei': '05',
            'juni': '06', 'jun': '06',
            'juli': '07', 'jul': '07',
            'agustus': '08', 'agu': '08',
            'september': '09', 'sep': '09',
            'oktober': '10', 'okt': '10',
            'november': '11', 'nov': '11',
            'desember': '12', 'des': '12',
        }

        session_req = _get_wp_session()
        articles = []
        seen_links = set()
        task_id = request.args.get('task_id') or f"scrape_{int(time.time())}"
        _set_progress(task_id, {'stage': 'scrape', 'progress': 0, 'message': 'Mulai scrape...', 'total': pages, 'current': 0})

        for page_num in range(1, pages + 1):
            _set_progress(task_id, {'stage': 'scrape', 'progress': int((page_num / pages) * 80), 'message': f'Scrape halaman {page_num}/{pages}...', 'total': pages, 'current': page_num})
            page_url = scrape_url if page_num == 1 else f"{scrape_url}?page={page_num}"
            try:
                r = session_req.get(page_url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=30)
                if r.status_code != 200:
                    continue
                soup = BeautifulSoup(r.text, 'html.parser')
                # New structure: cards are divs with class containing 'rounded-xl'
                cards = soup.find_all('div', class_=lambda c: c and 'rounded-xl' in str(c) and 'group' in str(c))
                for card in cards:
                    try:
                        # Title from h3
                        title_tag = card.find('h3')
                        if not title_tag:
                            continue
                        title = title_tag.text.strip()
                        if not title:
                            continue

                        # Link from 'BACA SELENGKAPNYA' button
                        link_tag = card.find('a', href=lambda h: h and '/id/news/' in h)
                        if not link_tag:
                            continue
                        link = link_tag['href']
                        if not link.startswith('http'):
                            link = "https://www.newsmaker.id" + link
                        if link in seen_links:
                            continue
                        seen_links.add(link)

                        # Category from badge
                        cat_p = card.find('p', class_=lambda c: c and 'uppercase' in str(c))
                        category = cat_p.text.strip().upper() if cat_p else ""

                        # Date: '24 Agu 2026 - 08.18'
                        date_p = card.find('p', class_=lambda c: c and 'text-slate-400' in str(c) and 'text-[10px]' in str(c))
                        date_text = date_p.text.strip() if date_p else ""
                        publish_date = ""
                        publish_time = ""
                        try:
                            # Parse '24 Agu 2026 - 08.18'
                            parts = date_text.split(' - ')
                            if len(parts) == 2:
                                date_part = parts[0].strip()  # '24 Agu 2026'
                                publish_time = parts[1].strip()  # '08.18'
                                dp = date_part.split()
                                if len(dp) == 3:
                                    day, mon_id, year = dp
                                    month = _ID_MONTHS.get(mon_id.lower(), '01')
                                    publish_date = f"{year}-{month}-{day.zfill(2)}"
                                    publish_time = publish_time.replace('.', ':')
                        except Exception:
                            publish_date = datetime.now().strftime("%Y-%m-%d")
                            publish_time = datetime.now().strftime("%H:%M")

                        # Image
                        img_tag = card.find('img')
                        image_url = ""
                        if img_tag and img_tag.get('src'):
                            img_src = img_tag['src']
                            if not img_src.startswith('http'):
                                img_src = "https://www.newsmaker.id" + img_src
                            image_url = img_src

                        articles.append({
                            'title': title,
                            'link': link,
                            'category': category,
                            'publish_date': publish_date,
                            'publish_time': publish_time,
                            'image_url': image_url,
                            'content': None,
                        })
                    except Exception:
                        continue
            except Exception:
                continue
            time.sleep(1)

        # Fetch content for each article (parallel)
        def fetch_content(article):
            try:
                r = session_req.get(article['link'], headers={'User-Agent': 'Mozilla/5.0'}, timeout=30)
                if r.status_code == 200:
                    soup = BeautifulSoup(r.text, 'html.parser')
                    # Collect images from article page
                    content_images = []
                    # New structure: content in div.prose.prose-slate
                    content_div = soup.find('div', class_=lambda c: c and 'prose' in str(c))
                    if content_div:
                        paras = [p.text.strip() for p in content_div.find_all('p') if p.text.strip()]
                        article['content'] = "\n".join(paras)
                        # Extract images from content
                        for img in content_div.find_all('img'):
                            src = img.get('src', '') or img.get('data-src', '')
                            if src and not src.startswith('data:'):
                                if not src.startswith('http'):
                                    src = "https://www.newsmaker.id" + src
                                content_images.append(src)
                        if not article.get('image_url') and content_images:
                            article['image_url'] = content_images[0]
                        article['content_images'] = content_images
                        return
                    # Fallback: old structure
                    content_div = soup.find('div', class_='article-content')
                    if content_div:
                        paras = [p.text.strip() for p in content_div.find_all('p') if p.text.strip()]
                        article['content'] = "\n".join(paras)
                        for img in content_div.find_all('img'):
                            src = img.get('src', '') or img.get('data-src', '')
                            if src and not src.startswith('data:'):
                                if not src.startswith('http'):
                                    src = "https://www.newsmaker.id" + src
                                content_images.append(src)
                        article['content_images'] = content_images
                        return
                article['content'] = "Content not found"
            except Exception:
                article['content'] = "Content not found"

        _set_progress(task_id, {'stage': 'content', 'progress': 85, 'message': f'Mengambil konten {len(articles)} artikel...', 'total': len(articles), 'current': 0})
        done_count = [0]
        def fetch_with_progress(article):
            fetch_content(article)
            done_count[0] += 1
            if len(articles) > 0:
                _set_progress(task_id, {'stage': 'content', 'progress': 85 + int((done_count[0] / len(articles)) * 15), 'message': f'Konten {done_count[0]}/{len(articles)}...', 'total': len(articles), 'current': done_count[0]})

        with ThreadPoolExecutor(max_workers=3) as pool:
            list(pool.map(fetch_with_progress, articles))

        _set_progress(task_id, {'stage': 'done', 'progress': 100, 'message': f'{len(articles)} artikel siap diupload', 'total': len(articles), 'current': len(articles)})
        _log_scraper(f"Scraped {len(articles)} articles ({pages} pages)", session.get('user_name', 'unknown'))

        # Save to history
        _save_upload_history({
            'date': datetime.now().strftime('%Y-%m-%d'),
            'time': datetime.now().strftime('%H:%M'),
            'action': 'scrape',
            'user': session.get('user_name', 'unknown'),
            'pages': pages,
            'articles_found': len(articles),
            'categories': list(set(a.get('category', '') for a in articles)),
        })

        return jsonify({'ok': True, 'articles': articles, 'count': len(articles), 'task_id': task_id})
    except Exception as e:
        return jsonify({'ok': False, 'error': f'Scrape gagal: {str(e)}', 'articles': [], 'count': 0}), 500


# ----- UPLOAD ARTICLES -----

@news_scraper_bp.route('/api/scraper/upload', methods=['POST'])
@role_required(SCRAPER_ROLES)
def upload_articles():
    """Upload scraped articles to WordPress with SEO optimization."""
    try:
        d = request.get_json(force=True)
        site_name = (d.get('site_name') or '').strip()
        articles = d.get('articles', [])
        settings = d.get('settings', {})

        if not site_name:
            return jsonify({'error': 'Pilih WordPress site'}), 400
        if not articles:
            return jsonify({'error': 'Tidak ada artikel untuk diupload'}), 400

        sites = _load_json(WP_SITES_FILE, {})
        if site_name not in sites:
            return jsonify({'error': f'Site "{site_name}" tidak ditemukan'}), 404

        site = sites[site_name]
        wp_url = site['wp_url']
        wp_media_url = site.get('wp_media_url', wp_url.replace('/posts', '/media'))

        # Dual auth: Basic Auth server + WordPress login
        task_id = request.args.get('task_id') or f"upload_{int(time.time())}"
        _set_progress(task_id, {'stage': 'login', 'progress': 5, 'message': 'Login ke WordPress...', 'total': len(articles), 'current': 0})
        wp_session = _get_wp_session()
        login_ok, nonce = _wp_login(wp_session, wp_url, site['username'], site['app_password'])
        if not login_ok:
            return jsonify({'ok': False, 'error': f'WordPress login gagal: {nonce}', 'new_posts': 0, 'updated_posts': 0, 'errors': []}), 401
        _set_progress(task_id, {'stage': 'login', 'progress': 10, 'message': 'Login berhasil! Memeriksa existing posts...', 'total': len(articles), 'current': 0})

        enable_backlinks = settings.get('backlinks', True)
        max_backlinks = settings.get('max_backlinks', 3)
        enable_seo = settings.get('seo_optimize', True)
        static_tags = settings.get('static_tags', 'newsmaker.id, Market, Financial News')

        # Load backlinks config
        bl_config = _load_json(BACKLINKS_FILE, {})
        authority_sites = bl_config.get('authority_sites', DEFAULT_AUTHORITY_SITES)
        keyword_mapping = bl_config.get('keyword_mapping', DEFAULT_KEYWORD_MAPPING)

        # Get existing posts to avoid duplicates
        existing_titles = set()
        try:
            r = _wp_request(wp_session, 'GET', wp_url, nonce=nonce, params={"per_page": 100}, timeout=30)
            if r.status_code == 200:
                for post in r.json():
                    existing_titles.add(post.get('title', {}).get('rendered', ''))
        except Exception:
            pass

        new_count = 0
        updated_count = 0
        errors = []
        article_details = []

        for idx, article in enumerate(articles):
            title = article.get('title', '')
            content = article.get('content', '')
            if not content or content == "Content not found":
                errors.append(f"{title}: content not found")
                continue

            # Build HTML content
            html_content = f"<h1>{title}</h1>\n<p>{content}</p>"

            # SEO optimization
            seo_score = 0
            if enable_seo:
                analysis = _seo_analyze(html_content, title)
                seo_score = analysis['seo_score']

            # Apply backlinks
            backlinks_used = []
            if enable_backlinks:
                html_content, backlinks_used = _apply_backlinks(
                    html_content, title, authority_sites, keyword_mapping, max_backlinks
                )

            # Process tags
            tag_input = [t.strip().capitalize() for t in static_tags.split(',') if t.strip()]
            title_words = [w.capitalize() for w in title.lower().split()
                           if w not in {'dan', 'di', 'ke', 'dari', 'yang', 'untuk', 'dengan', 'ini', 'itu'} and len(w) > 3]
            all_tags = list(set(tag_input + title_words[:5]))

            tag_ids = []
            for tag_name in all_tags:
                try:
                    tags_url = wp_url.replace('/posts', '/tags')
                    r = _wp_request(wp_session, 'GET', tags_url, nonce=nonce, params={"search": tag_name}, timeout=10)
                    if r.status_code == 200 and r.json():
                        tag_ids.append(r.json()[0]['id'])
                    else:
                        r2 = _wp_request(wp_session, 'POST', tags_url, nonce=nonce, json={"name": tag_name}, timeout=10)
                        if r2.status_code == 201:
                            tag_ids.append(r2.json()['id'])
                except Exception:
                    pass

            # Schema markup
            publish_date = article.get('publish_date', datetime.now().strftime("%Y-%m-%d"))
            publish_time = article.get('publish_time', datetime.now().strftime("%H:%M"))
            schema = {
                "@context": "https://schema.org",
                "@type": "Article",
                "headline": title,
                "datePublished": f"{publish_date}T{publish_time}:00",
                "author": {"@type": "Organization", "name": "PT BESTPROFIT FUTURES Surabaya"},
            }
            html_content = f'<script type="application/ld+json">{json.dumps(schema, ensure_ascii=False)}</script>\n' + html_content

            # Upload featured image to WordPress
            featured_img_html = ''
            featured_media_id = 0
            image_url = article.get('image_url', '')
            if image_url:
                wp_media = _upload_image_to_wp(wp_session, wp_url, nonce, image_url)
                if wp_media:
                    featured_img_html = wp_media.get('html', '')
                    featured_media_id = wp_media.get('id', 0)
                    # Prepend featured image to content
                    html_content = featured_img_html + html_content

            post_data = {
                'title': title,
                'content': html_content,
                'status': 'publish',
                'date': f"{publish_date}T{publish_time}:00",
                'tags': tag_ids,
                'featured_media': featured_media_id,
            }

            # Progress per article
            progress_pct = 10 + int(((idx + 1) / len(articles)) * 85)
            status_msg = '⏳ Upload' if title not in existing_titles else '🔄 Update'
            _set_progress(task_id, {'stage': 'upload', 'progress': progress_pct, 'message': f'{status_msg} [{idx+1}/{len(articles)}] {title[:50]}...', 'total': len(articles), 'current': idx + 1})

            article_detail = {'title': title, 'category': article.get('category', ''), 'date': article.get('publish_date', ''), 'status': 'pending'}

            if title in existing_titles:
                # Update existing
                try:
                    r = _wp_request(wp_session, 'GET', wp_url, nonce=nonce, params={"per_page": 100, "search": title}, timeout=15)
                    if r.status_code == 200:
                        for post in r.json():
                            if post.get('title', {}).get('rendered') == title:
                                update_data = {'content': html_content, 'tags': tag_ids}
                                if featured_media_id:
                                    update_data['featured_media'] = featured_media_id
                                r2 = _wp_request(wp_session, 'POST', f"{wp_url}/{post['id']}", nonce=nonce,
                                                 json=update_data)
                                if r2.status_code == 200:
                                    updated_count += 1
                                    article_detail['status'] = 'updated'
                                    article_detail['post_id'] = post['id']
                                break
                except Exception as e:
                    errors.append(f"{title}: {str(e)}")
                    article_detail['status'] = 'error'
                    article_detail['error'] = str(e)
            else:
                # Create new
                try:
                    r = _wp_request(wp_session, 'POST', wp_url, nonce=nonce, json=post_data, timeout=30)
                    if r.status_code == 201:
                        new_count += 1
                        article_detail['status'] = 'new'
                        article_detail['post_id'] = r.json().get('id')
                    else:
                        errors.append(f"{title}: HTTP {r.status_code}")
                        article_detail['status'] = 'error'
                        article_detail['error'] = f'HTTP {r.status_code}'
                except Exception as e:
                    errors.append(f"{title}: {str(e)}")
                    article_detail['status'] = 'error'
                    article_detail['error'] = str(e)

            article_details.append(article_detail)

        # Progress selesai
        _set_progress(task_id, {'stage': 'done', 'progress': 100, 'message': f'Selesai! {new_count} baru, {updated_count} update, {len(errors)} error', 'total': len(articles), 'current': len(articles)})

        _log_scraper(
            f"Upload selesai: {new_count} baru, {updated_count} update, {len(errors)} error",
            session.get('user_name', 'unknown')
        )

        # Save to history
        _save_upload_history({
            'date': datetime.now().strftime('%Y-%m-%d'),
            'time': datetime.now().strftime('%H:%M'),
            'action': 'upload',
            'user': session.get('user_name', 'unknown'),
            'site': site_name,
            'total': len(articles),
            'new_posts': new_count,
            'updated_posts': updated_count,
            'errors': len(errors),
            'error_details': errors[:10],
            'articles': [{'title': a.get('title', ''), 'category': a.get('category', ''), 'date': a.get('publish_date', '')} for a in articles],
        })

        return jsonify({
            'ok': True,
            'new_posts': new_count,
            'updated_posts': updated_count,
            'errors': errors,
            'task_id': task_id,
        })
    except Exception as e:
        return jsonify({'ok': False, 'error': f'Upload gagal: {str(e)}', 'new_posts': 0, 'updated_posts': 0, 'errors': []}), 500


# ----- DUPLICATE CHECKER -----

@news_scraper_bp.route('/api/scraper/duplicates', methods=['POST'])
@role_required(SCRAPER_ROLES)
def check_duplicates():
    """Check for duplicate articles on a WordPress site."""
    try:
        d = request.get_json(force=True)
        site_name = (d.get('site_name') or '').strip()
        if not site_name:
            return jsonify({'error': 'Pilih WordPress site'}), 400

        sites = _load_json(WP_SITES_FILE, {})
        if site_name not in sites:
            return jsonify({'error': f'Site "{site_name}" tidak ditemukan'}), 404

        site = sites[site_name]
        wp_url = site['wp_url']

        wp_session = _get_wp_session()
        login_ok, nonce = _wp_login(wp_session, wp_url, site['username'], site['app_password'])
        if not login_ok:
            return jsonify({'ok': False, 'error': f'Login gagal: {nonce}', 'duplicates': [], 'total_posts': 0}), 401

        posts = []
        page = 1
        while True:
            try:
                r = _wp_request(wp_session, 'GET', wp_url, nonce=nonce,
                                params={'page': page, 'per_page': 100, 'orderby': 'date', 'order': 'desc'},
                                timeout=30)
                if r.status_code != 200:
                    break
                page_posts = r.json()
                if not page_posts:
                    break
                posts.extend(page_posts)
                page += 1
                time.sleep(0.1)
            except Exception:
                break

        title_count = Counter()
        posts_by_title = {}
        for post in posts:
            t = post.get('title', {}).get('rendered', '')
            title_count[t] += 1
            posts_by_title.setdefault(t, []).append(post)

        duplicates = []
        for title, count in title_count.items():
            if count > 1:
                plist = posts_by_title[title]
                duplicates.append({
                    'title': title,
                    'count': count,
                    'post_ids': [p['id'] for p in plist],
                    'dates': [p.get('date', '') for p in plist],
                })

        return jsonify({'ok': True, 'duplicates': duplicates, 'total_posts': len(posts)})
    except Exception as e:
        return jsonify({'ok': False, 'error': f'Cek duplikat gagal: {str(e)}', 'duplicates': [], 'total_posts': 0}), 500


@news_scraper_bp.route('/api/scraper/duplicates/delete', methods=['POST'])
@role_required(SCRAPER_ROLES)
def delete_duplicates():
    """Delete duplicate articles (keep latest only)."""
    d = request.get_json(force=True)
    site_name = (d.get('site_name') or '').strip()
    post_ids_to_delete = d.get('post_ids', [])

    if not site_name or not post_ids_to_delete:
        return jsonify({'error': 'site_name dan post_ids wajib'}), 400

    sites = _load_json(WP_SITES_FILE, {})
    if site_name not in sites:
        return jsonify({'error': f'Site "{site_name}" tidak ditemukan'}), 404

    site = sites[site_name]
    wp_url = site['wp_url']

    wp_session = _get_wp_session()
    login_ok, nonce = _wp_login(wp_session, wp_url, site['username'], site['app_password'])
    if not login_ok:
        return jsonify({'ok': False, 'error': f'Login gagal: {nonce}', 'deleted': 0}), 401

    deleted = 0
    for pid in post_ids_to_delete:
        try:
            r = _wp_request(wp_session, 'DELETE', f"{wp_url}/{pid}", nonce=nonce, params={'force': True}, timeout=15)
            if r.status_code == 200:
                deleted += 1
        except Exception:
            pass

    _log_scraper(f"Deleted {deleted} duplicate posts", session.get('user_name', 'unknown'))
    return jsonify({'ok': True, 'deleted': deleted})


# ----- BACKLINKS MANAGEMENT -----

@news_scraper_bp.route('/api/scraper/backlinks', methods=['GET'])
@role_required(SCRAPER_ROLES)
def get_backlinks():
    """Get financial authority backlinks configuration."""
    bl = _load_json(BACKLINKS_FILE, {})
    return jsonify({
        'authority_sites': bl.get('authority_sites', DEFAULT_AUTHORITY_SITES),
        'keyword_mapping': bl.get('keyword_mapping', DEFAULT_KEYWORD_MAPPING),
    })


@news_scraper_bp.route('/api/scraper/backlinks', methods=['POST'])
@role_required(SCRAPER_ROLES)
def save_backlinks():
    """Save backlinks configuration."""
    d = request.get_json(force=True)
    authority_sites = d.get('authority_sites', DEFAULT_AUTHORITY_SITES)
    keyword_mapping = d.get('keyword_mapping', DEFAULT_KEYWORD_MAPPING)

    _save_json(BACKLINKS_FILE, {
        'authority_sites': authority_sites,
        'keyword_mapping': keyword_mapping,
    })
    _log_scraper("Backlinks config updated", session.get('user_name', 'unknown'))
    return jsonify({'ok': True, 'message': 'Backlinks config berhasil disimpan'})


@news_scraper_bp.route('/api/scraper/backlinks/add-keyword', methods=['POST'])
@role_required(SCRAPER_ROLES)
def add_keyword_mapping():
    """Add a new keyword → authority site mapping."""
    d = request.get_json(force=True)
    keyword = (d.get('keyword') or '').strip()
    site_name = (d.get('site_name') or '').strip()

    if not keyword or not site_name:
        return jsonify({'error': 'keyword dan site_name wajib'}), 400

    bl = _load_json(BACKLINKS_FILE, {})
    km = bl.get('keyword_mapping', dict(DEFAULT_KEYWORD_MAPPING))
    km[keyword] = site_name
    bl['keyword_mapping'] = km
    _save_json(BACKLINKS_FILE, bl)
    return jsonify({'ok': True, 'message': f'Keyword "{keyword}" → "{site_name}" ditambahkan'})


# ----- HYPERLINKS -----

@news_scraper_bp.route('/api/scraper/hyperlinks', methods=['GET'])
@role_required(SCRAPER_ROLES)
def get_hyperlinks():
    return jsonify(_load_json(HYPERLINKS_FILE, {}))


@news_scraper_bp.route('/api/scraper/hyperlinks', methods=['POST'])
@role_required(SCRAPER_ROLES)
def save_hyperlinks():
    d = request.get_json(force=True)
    _save_json(HYPERLINKS_FILE, d.get('hyperlinks', {}))
    return jsonify({'ok': True, 'message': 'Hyperlinks disimpan'})


# ----- SCRAPER LOG -----

@news_scraper_bp.route('/api/scraper/log', methods=['GET'])
@role_required(SCRAPER_ROLES)
def get_scraper_log():
    logs = _load_json(SCRAPER_LOG_FILE, [])
    limit = request.args.get('limit', 100, type=int)
    return jsonify(logs[-limit:])


@news_scraper_bp.route('/api/scraper/log', methods=['DELETE'])
@role_required(SCRAPER_ROLES)
def clear_scraper_log():
    _save_json(SCRAPER_LOG_FILE, [])
    return jsonify({'ok': True, 'message': 'Log cleared'})


# ----- PROGRESS SSE -----

@news_scraper_bp.route('/api/scraper/progress/<task_id>', methods=['GET'])
@role_required(SCRAPER_ROLES)
def get_progress(task_id):
    """Get progress for a scrape/upload task (polling)."""
    data = _get_progress(task_id)
    if not data:
        return jsonify({'ok': False, 'error': 'Task tidak ditemukan'}), 404
    return jsonify({'ok': True, **data})


# ----- UPLOAD HISTORY -----

@news_scraper_bp.route('/api/scraper/history', methods=['GET'])
@role_required(SCRAPER_ROLES)
def get_upload_history_route():
    """Get upload/scrape history with filters."""
    date_from = request.args.get('date_from', '')
    date_to = request.args.get('date_to', '')
    action = request.args.get('action', '')  # 'scrape' or 'upload'
    limit = request.args.get('limit', 50, type=int)

    history = _get_upload_history(
        date_from=date_from or None,
        date_to=date_to or None,
        action=action or None,
    )
    # Return most recent first
    history = list(reversed(history))[-limit:]
    return jsonify({'ok': True, 'history': history, 'total': len(history)})


@news_scraper_bp.route('/api/scraper/history', methods=['DELETE'])
@role_required(SCRAPER_ROLES)
def clear_upload_history():
    """Clear upload history."""
    _save_json(UPLOAD_HISTORY_FILE, [])
    return jsonify({'ok': True, 'message': 'History cleared'})


# ---------------------------------------------------------------------------
# Register
# ---------------------------------------------------------------------------

def register_news_scraper_routes(app):
    app.register_blueprint(news_scraper_bp)
