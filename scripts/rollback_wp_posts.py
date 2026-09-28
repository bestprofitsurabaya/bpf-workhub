#!/usr/bin/env python3
"""Rollback post yang dibuat auto-scrape (identifikasi via rentang ID).

Satu-kali pakai (rollback 278 artikel Bandung, 28 Sep 2026). Post baru yang
dibuat auto-scrape membawa TANGGAL BACKDATE dari artikel sumbernya (date_gmt
= tanggal terbit di newsmaker), jadi filter waktu tidak bisa dipakai —
identifikasi memakai rentang ID: semua post dgn ID >= batas yang pasti
dibuat oleh run (diverifikasi dgn bukti bahwa tidak ada post lain yang
dimodifikasi di window tsb).

Mode aman: jumlah post yang ditemukan dibandingkan dgn --expect-count;
kalau tidak sama, GAGAL tanpa menghapus (kecuali --force).

Usage:
    python3 scripts/rollback_wp_posts.py --site S --min-id 29808 --expect-count 278
    python3 scripts/rollback_wp_posts.py --site S --min-id 29808 --expect-count 278 --apply
"""
import argparse
import sys
import time

sys.path.insert(0, '/app')

from modules.news_scraper.routes import _load_json, WP_SITES_FILE, _make_wp_client


def norm(t):
    import re
    t = (t or '').lower().strip()
    t = re.sub(r'[^a-z0-9\s]', '', t)
    return re.sub(r'\s+', ' ', t).strip()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--site', required=True)
    ap.add_argument('--min-id', type=int, required=True,
                    help='Hapus post dgn ID >= nilai ini (pasti dibuat oleh run)')
    ap.add_argument('--expect-count', type=int, default=0,
                    help='Gagal bila jumlah post yg ditemukan tidak sama (guard)')
    ap.add_argument('--apply', action='store_true', help='Hapus permanen (default: laporan)')
    args = ap.parse_args()

    sites = _load_json(WP_SITES_FILE, {})
    site = sites[args.site]
    client = _make_wp_client(site)
    ok, nonce = client.login()
    if not ok:
        sys.exit(f'Login gagal: {nonce}')
    print(f'✅ Login OK: {args.site}')

    # Ambil post ber-ID tertinggi dulu sampai lewat batas min-id.
    targets = []
    page = 1
    while page <= 30:
        r = client.get_posts(nonce, params={'per_page': 100, 'page': page,
                                            'orderby': 'id', 'order': 'desc'})
        if r.status_code != 200:
            sys.exit(f'get_posts page {page} -> HTTP {r.status_code}')
        batch = r.json()
        if not batch:
            break
        done = False
        for p in batch:
            if p['id'] >= args.min_id:
                targets.append(p)
            else:
                done = True
                break
        if done:
            break
        page += 1
        time.sleep(0.1)

    print(f'🎯 Post dgn ID >= {args.min_id}: {len(targets)}')
    titles = {}
    for p in targets:
        t = (p.get('title') or {}).get('rendered', '')[:60]
        titles[t] = titles.get(t, 0) + 1
    print('10 judul teratas:')
    for t, c in sorted(titles.items(), key=lambda x: -x[1])[:10]:
        print(f'  {c}x  {t}')
    if targets:
        ids = sorted(p['id'] for p in targets)
        print(f'Rentang ID: {ids[0]} .. {ids[-1]}')

    if args.expect_count and len(targets) != args.expect_count:
        sys.exit(f'❌ JUMLAH TIDAK SESUAI: {len(targets)} != expect {args.expect_count} — TIDAK ada yang dihapus.')

    if not args.apply:
        print(f'\n🟡 DRY RUN — tidak ada yang dihapus. Jalankan dengan --apply (expect {len(targets)}).')
        return

    print(f'\n🗑 Menghapus {len(targets)} post (force=true) ...')
    deleted = 0
    for i, p in enumerate(targets, 1):
        try:
            r = client.request('DELETE', f"{site['wp_url']}/{p['id']}", nonce,
                               params={'force': True}, timeout=60)
            if r.status_code in (200, 404, 410):
                deleted += 1
            else:
                print(f'  ✗ #{p["id"]} HTTP {r.status_code}')
        except Exception as e:
            print(f'  ✗ #{p["id"]} {type(e).__name__}: {str(e)[:60]}')
        if i % 25 == 0:
            print(f'  ... {i}/{len(targets)} diproses, {deleted} sukses')
            time.sleep(1)

    print(f'\n✅ Selesai: {deleted}/{len(targets)} dihapus')


if __name__ == '__main__':
    main()
