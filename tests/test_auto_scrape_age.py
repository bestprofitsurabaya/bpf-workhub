"""Tests untuk filter usia artikel auto-scrape (anti-backdate backlog).

Insiden 28 Sep 2026: auto-scrape yang lama mati mengejar 278 artikel backlog
sekaligus (tanggal backdate dari artikel sumber) — hasil jelek di site dan
harus di-rollback. Filter usia memastikan hanya artikel terbaru yang di-upload.
"""
import datetime
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.auto_scrape import filter_recent

NOW = datetime.datetime(2026, 9, 28, 13, 30)


def art(date_str):
    return {'title': f'Artikel {date_str or "tanpa-tanggal"}', 'publish_date': date_str}


class TestFilterRecent:
    def test_old_articles_skipped(self):
        kept, st = filter_recent(
            [art('2026-09-21'), art('2026-09-15')], 1, now=NOW)
        assert kept == []
        assert st['old'] == 2
        assert st['newest_skipped'] == '2026-09-21'

    def test_fresh_articles_kept(self):
        kept, _ = filter_recent(
            [art('2026-09-28'), art('2026-09-27')], 1, now=NOW)
        assert [a['publish_date'] for a in kept] == ['2026-09-28', '2026-09-27']
        assert kept[0]['title'] == 'Artikel 2026-09-28'

    def test_boundary_exactly_cutoff_kept(self):
        # cutoff = now - 1 hari = 2026-09-27 → artikel tanggal itu MASIH lolos
        kept, st = filter_recent([art('2026-09-27'), art('2026-09-26')], 1, now=NOW)
        assert [a['publish_date'] for a in kept] == ['2026-09-27']
        assert st['old'] == 1

    def test_wider_window(self):
        # cutoff = 2026-09-21 → artikel tanggal cutoff masih lolos, 20 Sep tidak
        kept, st = filter_recent(
            [art('2026-09-21'), art('2026-09-20')], 7, now=NOW)
        assert [a['publish_date'] for a in kept] == ['2026-09-21']
        assert st['old'] == 1

    def test_no_date_kept_and_counted(self):
        kept, st = filter_recent([art(''), art(None)], 1, now=NOW)
        assert len(kept) == 2
        assert st['nodate'] == 2
        assert st['old'] == 0

    def test_mixed_batch(self):
        batch = [art('2026-09-28'), art('2026-09-26'), art('2026-09-20'), art('')]
        kept, st = filter_recent(batch, 1, now=NOW)
        assert [a['publish_date'] for a in kept] == ['2026-09-28', '']
        assert st == {'old': 2, 'nodate': 1, 'newest_skipped': '2026-09-26'}

    def test_fractional_age_days(self):
        # 0.5 hari → cutoff 28 Sep 01:30 → artikel 27 Sep sudah terlalu tua
        kept, st = filter_recent(
            [art('2026-09-28'), art('2026-09-27')], 0.5, now=NOW)
        assert [a['publish_date'] for a in kept] == ['2026-09-28']
        assert st['old'] == 1

    def test_empty_input(self):
        kept, st = filter_recent([], 1, now=NOW)
        assert kept == []
        assert st['old'] == 0
