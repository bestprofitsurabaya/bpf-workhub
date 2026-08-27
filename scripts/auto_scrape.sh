#!/bin/bash
# auto_scrape.sh — Auto-scrape new articles and upload to WordPress
# Runs via cron (e.g., every 4 hours during business hours)
# Log output: /app/data/news_scraper/auto_scrape.log

set -e
cd /app
LOG="/app/data/news_scraper/auto_scrape.log"
LOCK="/tmp/auto_scrape.lock"

# Prevent overlapping runs
if [ -f "$LOCK" ]; then
    pid=$(cat "$LOCK" 2>/dev/null)
    if kill -0 "$pid" 2>/dev/null; then
        echo "[$(date '+%Y-%m-%d %H:%M:%S')] SKIP: previous run still active (PID $pid)" >> "$LOG"
        exit 0
    fi
fi
echo $$ > "$LOCK"
trap 'rm -f "$LOCK"' EXIT

echo "[$(date '+%Y-%m-%d %H:%M:%S')] Starting auto-scrape..." >> "$LOG"

python3 -u -c "
import sys, os, json, time
sys.path.insert(0, '/app')

from modules.news_scraper.scraper_engine import scrape_newsmaker, fetch_article_content
from modules.news_scraper.wp_client import WpClient
from modules.news_scraper.seo_optimizer import (
    rewrite_content, build_article_html, seo_analyze,
    apply_backlinks, normalize_title
)
from modules.news_scraper import WP_SITES_FILE, BACKLINKS_FILE, DEFAULT_AUTHORITY_SITES, DEFAULT_KEYWORD_MAPPING
from modules.news_scraper.scraper_logger import get_logger

_sl = get_logger()

def load_json(p, d):
    try:
        with open(p) as f: return json.load(f)
    except: return d

# 1. Scrape
_sl.log('INFO', 'AUTO', 'Auto-scrape started')
articles = scrape_newsmaker(pages=1)
_sl.log('INFO', 'AUTO', f'Found {len(articles)} articles')

# 2. Fetch content
for a in articles:
    fetch_article_content(a)
    time.sleep(0.3)

ready = [a for a in articles if a.get('content') and a['content'] != 'Content not found']
_sl.log('INFO', 'AUTO', f'{len(ready)} articles with content ready')

if not ready:
    _sl.log('WARNING', 'AUTO', 'No articles with content — aborting')
    print('No articles ready', flush=True)
    sys.exit(0)

# 3. Load sites
sites = load_json(WP_SITES_FILE, {})
bl = load_json(BACKLINKS_FILE, {})
auth = bl.get('authority_sites', DEFAULT_AUTHORITY_SITES)
km = bl.get('keyword_mapping', DEFAULT_KEYWORD_MAPPING)

# Upload to each active site
total_new = total_upd = total_err = 0

for site_name, site_data in sites.items():
    if site_data.get('username') in ('PENDING', '', None):
        continue
    if site_data.get('app_password') in ('PENDING', '', None):
        continue

    print(f'Uploading to {site_name}...', flush=True)
    fallback = None
    bu = site_data.get('basic_username', '').strip()
    bp = site_data.get('basic_password', '').strip()
    if bu and bp:
        fallback = (bu, bp)

    client = WpClient(site_data['wp_url'], site_data['username'], site_data['app_password'],
                      fallback_auth=fallback)
    ok, msg = client.login()
    if not ok:
        _sl.log('ERROR', 'AUTO', f'{site_name} login failed: {msg}')
        continue

    # Fetch existing posts
    existing = {}
    for page in range(1, 6):
        r = client.session.get(f'{client.wp_url}/wp-json/wp/v2/posts',
                               auth=client.active_auth,
                               params={'per_page': 100, 'page': page, 'orderby': 'date', 'order': 'desc'},
                               timeout=30)
        if r.status_code != 200 or not r.json(): break
        for p in r.json():
            nt = normalize_title(p.get('title', {}).get('rendered', ''))
            existing[nt] = p.get('id')
        if len(r.json()) < 100: break
        time.sleep(0.1)

    site_new = site_upd = site_err = 0
    for art in ready:
        title = art.get('title', '')
        content = rewrite_content(art.get('content', ''), title)
        pd = art.get('publish_date', time.strftime('%Y-%m-%d'))
        pt = art.get('publish_time', '') or '08:00'
        html = build_article_html(title, content, art, pd, pt)
        a = seo_analyze(html, title)
        html, _ = apply_backlinks(html, title, auth, km, 3)

        tags = [t.strip().capitalize() for t in 'newsmaker.id,Market,Financial News'.split(',') if t.strip()]
        tw = [w.capitalize() for w in title.lower().split()
              if w not in {'dan','di','ke','dari','yang','untuk','dengan','ini','itu'} and len(w) > 3]
        all_tags = list(set(tags + tw[:5]))
        tids = []
        for tn in all_tags:
            try:
                tid = client.get_or_create_tag(tn, client.active_auth[1])
                if tid: tids.append(tid)
            except: pass

        nt = normalize_title(title)
        is_dup = nt in existing
        pid = existing.get(nt)

        try:
            post_data = {'title': title, 'content': html, 'status': 'publish',
                         'date': f'{pd}T{pt}:00', 'tags': tids, 'featured_media': 0}

            if len(html.encode('utf-8')) > 120 * 1024:
                se = html.rfind('<!-- BPF CTA Widget -->')
                if se > 0: html = html[:se]
                html = html[:120*1024].rsplit(chr(10), 1)[0] + chr(10) + '</article>'
                post_data['content'] = html

            if is_dup and pid:
                r = client.update_post(pid, {'content': html, 'tags': tids}, client.active_auth[1])
                if r.status_code == 200:
                    site_upd += 1
                else:
                    site_err += 1
            elif not is_dup:
                r = client.create_post(post_data, client.active_auth[1])
                if r.status_code == 201:
                    site_new += 1
                    existing[nt] = r.json().get('id')
                else:
                    site_err += 1
            time.sleep(0.3)
        except Exception as e:
            site_err += 1

    total_new += site_new
    total_upd += site_upd
    total_err += site_err
    _sl.log('INFO', 'AUTO', f'{site_name}: {site_new} new, {site_upd} update, {site_err} errors')
    print(f'  {site_name}: {site_new} new, {site_upd} update, {site_err} errors', flush=True)

_sl.log('INFO', 'AUTO', f'Auto-scrape done: {total_new} new, {total_upd} update, {total_err} errors')
print(f'DONE: {total_new} new, {total_upd} update, {total_err} errors', flush=True)
" >> "$LOG" 2>&1

echo "[$(date '+%Y-%m-%d %H:%M:%S')] Auto-scrape finished" >> "$LOG"
