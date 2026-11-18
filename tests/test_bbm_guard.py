"""Unit tests — guard BBM/LPJ bersama (v2.120.0).

Mengunci paritas yang dulu hilang: LPJ kasbon tidak memeriksa foto rusak,
foto yang pernah dipakai, ODO mundur, atau kapasitas tangki.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import pytest  # noqa: E402

from modules import bbm_guard  # noqa: E402


class FakeCursor:
    def __init__(self, rows=None):
        self.rows = list(rows or [])
        self.sql = ''
        self.params = ()

    def execute(self, sql, params=None):
        self.sql = ' '.join(str(sql).split())
        self.params = params or ()

    def fetchone(self):
        return self.rows.pop(0) if self.rows else None


def test_odo_mundur_ditolak_dengan_pesan_jelas():
    prev = {'odo_km': 90000, 'display_id': 'BPF-SBY-1'}
    msg = bbm_guard.odo_backward_message(prev, 89999)
    assert msg and 'ODO mundur' in msg and 'BPF-SBY-1' in msg
    assert bbm_guard.odo_backward_message(prev, 90000) is None
    assert bbm_guard.odo_backward_message(None, 10) is None


def test_kapasitas_tangki():
    assert bbm_guard.capacity_reject_message(51, 50, 'AVANZA')
    assert bbm_guard.capacity_reject_message(50, 50, 'AVANZA') is None
    assert bbm_guard.capacity_reject_message(80, 0, 'AVANZA') is None


def test_foto_rusak_terdeteksi(tmp_path):
    pytest.importorskip('PIL')
    bad = tmp_path / 'palsu.jpg'
    bad.write_text('ini bukan gambar')
    good = tmp_path / 'baik.png'
    from PIL import Image
    Image.new('RGB', (2, 2), 'white').save(good)

    saved = {'foto_struk': 'palsu.jpg', 'foto_odo_sebelum': 'baik.png'}
    assert bbm_guard.invalid_saved_photos(str(tmp_path), saved) == ['foto_struk']

    bbm_guard.delete_saved_photos(str(tmp_path), ['palsu.jpg', None, 'tidak-ada.jpg'])
    assert not bad.exists()


def test_anomali_odo_kapasitas_dan_exif():
    cur = FakeCursor(rows=[{'config_value': 0}, {'config_value': 0}])
    reasons = bbm_guard.anomaly_reasons(
        cur, 'RIVAN', {'odo_km': 1000}, 1000, 46, 50, {}, 200000)
    joined = ' | '.join(reasons)
    assert 'ODO tidak berubah' in joined
    assert '90% kapasitas' in joined
    assert 'exif' in joined


def test_anomali_odo_mundur_ditandai_bukan_ditolak():
    cur = FakeCursor(rows=[{'config_value': 0}, {'config_value': 0}])
    reasons = bbm_guard.anomaly_reasons(
        cur, 'RIVAN', {'odo_km': 5000}, 4000, 10, 50, {}, 100000,
        odo_backward=True)
    assert any('lebih rendah' in r for r in reasons)
    assert not any('tidak berubah' in r for r in reasons)


def test_hash_dan_duplikat_registry(monkeypatch, tmp_path):
    foto = tmp_path / 'struk.jpg'
    foto.write_bytes(b'isi-struk')
    hashes, meta = bbm_guard.hashes_and_meta({'foto_struk': str(foto)})
    assert hashes['foto_struk']
    assert meta['foto_struk']['bytes'] == len(b'isi-struk')

    class Cur:
        def execute(self, sql, params=None):
            self.params = params

        def fetchall(self):
            return [{'display_id': 'BPF-LAMA', 'sha256': hashes['foto_struk']}]

        def close(self):
            pass

    class Conn:
        def cursor(self, dictionary=False):
            return Cur()

        def close(self):
            pass

    monkeypatch.setattr(bbm_guard, 'get_master_connection', lambda: Conn(), raising=False)
    import modules.config as config
    monkeypatch.setattr(config, 'get_master_connection', lambda: Conn())
    dups = bbm_guard.find_duplicate_proofs(hashes)
    assert dups and dups[0]['display_id'] == 'BPF-LAMA'
