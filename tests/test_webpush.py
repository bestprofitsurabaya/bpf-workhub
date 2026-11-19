"""Tes Web Push (v2.128.0): validasi langganan, payload, dan kunci VAPID."""
import base64
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from modules import webpush  # noqa: E402


def test_langganan_valid_dinormalisasi():
    sub = webpush.subscription_from_payload({
        'subscription': {
            'endpoint': 'https://fcm.googleapis.com/wp/abc123',
            'keys': {'p256dh': 'BPublicKey', 'auth': 'secret'},
        }
    })
    assert sub == {
        'endpoint': 'https://fcm.googleapis.com/wp/abc123',
        'p256dh': 'BPublicKey',
        'auth': 'secret',
    }


def test_format_langsung_tanpa_pembungkus_diterima():
    sub = webpush.subscription_from_payload({
        'endpoint': 'https://updates.push.services.mozilla.com/wpush/v2/x',
        'keys': {'p256dh': 'k', 'auth': 'a'},
    })
    assert sub and sub['endpoint'].startswith('https://')


def test_langganan_tidak_sah_ditolak():
    assert webpush.subscription_from_payload(None) is None
    assert webpush.subscription_from_payload({}) is None
    # endpoint wajib https
    assert webpush.subscription_from_payload({
        'endpoint': 'http://contoh/x', 'keys': {'p256dh': 'k', 'auth': 'a'}}) is None
    # keys wajib lengkap
    assert webpush.subscription_from_payload({
        'endpoint': 'https://contoh/x', 'keys': {'p256dh': 'k'}}) is None


def test_payload_json_memuat_judul_badan_dan_url():
    data = json.loads(webpush.build_payload('Notifikasi', 'Pesan uji', '/app/driver'))
    assert data['title'] == 'Notifikasi'
    assert data['body'] == 'Pesan uji'
    assert data['url'] == '/app/driver'
    assert data['tag'] == 'bpf-driver'
    assert 'at' in data


def test_payload_membatasi_panjang_teks():
    data = json.loads(webpush.build_payload('x' * 500, 'y' * 1000))
    assert len(data['title']) <= 120
    assert len(data['body']) <= 300


def test_kunci_vapid_p256_konsisten():
    pem, pub_b64 = webpush.generate_vapid_keys()
    assert 'PRIVATE KEY' in pem
    raw = base64.urlsafe_b64decode(pub_b64 + '=' * (-len(pub_b64) % 4))
    assert len(raw) == 65 and raw[0] == 0x04  # titik EC uncompressed

    from cryptography.hazmat.primitives import serialization
    key = serialization.load_pem_private_key(pem.encode(), password=None)
    derived = key.public_key().public_bytes(
        serialization.Encoding.X962,
        serialization.PublicFormat.UncompressedPoint,
    )
    assert base64.urlsafe_b64encode(derived).rstrip(b'=').decode() == pub_b64


def test_pembersihan_langganan_mati_memakai_db_asal(monkeypatch):
    """v2.128.2 — thread push tanpa sesi harus menghapus di DB cabang asal."""
    from modules import config

    deleted = []
    named = []

    class FakeCursor:
        def __init__(self):
            self.queries = []

        def execute(self, sql, params=None):
            self.queries.append((sql, params))
            if sql.strip().upper().startswith('DELETE'):
                deleted.append(params[0])

        def close(self):
            pass

    class FakeConn:
        def cursor(self, dictionary=False):
            return FakeCursor()

        def commit(self):
            pass

        def close(self):
            pass

    def fake_by_name(db_name):
        named.append(db_name)
        return FakeConn()

    monkeypatch.setattr(webpush, 'push_available', lambda: True)
    monkeypatch.setattr(webpush, '_send_one', lambda sub, payload, key: 'gone')
    monkeypatch.setattr(webpush, 'get_vapid_keys', lambda: ('pub', '-----BEGIN EC PRIVATE KEY-----'))
    monkeypatch.setattr(config, 'get_db_connection_by_name', fake_by_name)
    monkeypatch.setattr(config, 'get_db_connection', lambda *a, **k: (_ for _ in ()).throw(
        AssertionError('get_db_connection() generik tidak boleh dipakai saat db_name ada')))

    subs = [{'endpoint': 'https://push/contoh', 'p256dh': 'k', 'auth': 'a'}]
    out = webpush.send_to_driver('Ahmad', 'Judul', 'Isi', subs=subs, db_name='bpf_branch_sby')

    assert out == {'ok': 0, 'gone': 1, 'error': 0}
    assert named == ['bpf_branch_sby']
    assert deleted == ['https://push/contoh']


def test_objek_vapid_dipakai_untuk_pengiriman():
    """v2.128.3 — pywebpush 2.5 menolak string PEM; objek Vapid wajib dipakai."""
    from py_vapid import Vapid01

    pem, _pub = webpush.generate_vapid_keys()
    obj = webpush._vapid_object(pem)
    assert isinstance(obj, Vapid01)
    # cache: kunci yang sama menghasilkan objek yang sama
    assert webpush._vapid_object(pem) is obj


def test_send_one_mengoper_objek_vapid(monkeypatch):
    """_send_one tidak boleh meneruskan string PEM mentah ke pywebpush."""
    import pywebpush as pywebpush_mod

    captured = {}

    def fake_webpush(**kwargs):
        captured.update(kwargs)
        return True

    monkeypatch.setattr(pywebpush_mod, 'webpush', fake_webpush)
    pem, _pub = webpush.generate_vapid_keys()
    obj = webpush._vapid_object(pem)
    out = webpush._send_one(
        {'endpoint': 'https://push/contoh', 'p256dh': 'k', 'auth': 'a'},
        '{}', pem,
    )
    assert out == 'ok'
    assert captured['vapid_private_key'] is obj
    assert not isinstance(captured['vapid_private_key'], str)
