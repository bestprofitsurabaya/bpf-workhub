#!/usr/bin/env python3
"""Cleanup duplicate WordPress posts for the news scraper.

Bypasses the Flask layer (and the delete-all post-count cap) and reuses the
same duplicate-detection logic as the /api/scraper/duplicates endpoints:
titles are normalized via normalize_title() so near-identical titles
(HTML entities, punctuation, case, whitespace) count as duplicates.

Default is a DRY RUN (report only). Pass --apply to permanently delete
(force=true) all but one post per duplicate group.

Usage:
    python3 scripts/cleanup_wp_duplicates.py --site "BPF Surabaya"            # dry run
    python3 scripts/cleanup_wp_duplicates.py --site "BPF Surabaya" --apply    # delete
"""
import argparse
import html
import json
import os
import re
import sys
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from modules.news_scraper import WP_SITES_FILE
from modules.news_scraper.wp_client import WpClient
from modules.news_scraper.seo_optimizer import normalize_title

PER_PAGE = 100
MAX_PAGES = 150          # generous; 5000 posts = 50 pages
DELETE_WORKERS = 8       # WP handles this fine; keeps chunks under tool timeouts


def load_sites():
    with open(WP_SITES_FILE, 'r', encoding='utf-8') as f:
        return json.load(f)


def make_client(site):
    """Same credential chain as routes._make_wp_client (app password, then
    optional basic-auth fallback) without importing the Flask app."""
    fallback = None
    bu = (site.get('basic_username') or '').strip()
    bp = (site.get('basic_password') or '').strip()
    if bu and bp:
        fallback = (bu, bp)
    return WpClient(site['wp_url'], site['username'], site['app_password'],
                    fallback_auth=fallback)


def fetch_all_posts(client, max_pages=MAX_PAGES):
    """Paginated fetch, same end-of-range handling as routes._fetch_all_posts."""
    posts, page = [], 1
    while page <= max_pages:
        r = client.get_posts(None,
                             params={'page': page, 'per_page': PER_PAGE,
                                     'orderby': 'date', 'order': 'desc'})
        if r.status_code == 400:      # WP: page out of range = end of list
            return posts, True
        if r.status_code != 200:
            raise RuntimeError(f'get_posts page {page} -> HTTP {r.status_code}: {r.text[:200]}')
        page_posts = r.json()
        if not page_posts:
            return posts, True
        posts.extend(page_posts)
        if len(page_posts) < PER_PAGE:
            return posts, True
        page += 1
        time.sleep(0.1)
    return posts, False


def norm_key(post):
    raw = (post.get('title') or {}).get('rendered', '')
    return normalize_title(html.unescape(re.sub(r'<[^>]+>', '', raw)))


def build_groups(posts):
    """Group posts by normalized title. Within a group, posts stay ordered
    newest-first (fetch is date-desc; re-sorted defensively by date)."""
    by_norm = {}
    for post in posts:
        key = norm_key(post)
        if not key:
            continue
        by_norm.setdefault(key, []).append(post)
    groups = []
    for key, plist in by_norm.items():
        if len(plist) < 2:
            continue
        plist.sort(key=lambda p: p.get('date', ''), reverse=True)  # newest first
        groups.append({
            'title': (plist[0].get('title') or {}).get('rendered', ''),
            'keep_id': plist[0]['id'],
            'keep_date': plist[0].get('date', ''),
            'delete_ids': [p['id'] for p in plist[1:]],
            'delete_dates': [p.get('date', '') for p in plist[1:]],
        })
    groups.sort(key=lambda g: len(g['delete_ids']), reverse=True)
    return groups


def delete_posts(client, site, ids, workers=DELETE_WORKERS, delay=0.0):
    """Permanent delete (force=true) with a small worker pool, mirroring the
    delete-all endpoint. 404/410 count as success (already deleted, e.g. when
    resuming an interrupted run). 429/5xx are retried with back-off honoring
    Retry-After (shared hosts throttle bulk deletes). Returns (deleted, failed_ids)."""
    base = site['wp_url']

    def _one(pid):
        for attempt in range(4):
            try:
                r = client.request('DELETE', f'{base}/{pid}', None,
                                   params={'force': True}, timeout=60)
                if r.status_code in (200, 404, 410):
                    return pid, True
                if r.status_code == 429 or r.status_code >= 500:
                    wait = float(r.headers.get('Retry-After') or 10 * attempt + 5)
                    print(f'  ⏳ #{pid} HTTP {r.status_code}, backoff {wait:.0f}s')
                    time.sleep(wait)
                    continue
                print(f'  ✗ #{pid} HTTP {r.status_code}: {r.text[:80]}')
                break  # other 4xx: permanent failure
            except Exception as exc:
                print(f'  ✗ #{pid} error: {type(exc).__name__}: {str(exc)[:80]}')
                time.sleep(2 * attempt + 1)
        return pid, False

    deleted, failed = 0, []
    done = 0
    with ThreadPoolExecutor(max_workers=workers) as pool:
        for pid, ok in pool.map(_one, ids):
            done += 1
            if ok:
                deleted += 1
            else:
                failed.append(pid)
            if delay:
                time.sleep(delay)
            if done % 25 == 0:
                print(f'  ... {done}/{len(ids)} diproses, {deleted} sukses')
    return deleted, failed


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--site', required=True, help='Site name from wp_sites.json')
    ap.add_argument('--keep', choices=['newest', 'oldest'], default='newest',
                    help='Which post to keep per duplicate group (default: newest)')
    ap.add_argument('--apply', action='store_true',
                    help='Actually delete (default: dry run, report only)')
    ap.add_argument('--from-report', action='store_true',
                    help='Delete ids from an existing report without re-fetching '
                         '(resume mode; 404s counted as already deleted)')
    ap.add_argument('--offset', type=int, default=0,
                    help='Skip first N ids of the delete list (chunked resume)')
    ap.add_argument('--limit', type=int, default=0,
                    help='Delete at most N posts this run (0 = no limit; use '
                         'chunks of ~300 so one run never hits timeouts)')
    ap.add_argument('--workers', type=int, default=DELETE_WORKERS,
                    help='Parallel delete threads (lower it if the host throttles)')
    ap.add_argument('--delay', type=float, default=0.0,
                    help='Extra sleep (s) after each delete per worker, e.g. 0.2')
    ap.add_argument('--report', default=os.path.join(os.path.dirname(WP_SITES_FILE),
                                                     'duplicate_cleanup_report.json'),
                    help='Where to write the JSON report')
    args = ap.parse_args()

    sites = load_sites()
    if args.site not in sites:
        sys.exit(f'Site "{args.site}" tidak ditemukan di wp_sites.json')
    site = sites[args.site]
    if site.get('username') in ('PENDING', '', None) or site.get('app_password') in ('PENDING', '', None):
        sys.exit(f'Site "{args.site}" belum punya kredensial (PENDING)')

    client = make_client(site)
    ok, msg = client.login()
    if not ok:
        sys.exit(f'Login gagal: {msg}')
    print(f'✅ Login OK: {args.site}')

    report_path = args.report
    if args.from_report:
        with open(report_path, 'r', encoding='utf-8') as f:
            report = json.load(f)
        ids = [pid for g in report['groups'] for pid in g['delete_ids']]
        chunk = ids[args.offset: args.offset + args.limit] if args.limit else ids[args.offset:]
        if not chunk:
            print('✅ Tidak ada id tersisa pada offset ini — selesai.')
            return
        print(f'🗑 Resume: menghapus {len(chunk)}/{len(ids)} id '
              f'(offset {args.offset}, workers={args.workers}, delay={args.delay}, '
              f'permanent, force=true) ...')
        deleted, failed = delete_posts(client, site, chunk,
                                       workers=args.workers, delay=args.delay)
        done = min(len(ids), args.offset + (args.limit or len(chunk)))
        print(f'\n✅ Chunk selesai: {deleted} dihapus, {len(failed)} gagal. '
              f'Progress: {done}/{len(ids)}')
        if args.offset + (args.limit or len(chunk)) < len(ids):
            print(f'➡️ Lanjutkan: --from-report --offset {done} --limit {args.limit or len(chunk)}')
        if failed:
            print(f'⚠️ Gagal (coba ulang nanti): {failed[:50]}')
        return

    posts, complete = fetch_all_posts(client)
    print(f'📦 {len(posts)} post diambil (paginasi lengkap: {complete})')

    groups = build_groups(posts)
    all_delete_ids = [pid for g in groups for pid in g['delete_ids']]
    if args.limit:
        all_delete_ids = all_delete_ids[:args.limit]
    if args.keep == 'oldest':
        for g in groups:
            # oldest kept = last of newest-first list; delete the rest
            g['keep_id'], g['keep_date'] = g['delete_ids'][-1], g['delete_dates'][-1]
            g['delete_ids'], g['delete_dates'] = g['delete_ids'][:-1], g['delete_dates'][:-1]

    print(f'\n🔎 {len(groups)} grup duplikat, {len(all_delete_ids)} post akan dihapus '
          f'(keep {args.keep})')
    for g in groups[:20]:
        print(f'  • [{len(g["delete_ids"]) + 1}x] {g["title"][:70]}  keep #{g["keep_id"]}')
    if len(groups) > 20:
        print(f'  ... dan {len(groups) - 20} grup lainnya')

    if not args.apply:
        report = {
            'site': args.site,
            'generated_at': time.strftime('%Y-%m-%d %H:%M:%S'),
            'total_posts': len(posts),
            'pagination_complete': complete,
            'duplicate_groups': len(groups),
            'to_delete': len(all_delete_ids),
            'mode': 'dry-run',
            'groups': groups,
        }
        with open(args.report, 'w', encoding='utf-8') as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
        print(f'\n📝 Report: {args.report}')
        print('\n🟡 DRY RUN — tidak ada yang dihapus. Jalankan ulang dengan --apply untuk menghapus.')
        return

    if not all_delete_ids:
        print('Tidak ada duplikat. Selesai.')
        return

    print(f'\n🗑 Menghapus {len(all_delete_ids)} post (permanent, force=true) ...')
    deleted, failed = delete_posts(client, site, all_delete_ids)
    print(f'\n✅ Selesai: {deleted}/{len(all_delete_ids)} dihapus, {len(failed)} gagal')
    if failed:
        print(f'⚠️ Gagal (coba ulang nanti): {failed[:50]}')


if __name__ == '__main__':
    main()
