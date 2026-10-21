"""Regresi v2.47.1 — kegagalan tulis log scraper tidak boleh mematikan app.

Dulu `_log_scraper()` dipanggil saat register blueprint (startup). Bila
`data/news_scraper/scraper_log.json` tidak bisa ditulis (izin/volume read-only/
disk penuh), PermissionError naik dan `import app` gagal total.
"""
import json

import modules.news_scraper as ns


def test_log_write_failure_is_non_fatal(tmp_path, monkeypatch, capsys):
    """Path log yang tidak bisa ditulis → tidak raise, ada peringatan."""
    # Direktori sebagai "file" → open() gagal (IsADirectoryError/OSError).
    unwritable = tmp_path / 'scraper_log.json'
    unwritable.mkdir()
    monkeypatch.setattr(ns, 'SCRAPER_LOG_FILE', str(unwritable))

    ns._log_scraper('pesan uji', user='pytest')   # tidak boleh raise

    out = capsys.readouterr().out
    assert 'log tidak dapat ditulis' in out


def test_log_write_success_appends_entry(tmp_path, monkeypatch):
    target = tmp_path / 'scraper_log.json'
    monkeypatch.setattr(ns, 'SCRAPER_LOG_FILE', str(target))

    ns._log_scraper('pertama')
    ns._log_scraper('kedua', user='tester')

    logs = json.loads(target.read_text(encoding='utf-8'))
    assert [e['message'] for e in logs] == ['pertama', 'kedua']
    assert logs[1]['user'] == 'tester'
    assert all('timestamp' in e for e in logs)


def test_log_is_capped_at_max_entries(tmp_path, monkeypatch):
    target = tmp_path / 'scraper_log.json'
    monkeypatch.setattr(ns, 'SCRAPER_LOG_FILE', str(target))
    monkeypatch.setattr(ns, 'MAX_LOG_ENTRIES', 5)

    for i in range(8):
        ns._log_scraper(f'pesan-{i}')

    logs = json.loads(target.read_text(encoding='utf-8'))
    assert len(logs) == 5
    assert logs[-1]['message'] == 'pesan-7'


def test_corrupt_log_file_is_replaced(tmp_path, monkeypatch):
    target = tmp_path / 'scraper_log.json'
    target.write_text('{bukan json', encoding='utf-8')
    monkeypatch.setattr(ns, 'SCRAPER_LOG_FILE', str(target))

    ns._log_scraper('setelah korup')

    logs = json.loads(target.read_text(encoding='utf-8'))
    assert logs[0]['message'] == 'setelah korup'
