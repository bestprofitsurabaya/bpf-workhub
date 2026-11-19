"""Web Push (VAPID) untuk notifikasi driver — v2.128.0.

Tujuan: driver tetap menerima notifikasi saat aplikasi **tertutup** —
penugasan kendaraan, appointment baru, klaim disetujui, dsb. SocketIO hanya
bekerja saat halaman terbuka; Web Push menjangkau Android Chrome dan iOS
Safari >= 16.4 (PWA "Add to Home Screen").

Kunci VAPID:
- utamakan environment `VAPID_PUBLIC_KEY` / `VAPID_PRIVATE_KEY`
  (disarankan untuk deployment multi-worker);
- bila kosong, dibuat sekali dan disimpan di DB master (`system_config`).

Pengiriman bersifat best-effort: kegagalan tidak pernah menggagalkan alur
bisnis. Langganan yang sudah mati (404/410) dihapus otomatis.
"""
import base64
import json
import os
import threading
from datetime import datetime

SUPPORTED = None  # diisi saat pertama dipakai

SUBJECT = os.environ.get('VAPID_SUBJECT', 'mailto:admin@bpf.local').strip() or 'mailto:admin@bpf.local'

TABLE_DDL = """
CREATE TABLE IF NOT EXISTS push_subscriptions (
    id INT AUTO_INCREMENT PRIMARY KEY,
    driver_name VARCHAR(100) NOT NULL,
    endpoint VARCHAR(500) NOT NULL,
    p256dh VARCHAR(255) NOT NULL,
    auth VARCHAR(100) NOT NULL,
    user_agent VARCHAR(255) DEFAULT '',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uq_push_endpoint (endpoint(255)),
    KEY idx_push_driver (driver_name)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
"""


def push_available():
    """True bila pustaka pywebpush terpasang (setelah image di-rebuild)."""
    global SUPPORTED
    if SUPPORTED is None:
        try:
            import pywebpush  # noqa: F401
            SUPPORTED = True
        except Exception as e:
            print(f"[webpush] pywebpush tidak tersedia: {e}")
            SUPPORTED = False
    return SUPPORTED


def ensure_push_table(conn=None):
    """Idempoten: buat tabel langganan push di satu DB."""
    own = conn is None
    if conn is None:
        from modules.config import get_db_connection
        conn = get_db_connection()
    if not conn:
        return False
    cur = None
    try:
        cur = conn.cursor()
        cur.execute(TABLE_DDL)
        conn.commit()
        return True
    except Exception as e:
        print(f"[webpush] ensure table: {e}")
        return False
    finally:
        if cur:
            try: cur.close()
            except Exception: pass
        if own:
            try: conn.close()
            except Exception: pass


# ---------------------------------------------------------------- VAPID keys

def _b64url(raw):
    return base64.urlsafe_b64encode(raw).rstrip(b'=').decode('ascii')


def generate_vapid_keys():
    """Buat pasangan kunci P-256: (private_pem, public_key_b64url)."""
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import ec
    key = ec.generate_private_key(ec.SECP256R1())
    pem = key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.TraditionalOpenSSL,
        serialization.NoEncryption(),
    ).decode('ascii')
    raw_pub = key.public_key().public_bytes(
        serialization.Encoding.X962,
        serialization.PublicFormat.UncompressedPoint,
    )
    return pem, _b64url(raw_pub)


def _load_db_keys():
    from modules.config import get_master_connection
    conn = get_master_connection()
    if not conn:
        return None
    cur = None
    try:
        cur = conn.cursor(dictionary=True)
        cur.execute(
            "SELECT config_key, config_value FROM system_config "
            "WHERE config_key IN ('vapid_public_key','vapid_private_key')"
        )
        rows = {r['config_key']: r['config_value'] for r in cur.fetchall()}
        pub = (rows.get('vapid_public_key') or '').strip()
        priv = (rows.get('vapid_private_key') or '').strip()
        # Pertahanan: build v2.128.0 awal sempat menukar urutan (kunci privat
        # tersimpan di kolom publik). Pulihkan dengan menukar bila terdeteksi.
        if pub and priv and 'PRIVATE KEY' in pub and 'PRIVATE KEY' not in priv:
            pub, priv = priv, pub
            cur.execute(
                "UPDATE system_config SET config_value=%s WHERE config_key='vapid_public_key'", (pub,))
            cur.execute(
                "UPDATE system_config SET config_value=%s WHERE config_key='vapid_private_key'", (priv,))
            conn.commit()
        if pub and priv:
            return pub, priv
        priv, pub = generate_vapid_keys()
        cur.execute(
            "INSERT INTO system_config (config_key, config_value) VALUES (%s, %s) "
            "ON DUPLICATE KEY UPDATE config_value=VALUES(config_value)",
            ('vapid_public_key', pub),
        )
        cur.execute(
            "INSERT INTO system_config (config_key, config_value) VALUES (%s, %s) "
            "ON DUPLICATE KEY UPDATE config_value=VALUES(config_value)",
            ('vapid_private_key', priv),
        )
        conn.commit()
        return pub, priv
    except Exception as e:
        print(f"[webpush] kunci VAPID dari DB gagal: {e}")
        return None
    finally:
        if cur:
            try: cur.close()
            except Exception: pass
        try: conn.close()
        except Exception: pass


_KEYS = None


def get_vapid_keys():
    """(public_b64url, private_pem) — env dulu, lalu DB, lalu proses ini."""
    global _KEYS
    if _KEYS:
        return _KEYS
    env_pub = os.environ.get('VAPID_PUBLIC_KEY', '').strip()
    env_priv = os.environ.get('VAPID_PRIVATE_KEY', '').strip()
    if env_pub and env_priv:
        _KEYS = (env_pub, env_priv)
        return _KEYS
    db = _load_db_keys()
    if db:
        _KEYS = db
        return _KEYS
    priv, pub = generate_vapid_keys()
    _KEYS = (pub, priv)  # fallback proses ini (multi-worker sebaiknya pakai env/DB)
    return _KEYS


def get_vapid_public_key():
    return get_vapid_keys()[0]


# ------------------------------------------------------------- subscriptions

def subscription_from_payload(data):
    """Validasi payload klien → dict siap simpan, atau None bila tidak sah."""
    if not isinstance(data, dict):
        return None
    sub = data.get('subscription') if isinstance(data.get('subscription'), dict) else data
    endpoint = str(sub.get('endpoint') or '').strip()
    keys = sub.get('keys') if isinstance(sub.get('keys'), dict) else {}
    p256dh = str(keys.get('p256dh') or '').strip()
    auth = str(keys.get('auth') or '').strip()
    if not endpoint.startswith('https://') or len(endpoint) > 500:
        return None
    if not p256dh or not auth:
        return None
    return {
        'endpoint': endpoint,
        'p256dh': p256dh[:255],
        'auth': auth[:100],
    }


def save_subscription(driver_name, sub, user_agent='', conn=None):
    """Upsert langganan untuk satu driver (endpoint unik)."""
    own = conn is None
    if conn is None:
        from modules.config import get_db_connection
        conn = get_db_connection()
    if not conn:
        return False
    cur = None
    try:
        from modules.webpush import ensure_push_table
        ensure_push_table(conn)
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO push_subscriptions (driver_name, endpoint, p256dh, auth, user_agent) "
            "VALUES (%s, %s, %s, %s, %s) "
            "ON DUPLICATE KEY UPDATE driver_name=VALUES(driver_name), p256dh=VALUES(p256dh), "
            "auth=VALUES(auth), user_agent=VALUES(user_agent)",
            (str(driver_name).strip().upper(), sub['endpoint'], sub['p256dh'], sub['auth'],
             str(user_agent or '')[:255]),
        )
        conn.commit()
        return True
    except Exception as e:
        print(f"[webpush] save subscription: {e}")
        return False
    finally:
        if cur:
            try: cur.close()
            except Exception: pass
        if own:
            try: conn.close()
            except Exception: pass


def delete_subscription(driver_name, endpoint, conn=None):
    own = conn is None
    if conn is None:
        from modules.config import get_db_connection
        conn = get_db_connection()
    if not conn:
        return 0
    cur = None
    try:
        cur = conn.cursor()
        cur.execute(
            "DELETE FROM push_subscriptions WHERE driver_name=%s AND endpoint=%s",
            (str(driver_name).strip().upper(), endpoint),
        )
        conn.commit()
        return cur.rowcount or 0
    except Exception as e:
        print(f"[webpush] delete subscription: {e}")
        return 0
    finally:
        if cur:
            try: cur.close()
            except Exception: pass
        if own:
            try: conn.close()
            except Exception: pass


def count_subscriptions(driver_name, conn=None):
    own = conn is None
    if conn is None:
        from modules.config import get_db_connection
        conn = get_db_connection()
    if not conn:
        return 0
    cur = None
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT COUNT(*) FROM push_subscriptions WHERE driver_name=%s",
            (str(driver_name).strip().upper(),),
        )
        row = cur.fetchone()
        return int(row[0]) if row else 0
    except Exception:
        return 0
    finally:
        if cur:
            try: cur.close()
            except Exception: pass
        if own:
            try: conn.close()
            except Exception: pass


# ------------------------------------------------------------------- sending

def build_payload(title, body, url='/app/driver', tag='bpf-driver'):
    return json.dumps({
        'title': str(title or 'BPF WorkHub')[:120],
        'body': str(body or '')[:300],
        'url': url or '/app/driver',
        'tag': tag or 'bpf-driver',
        'at': datetime.now().isoformat(timespec='seconds'),
    }, ensure_ascii=False)


def _send_one(sub, payload, vapid_private_key):
    """Kirim satu push. Return 'ok' | 'gone' | 'error'."""
    from pywebpush import webpush, WebPushException
    info = {
        'endpoint': sub['endpoint'],
        'keys': {'p256dh': sub['p256dh'], 'auth': sub['auth']},
    }
    try:
        webpush(
            subscription_info=info,
            data=payload,
            vapid_private_key=vapid_private_key,
            vapid_claims={'sub': SUBJECT},
            timeout=8,
        )
        return 'ok'
    except WebPushException as e:
        status = getattr(getattr(e, 'response', None), 'status_code', None)
        if status in (404, 410):
            return 'gone'
        print(f"[webpush] kirim gagal ({status}): {str(e)[:200]}")
        return 'error'
    except Exception as e:
        print(f"[webpush] kirim error: {str(e)[:200]}")
        return 'error'


def send_to_driver(driver_name, title, body, url='/app/driver', subs=None, conn=None, db_name=None):
    """Kirim push ke semua perangkat driver. Return ringkasan {ok,gone,error}.

    `db_name` wajib diberikan bila dipanggil dari thread latar: tanpa sesi,
    koneksi generik selalu menunjuk master dan baris mati di DB cabang tidak
    akan terhapus (v2.128.2).
    """
    summary = {'ok': 0, 'gone': 0, 'error': 0}
    if not driver_name or not push_available():
        return summary
    rows = subs
    if rows is None:
        conn_local = conn
        own_conn = False
        if conn_local is None:
            from modules.config import get_db_connection
            conn_local = get_db_connection()
            own_conn = True
        if not conn_local:
            return summary
        try:
            cur = conn_local.cursor(dictionary=True)
            cur.execute(
                "SELECT endpoint, p256dh, auth FROM push_subscriptions WHERE driver_name=%s",
                (str(driver_name).strip().upper(),),
            )
            rows = cur.fetchall()
            cur.close()
        except Exception as e:
            print(f"[webpush] baca langganan: {e}")
            return summary
        finally:
            if own_conn:
                try: conn_local.close()
                except Exception: pass
    if not rows:
        return summary
    payload = build_payload(title, body, url)
    _, private_key = get_vapid_keys()
    gone = []
    for row in rows:
        result = _send_one(row, payload, private_key)
        summary[result] += 1
        if result == 'gone':
            gone.append(row['endpoint'])
    # Bersihkan langganan mati — koneksi baru ke DB yang sama (thread aman).
    if gone:
        from modules.config import get_db_connection, get_db_connection_by_name
        cleanup = get_db_connection_by_name(db_name) if db_name else get_db_connection()
        if cleanup:
            try:
                cur = cleanup.cursor()
                for ep in gone:
                    cur.execute("DELETE FROM push_subscriptions WHERE endpoint=%s", (ep,))
                cleanup.commit()
                cur.close()
            except Exception as e:
                print(f"[webpush] cleanup langganan mati: {e}")
            finally:
                try: cleanup.close()
                except Exception: pass
    return summary


def send_to_driver_async(driver_name, title, body, url='/app/driver', subs=None, db_name=None):
    """Kirim di latar belakang agar request bisnis tidak menunggu jaringan."""
    if not push_available():
        return None
    if subs is not None and not subs:
        return None  # tidak ada perangkat terdaftar

    def _run():
        try:
            send_to_driver(driver_name, title, body, url, subs=subs, db_name=db_name)
        except Exception as e:
            print(f"[webpush] async error: {e}")

    try:
        threading.Thread(target=_run, daemon=True).start()
    except Exception:
        _run()
    return True
