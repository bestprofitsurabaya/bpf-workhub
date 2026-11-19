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
