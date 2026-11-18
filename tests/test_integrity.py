"""Unit tests — penghitung kegagalan yang ditelan + sinyal health (v2.119.0)."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import pytest  # noqa: E402

import modules.integrity as integrity  # noqa: E402
import modules.security as security  # noqa: E402


class FakeCursor:
    def execute(self, *args, **kwargs):
        pass

    def fetchone(self):
        return (1,)

    def close(self):
        pass


class FakeConn:
    def cursor(self, dictionary=False):
        return FakeCursor()

    def close(self):
        pass


@pytest.fixture(autouse=True)
def _clean_registry():
    integrity.reset()
    yield
    integrity.reset()


def test_note_mencatat_dan_snapshot():
    integrity.note('uji.ctx', ValueError('rusak'), critical=True)
    snap = integrity.snapshot()
    assert snap['total'] == 1
    assert snap['critical_total'] == 1
    assert snap['recent_critical'] == 1
    assert snap['by_context'] == [{'context': 'uji.ctx', 'count': 1}]
    assert snap['recent'][-1]['error'] == 'rusak'
    assert snap['recent'][-1]['critical'] is True


def test_non_kritis_tetap_dicatat_tanpa_menurunkan_status():
    integrity.note('uji.opsional', RuntimeError('redis mati'))
    snap = integrity.snapshot()
    assert snap['total'] == 1
    assert snap['recent_critical'] == 0
    assert snap['recent'][-1]['critical'] is False


def test_error_lama_tidak_lagi_dianggap_kritis():
    integrity.note('uji.lama', RuntimeError('x'), critical=True)
    integrity._recent[-1]['at'] = 0  # jauh di luar jendela 30 menit
    snap = integrity.snapshot()
    assert snap['critical_total'] == 1
    assert snap['recent_critical'] == 0


def test_note_tidak_pernah_melempar():
    class Boom:
        def __str__(self):
            raise RuntimeError('boom')

    integrity.note('uji.boom', Boom(), critical=True)
    integrity.note(None, None)
    assert integrity.snapshot()['total'] == 2


def test_health_menampilkan_integritas_dan_degraded(monkeypatch):
    monkeypatch.setattr('modules.config.get_master_connection', lambda: FakeConn())
    monkeypatch.setattr('modules.config.get_db_pool_info', lambda: {})
    monkeypatch.setattr(security, '_redis_ping', lambda: True)
    monkeypatch.setattr('modules.deploy_guard.status_dict',
                        lambda: {'state': 'ok', 'stale': False})

    sehat = security.health_payload()
    assert sehat['status'] == 'ok'
    assert sehat['checks']['integrity']['total'] == 0

    integrity.note('laporan.bbm', RuntimeError('SQL gagal'), critical=True)
    rusak = security.health_payload()
    assert rusak['status'] == 'degraded'
    assert rusak['checks']['integrity']['recent_critical'] == 1
    assert rusak['checks']['integrity']['by_context'][0]['context'] == 'laporan.bbm'


def test_resolusi_db_gagal_tercatat_kritis(monkeypatch):
    from modules import config

    def boom(code):
        raise RuntimeError('peta cabang rusak')

    monkeypatch.setattr('modules.branch_manager.get_branch_db_name', boom)
    # Perilaku lama dipertahankan: jatuh ke master.
    assert config.resolve_db_name('SBY') == config.DB_CONFIG['database']
    snap = integrity.snapshot()
    assert snap['critical_total'] == 1
    assert snap['by_context'][0]['context'] == 'config.resolve_db_name'


def test_rate_limit_redis_gagal_tetap_membatasi(monkeypatch):
    from modules import helpers

    class BoomRedis:
        def register_script(self, *args):
            raise RuntimeError('redis mati')

    monkeypatch.setattr(helpers, '_get_redis', lambda: BoomRedis())
    key = 'uji-rate-limit-v2119'
    helpers._counter_mem.pop(key, None)
    assert helpers.redis_rate_hit(key, 2, 60) is True
    assert helpers.redis_rate_hit(key, 2, 60) is True
    assert helpers.redis_rate_hit(key, 2, 60) is False
    contexts = [c['context'] for c in integrity.snapshot()['by_context']]
    assert 'helpers.rate_limit_redis' in contexts
