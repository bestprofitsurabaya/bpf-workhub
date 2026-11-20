"""Unit Tests — km/L & top-up BBM (v2.130.0).

Menguji `modules.engine.compute_km_metrics` tanpa DB:

- pengisian penuh berurutan → km/L = jarak / liter,
- pengisian beruntun (jarak < threshold) → liter dibawa ke pengisian penuh
  berikutnya ("top up"), bukan dihitung sebagai interval pendek,
- baris tanpa ODO tidak memutus interval; liternya ikut diakumulasi,
- ODO mundur/tidak berubah tidak mereset patokan.

Jalankan:
    python3 -m pytest tests/test_engine_km.py -v
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from modules.km_metrics import compute_km_metrics  # noqa: E402


def tx(odo, liter, created_at='2026-11-01 08:00:00'):
    return {'odo_km': odo, 'liter': liter, 'created_at': created_at}


def test_pengisian_penuh_berurutan():
    rows = compute_km_metrics([tx(1000, 10), tx(1300, 30)])
    assert rows[0]['rata_rata'] == 0.0          # ODO pertama = patokan
    assert rows[0]['total_km'] == 0
    assert rows[1]['km_awal'] == 1000
    assert rows[1]['km_akhir'] == 1300
    assert rows[1]['total_km'] == 300
    assert rows[1]['rata_rata'] == 10.0
    assert rows[1]['is_multifill'] is False and rows[1]['is_topup'] is False


def test_pengisian_beruntun_diakumulasi_ke_pengisian_penuh():
    """Top up 10 km (5 L) tidak dihitung sendiri; liternya ikut ke isi penuh."""
    rows = compute_km_metrics(
        [tx(1000, 10), tx(1010, 5), tx(1300, 25)], threshold=40)
    assert rows[1]['is_multifill'] is True
    assert rows[1]['is_topup'] is True
    assert rows[1]['rata_rata'] == 0.0
    # 300 km / (25 L + 5 L top up) = 10 km/L
    assert rows[2]['total_km'] == 300
    assert rows[2]['rata_rata'] == 10.0
    assert rows[2]['is_topup'] is False


def test_baris_tanpa_odo_tidak_memutus_interval():
    """ODO kosong bukan 0 km: liter baris itu masuk akumulasi top up."""
    rows = compute_km_metrics(
        [tx(1000, 10), tx(0, 10), tx(1300, 20)], threshold=40)
    assert rows[1]['is_topup'] is True
    assert rows[1]['km_awal'] == 0 and rows[1]['km_akhir'] == 0
    assert rows[1]['total_km'] == 0
    # 300 km / (20 L + 10 L tanpa ODO) = 10 km/L
    assert rows[2]['km_awal'] == 1000
    assert rows[2]['total_km'] == 300
    assert rows[2]['rata_rata'] == 10.0


def test_beberapa_baris_tanpa_odo_diakumulasi():
    rows = compute_km_metrics(
        [tx(1000, 10), tx(0, 4), tx(0, 6), tx(1300, 20)], threshold=40)
    assert rows[3]['rata_rata'] == 10.0  # 300 / (20 + 4 + 6)


def test_odo_kosong_sebelum_patokan_tidak_dipakai():
    """Tidak ada jarak acuan sebelum ODO pertama — liter itu diabaikan."""
    rows = compute_km_metrics([tx(0, 10), tx(1000, 10), tx(1300, 20)])
    assert rows[0]['is_topup'] is True
    assert rows[1]['total_km'] == 0
    assert rows[2]['rata_rata'] == 15.0  # 300 / 20, bukan 300 / 30


def test_odo_mundur_tidak_mereset_patokan():
    rows = compute_km_metrics(
        [tx(1000, 10), tx(1300, 20), tx(1200, 5), tx(1600, 20)], threshold=40)
    assert rows[1]['rata_rata'] == 15.0
    assert rows[2]['total_km'] < 0
    assert rows[2]['rata_rata'] == 0.0
    # Patokan tetap 1300 → 1600 = 300 km / 20 L
    assert rows[3]['km_awal'] == 1300
    assert rows[3]['rata_rata'] == 15.0
