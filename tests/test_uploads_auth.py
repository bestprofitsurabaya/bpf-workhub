"""Regression test — /uploads/<file> (v2.37.2).

Bug: commit 584ba88 (hardening Ox Alpha) menambah auth check yang memakai
`session`, tapi `session` tidak di-import di routes_driver.py → setiap
GET /uploads/ meledak NameError (500) dan SEMUA foto bukti (air minum,
trip, disp, overtime) tidak pernah tampil di UI.

Test ini mengunci perbaikannya:
- tanpa sesi        → 401 (bukan 500) — IDOR guard tetap terpasang;
- sesi back-office  → 200 + header hardening (nosniff + inline);
- sesi driver PWA   → 200 (driver butuh lihat foto trip-nya).

Jalankan: python3 -m pytest tests/test_uploads_auth.py -v
"""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import pytest
from flask import Flask

from modules.routes_driver import register_driver_routes  # noqa: E402

# JPEG 1x1 minimal (magic bytes valid — cukup untuk send_from_directory)
JPEG_1PX = bytes.fromhex(
    "ffd8ffe000104a46494600010100000100010000"
    "ffdb004300080606070605080707070909080a0c140d0c0b0b0c1912130f141d1a"
    "1f1e1d1a1c1c20242e2720222c231c1c2837292c30313434341f27393d38323c2e"
    "333432ffd9"
)


@pytest.fixture()
def client(tmp_path):
    app = Flask(__name__)
    app.secret_key = "test-secret"
    up = tmp_path / "uploads"
    up.mkdir()
    (up / "WTR_TEST_1.jpeg").write_bytes(JPEG_1PX)
    app.config["UPLOAD_FOLDER"] = str(up)
    app.config["TESTING"] = True
    register_driver_routes(app, None)  # socketio None — hanya dipakai di handler lain
    with app.test_client() as c:
        yield c


def test_tanpa_sesi_401_bukan_500(client):
    """Tanpa login harus 401 — regression NameError (dulu 500)."""
    r = client.get("/uploads/WTR_TEST_1.jpeg")
    assert r.status_code == 401, (r.status_code, r.get_data(as_text=True)[:120])


def test_sesi_backoffice_200(client):
    """Finance/admin login → foto terkirim + header hardening utuh."""
    with client.session_transaction() as s:
        s["user_name"] = "finance_sby"
        s["user_role"] = "finance"
    r = client.get("/uploads/WTR_TEST_1.jpeg")
    assert r.status_code == 200
    assert r.headers.get("X-Content-Type-Options") == "nosniff"
    assert "inline" in r.headers.get("Content-Disposition", "")
    assert r.data.startswith(b"\xff\xd8")


def test_sesi_driver_pwa_200(client):
    """Driver PWA (driver_name) juga boleh mengambil foto bukti."""
    with client.session_transaction() as s:
        s["driver_name"] = "AKHAD"
    r = client.get("/uploads/WTR_TEST_1.jpeg")
    assert r.status_code == 200


def test_file_tidak_ada_404(client):
    """Nama file yang tidak ada → 404 (bukan 500/401 campur aduk)."""
    with client.session_transaction() as s:
        s["user_name"] = "finance_sby"
    r = client.get("/uploads/WTR_TIDAK_ADA.jpeg")
    assert r.status_code == 404
