"""
modules/news_scraper/routes.py
Flask route handlers for the news scraper module.
"""

import os, json, time, io, csv, re, threading
from datetime import datetime
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from flask import Blueprint, request, jsonify, session, Response

from modules.helpers import role_required

from . import (news_scraper_bp, DATA_DIR, WP_SITES_FILE, BACKLINKS_FILE,
    HYPERLINKS_FILE, SCRAPER_LOG_FILE, UPLOAD_HISTORY_FILE, SETTINGS_FILE,
    SCRAPER_ROLES, DEFAULT_AUTHORITY_SITES, DEFAULT_KEYWORD_MAPPING)
from .wp_client import get_wp_session, WpClient
from .scraper_engine import scrape_newsmaker, scrape_detik_finance, fetch_article_content, RateLimiter, ProgressTracker
from .seo_optimizer import (apply_backlinks, build_article_html, seo_analyze, build_advanced_schema,
    ping_sitemap, track_performance, get_analytics, get_optimal_publish_time, should_publish_today,
    JsonCache, normalize_title, rewrite_content)


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
    """Append an entry to the scraper activity log."""
    logs = _load_json(SCRAPER_LOG_FILE, [])
    logs.append({
        'time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'user': user,
        'message': message,
    })
    _save_json(SCRAPER_LOG_FILE, logs[-2000:])


# Rate limiter: 5 scrape requests / minute per user
_scrape_rate_limiter = RateLimiter(max_calls=5, per_seconds=60)

# In-memory progress trackers keyed by task_id
_progress_trackers = {}
_progress_lock = threading.Lock()


def _get_tracker(task_id):
    with _progress_lock:
        if task_id not in _progress_trackers:
            _progress_trackers[task_id] = ProgressTracker(task_id)
        # Prune old trackers (keep last 50)
        if len(_progress_trackers) > 50:
            for k in list(_progress_trackers.keys())[:-50]:
                del _progress_trackers[k]
        return _progress_trackers[task_id]


def _set_progress(task_id, data):
    tracker = _get_tracker(task_id)
    tracker.update(
        stage=data.get('stage', ''),
        progress=data.get('progress', 0),
        message=data.get('message', ''),
        total=data.get('total', 0),
        current=data.get('current', 0),
    )


def _get_progress(task_id):
    with _progress_lock:
        tracker = _progress_trackers.get(task_id)
    if not tracker:
        return None
    return tracker.snapshot()


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
    user_branch = session.get('branch_code', '')
    user_role = session.get('user_role', '')
    result = []
    for name, data in sites.items():
        is_hq = session.get('user_name', '') in ('it_hu', 'admin')
        if user_role == 'admin' or is_hq:
            result.append({
                'name': name, 'wp_url': data.get('wp_url', ''),
                'wp_media_url': data.get('wp_media_url', ''),
                'username': data.get('username', ''),
                'app_password': data.get('app_password', ''),
                'branch_code': data.get('branch_code', ''),
            })
        else:
            site_branch = data.get('branch_code', '')
            if not site_branch:
                name_lower = name.lower()
                if user_branch.lower() in name_lower:
                    site_branch = user_branch
            if site_branch == user_branch:
                result.append({
                    'name': name, 'wp_url': data.get('wp_url', ''),
                    'wp_media_url': data.get('wp_media_url', ''),
                    'username': data.get('username', ''),
                    'app_password': data.get('app_password', ''),
                    'branch_code': data.get('branch_code', ''),
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
        client = WpClient(wp_url, username, app_password)
        login_ok, nonce_or_err = client.login()
        if not login_ok:
            return jsonify({'ok': False, 'message': f'Login gagal: {nonce_or_err}'}), 200
        r = client.request('GET', params={"per_page": 1}, timeout=10)
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
    allowed, retry_after = _scrape_rate_limiter.check(user)
    if not allowed:
        return jsonify({'ok': False, 'error': f'Rate limit tercapai (5/menit). Coba lagi dalam {retry_after}s.'}), 429

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

        if source in ('all', 'newsmaker'):
            _set_progress(task_id, {'stage': 'scrape', 'progress': 5, 'message': 'Scrape Newsmaker.id...', 'total': pages, 'current': 0})
            try:
                newsmaker_articles = scrape_newsmaker(pages)
                for a in newsmaker_articles:
                    if a['link'] not in seen_links:
                        seen_links.add(a['link'])
                        articles.append(a)
            except Exception:
                pass

        if source in ('all', 'detik'):
            _set_progress(task_id, {'stage': 'scrape', 'progress': 50, 'message': 'Scrape Detik Finance...', 'total': 1, 'current': 0})
            try:
                detik_articles = scrape_detik_finance(pages)
                for a in detik_articles:
                    if a['link'] not in seen_links:
                        seen_links.add(a['link'])
                        articles.append(a)
            except Exception:
                pass

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

def _upload_articles_to_site(site_name, articles, settings, task_prefix='upload'):
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
    task_id = f"{task_prefix}_{int(time.time())}"
    _set_progress(task_id, {'stage': 'login', 'progress': 5, 'message': 'Login ke WordPress...', 'total': len(articles), 'current': 0})

    client = WpClient(wp_url, site['username'], site['app_password'])
    login_ok, nonce_or_err = client.login()
    if not login_ok:
        return {'ok': False, 'status': 401, 'error': f'WordPress login gagal: {nonce_or_err}',
                'new_posts': 0, 'updated_posts': 0, 'errors': [], 'task_id': task_id}
    _set_progress(task_id, {'stage': 'login', 'progress': 10, 'message': 'Login berhasil! Memeriksa existing posts...',
                            'total': len(articles), 'current': 0})

    enable_backlinks = settings.get('backlinks', True)
    max_backlinks = settings.get('max_backlinks', 3)
    enable_seo = settings.get('seo_optimize', True)
    static_tags = settings.get('static_tags', 'newsmaker.id, Detik Finance, Market, Financial News')

    bl_config = _load_json(BACKLINKS_FILE, {})
    authority_sites = bl_config.get('authority_sites', DEFAULT_AUTHORITY_SITES)
    keyword_mapping = bl_config.get('keyword_mapping', DEFAULT_KEYWORD_MAPPING)

    existing_titles = set()
    existing_posts = {}
    try:
        for page in range(1, 6):
            r = client.request('GET', params={"per_page": 100, "page": page, "orderby": "date", "order": "desc"}, timeout=30)
            if r.status_code != 200 or not r.json():
                break
            for post in r.json():
                t = post.get('title', {}).get('rendered', '')
                existing_titles.add(t)
                existing_posts[t] = post.get('id')
            if len(r.json()) < 100:
                break
            time.sleep(0.2)
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
            source_backlink = f'<p style="margin-top:20px;padding:12px;background:#f0f9ff;border:1px solid #bae6fd;border-radius:8px;font-size:13px;color:#0369a1;">📰 Sumber asli: <a href="{source_url}" target="_blank" rel="nofollow noopener" style="color:#0284c7;font-weight:600;">{source_name}</a></p>'
            if '<!-- BPF CTA Widget -->' in html_content:
                html_content = html_content.replace('<!-- BPF CTA Widget -->', source_backlink + '<!-- BPF CTA Widget -->')
            else:
                html_content += source_backlink

        tag_input = [t.strip().capitalize() for t in static_tags.split(',') if t.strip()]
        title_words = [w.capitalize() for w in title.lower().split()
                       if w not in {'dan', 'di', 'ke', 'dari', 'yang', 'untuk', 'dengan', 'ini', 'itu'} and len(w) > 3]
        all_tags = list(set(tag_input + title_words[:5]))

        tag_ids = []
        tags_url = wp_url.replace('/posts', '/tags')
        for tag_name in all_tags:
            try:
                r = client.request('GET', full_url=tags_url, nonce=nonce_or_err, params={"search": tag_name}, timeout=10)
                if r.status_code == 200 and r.json():
                    tag_ids.append(r.json()[0]['id'])
                else:
                    r2 = client.request('POST', full_url=tags_url, nonce=nonce_or_err, json={"name": tag_name}, timeout=10)
                    if r2.status_code == 201:
                        tag_ids.append(r2.json()['id'])
            except Exception as e:
                print(f'[scraper-tag] Failed to create tag "{tag_name}": {e}')

        schemas = build_advanced_schema(title, content, publish_date, publish_time, article.get('image_url', ''))
        schema_tags = ''.join(f'<script type="application/ld+json">{json.dumps(s, ensure_ascii=False)}</script>' for s in schemas)
        html_content = schema_tags + html_content

        featured_img_html = ''
        featured_media_id = 0
        image_url = article.get('image_url', '')
        if image_url:
            wp_media = client.upload_image(image_url)
            if wp_media:
                featured_img_html = wp_media.get('html', '')
                featured_media_id = wp_media.get('id', 0)
                html_content = featured_img_html + html_content

        post_data = {
            'title': title,
            'content': html_content,
            'status': 'publish',
            'date': f"{publish_date}T{publish_time}:00",
            'tags': tag_ids,
            'featured_media': featured_media_id,
        }

        is_duplicate = False
        matched_post_id = None
        norm_title = normalize_title(title)
        for et in existing_titles:
            if title == et or norm_title == normalize_title(et):
                is_duplicate = True
                matched_post_id = existing_posts.get(et)
                break

        progress_pct = 10 + int(((idx + 1) / len(articles)) * 85)
        status_msg = '🔄 Update' if is_duplicate else '⏳ Upload'
        _set_progress(task_id, {'stage': 'upload', 'progress': progress_pct,
                                'message': f'{status_msg} [{idx+1}/{len(articles)}] {title[:50]}...',
                                'total': len(articles), 'current': idx + 1})

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
                r2 = client.request('POST', full_url=f"{wp_url}/{matched_post_id}", nonce=nonce_or_err, json=update_data)
                if r2.status_code == 200:
                    updated_count += 1
                    article_detail['status'] = 'updated'
                    article_detail['post_id'] = matched_post_id
                else:
                    errors.append(f"{title}: update HTTP {r2.status_code}")
                    article_detail['status'] = 'error'
                    article_detail['error'] = f'HTTP {r2.status_code}'
            except Exception as e:
                errors.append(f"{title}: {str(e)}")
                article_detail['status'] = 'error'
                article_detail['error'] = str(e)
        elif is_duplicate:
            try:
                r = client.request('GET', nonce=nonce_or_err, params={"per_page": 10, "search": title}, timeout=15)
                if r.status_code == 200:
                    for post in r.json():
                        if normalize_title(post.get('title', {}).get('rendered', '')) == norm_title:
                            update_data = {'content': html_content, 'tags': tag_ids}
                            if featured_media_id:
                                update_data['featured_media'] = featured_media_id
                            r2 = client.request('POST', full_url=f"{wp_url}/{post['id']}", nonce=nonce_or_err, json=update_data)
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
                r = client.request('POST', nonce=nonce_or_err, json=post_data, timeout=30)
                if r.status_code == 201:
                    new_count += 1
                    article_detail['status'] = 'new'
                    article_detail['post_id'] = r.json().get('id')
                    article_detail['seo_score'] = seo_score
                else:
                    errors.append(f"{title}: HTTP {r.status_code}")
                    article_detail['status'] = 'error'
                    article_detail['error'] = f'HTTP {r.status_code}'
            except Exception as e:
                errors.append(f"{title}: {str(e)}")
                article_detail['status'] = 'error'
                article_detail['error'] = str(e)

        article_details.append(article_detail)

    _set_progress(task_id, {'stage': 'done', 'progress': 100,
                            'message': f'Selesai! {new_count} baru, {updated_count} update, {len(errors)} error',
                            'total': len(articles), 'current': len(articles)})

    _log_scraper(f"[{site_name}] Upload selesai: {new_count} baru, {updated_count} update, {len(errors)} error",
                 session.get('user_name', 'unknown'))

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
        'articles': [{'title': a.get('title', ''), 'category': a.get('category', ''), 'date': a.get('publish_date', ''),
                      'source': a.get('source', ''), 'link': a.get('link', '')} for a in articles],
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

        result = _upload_articles_to_site(site_name, articles, settings)
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
        client = WpClient(site['wp_url'], site['username'], site['app_password'])
        login_ok, nonce_or_err = client.login()
        if not login_ok:
            return jsonify({'ok': False, 'error': f'Login gagal: {nonce_or_err}', 'duplicates': [], 'total_posts': 0}), 401

        posts = []
        page = 1
        while True:
            try:
                r = client.request('GET', nonce=nonce_or_err,
                                   params={'page': page, 'per_page': 100, 'orderby': 'date', 'order': 'desc'}, timeout=30)
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
    client = WpClient(site['wp_url'], site['username'], site['app_password'])
    login_ok, nonce_or_err = client.login()
    if not login_ok:
        return jsonify({'ok': False, 'error': f'Login gagal: {nonce_or_err}', 'deleted': 0}), 401

    deleted = 0
    for pid in post_ids_to_delete:
        try:
            r = client.request('DELETE', full_url=f"{site['wp_url']}/{pid}", nonce=nonce_or_err,
                               params={'force': True}, timeout=15)
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
    logs = _load_json(SCRAPER_LOG_FILE, [])
    limit = request.args.get('limit', 100, type=int)
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

    _save_json(SETTINGS_FILE, settings)
    _log_scraper(f'Settings updated: daily_limit={settings.get("daily_limit", 10)}', session.get('user_name', 'unknown'))
    return jsonify({'ok': True, 'settings': settings})

