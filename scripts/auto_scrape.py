#!/usr/bin/env python3
"""Auto-scrape newsmaker.id + upload ke semua site WordPress aktif.

Dipanggil oleh cron container tiap jam 06,10,14,18 WIB (lihat Dockerfile).
Log: /app/data/news_scraper/auto_scrape.log.

v2.45.1: pre-filter duplikat kini memakai _fetch_all_posts (paginasi PINUH,
sinkron dengan perbaikan routes.py) — dulu hanya 1.000 post terbaru sehingga
artikel lama di-upload ulang sebagai duplikat. Ditambah dedup intra-batch.
"""
import json
import sys
import time

sys.path.insert(0, '/app')

from modules.news_scraper.scraper_engine import scrape_newsmaker, fetch_article_content
from modules.news_scraper.wp_client import WpClient
from modules.news_scraper.seo_optimizer import (
    rewrite_content, build_article_html, seo_analyze,
    apply_backlinks, normalize_title
)
from modules.news_scraper.routes import _fetch_all_posts, _build_excerpt
from modules.news_scraper import WP_SITES_FILE, BACKLINKS_FILE, DEFAULT_AUTHORITY_SITES, DEFAULT_KEYWORD_MAPPING
from modules.news_scraper.scraper_logger import get_logger

_sl = get_logger()


def load_json(p, d):
    try:
        with open(p) as f:
            return json.load(f)
    except Exception:
        return d


def main():
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

    # 2b. Dedup intra-batch: judul sama dalam satu batch hanya diproses 1x.
    seen_norm = set()
    deduped = []
    for a in ready:
        nt = normalize_title(a.get('title', ''))
        if nt and nt in seen_norm:
            continue
        if nt:
            seen_norm.add(nt)
        deduped.append(a)
    if len(deduped) != len(ready):
        _sl.log('INFO', 'AUTO', f'Dedup intra-batch: {len(ready)} -> {len(deduped)}')
    ready = deduped

    if not ready:
        _sl.log('WARNING', 'AUTO', 'No articles with content — aborting')
        print('No articles ready', flush=True)
        return

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
        bu = (site_data.get('basic_username') or '').strip()
        bp = (site_data.get('basic_password') or '').strip()
        if bu and bp:
            fallback = (bu, bp)

        client = WpClient(site_data['wp_url'], site_data['username'], site_data['app_password'],
                          fallback_auth=fallback)
        ok, msg = client.login()
        if not ok:
            _sl.log('ERROR', 'AUTO', f'{site_name} login failed: {msg}')
            continue

        # Fetch existing posts — paginasi PINUH (bukan cuma 1000 terbaru).
        # Kegagalan dicatat; tanpa daftar existing yang andal upload berhenti
        # (dulu: diam-diam lanjut dan membuat duplikat).
        try:
            existing_posts, complete = _fetch_all_posts(client, msg)
        except Exception as e:
            _sl.log('ERROR', 'AUTO', f'{site_name} gagal ambil existing posts: {str(e)[:200]} — skip site')
            continue
        existing = {}
        for p in existing_posts:
            nt = normalize_title(p.get('title', {}).get('rendered', ''))
            if nt:
                existing[nt] = p.get('id')
        if not complete:
            _sl.log('WARNING', 'AUTO',
                    f'{site_name}: paginasi existing TIDAK lengkap '
                    f'({len(existing)} post terindeks) — lanjut dgn indeks parsial')

        # Pre-filter: only process articles NOT on WP
        new_arts = [a for a in ready if normalize_title(a.get('title', '')) not in existing]
        print(f'  {len(new_arts)} new articles (skipped {len(ready) - len(new_arts)} already on WP)', flush=True)

        site_new = site_upd = site_err = 0
        for art in new_arts:
            title = art.get('title', '')
            content = rewrite_content(art.get('content', ''), title)
            pd = art.get('publish_date', time.strftime('%Y-%m-%d'))
            pt = art.get('publish_time', '') or '08:00'
            html = build_article_html(title, content, art, pd, pt)
            a = seo_analyze(html, title)
            html, _ = apply_backlinks(html, title, auth, km, 3)

            tags = [t.strip().capitalize() for t in 'newsmaker.id,Market,Financial News'.split(',') if t.strip()]
            tw = [w.capitalize() for w in title.lower().split()
                  if w not in {'dan', 'di', 'ke', 'dari', 'yang', 'untuk', 'dengan', 'ini', 'itu'} and len(w) > 3]
            all_tags = list(set(tags + tw[:5]))
            tids = []
            for tn in all_tags:
                try:
                    tid = client.get_or_create_tag(tn, msg)
                    if tid:
                        tids.append(tid)
                except Exception:
                    pass

            nt = normalize_title(title)
            is_dup = nt in existing
            pid = existing.get(nt)

            try:
                post_data = {'title': title, 'content': html,
                             # Excerpt polos utk meta description Rank Math (sinkron routes.py).
                             'excerpt': _build_excerpt(content),
                             'status': 'publish',
                             'date': f'{pd}T{pt}:00', 'tags': tids, 'featured_media': 0}

                if len(html.encode('utf-8')) > 120 * 1024:
                    se = html.rfind('<!-- BPF CTA Widget -->')
                    if se > 0:
                        html = html[:se]
                    html = html[:120 * 1024].rsplit(chr(10), 1)[0] + chr(10) + '</article>'
                    post_data['content'] = html

                if is_dup and pid:
                    r = client.update_post(pid, {'content': html, 'tags': tids}, msg)
                    if r.status_code == 200:
                        site_upd += 1
                    else:
                        site_err += 1
                elif not is_dup:
                    r = client.create_post(post_data, msg)
                    if r.status_code == 201:
                        site_new += 1
                        # Registrasi post baru → judul sama berikutnya tidak di-create lagi.
                        existing[nt] = r.json().get('id')
                    else:
                        site_err += 1
                time.sleep(0.3)
            except Exception:
                site_err += 1

        total_new += site_new
        total_upd += site_upd
        total_err += site_err
        _sl.log('INFO', 'AUTO', f'{site_name}: {site_new} new, {site_upd} update, {site_err} errors')
        print(f'  {site_name}: {site_new} new, {site_upd} update, {site_err} errors', flush=True)

    _sl.log('INFO', 'AUTO', f'Auto-scrape done: {total_new} new, {total_upd} update, {total_err} errors')
    print(f'DONE: {total_new} new, {total_upd} update, {total_err} errors', flush=True)


if __name__ == '__main__':
    main()
