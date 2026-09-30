"""
modules/news_scraper/routes.py
Flask route handlers for the news scraper module.
"""

import os, json, time, io, csv, re, threading, html
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor
from flask import Blueprint, request, jsonify, session, Response

from modules.helpers import role_required

from . import (news_scraper_bp, DATA_DIR, WP_SITES_FILE, BACKLINKS_FILE,
    HYPERLINKS_FILE, SCRAPER_LOG_FILE, UPLOAD_HISTORY_FILE, SETTINGS_FILE,
    SCRAPER_ROLES, DEFAULT_AUTHORITY_SITES, DEFAULT_KEYWORD_MAPPING)
from .wp_client import get_wp_session, WpClient
from .scraper_engine import scrape_newsmaker, scrape_detik_finance, fetch_article_content, RateLimiter, progress_tracker
from .seo_optimizer import (apply_backlinks, build_article_html, seo_analyze, build_advanced_schema,
    ping_sitemap, track_performance, get_analytics, get_optimal_publish_time, should_publish_today,
    JsonCache, normalize_title, rewrite_content, wp_block)
from .scraper_logger import get_logger

_sl = get_logger()  # structured scraper logger


# ===================================================================
# HELPERS
# ===================================================================

def _load_json(path, default):
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return default


def _save_json(path, data):
    os.makedirs(os.path.dirname(path) or '.', exist_ok=True)
    tmp = path + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


def _log_scraper(message, user='unknown'):
    """Append an entry to the scraper activity log.

    ``message`` may be a plain string (legacy shape: time/user/message) or a
    structured dict (level/category/msg/extra) that the activity log modal
    renders with full detail (who did what).
    """
    if isinstance(message, dict):
        entry = dict(message)
        entry.setdefault('ts', datetime.now().isoformat())
        entry.setdefault('user', user)
        entry.setdefault('level', 'INFO')
        entry.setdefault('category', 'general')
        entry.setdefault('msg', '')
        entry.setdefault('extra', {})
    else:
        entry = {
            'time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'user': user,
            'message': message,
        }
    logs = _load_json(SCRAPER_LOG_FILE, [])
    logs.append(entry)
    _save_json(SCRAPER_LOG_FILE, logs[-2000:])


# Rate limiter: 5 scrape requests / minute per user
_scrape_rate_limiter = RateLimiter(max_requests=5, window_seconds=60)

def _set_progress(task_id, data):
    progress_tracker.set(task_id, {
        'stage': data.get('stage', ''),
        'progress': data.get('progress', 0),
        'message': data.get('message', ''),
        'total': data.get('total', 0),
        'current': data.get('current', 0),
    })


def _get_progress(task_id):
    return progress_tracker.get(task_id)


def _save_upload_history(entry):
    history = _load_json(UPLOAD_HISTORY_FILE, [])
    history.append(entry)
    _save_json(UPLOAD_HISTORY_FILE, history[-1000:])


def _get_upload_history(date_from=None, date_to=None, action=None):
    history = _load_json(UPLOAD_HISTORY_FILE, [])
    result = []
    for e in history:
        d = e.get('date', '')
        if date_from and d < date_from:
            continue
        if date_to and d > date_to:
            continue
        if action and e.get('action') != action:
            continue
        result.append(e)
    return result


def _sanitize_csv(val):
    """Prefix formula-triggering characters to prevent CSV injection in Excel."""
    s = str(val) if val is not None else ''
    if s and s[0] in ('=', '+', '-', '@', '\t', '\r'):
        s = "'" + s
    return s


def _build_excerpt(plain_text: str, limit: int = 290) -> str:
    """Bangun excerpt polos dari konten artikel (untuk meta description Rank Math).

    Rank Math memakai excerpt post sebagai meta description; bila kosong,
    ia fallback ke konten dan isi <script> non-teks bisa bocor ke snippet.
    Excerpt dipotong di batas kata pada ±290 karakter (aman utk snippet Google).
    """
    text = re.sub(r'<[^>]+>', ' ', plain_text or '')
    text = html.unescape(text)
    text = re.sub(r'\s+', ' ', text).strip()
    if len(text) <= limit:
        return text
    cut = text[:limit].rsplit(' ', 1)[0]
    return (cut if cut else text[:limit]) + '…'


# Stopword judul untuk derivasi fokus keyword Rank Math.
_TITLE_STOPWORDS = {'dan', 'di', 'ke', 'dari', 'yang', 'untuk', 'dengan',
                    'ini', 'itu', 'atau', 'dalam', 'pada', 'the'}


def _focus_keyword_from_title(title: str, max_words: int = 4) -> str:
    """Turunkan fokus keyword Rank Math dari judul artikel.

    Ambil hingga ``max_words`` kata pertama yang bermakna (buang stopword
    dan kata pendek) — cukup spesifik sebagai fokus keyword tanpa input
    manual per artikel.
    """
    words = [w.strip('.,:;!?()"\u201c\u201d\u2018\u2019') for w in (title or '').split()]
    picked = [w for w in words
              if w and len(w) > 3 and w.lower() not in _TITLE_STOPWORDS]
    return ' '.join(picked[:max_words])


# City-name aliases so branch codes (e.g. "SBY") can be matched against site
# names that only contain the full city name (e.g. "BPF Surabaya").
_BRANCH_CITY_ALIASES = {
    'SBY': ('surabaya',),
    'JKT': ('jakarta',),
    'JKT2': ('jakarta 2', 'jakarta2'),
    'BDG': ('bandung',),
    'SMG': ('semarang',),
    'MLG': ('malang',),
    'MDN': ('medan',),
    'BJM': ('banjarmasin',),
    'PLM': ('palembang',),
    'LPG': ('lampung',),
}


def _site_matches_branch(name, site_branch, user_branch):
    """Return True if a site belongs to ``user_branch``.

    Matches on ``branch_code`` first; falls back to matching the branch code
    or its full-city alias against the site name (case-insensitive).
    """
    if site_branch:
        return site_branch.upper() == user_branch.upper()
    name_lower = name.lower()
    ub = user_branch.upper()
    if ub in _BRANCH_CITY_ALIASES:
        return any(alias in name_lower for alias in _BRANCH_CITY_ALIASES[ub])
    return user_branch.lower() in name_lower


def _visible_sites(sites, user_branch, user_role, user_name):
    """Return the subset of ``sites`` visible to the current user.

    Admins and HQ users see everything; other scraper roles only see sites
    belonging to their own branch.
    """
    is_hq = user_name in ('it_hu', 'admin')
    if user_role == 'admin' or is_hq:
        return dict(sites)
    result = {}
    for name, data in sites.items():
        site_branch = data.get('branch_code', '')
        if _site_matches_branch(name, site_branch, user_branch):
            result[name] = data
    return result


# Scheduled jobs store
SCHEDULE_FILE = os.path.join(DATA_DIR, 'scraper_schedule.json')
_schedule_lock = threading.Lock()


def _load_schedule():
    return _load_json(SCHEDULE_FILE, [])


def _save_schedule(jobs):
    _save_json(SCHEDULE_FILE, jobs)


# Telegram notification helper
TELEGRAM_CONFIG_FILE = os.path.join(DATA_DIR, 'telegram_config.json')


def _send_telegram(message):
    cfg = _load_json(TELEGRAM_CONFIG_FILE, {})
    token = cfg.get('bot_token', '')
    chat_id = cfg.get('chat_id', '')
    if not token or not chat_id:
        return {'ok': False, 'error': 'Telegram belum dikonfigurasi'}
    try:
        import requests as _requests
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        r = _requests.post(url, json={'chat_id': chat_id, 'text': message}, timeout=15)
        return {'ok': r.status_code == 200}
    except Exception as e:
        return {'ok': False, 'error': str(e)[:200]}


# ===================================================================
# ROUTES
# ===================================================================

@news_scraper_bp.route('/api/scraper/sites', methods=['GET'])
@role_required(SCRAPER_ROLES)
def list_wp_sites():
    """List WordPress sites filtered by user's branch."""
    sites = _load_json(WP_SITES_FILE, {})
    visible = _visible_sites(
        sites,
        session.get('branch_code', ''),
        session.get('user_role', ''),
        session.get('user_name', ''),
    )
    return jsonify([
        {
            'name': name, 'wp_url': data.get('wp_url', ''),
            'wp_media_url': data.get('wp_media_url', ''),
            'username': data.get('username', ''),
            'app_password': data.get('app_password', ''),
            'branch_code': data.get('branch_code', ''),
        }
        for name, data in visible.items()
    ])


@news_scraper_bp.route('/api/scraper/sites', methods=['POST'])
@role_required(SCRAPER_ROLES)
def save_wp_site():
    """Add or update a WordPress site."""
    d = request.get_json(force=True)
    name = (d.get('name') or '').strip()
    wp_url = (d.get('wp_url') or '').strip()
    username = (d.get('username') or '').strip()
    app_password = (d.get('app_password') or '').strip()
    branch_code = (d.get('branch_code') or '').strip().upper()

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
    if old and not branch_code:
        branch_code = old.get('branch_code', '')

    sites[name] = {
        'wp_url': wp_url,
        'wp_media_url': wp_media_url,
        'username': username,
        'app_password': app_password,
        'branch_code': branch_code,
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
    """Test WordPress API connection.
    Accepts either:
    - {site_name: '...'} — test with saved credentials
    - {wp_url, username, app_password} — test with provided credentials
    """
    d = request.get_json(force=True)
    site_name = (d.get('site_name') or '').strip()
    wp_url = (d.get('wp_url') or '').strip()
    username = (d.get('username') or '').strip()
    app_password = (d.get('app_password') or '').strip()

    site = None
    if site_name:
        sites = _load_json(WP_SITES_FILE, {})
        if site_name not in sites:
            return jsonify({'ok': False, 'message': f'Site "{site_name}" tidak ditemukan'}), 200
        site = sites[site_name]
        wp_url = site.get('wp_url', '')
        username = site.get('username', '')
        app_password = site.get('app_password', '')

    if not all([wp_url, username, app_password]):
        return jsonify({'ok': False, 'message': 'Kredensial belum lengkap — isi username & password dulu'}), 200

    if username in ('PENDING', '') or app_password in ('PENDING', ''):
        return jsonify({'ok': False, 'message': 'Kredensial belum diisi — klik Edit dan isi username & password'}), 200

    try:
        # Situs tersimpan -> pakai fallback basic auth (jika dikonfigurasi);
        # kredensial manual (form Edit) -> tanpa fallback.
        if site is not None:
            client = _make_wp_client(site)
        else:
            client = WpClient(wp_url, username, app_password)
        login_ok, nonce_or_err = client.login()
        if not login_ok:
            return jsonify({'ok': False, 'message': f'Login gagal: {nonce_or_err}'}), 200
        r = client.get_posts(nonce_or_err, params={"per_page": 1}, timeout=10)
        if r.status_code == 200:
            data = r.json()
            post_count = len(data) if isinstance(data, list) else 1
            return jsonify({'ok': True, 'message': f'Koneksi berhasil! ({post_count} post ditemukan)'})
        else:
            return jsonify({'ok': False, 'message': f'Gagal — status {r.status_code}'}), 200
    except Exception as e:
        err_msg = str(e)
        if 'NameResolutionError' in err_msg or 'Failed to resolve' in err_msg:
            domain = wp_url.replace('https://', '').replace('http://', '').split('/')[0]
            return jsonify({'ok': False, 'message': f'🌐 Domain "{domain}" tidak dapat diakses. Pastikan DNS sudah dikonfigurasi dan server WordPress aktif.'}), 200
        elif 'ConnectionRefused' in err_msg or 'Connection refused' in err_msg:
            return jsonify({'ok': False, 'message': '🔌 Server WordPress menolak koneksi — pastikan port HTTPS aktif.'}), 200
        elif 'SSLError' in err_msg or 'SSL' in err_msg:
            return jsonify({'ok': False, 'message': '🔒 Error sertifikat SSL — periksa konfigurasi HTTPS server.'}), 200
        elif 'Timeout' in err_msg or 'timed out' in err_msg:
            return jsonify({'ok': False, 'message': '⏱️ Koneksi timeout — server WordPress lambat atau tidak merespon.'}), 200
        else:
            return jsonify({'ok': False, 'message': f'Error: {err_msg[:200]}'}), 200


# ----- SCRAPE ARTICLES -----

@news_scraper_bp.route('/api/scraper/check', methods=['POST'])
@role_required(SCRAPER_ROLES)
def check_articles():
    """Scrape articles from multiple sources (rate limited: 5/min per user)."""
    user = session.get('user_name', 'unknown')
    allowed = _scrape_rate_limiter.check(user)
    if not allowed:
        return jsonify({'ok': False, 'error': 'Rate limit tercapai (5/menit). Coba lagi dalam 60 detik.'}), 429

    try:
        d = request.get_json(force=True)
        pages = int(d.get('pages', 1))
        pages = max(1, min(pages, 20))
        source = d.get('source', 'all')
    except (ValueError, TypeError):
        pages = 1
        source = 'all'

    try:
        articles = []
        seen_links = set()
        task_id = request.args.get('task_id') or f"scrape_{int(time.time())}"
        _set_progress(task_id, {'stage': 'scrape', 'progress': 0, 'message': 'Mulai scrape...', 'total': pages, 'current': 0})
        _sl.log('INFO', 'SCRAPE', f'Start scrape: source={source}, pages={pages}, user={user}')

        if source in ('all', 'newsmaker'):
            _set_progress(task_id, {'stage': 'scrape', 'progress': 5, 'message': 'Scrape Newsmaker.id...', 'total': pages, 'current': 0})
            try:
                newsmaker_articles = scrape_newsmaker(pages)
                for a in newsmaker_articles:
                    if a['link'] not in seen_links:
                        seen_links.add(a['link'])
                        articles.append(a)
                _sl.log('SUCCESS', 'SCRAPE', f'Newsmaker: {len(newsmaker_articles)} articles found')
            except Exception as e:
                _sl.log('ERROR', 'SCRAPE', f'Newsmaker scrape failed: {str(e)[:200]}')

        if source in ('all', 'detik'):
            _set_progress(task_id, {'stage': 'scrape', 'progress': 50, 'message': 'Scrape Detik Finance...', 'total': 1, 'current': 0})
            try:
                detik_articles = scrape_detik_finance(pages)
                for a in detik_articles:
                    if a['link'] not in seen_links:
                        seen_links.add(a['link'])
                        articles.append(a)
                _sl.log('SUCCESS', 'SCRAPE', f'Detik: {len(detik_articles)} articles found')
            except Exception as e:
                _sl.log('ERROR', 'SCRAPE', f'Detik scrape failed: {str(e)[:200]}')

        _set_progress(task_id, {'stage': 'scrape', 'progress': 70, 'message': f'Ditemukan {len(articles)} artikel...', 'total': len(articles), 'current': 0})

        done_count = [0]

        def fetch_with_progress(article):
            fetch_article_content(article)
            done_count[0] += 1
            if len(articles) > 0:
                _set_progress(task_id, {'stage': 'content', 'progress': 75 + int((done_count[0] / len(articles)) * 25),
                                        'message': f'Konten {done_count[0]}/{len(articles)}...',
                                        'total': len(articles), 'current': done_count[0]})

        _set_progress(task_id, {'stage': 'content', 'progress': 75, 'message': f'Mengambil konten {len(articles)} artikel...', 'total': len(articles), 'current': 0})
        with ThreadPoolExecutor(max_workers=5) as pool:
            list(pool.map(fetch_with_progress, articles))

        _set_progress(task_id, {'stage': 'done', 'progress': 100, 'message': f'{len(articles)} artikel siap diupload',
                                'total': len(articles), 'current': len(articles)})
        _log_scraper(f"Scraped {len(articles)} articles (source: {source})", user)

        _save_upload_history({
            'date': datetime.now().strftime('%Y-%m-%d'),
            'time': datetime.now().strftime('%H:%M'),
            'action': 'scrape',
            'user': user,
            'pages': pages,
            'source': source,
            'articles_found': len(articles),
            'categories': list(set(a.get('category', '') for a in articles)),
            'sources': list(set(a.get('source', '') for a in articles)),
        })

        return jsonify({'ok': True, 'articles': articles, 'count': len(articles), 'task_id': task_id})
    except Exception as e:
        return jsonify({'ok': False, 'error': f'Scrape gagal: {str(e)}', 'articles': [], 'count': 0}), 500


# ----- UPLOAD ARTICLES -----

def _make_wp_client(site):
    """Bangun WpClient dari config site, dengan fallback basic auth opsional.

    Site config dapat memuat `basic_username`/`basic_password` (login WP biasa
    via plugin JSON Basic Authentication) sebagai cadangan bila application
    password ditolak.
    """
    fallback = None
    bu = (site.get('basic_username') or '').strip()
    bp = (site.get('basic_password') or '').strip()
    if bu and bp:
        fallback = (bu, bp)
    return WpClient(site['wp_url'], site['username'], site['app_password'],
                    fallback_auth=fallback)


def _upload_articles_to_site(site_name, articles, settings, task_prefix='upload', task_id=None):
    """Core upload logic shared by single-site and multi-site upload."""
    sites = _load_json(WP_SITES_FILE, {})
    if site_name not in sites:
        return {'ok': False, 'status': 404, 'error': f'Site "{site_name}" tidak ditemukan'}

    site = sites[site_name]

    if site.get('username') in ('PENDING', '', None) or site.get('app_password') in ('PENDING', '', None):
        return {'ok': False, 'status': 400,
                'error': f'Kredensial WordPress belum diisi untuk "{site_name}". Silakan edit site dan isi username & password.',
                'new_posts': 0, 'updated_posts': 0, 'errors': []}

    wp_url = site['wp_url']
    if not task_id:
        task_id = f"{task_prefix}_{int(time.time())}"
    _set_progress(task_id, {'stage': 'login', 'progress': 5, 'message': 'Login ke WordPress...', 'total': len(articles), 'current': 0})

    client = _make_wp_client(site)
    login_ok, nonce_or_err = client.login()
    _sl.wp_login(site_name, success=login_ok, user=site.get('username'),
                  error=None if login_ok else str(nonce_or_err)[:200])
    if not login_ok:
        return {'ok': False, 'status': 401, 'error': f'WordPress login gagal: {nonce_or_err}',
                'new_posts': 0, 'updated_posts': 0, 'errors': [], 'task_id': task_id}
    _set_progress(task_id, {'stage': 'login', 'progress': 10, 'message': 'Login berhasil! Memeriksa existing posts...',
                            'total': len(articles), 'current': 0})

    enable_backlinks = settings.get('backlinks', True)
    max_backlinks = settings.get('max_backlinks', 3)
    enable_seo = settings.get('seo_optimize', True)
    static_tags = settings.get('static_tags', 'newsmaker.id, Detik Finance, Market, Financial News')
    # v2.46.4: set meta rank_math_focus_keyword (plugin Rank Math SEO).
    rank_math_keywords = settings.get('rank_math_keywords', True)

    bl_config = _load_json(BACKLINKS_FILE, {})
    authority_sites = bl_config.get('authority_sites', DEFAULT_AUTHORITY_SITES)
    keyword_mapping = bl_config.get('keyword_mapping', DEFAULT_KEYWORD_MAPPING)

    # ── Fetch existing posts dari WordPress untuk pre-filter duplikat ──
    # v2.44: paginasi PINUH (dulu hanya 1000 post terbaru — di site besar seperti
    # BPF Surabaya ~9400 post, artikel lama tidak terdeteksi sehingga upload
    # membuat duplikat baru di setiap batch). Bila paginasi tidak lengkap
    # (cap _MAX_POST_PAGES tercapai / error transport), fallback search
    # per-artikel di bawah yang menutup celahnya.
    existing_titles = set()
    existing_norm_map = {}  # normalized_title -> post_id
    existing_fetch_complete = False
    try:
        all_existing, existing_fetch_complete = _fetch_all_posts(client, nonce_or_err)
        for post in all_existing:
            t = post.get('title', {}).get('rendered', '')
            existing_titles.add(t)
            existing_norm_map[normalize_title(t)] = post.get('id')
    except Exception as e:
        # Jangan diam-diam: gagal fetch = pre-filter lemah = risiko duplikat.
        _sl.log('ERROR', 'UPLOAD',
                f'Gagal mengambil existing posts untuk pre-filter: {str(e)[:200]}')

    if not existing_fetch_complete:
        _sl.log('WARNING', 'UPLOAD',
                'Paginasi existing posts TIDAK lengkap (cap/error) — '
                'fallback search per-artikel aktif untuk mencegah duplikat')

    # ── Pre-filter: only process articles NOT yet on WordPress ──
    # Tiga lapis: (1) norm_map hasil paginasi penuh, (2) dedup intra-batch
    # (judul sama 2x dalam satu batch scrape), (3) fallback search WP saat
    # paginasi existing tidak lengkap (site > ~5000 post).
    new_articles = []
    seen_norm_in_batch = set()
    skipped_existing = 0
    skipped_dup_batch = 0
    skipped_no_content = 0
    _MAX_WP_SEARCHES = 60   # batas fallback search per upload (biaya HTTP)
    wp_searches_used = 0
    for article in articles:
        title = article.get('title', '')
        content = article.get('content', '')
        if not content or content == 'Content not found':
            skipped_no_content += 1
            continue
        norm = normalize_title(title)
        if norm in existing_norm_map:
            skipped_existing += 1
            continue
        if norm in seen_norm_in_batch:
            skipped_dup_batch += 1
            continue
        if not existing_fetch_complete and wp_searches_used < _MAX_WP_SEARCHES:
            try:
                r = client.search_posts(title, nonce_or_err, timeout=15)
                wp_searches_used += 1
                if r.status_code == 200:
                    for post in r.json():
                        if _normalized_post_title(post) == norm:
                            existing_norm_map[norm] = post.get('id')
                            skipped_existing += 1
                            break
                    else:
                        seen_norm_in_batch.add(norm)
                        new_articles.append(article)
                    continue
            except Exception:
                pass
        seen_norm_in_batch.add(norm)
        new_articles.append(article)

    _sl.log('INFO', 'UPLOAD',
            f'Pre-filter: {len(articles)} scraped → {len(new_articles)} new, '
            f'{skipped_existing} already on WP, {skipped_dup_batch} duplikat intra-batch, '
            f'{skipped_no_content} no content (paginasi existing: '
            f'{"lengkap" if existing_fetch_complete else "TIDAK lengkap"})')
    _set_progress(task_id, {'stage': 'filter', 'progress': 15,
                            'message': f'{len(new_articles)} artikel baru dari {len(articles)} — {skipped_existing} sudah ada di WP',
                            'total': len(new_articles), 'current': 0})

    new_count = 0
    updated_count = 0
    errors = []
    article_details = []

    for idx, article in enumerate(new_articles):
        title = article.get('title', '')
        content = article.get('content', '')
        if not content or content == "Content not found":
            errors.append(f"{title}: content not found")
            continue

        content = rewrite_content(content, title)

        publish_date = article.get('publish_date', datetime.now().strftime("%Y-%m-%d"))
        publish_time = article.get('publish_time', datetime.now().strftime("%H:%M"))

        html_content = build_article_html(title, content, article, publish_date, publish_time)

        seo_score = 0
        if enable_seo:
            analysis = seo_analyze(html_content, title)
            seo_score = analysis['seo_score']

        backlinks_used = []
        if enable_backlinks:
            html_content, backlinks_used = apply_backlinks(html_content, title, authority_sites, keyword_mapping, max_backlinks)

        source_url = article.get('link', '')
        raw_source = article.get('source', 'newsmaker')
        source_map = {'newsmaker': 'Newsmaker.id', 'detik_finance': 'Detik Finance', 'detik_tag': 'Detik Finance', 'detik': 'Detik Finance'}
        source_name = source_map.get(raw_source, raw_source.title())
        if source_url and 'Content not found' not in (article.get('content', '') or ''):
            # v2.46.4: sisip sebagai blok tersendiri (wp:html) — bukan
            # mengganti marker di tengah blok lain agar blok tetap valid.
            source_backlink = wp_block(
                f'<p style="margin-top:20px;padding:12px;background:#f0f9ff;border:1px solid #bae6fd;border-radius:8px;font-size:13px;color:#0369a1;">📰 Sumber asli: <a href="{source_url}" target="_blank" rel="nofollow noopener" style="color:#0284c7;font-weight:600;">{source_name}</a></p>'
            )
            cta_marker = '<!-- BPF CTA Widget -->'
            cta_pos = html_content.find(cta_marker)
            if cta_pos != -1:
                # Sisip SEBELUM blok wp:html yang membungkus CTA (bila ada).
                block_open = html_content.rfind('<!-- wp:html -->', 0, cta_pos)
                insert_at = block_open if block_open != -1 else cta_pos
                html_content = (html_content[:insert_at] + source_backlink
                                + '\n\n' + html_content[insert_at:])
            else:
                html_content = html_content.rstrip() + '\n\n' + source_backlink

        tag_input = [t.strip().capitalize() for t in static_tags.split(',') if t.strip()]
        title_words = [w.capitalize() for w in title.lower().split()
                       if w not in {'dan', 'di', 'ke', 'dari', 'yang', 'untuk', 'dengan', 'ini', 'itu'} and len(w) > 3]
        all_tags = list(set(tag_input + title_words[:5]))

        tag_ids = []
        for tag_name in all_tags:
            try:
                tag_id = client.get_or_create_tag(tag_name, nonce_or_err)
                if tag_id is not None:
                    tag_ids.append(tag_id)
                    _sl.tag_create(tag_name, tag_id=tag_id, created=True)
            except Exception as e:
                _sl.tag_create(tag_name, created=False, error=str(e)[:100])
                print(f'[scraper-tag] Failed to create tag "{tag_name}": {e}')

        # Catatan (25 Sep 2026): injeksi <script type="application/ld+json"> ke konten
        # DIHAPUS. Plugin SEO di WordPress (Rank Math) sudah menghasilkan schema-nya
        # sendiri di <head>; blok ld+json di awal konten membuat isi JSON bocor ke
        # meta description (Rank Math fallback ke konten) + schema duplikat di halaman.
        # build_advanced_schema() tetap tersedia bila nanti schema ingin di-inject
        # lewat <head> (mis. via plugin/filter), bukan ke dalam konten.

        featured_img_html = ''
        featured_media_id = 0
        image_url = article.get('image_url', '')
        if image_url:
            wp_media = client.upload_image(image_url, nonce_or_err)
            if wp_media:
                featured_media_id = wp_media.get('id', 0)
                # WordPress REST API does not return 'html' — build it from source_url
                wp_img_url = wp_media.get('source_url', '')
                if wp_img_url:
                    details = wp_media.get('media_details', {})
                    w = details.get('width', 1200)
                    h = details.get('height', 675)
                    featured_img_html = (
                        f'<figure class="wp-block-image size-large">'
                        f'<img src="{wp_img_url}" alt="{title}" '
                        f'width="{w}" height="{h}" class="wp-post-image"/>'
                        f'</figure>'
                    )
                    # v2.46.4: bungkus dalam blok wp:image agar tetap blok
                    # Gutenberg di editor (bukan bagian blok classic).
                    html_content = wp_block(featured_img_html) + '\n\n' + html_content
                _sl.image_upload(image_url[:80], media_id=featured_media_id, success=True)
                print(f'[scraper-img] Upload OK: media_id={featured_media_id}, wp_url={wp_img_url[:80] if wp_img_url else "(none)"}, title={title[:50]}')
            else:
                _sl.image_upload(image_url[:80], success=False, error='Upload failed')
                print(f'[scraper-img] Upload FAILED for "{title[:50]}" — image_url={image_url[:80]}')

        # Safety: WordPress may reject posts with extremely large content.
        # Truncate if over ~120KB — v2.46.4: potong pada BATAS BLOK (pemisah
        # baris kosong) agar komentar pembuka/penutup wp:* selalu berpasangan;
        # memotong di tengah blok meninggalkan blok tanpa penutup (error
        # validasi blok di editor).
        _MAX_CONTENT_BYTES = 120 * 1024
        if len(html_content.encode('utf-8')) > _MAX_CONTENT_BYTES:
            _sl.log('WARNING', 'UPLOAD', f'Content too large ({len(html_content.encode("utf-8"))} bytes) for "{title[:50]}" — truncating')
            kept, size = [], 0
            for chunk in html_content.split('\n\n'):
                b = len((chunk + '\n\n').encode('utf-8'))
                if kept and size + b > _MAX_CONTENT_BYTES:
                    break
                kept.append(chunk)
                size += b
            html_content = '\n\n'.join(kept)

        # v2.46.4: fokus keyword Rank Math via REST meta. Field
        # rank_math_focus_keyword diregistrasi plugin Rank Math; bila plugin
        # nonaktif/versi lama membalas rest_invalid_param → diulang tanpa
        # meta agar artikel tetap terbit (lihat create_post di bawah).
        rm_meta = {}
        if rank_math_keywords:
            focus_kw = _focus_keyword_from_title(title)
            if focus_kw:
                rm_meta['rank_math_focus_keyword'] = focus_kw

        post_data = {
            'title': title,
            'content': html_content,
            # Excerpt polos — Rank Math memakainya sebagai meta description.
            # Tanpa excerpt, Rank Math fallback ke konten dan bisa menyerap isi tag.
            'excerpt': _build_excerpt(content),
            'status': 'publish',
            'date': f"{publish_date}T{publish_time or '08:00'}:00",
            'tags': tag_ids,
            'featured_media': featured_media_id,
        }
        if rm_meta:
            post_data['meta'] = rm_meta
        print(f'[scraper-post] Creating post: featured_media={featured_media_id}, title={title[:50]}')

        # Pre-filtered: all articles here are new, but double-check via norm_map
        norm_title = normalize_title(title)
        matched_post_id = existing_norm_map.get(norm_title)
        is_duplicate = matched_post_id is not None

        progress_pct = 15 + int(((idx + 1) / max(len(new_articles), 1)) * 80)
        status_msg = '🔄 Update' if is_duplicate else '⏳ Upload'
        _set_progress(task_id, {'stage': 'upload', 'progress': progress_pct,
                                'message': f'{status_msg} [{idx+1}/{len(new_articles)}] {title[:50]}...',
                                'total': len(new_articles), 'current': idx + 1})

        article_detail = {
            'title': title, 'category': article.get('category', ''),
            'date': article.get('publish_date', ''), 'status': 'pending',
            'source': article.get('source', ''), 'link': article.get('link', ''),
            'seo_score': 0, 'post_id': 0, 'wp_url': wp_url.split('/wp-json')[0],
        }

        if is_duplicate and matched_post_id:
            try:
                update_data = {'content': html_content, 'tags': tag_ids}
                if featured_media_id:
                    update_data['featured_media'] = featured_media_id
                print(f'[scraper-update] Updating post {matched_post_id}: featured_media={featured_media_id}, title={title[:50]}')
                r2 = client.update_post(matched_post_id, update_data, nonce_or_err)
                if r2.status_code == 200:
                    updated_count += 1
                    article_detail['status'] = 'updated'
                    article_detail['post_id'] = matched_post_id
                    _sl.upload_article(post_id=matched_post_id, title=title[:50], status='updated', seo_score=seo_score)
                else:
                    err_body = r2.text[:200] if hasattr(r2, 'text') else ''
                    errors.append(f"{title}: update HTTP {r2.status_code} — {err_body}")
                    article_detail['status'] = 'error'
                    article_detail['error'] = f'HTTP {r2.status_code}: {err_body}'
                    _sl.upload_article(title=title[:50], status='error', error=f'HTTP {r2.status_code}: {err_body}')
            except Exception as e:
                errors.append(f"{title}: {str(e)}")
                article_detail['status'] = 'error'
                article_detail['error'] = str(e)
                _sl.upload_article(title=title[:50], status='error', error=str(e)[:200])
        elif is_duplicate:
            try:
                r = client.search_posts(title, nonce_or_err, timeout=15)
                if r.status_code == 200:
                    for post in r.json():
                        if normalize_title(post.get('title', {}).get('rendered', '')) == norm_title:
                            update_data = {'content': html_content, 'tags': tag_ids}
                            if featured_media_id:
                                update_data['featured_media'] = featured_media_id
                            print(f'[scraper-update] Updating post {post["id"]}: featured_media={featured_media_id}, title={title[:50]}')
                            r2 = client.update_post(post['id'], update_data, nonce_or_err)
                            if r2.status_code == 200:
                                updated_count += 1
                                article_detail['status'] = 'updated'
                                article_detail['post_id'] = post['id']
                                article_detail['seo_score'] = seo_score
                            break
            except Exception as e:
                errors.append(f"{title}: {str(e)}")
        else:
            try:
                r = client.create_post(post_data, nonce_or_err)
                if r.status_code == 400 and post_data.get('meta') \
                        and 'rest_invalid_param' in (getattr(r, 'text', '') or ''):
                    # Field meta tidak dikenali WP (Rank Math nonaktif/versi
                    # lama) → ulangi tanpa meta agar artikel tetap terbit.
                    post_data_wo = {k: v for k, v in post_data.items() if k != 'meta'}
                    r = client.create_post(post_data_wo, nonce_or_err)
                if r.status_code == 201:
                    new_count += 1
                    article_detail['status'] = 'new'
                    article_detail['post_id'] = r.json().get('id')
                    # Registrasi post baru ke norm_map — melindungi artikel
                    # berjudul sama berikutnya dalam batch yang sama.
                    existing_norm_map[normalize_title(title)] = article_detail['post_id']
                    article_detail['seo_score'] = seo_score
                    _sl.upload_article(post_id=r.json().get('id'), title=title[:50], status='new', seo_score=seo_score)
                else:
                    error_body = ''
                    try: error_body = r.text[:200]
                    except Exception: pass
                    errors.append(f"{title}: HTTP {r.status_code} — {error_body}")
                    article_detail['status'] = 'error'
                    article_detail['error'] = f'HTTP {r.status_code}: {error_body}'
                    _sl.upload_article(title=title[:50], status='error', error=f'HTTP {r.status_code}: {error_body}')
            except Exception as e:
                errors.append(f"{title}: {str(e)}")
                _sl.upload_article(title=title[:50], status='error', error=str(e)[:200])
                article_detail['status'] = 'error'
                article_detail['error'] = str(e)

        article_details.append(article_detail)

    _set_progress(task_id, {'stage': 'done', 'progress': 100,
                            'message': f'Selesai! {new_count} baru, {updated_count} update, {len(errors)} error — {skipped_existing} sudah ada di WP',
                            'total': len(new_articles), 'current': len(new_articles)})

    _sl.upload_done(uploaded=new_count + updated_count, failed=len(errors))
    _log_scraper(f"[{site_name}] Upload selesai: {new_count} baru, {updated_count} update, {len(errors)} error "
                 f"(skipped {skipped_existing} sudah ada, {skipped_no_content} tanpa konten)",
                 session.get('user_name', 'unknown'))

    _save_upload_history({
        'date': datetime.now().strftime('%Y-%m-%d'),
        'time': datetime.now().strftime('%H:%M'),
        'action': 'upload',
        'user': session.get('user_name', 'unknown'),
        'site': site_name,
        'total_scraped': len(articles),
        'total': len(new_articles),
        'skipped_existing': skipped_existing,
        'skipped_no_content': skipped_no_content,
        'new_posts': new_count,
        'updated_posts': updated_count,
        'errors': len(errors),
        'error_details': errors[:10],
        'articles': [{'title': a.get('title', ''), 'category': a.get('category', ''), 'date': a.get('publish_date', ''),
                      'source': a.get('source', ''), 'link': a.get('link', '')} for a in new_articles],
        'article_details': article_details,
    })

    ping_results = []
    if new_count > 0:
        base_url = wp_url.split('/wp-json')[0]
        ping_results = ping_sitemap(base_url)

    for detail in article_details:
        if detail.get('status') in ('new', 'updated') and detail.get('post_id'):
            track_performance(detail['post_id'], site_name, detail['title'])

    return {'ok': True, 'task_id': task_id, 'new_posts': new_count, 'updated_posts': updated_count,
            'skipped_existing': skipped_existing, 'skipped_no_content': skipped_no_content,
            'errors': errors, 'sitemap_ping': ping_results}


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

        task_id = request.args.get('task_id') or d.get('task_id')
        result = _upload_articles_to_site(site_name, articles, settings, task_id=task_id)
        status = result.pop('status', 200)
        return jsonify(result), status
    except Exception as e:
        return jsonify({'ok': False, 'error': f'Upload gagal: {str(e)}', 'new_posts': 0, 'updated_posts': 0, 'errors': []}), 500


@news_scraper_bp.route('/api/scraper/upload-multi', methods=['POST'])
@role_required(SCRAPER_ROLES)
def upload_articles_multi():
    """Upload scraped articles to MULTIPLE WordPress sites sequentially."""
    try:
        d = request.get_json(force=True)
        site_names = d.get('site_names', [])
        articles = d.get('articles', [])
        settings = d.get('settings', {})

        if not site_names:
            return jsonify({'error': 'Pilih minimal satu WordPress site'}), 400
        if not articles:
            return jsonify({'error': 'Tidak ada artikel untuk diupload'}), 400

        results = {}
        total_new = total_updated = 0
        all_errors = []

        for i, site_name in enumerate(site_names):
            site_name = (site_name or '').strip()
            if not site_name:
                continue
            _set_progress(f"multi_{int(time.time())}", {'stage': 'multi', 'progress': int((i / len(site_names)) * 100),
                                                        'message': f'Site {i+1}/{len(site_names)}: {site_name}',
                                                        'total': len(site_names), 'current': i})
            res = _upload_articles_to_site(site_name, articles, settings, task_prefix=f"upload_{re.sub(r'[^a-zA-Z0-9]', '_', site_name)}")
            ok = res.pop('ok', False)
            status = res.pop('status', 200)
            results[site_name] = {'ok': ok, **res}
            if ok:
                total_new += res.get('new_posts', 0)
                total_updated += res.get('updated_posts', 0)
                all_errors.extend([f"[{site_name}] {e}" for e in res.get('errors', [])])
            else:
                all_errors.append(f"[{site_name}] {res.get('error', 'unknown error')}")

        _log_scraper(f"Multi-upload selesai ({len(site_names)} sites): {total_new} baru, {total_updated} update",
                     session.get('user_name', 'unknown'))

        return jsonify({
            'ok': True,
            'results': results,
            'sites_total': len(site_names),
            'new_posts': total_new,
            'updated_posts': total_updated,
            'errors': all_errors,
        })
    except Exception as e:
        return jsonify({'ok': False, 'error': f'Multi-upload gagal: {str(e)}', 'new_posts': 0, 'updated_posts': 0, 'errors': []}), 500


# ----- DUPLICATE CHECKER -----

# Hard limit on pagination so a misbehaving site cannot loop forever.
_MAX_POST_PAGES = 50


def _fetch_all_posts(client, nonce, per_page=100, max_pages=_MAX_POST_PAGES):
    """Fetch every post from a WP site via paginated get_posts calls.

    Returns ``(posts, complete)``. ``complete`` is True only when pagination
    ended naturally: an empty page, a short page, or WP's own end-of-range
    signal (HTTP 400 ``rest_post_invalid_page_number``). Hitting ``max_pages``
    or a transport/server error marks the result incomplete, i.e. more posts
    may exist on the site.
    """
    posts = []
    page = 1
    while page <= max_pages:
        try:
            r = client.get_posts(nonce,
                                 params={'page': page, 'per_page': per_page,
                                         'orderby': 'date', 'order': 'desc'})
            if r.status_code == 400:
                # WP signals "page out of range" = we reached the end.
                return posts, True
            if r.status_code != 200:
                return posts, False
            page_posts = r.json()
            if not page_posts:
                return posts, True
            posts.extend(page_posts)
            if len(page_posts) < per_page:
                return posts, True
        except Exception:
            return posts, False
        page += 1
        time.sleep(0.1)
    return posts, False


def _normalized_post_title(post):
    """Canonical fuzzy key for a WP post title (entities, tags, punctuation,
    case and whitespace are all normalized away)."""
    raw = (post.get('title') or {}).get('rendered', '')
    return normalize_title(html.unescape(re.sub(r'<[^>]+>', '', raw)))


def _build_duplicate_groups(posts):
    """Kelompokkan post dengan judul ternormalisasi sama.

    Return list {key, title, keep_id, keep_date, delete_ids, delete_dates}.
    Di dalam grup post terurut TERBARU-dulu (elemen pertama = yang dipertahankan
    secara default), dan grup terurut dari yang paling banyak duplikatnya.
    """
    by_norm = {}
    for post in posts:
        key = _normalized_post_title(post)
        if not key:
            continue
        by_norm.setdefault(key, []).append(post)
    groups = []
    for key, plist in by_norm.items():
        if len(plist) < 2:
            continue
        plist.sort(key=lambda p: p.get('date', ''), reverse=True)
        groups.append({
            'key': key,
            'title': (plist[0].get('title') or {}).get('rendered', ''),
            'keep_id': plist[0]['id'],
            'keep_date': plist[0].get('date', ''),
            'delete_ids': [p['id'] for p in plist[1:]],
            'delete_dates': [p.get('date', '') for p in plist[1:]],
        })
    groups.sort(key=lambda g: len(g['delete_ids']), reverse=True)
    return groups


_DELETE_RETRY_BASE_SLEEP = 5   # detik; backoff 429/5xx (di-test dipatch ke 0)
_DELETE_WORKERS = 5            # thread hapus paralel (sama dgn delete-all)
_CLEANUP_LIMIT_PER_REQUEST = 150  # maks hapus per request cleanup (hindari timeout worker)


def _delete_post_force(client, base_url, nonce, pid, max_attempts=4):
    """Hapus permanen satu post (force=true) dengan retry utk 429/5xx.

    404/410 dianggap sukses (sudah terhapus — aman untuk run resume).
    Shared-host sering throttle bulk delete, jadi hormati Retry-After.
    """
    for attempt in range(max_attempts):
        try:
            r = client.request('DELETE', f"{base_url}/{pid}", nonce,
                               params={'force': True}, timeout=60)
            if r.status_code in (200, 404, 410):
                return True
            if r.status_code == 429 or r.status_code >= 500:
                wait = float((getattr(r, 'headers', {}) or {}).get('Retry-After')
                             or _DELETE_RETRY_BASE_SLEEP * attempt)
                time.sleep(min(wait, 30))
                continue
            return False
        except Exception:
            time.sleep(min(2 * attempt + 1, 10))
    return False


@news_scraper_bp.route('/api/scraper/duplicates', methods=['POST'])
@role_required(SCRAPER_ROLES)
def check_duplicates():
    """Check for duplicate articles on a WordPress site (fuzzy title match)."""
    try:
        d = request.get_json(force=True)
        site_name = (d.get('site_name') or '').strip()
        if not site_name:
            return jsonify({'error': 'Pilih WordPress site'}), 400

        sites = _load_json(WP_SITES_FILE, {})
        if site_name not in sites:
            return jsonify({'error': f'Site "{site_name}" tidak ditemukan'}), 404

        site = sites[site_name]
        client = _make_wp_client(site)
        login_ok, nonce_or_err = client.login()
        if not login_ok:
            return jsonify({'ok': False, 'error': f'Login gagal: {nonce_or_err}', 'duplicates': [], 'total_posts': 0}), 401

        posts, complete = _fetch_all_posts(client, nonce_or_err)

        # Group by normalized title so near-identical titles (HTML entities,
        # punctuation, case, stray whitespace) are detected as duplicates.
        # post_ids terurut TERBARU-dulu: elemen pertama = yang dipertahankan.
        duplicates = []
        for g in _build_duplicate_groups(posts):
            duplicates.append({
                'title': g['title'],
                'count': len(g['delete_ids']) + 1,
                'post_ids': [g['keep_id']] + g['delete_ids'],
                'dates': [g['keep_date']] + g['delete_dates'],
            })

        return jsonify({'ok': True, 'duplicates': duplicates, 'total_posts': len(posts)})
    except Exception as e:
        return jsonify({'ok': False, 'error': f'Cek duplikat gagal: {str(e)}', 'duplicates': [], 'total_posts': 0}), 500


@news_scraper_bp.route('/api/scraper/duplicates/delete', methods=['POST'])
@role_required(SCRAPER_ROLES)
def delete_duplicates():
    """Hapus duplikat dari grup yang diberikan.

    Semantik keep-TERBARU: post pertama tiap grup (post_ids[0], terbaru menurut
    check_duplicates) SELALU dipertahankan dan TIDAK BOLEH ikut terhapus bila
    klien mengirimnya — ini menutup bug lama di mana tombol "Hapus N" mengirim
    seluruh anggota grup sehingga artikel bisa hilang total.
    """
    d = request.get_json(force=True)
    site_name = (d.get('site_name') or '').strip()
    post_ids_to_delete = d.get('post_ids', [])
    keep_ids = set(d.get('keep_ids') or [])

    if not site_name or not post_ids_to_delete:
        return jsonify({'error': 'site_name dan post_ids wajib'}), 400

    sites = _load_json(WP_SITES_FILE, {})
    if site_name not in sites:
        return jsonify({'error': f'Site "{site_name}" tidak ditemukan'}), 404

    site = sites[site_name]
    client = _make_wp_client(site)
    login_ok, nonce_or_err = client.login()
    if not login_ok:
        return jsonify({'ok': False, 'error': f'Login gagal: {nonce_or_err}', 'deleted': 0}), 401

    protected = []
    deleted = 0
    failed = 0
    base = site['wp_url']
    for pid in post_ids_to_delete:
        if pid in keep_ids:
            protected.append(pid)
            continue
        if _delete_post_force(client, base, nonce_or_err, pid):
            deleted += 1
        else:
            failed += 1

    _log_scraper({
        'level': 'WARNING' if failed else 'INFO',
        'category': 'DELETE_ALL',
        'msg': f"Hapus duplikat: {deleted} post dihapus dari '{site_name}' "
               f"({failed} gagal, {len(protected)} dilindungi)",
        'extra': {
            'user': session.get('user_name', 'unknown'),
            'site': site_name,
            'deleted': deleted,
            'failed': failed,
            'protected': len(protected),
        },
    }, session.get('user_name', 'unknown'))
    return jsonify({'ok': True, 'deleted': deleted, 'failed': failed,
                    'protected': protected})


@news_scraper_bp.route('/api/scraper/duplicates/cleanup', methods=['POST'])
@role_required(SCRAPER_ROLES)
def cleanup_duplicates():
    """BULK: hapus SEMUA duplikat di satu site, simpan yang terbaru per grup.

    Ini aksi "hapus masal yang aman" (beda dgn delete-all yang mengosongkan
    site): hanya anggota grup duplikat selain post terbaru yang dihapus.
    `limit` membatasi jumlah hapus per request (default 150) supaya worker
    Flask tidak timeout — UI otomatis mengulang sampai bersih.
    """
    try:
        d = request.get_json(force=True) or {}
        site_name = (d.get('site_name') or '').strip()
        if not site_name:
            return jsonify({'error': 'Pilih WordPress site'}), 400
        try:
            limit = int(d.get('limit') or _CLEANUP_LIMIT_PER_REQUEST)
        except (TypeError, ValueError):
            limit = _CLEANUP_LIMIT_PER_REQUEST
        limit = max(1, min(limit, 500))
        keep_oldest = bool(d.get('keep_oldest', False))

        sites = _load_json(WP_SITES_FILE, {})
        if site_name not in sites:
            return jsonify({'error': f'Site "{site_name}" tidak ditemukan'}), 404

        site = sites[site_name]
        client = _make_wp_client(site)
        login_ok, nonce_or_err = client.login()
        if not login_ok:
            return jsonify({'ok': False, 'error': f'Login gagal: {nonce_or_err}', 'deleted': 0}), 401

        posts, complete = _fetch_all_posts(client, nonce_or_err)
        groups = _build_duplicate_groups(posts)
        if keep_oldest:
            for g in groups:
                g['keep_id'], g['keep_date'] = g['delete_ids'][-1], g['delete_dates'][-1]
                g['delete_ids'], g['delete_dates'] = g['delete_ids'][:-1], g['delete_dates'][:-1]
                g['delete_ids'] = [i for i in g['delete_ids'] if i != g['keep_id']]

        delete_ids = [pid for g in groups for pid in g['delete_ids']][:limit]
        remaining = max(0, (sum(len(g['delete_ids']) for g in groups)) - len(delete_ids))

        def _one(pid):
            return 1 if _delete_post_force(client, site['wp_url'], nonce_or_err, pid) else 0

        deleted = 0
        with ThreadPoolExecutor(max_workers=_DELETE_WORKERS) as pool:
            for ok in pool.map(_one, delete_ids):
                deleted += ok

        failed = len(delete_ids) - deleted
        _log_scraper({
            'level': 'WARNING' if failed else 'INFO',
            'category': 'DELETE_ALL',
            'msg': f"Cleanup duplikat '{site_name}': {deleted} dihapus "
                   f"({len(groups)} grup duplikat, {remaining} tersisa)",
            'extra': {
                'user': session.get('user_name', 'unknown'),
                'site': site_name,
                'deleted': deleted,
                'failed': failed,
                'remaining': remaining,
                'duplicate_groups': len(groups),
                'pagination_complete': complete,
                'keep': 'oldest' if keep_oldest else 'newest',
            },
        }, session.get('user_name', 'unknown'))
        return jsonify({
            'ok': True, 'deleted': deleted, 'failed': failed,
            'duplicate_groups': len(groups),
            'remaining': remaining,
            'total_posts': len(posts),
            'pagination_complete': complete,
        })
    except Exception as e:
        return jsonify({'ok': False, 'error': f'Cleanup duplikat gagal: {str(e)}', 'deleted': 0}), 500


# ----- DELETE ALL POSTS -----

_DELETE_ALL_CONFIRM = 'HAPUS SEMUA'   # token the client must echo back
_DELETE_ALL_CAP = 500                 # default safety cap
_DELETE_ALL_MAX_CAP = 2000            # absolute ceiling (opt-in via `cap`)
_DELETE_ALL_WORKERS = 5               # parallel delete threads


@news_scraper_bp.route('/api/scraper/duplicates/delete-all', methods=['POST'])
@role_required(SCRAPER_ROLES)
def delete_all_posts():
    """Delete ALL posts on a WordPress site.

    Extremely destructive, so it is triple-guarded: an explicit confirm
    token, a post-count cap (opt-in raisable up to _DELETE_ALL_MAX_CAP),
    and deletion runs through a small thread pool for speed.
    """
    try:
        d = request.get_json(force=True) or {}
        site_name = (d.get('site_name') or '').strip()
        if not site_name:
            return jsonify({'error': 'Pilih WordPress site'}), 400
        if (d.get('confirm') or '').strip().upper() != _DELETE_ALL_CONFIRM:
            return jsonify({'error': f'Konfirmasi wajib: kirim confirm="{_DELETE_ALL_CONFIRM}"'}), 400

        try:
            cap = int(d.get('cap') or _DELETE_ALL_CAP)
        except (TypeError, ValueError):
            cap = _DELETE_ALL_CAP
        cap = max(1, min(cap, _DELETE_ALL_MAX_CAP))

        sites = _load_json(WP_SITES_FILE, {})
        if site_name not in sites:
            return jsonify({'error': f'Site "{site_name}" tidak ditemukan'}), 404

        site = sites[site_name]
        client = _make_wp_client(site)
        login_ok, nonce_or_err = client.login()
        if not login_ok:
            return jsonify({'ok': False, 'error': f'Login gagal: {nonce_or_err}', 'deleted': 0}), 401

        posts, complete = _fetch_all_posts(client, nonce_or_err)
        if not posts:
            return jsonify({'ok': True, 'deleted': 0, 'total_posts': 0, 'truncated': False})
        if len(posts) > cap:
            return jsonify({
                'ok': False,
                'error': (f'Site memiliki {len(posts)} post (> cap {cap}). '
                          f'Naikkan cap (maks {_DELETE_ALL_MAX_CAP}) atau hapus bertahap.'),
                'total_posts': len(posts),
                'deleted': 0,
                'cap': cap,
            }), 400

        def _delete_one(pid):
            try:
                r = client.request('DELETE', f"{site['wp_url']}/{pid}", nonce_or_err,
                                   params={'force': True}, timeout=15)
                return 1 if r.status_code == 200 else 0
            except Exception:
                return 0

        deleted = 0
        with ThreadPoolExecutor(max_workers=_DELETE_ALL_WORKERS) as pool:
            for ok in pool.map(_delete_one, [p['id'] for p in posts]):
                deleted += ok

        user = session.get('user_name', 'unknown')
        _log_scraper({
            'level': 'WARNING' if deleted < len(posts) else 'INFO',
            'category': 'DELETE_ALL',
            'msg': f"Hapus semua: {deleted}/{len(posts)} post dihapus dari site '{site_name}'",
            'extra': {
                'user': user,
                'site': site_name,
                'deleted': deleted,
                'total_posts': len(posts),
                'failed': len(posts) - deleted,
                'truncated': not complete,
                'cap': cap,
            },
        }, user)
        return jsonify({'ok': True, 'deleted': deleted, 'total_posts': len(posts),
                        'truncated': not complete})
    except Exception as e:
        return jsonify({'ok': False, 'error': f'Hapus semua gagal: {str(e)}', 'deleted': 0}), 500


# ----- BACKLINKS MANAGEMENT -----

@news_scraper_bp.route('/api/scraper/backlinks', methods=['GET'])
@role_required(SCRAPER_ROLES)
def get_backlinks():
    bl = _load_json(BACKLINKS_FILE, {})
    return jsonify({
        'authority_sites': bl.get('authority_sites', DEFAULT_AUTHORITY_SITES),
        'keyword_mapping': bl.get('keyword_mapping', DEFAULT_KEYWORD_MAPPING),
    })


@news_scraper_bp.route('/api/scraper/backlinks', methods=['POST'])
@role_required(SCRAPER_ROLES)
def save_backlinks():
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
    logs = []
    limit = request.args.get('limit', 100, type=int)
    try:
        with open(SCRAPER_LOG_FILE, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    logs.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
    except (FileNotFoundError, OSError):
        pass
    # Also handle legacy JSON array format
    if not logs:
        logs = _load_json(SCRAPER_LOG_FILE, [])
    return jsonify(logs[-limit:])


@news_scraper_bp.route('/api/scraper/log', methods=['DELETE'])
@role_required(SCRAPER_ROLES)
def clear_scraper_log():
    _save_json(SCRAPER_LOG_FILE, [])
    return jsonify({'ok': True, 'message': 'Log cleared'})


# ----- PROGRESS -----

@news_scraper_bp.route('/api/scraper/progress/<task_id>', methods=['GET'])
@role_required(SCRAPER_ROLES)
def get_progress_route(task_id):
    """Get progress for a scrape/upload task (polling)."""
    data = _get_progress(task_id)
    if not data:
        return jsonify({'ok': False, 'error': 'Task tidak ditemukan'}), 404
    return jsonify({'ok': True, **data})


# ----- UPLOAD HISTORY -----

@news_scraper_bp.route('/api/scraper/history', methods=['GET'])
@role_required(SCRAPER_ROLES)
def get_upload_history_route():
    date_from = request.args.get('date_from', '')
    date_to = request.args.get('date_to', '')
    action = request.args.get('action', '')
    limit = request.args.get('limit', 50, type=int)

    history = _get_upload_history(date_from=date_from or None, date_to=date_to or None, action=action or None)
    history = list(reversed(history))[-limit:]
    return jsonify({'ok': True, 'history': history, 'total': len(history)})


@news_scraper_bp.route('/api/scraper/history', methods=['DELETE'])
@role_required(SCRAPER_ROLES)
def clear_upload_history():
    _save_json(UPLOAD_HISTORY_FILE, [])
    return jsonify({'ok': True, 'message': 'History cleared'})


# Note: scrape-multi endpoint removed — kontan.co.id (404) and bisnis.com (403)
# are not scrapable. Use /api/scraper/check for newsmaker.id only.


# ----- ANALYTICS -----

@news_scraper_bp.route('/api/scraper/analytics', methods=['GET'])
@role_required(SCRAPER_ROLES)
def get_analytics_route():
    date_from = request.args.get('date_from', '')
    date_to = request.args.get('date_to', '')
    analytics = get_analytics(date_from=date_from or None, date_to=date_to or None)
    return jsonify({'ok': True, **analytics})


# ----- SCHEDULE -----

@news_scraper_bp.route('/api/scraper/schedule', methods=['GET'])
@role_required(SCRAPER_ROLES)
def get_schedule():
    optimal_time = get_optimal_publish_time()
    analytics = get_analytics(date_from=datetime.now().strftime('%Y-%m-%d'))
    published_today = analytics.get('by_date', {}).get(datetime.now().strftime('%Y-%m-%d'), 0)
    settings = _load_json(SETTINGS_FILE, {})
    daily_limit = int(settings.get('daily_limit', 10))
    return jsonify({
        'ok': True,
        'optimal_time': optimal_time.strftime('%Y-%m-%d %H:%M'),
        'published_today': published_today,
        'can_publish': should_publish_today(published_today),
        'daily_limit': daily_limit,
    })


@news_scraper_bp.route('/api/scraper/schedule/list', methods=['GET'])
@role_required(SCRAPER_ROLES)
def list_scheduled_jobs():
    """List scheduled jobs."""
    jobs = _load_schedule()
    now = datetime.now().strftime('%Y-%m-%d %H:%M')
    for j in jobs:
        j['is_due'] = bool(j.get('scheduled_at') and j['scheduled_at'] <= now and j.get('status') == 'pending')
    jobs.sort(key=lambda j: j.get('scheduled_at', ''), reverse=True)
    return jsonify({'ok': True, 'jobs': jobs, 'total': len(jobs)})


@news_scraper_bp.route('/api/scraper/schedule/create', methods=['POST'])
@role_required(SCRAPER_ROLES)
def create_scheduled_job():
    """Create a scheduled job (scrape or upload at a future time)."""
    d = request.get_json(force=True)
    job_type = (d.get('job_type') or 'upload').strip()          # 'scrape' | 'upload'
    scheduled_at = (d.get('scheduled_at') or '').strip()        # 'YYYY-MM-DD HH:MM'
    site_name = (d.get('site_name') or '').strip()
    pages = d.get('pages', 1)
    settings = d.get('settings', {})

    if job_type not in ('scrape', 'upload'):
        return jsonify({'error': "job_type harus 'scrape' atau 'upload'"}), 400
    if not scheduled_at:
        return jsonify({'error': 'scheduled_at wajib (format YYYY-MM-DD HH:MM)'}), 400
    try:
        dt = datetime.strptime(scheduled_at, '%Y-%m-%d %H:%M')
    except ValueError:
        return jsonify({'error': 'Format scheduled_at salah — gunakan YYYY-MM-DD HH:MM'}), 400
    if dt <= datetime.now():
        return jsonify({'error': 'scheduled_at harus di masa depan'}), 400
    if job_type == 'upload' and not site_name:
        return jsonify({'error': 'site_name wajib untuk job upload'}), 400

    with _schedule_lock:
        jobs = _load_schedule()
        job = {
            'id': f"job_{int(time.time()*1000)}",
            'job_type': job_type,
            'scheduled_at': scheduled_at,
            'site_name': site_name,
            'pages': max(1, min(int(pages), 20)),
            'settings': settings,
            'status': 'pending',
            'created_by': session.get('user_name', 'unknown'),
            'created_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'result': None,
        }
        jobs.append(job)
        _save_schedule(jobs)

    _log_scraper(f"Scheduled job created: {job_type} @ {scheduled_at}", session.get('user_name', 'unknown'))

    # Background runner that executes due jobs
    def _run_job(job):
        try:
            if job['job_type'] == 'scrape':
                arts = scrape_newsmaker(job.get('pages', 1))
                with _schedule_lock:
                    fresh = _load_schedule()
                    for j in fresh:
                        if j['id'] == job['id']:
                            j['status'] = 'done'
                            j['result'] = {'articles_found': len(arts)}
                    _save_schedule(fresh)
            else:
                arts = scrape_newsmaker(job.get('pages', 1))
                res = _upload_articles_to_site(job['site_name'], arts, job.get('settings', {}), task_prefix='sched_upload')
                with _schedule_lock:
                    fresh = _load_schedule()
                    for j in fresh:
                        if j['id'] == job['id']:
                            j['status'] = 'done' if res.get('ok') else 'failed'
                            j['result'] = {k: v for k, v in res.items() if k != 'status'}
                    _save_schedule(fresh)
            _send_telegram(f"📰 Scraper job '{job['job_type']}' selesai ({job['scheduled_at']})")
        except Exception as e:
            with _schedule_lock:
                fresh = _load_schedule()
                for j in fresh:
                    if j['id'] == job['id']:
                        j['status'] = 'failed'
                        j['result'] = {'error': str(e)[:300]}
                _save_schedule(fresh)

    delay = max((dt - datetime.now()).total_seconds(), 0)
    threading.Timer(delay, _run_job, args=(dict(job),)).start()

    return jsonify({'ok': True, 'message': f'Job {job_type} dijadwalkan pada {scheduled_at}', 'job': job})


# ----- TELEGRAM NOTIFY -----

@news_scraper_bp.route('/api/scraper/notify', methods=['POST'])
@role_required(SCRAPER_ROLES)
def send_notification():
    """Send a Telegram notification."""
    d = request.get_json(force=True)
    message = (d.get('message') or '').strip()
    if not message:
        return jsonify({'ok': False, 'error': 'message wajib diisi'}), 400
    if len(message) > 4000:
        message = message[:4000]

    result = _send_telegram(message)
    if result.get('ok'):
        _log_scraper("Telegram notification sent", session.get('user_name', 'unknown'))
        return jsonify({'ok': True, 'message': 'Notifikasi Telegram terkirim'})
    return jsonify(result), 200


# ----- UPLOAD REPORT (per-article detail) -----

@news_scraper_bp.route('/api/scraper/report', methods=['GET'])
@role_required(SCRAPER_ROLES)
def get_upload_report():
    date_from = request.args.get('date_from', '')
    date_to = request.args.get('date_to', '')
    site_filter = request.args.get('site', '')
    status_filter = request.args.get('status', '')
    source_filter = request.args.get('source', '')
    search = request.args.get('search', '').lower()

    history = _load_json(UPLOAD_HISTORY_FILE, [])
    all_articles = []
    for entry in history:
        if entry.get('action') != 'upload':
            continue
        entry_date = entry.get('date', '')
        if date_from and entry_date < date_from:
            continue
        if date_to and entry_date > date_to:
            continue
        entry_site = entry.get('site', '')
        if site_filter and entry_site != site_filter:
            continue
        for detail in entry.get('article_details', []):
            detail['upload_date'] = entry_date
            detail['upload_time'] = entry.get('time', '')
            detail['upload_user'] = entry.get('user', '')
            detail['upload_site'] = entry_site
            if status_filter and detail.get('status', '') != status_filter:
                continue
            if source_filter and detail.get('source', '') != source_filter:
                continue
            if search and search not in (detail.get('title', '') + detail.get('category', '')).lower():
                continue
            all_articles.append(detail)

    all_articles.sort(key=lambda a: a.get('upload_date', ''), reverse=True)

    summary = {
        'total': len(all_articles),
        'new': sum(1 for a in all_articles if a.get('status') == 'new'),
        'updated': sum(1 for a in all_articles if a.get('status') == 'updated'),
        'error': sum(1 for a in all_articles if a.get('status') == 'error'),
        'avg_seo': round(sum(a.get('seo_score', 0) for a in all_articles) / max(len(all_articles), 1), 1),
    }

    sites_set = set()
    sources_set = set()
    for entry in history:
        if entry.get('action') == 'upload':
            sites_set.add(entry.get('site', ''))
            for art in entry.get('articles', []):
                if art.get('source'):
                    sources_set.add(art['source'])

    return jsonify({
        'ok': True,
        'articles': all_articles,
        'summary': summary,
        'filter_options': {
            'sites': sorted(sites_set),
            'sources': sorted(sources_set),
        },
    })


@news_scraper_bp.route('/api/scraper/report/export', methods=['GET'])
@role_required(SCRAPER_ROLES)
def export_report_csv():
    """Export upload report as CSV (with CSV-injection protection)."""
    date_from = request.args.get('date_from', '')
    date_to = request.args.get('date_to', '')
    site_filter = request.args.get('site', '')
    status_filter = request.args.get('status', '')
    source_filter = request.args.get('source', '')

    history = _load_json(UPLOAD_HISTORY_FILE, [])
    rows = []
    for entry in history:
        if entry.get('action') != 'upload':
            continue
        entry_date = entry.get('date', '')
        if date_from and entry_date < date_from:
            continue
        if date_to and entry_date > date_to:
            continue
        if site_filter and entry.get('site', '') != site_filter:
            continue
        for detail in entry.get('article_details', []):
            if status_filter and detail.get('status', '') != status_filter:
                continue
            if source_filter and detail.get('source', '') != source_filter:
                continue
            rows.append({
                'Tanggal': f"{entry_date} {entry.get('time', '')}",
                'Judul': detail.get('title', ''),
                'Kategori': detail.get('category', ''),
                'Sumber': detail.get('source', ''),
                'Status': detail.get('status', ''),
                'SEO Score': detail.get('seo_score', 0),
                'Site': entry.get('site', ''),
                'WP Post ID': detail.get('post_id', ''),
                'URL Source': detail.get('link', ''),
                'User': entry.get('user', ''),
            })

    output = io.StringIO()
    if rows:
        sanitized = [{k: _sanitize_csv(v) for k, v in row.items()} for row in rows]
        writer = csv.DictWriter(output, fieldnames=sanitized[0].keys())
        writer.writeheader()
        writer.writerows(sanitized)
    else:
        output.write('Tidak ada data untuk filter ini')

    return Response(
        output.getvalue(),
        mimetype='text/csv',
        headers={'Content-Disposition': f'attachment; filename=upload-report-{datetime.now().strftime("%Y%m%d")}.csv'}
    )


# ----- SETTINGS MANAGEMENT -----

@news_scraper_bp.route('/api/scraper/settings', methods=['GET'])
@role_required(SCRAPER_ROLES)
def get_scraper_settings():
    settings = _load_json(SETTINGS_FILE, {})
    return jsonify({
        'daily_limit': int(settings.get('daily_limit', 10)),
        'seo_optimize': settings.get('seo_optimize', True),
        'backlinks': settings.get('backlinks', True),
        'max_backlinks': settings.get('max_backlinks', 3),
        'static_tags': settings.get('static_tags', 'newsmaker.id, Detik Finance, Market, Financial News'),
        'rank_math_keywords': settings.get('rank_math_keywords', True),
    })


@news_scraper_bp.route('/api/scraper/settings', methods=['POST'])
@role_required(SCRAPER_ROLES)
def save_scraper_settings():
    d = request.get_json(force=True)
    settings = _load_json(SETTINGS_FILE, {})

    if 'daily_limit' in d:
        val = int(d['daily_limit'])
        settings['daily_limit'] = max(1, min(val, 100))
    if 'seo_optimize' in d:
        settings['seo_optimize'] = bool(d['seo_optimize'])
    if 'backlinks' in d:
        settings['backlinks'] = bool(d['backlinks'])
    if 'max_backlinks' in d:
        settings['max_backlinks'] = max(1, min(int(d['max_backlinks']), 10))
    if 'static_tags' in d:
        settings['static_tags'] = str(d['static_tags'])[:500]
    if 'rank_math_keywords' in d:
        settings['rank_math_keywords'] = bool(d['rank_math_keywords'])

    _save_json(SETTINGS_FILE, settings)
    _log_scraper(f'Settings updated: daily_limit={settings.get("daily_limit", 10)}', session.get('user_name', 'unknown'))
    return jsonify({'ok': True, 'settings': settings})

