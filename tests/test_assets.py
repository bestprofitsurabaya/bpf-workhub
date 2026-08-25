"""Sistem Aset & Pemeliharaan (v2.18) — AC kantor, kendaraan, rekomendasi, PDF.

Migrasi dari bpf-asset-system (Streamlit/SQLite) ke BPF WorkHub (role GA/Admin).
Unit test: health score AC dari parameter teknikal, rekomendasi berbasis aturan,
label & role akses, PDF berlogo.
"""
import io
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from modules.routes_assets import _ac_health_score  # noqa: E402
from modules.pdf_generator import AssetReportPDF  # noqa: E402
from tests.pdf_text import _pdf_text  # noqa: E402


class TestAcHealthScore:
    def test_normal_params_high_score(self):
        log = {'amp_kompresor': 5.0, 'delta_t': 12, 'low_p': 70}
        s = _ac_health_score(log)
        assert s is not None and s >= 85

    def test_high_amp_reduces_score(self):
        log = {'amp_kompresor': 9.0, 'delta_t': 12, 'low_p': 70}
        s = _ac_health_score(log)
        assert s <= 75

    def test_low_delta_t_reduces_score(self):
        log = {'amp_kompresor': 5.0, 'delta_t': 6, 'low_p': 70}
        s = _ac_health_score(log)
        assert s <= 80

    def test_empty_log_none(self):
        assert _ac_health_score({}) is None


class TestRecommendationRules:
    """Rekomendasi berbasis aturan (tanpa ML): AC > 90 hari, health rendah,
    komponen kendaraan melewati umur pakai."""

    def test_ac_recommendation_triggered_when_overdue(self):
        # last_maintenance None -> dianggap 120 hari lalu -> rekomendasi muncul
        from datetime import date, timedelta
        from modules.routes_assets import _compute_ac_recommendations

        class FakeConn:
            def commit(self):
                pass

        class FakeRow(dict):
            pass

        class FakeCursor:
            def __init__(self, acs):
                self._acs = acs
                self._log_calls = 0

            def execute(self, sql, params=None):
                if 'asset_ac_logs' in sql:
                    self._rows = []
                elif 'asset_ac' in sql:
                    self._rows = self._acs
                else:
                    self._rows = []
                return self

            def fetchall(self):
                return self._rows

            def fetchone(self):
                return self._rows[0] if self._rows else None

        ac = FakeRow(asset_id='AC-01-R. BEST 8', merk='Daikin',
                     lokasi='R. BEST 8', status='Aktif', last_maintenance=None)
        cur = FakeCursor([ac])
        recs = _compute_ac_recommendations(FakeConn(), cur)
        assert len(recs) >= 1
        assert recs[0]['asset_type'] == 'ac'
        assert recs[0]['asset_ref'] == 'AC-01-R. BEST 8'
        assert recs[0]['priority'] in ('Tinggi', 'Sedang', 'Kritis')

    def test_ac_no_recommendation_when_recent(self):
        from datetime import date, timedelta
        from modules.routes_assets import _compute_ac_recommendations

        class FakeRow(dict):
            pass

        class FakeCursor:
            def execute(self, sql, params=None):
                if 'asset_ac_logs' in sql:
                    self._rows = []
                elif 'asset_ac' in sql:
                    self._rows = [FakeRow(asset_id='AC-15', merk='Daikin',
                                          lokasi='TRAINING', status='Aktif',
                                          last_maintenance=date.today())]
                else:
                    self._rows = []
                return self

            def fetchall(self):
                return self._rows

            def fetchone(self):
                return self._rows[0] if self._rows else None

        recs = _compute_ac_recommendations(None, FakeCursor())
        assert recs == []


class TestAssetPDF:
    def _mk_pdf(self, kind, rows):
        pdf = AssetReportPDF(kind=kind)
        pdf.generate(rows, generated_by='GA Officer')
        buf = io.BytesIO()
        pdf.output(buf)
        return buf.getvalue()

    def test_ac_pdf_valid_with_data(self):
        rows = [{
            'asset_id': 'AC-01-R. BEST 8', 'merk': 'Daikin', 'tipe': 'Split Duct',
            'kapasitas': '60.000 Btu/h', 'lokasi': 'R. BEST 8', 'status': 'Aktif',
            'last_maintenance': datetime(2026, 8, 1), 'logs': [],
        }]
        data = self._mk_pdf('ac', rows)
        assert data.startswith(b'%PDF')
        assert b'%%EOF' in data[-32:]
        txt = _pdf_text(data).upper()
        assert 'LAPORAN ASET AC KANTOR' in txt
        assert 'AC-01' in txt
        assert 'GA OFFICER' in txt

    def test_vehicle_pdf_valid_with_data(self):
        rows = [{
            'nopol': 'B 1126 DFC', 'vehicle_type': 'INNOVA', 'brand': 'Toyota',
            'year': 2020, 'last_odometer': 85000, 'status': 'Aktif', 'services': [],
        }]
        data = self._mk_pdf('vehicle', rows)
        assert data.startswith(b'%PDF')
        assert b'%%EOF' in data[-32:]
        txt = _pdf_text(data).upper()
        assert 'LAPORAN ASET KENDARAAN' in txt
        assert 'B 1126 DFC' in txt

    def test_empty_pdf_still_valid(self):
        data = self._mk_pdf('ac', [])
        assert data.startswith(b'%PDF')
        assert b'%%EOF' in data[-32:]
