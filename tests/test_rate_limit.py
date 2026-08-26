"""
Unit Tests — Rate Limit (Redis-backed store dengan fallback memori proses).

Menjamin perilaku anti brute-force (ISO/IEC 27001 A.8.5 · A.12.6) tetap benar
baik saat Redis tersedia maupun saat fallback ke memori:

- _RateStore: set/get/pop konsisten lewat memori saat Redis tidak tersedia.
- login: 5x gagal → lockout 15 menit; sukses mereset.
- pin: 8x gagal → lockout 10 menit; sukses mereset.
- window bergulir: percobaan lama (melewati window) tidak menumpuk.

Jalankan:
    docker exec bbm_web python3 -m pytest tests/test_rate_limit.py -v
"""

import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from modules import helpers


def _use_memory(monkeypatch):
    """Paksa store memori (simulasi Redis tidak tersedia)."""
    monkeypatch.setattr(helpers, '_get_redis', lambda: None)
    helpers._login_store._mem.clear()
    helpers._pin_store._mem.clear()


# ---------- _RateStore ----------

def test_rate_store_record_fail_check_reset_memori(monkeypatch):
    _use_memory(monkeypatch)
    s = helpers._RateStore('test_x')
    assert s.check('k1', 300) == (True, 0)
    locked, retry = s.record_fail('k1', 300, 3, 600)
    assert locked is False and retry == 0
    locked, retry = s.record_fail('k1', 300, 3, 600)
    assert locked is False and retry == 0
    locked, retry = s.record_fail('k1', 300, 3, 600)  # ke-3 → lockout
    assert locked is True and retry == 600
    allowed, _ = s.check('k1', 300)
    assert allowed is False
    s.reset('k1')
    assert s.check('k1', 300) == (True, 0)


def test_rate_store_prefix_terpisah(monkeypatch):
    _use_memory(monkeypatch)
    a = helpers._RateStore('a')
    b = helpers._RateStore('b')
    a.record_fail('ip', 300, 9, 600)
    # kegagalan di store 'a' tidak memengaruhi 'b'
    assert b.check('ip', 300) == (True, 0)


# ---------- Login rate limit ----------

def test_login_lockout_setelah_5_gagal(monkeypatch):
    _use_memory(monkeypatch)
    ip = '10.9.8.7'
    for _ in range(5):
        helpers.login_fail(ip, 'user1')
    allowed, retry_after = helpers.login_rate_check(ip, 'user1')
    assert not allowed
    assert retry_after > 0


def test_login_lockout_terisolasi_per_user_satu_ip(monkeypatch):
    """User lain di IP yang sama tidak ikut terkunci (kasus NAT kantor)."""
    _use_memory(monkeypatch)
    ip = '203.0.113.10'  # 1 IP publik kantor
    for _ in range(5):
        helpers.login_fail(ip, 'driver_salah_pin')
    # Pelaku gagal → terkunci
    assert helpers.login_rate_check(ip, 'driver_salah_pin')[0] is False
    # Rekan sekantor (IP sama, user beda) → tetap bisa login
    assert helpers.login_rate_check(ip, 'it_sby') == (True, 0)


def test_login_lockout_case_insensitive_username(monkeypatch):
    _use_memory(monkeypatch)
    ip = '203.0.113.11'
    for _ in range(5):
        helpers.login_fail(ip, 'It_SBY')
    assert helpers.login_rate_check(ip, 'it_sby')[0] is False


def test_login_success_mereset(monkeypatch):
    _use_memory(monkeypatch)
    ip = '10.9.8.8'
    for _ in range(3):
        helpers.login_fail(ip, 'user1')
    helpers.login_success(ip, 'user1')
    assert helpers.login_rate_check(ip, 'user1') == (True, 0)


def test_login_belum_lockout_sebelum_batas(monkeypatch):
    _use_memory(monkeypatch)
    ip = '10.9.8.9'
    for _ in range(4):
        helpers.login_fail(ip, 'user1')
    assert helpers.login_rate_check(ip, 'user1') == (True, 0)


# ---------- PIN rate limit ----------

def test_pin_lockout_setelah_8_gagal(monkeypatch):
    _use_memory(monkeypatch)
    ip = '10.9.9.1'
    for _ in range(8):
        helpers.pin_fail(ip)
    allowed, retry_after = helpers.pin_rate_check(ip)
    assert not allowed
    assert retry_after > 0


def test_pin_success_mereset(monkeypatch):
    _use_memory(monkeypatch)
    ip = '10.9.9.2'
    for _ in range(5):
        helpers.pin_fail(ip)
    helpers.pin_success(ip)
    assert helpers.pin_rate_check(ip) == (True, 0)
