"""Idempotensi submit driver (v2.120.0).

Masalah yang ditutup: pengiriman ulang (retry manual, antrean offline, atau
respons yang hilang di tengah jaringan) bisa membuat dua baris bisnis untuk
satu pengajuan. Tidak ada endpoint submit yang punya kunci idempoten.

Desain: satu tabel `submit_idempotency` per DB cabang. Klien mengirim
`client_uuid` (dibuat sekali per percobaan, dipertahankan saat retry/antrean).
Server mengklaim kunci SEBELUM menulis data bisnis; transaksi yang sama baru
di-commit setelah data bisnis selesai. Jadi:

- commit berhasil  -> replay mengembalikan dokumen yang sama (status success,
  `duplicate: true`), bukan membuat baris baru;
- gagal/rollback   -> klaim ikut hilang, retry tetap boleh.

Best-effort: bila tabel belum siap (startup race), submit tetap berjalan
tanpa idempotensi dan kegagalannya dicatat — bukan menggagalkan pengajuan.
"""
import re

DDL = """
CREATE TABLE IF NOT EXISTS submit_idempotency (
    client_uuid VARCHAR(64) NOT NULL PRIMARY KEY,
    scope VARCHAR(40) NOT NULL DEFAULT '',
    display_id VARCHAR(40) NOT NULL DEFAULT '',
    doc_id BIGINT NOT NULL DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    KEY idx_idem_created (created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
"""

# UUID browser (crypto.randomUUID) atau fallback hex — tolak nilai aneh/raksasa.
_UUID_RE = re.compile(r'^[A-Za-z0-9_-]{8,64}$')


def ensure_table(conn):
    """Buat tabel idempotensi pada koneksi tertentu (idempoten)."""
    if not conn:
        return False
    cur = None
    try:
        cur = conn.cursor()
        cur.execute(DDL)
        conn.commit()
        return True
    except Exception as exc:
        print(f"[idempotency] ensure table: {exc}")
        return False
    finally:
        if cur:
            try:
                cur.close()
            except Exception:
                pass


def normalize(client_uuid):
    value = (client_uuid or '').strip()
    return value if _UUID_RE.match(value) else ''


def begin(conn, client_uuid, scope):
    """Klaim kunci.

    Return (state, row):
      ('new', None)     -> lanjutkan pemrosesan
      ('replay', row)   -> sudah pernah tercatat; jangan tulis lagi
      ('skip', None)    -> tanpa kunci / tabel tidak siap; lanjut tanpa proteksi
    """
    token = normalize(client_uuid)
    if not token:
        return 'skip', None
    cur = None
    try:
        cur = conn.cursor()
        try:
            cur.execute(
                "INSERT IGNORE INTO submit_idempotency (client_uuid, scope) "
                "VALUES (%s,%s)", (token, scope))
            inserted = cur.rowcount
        finally:
            cur.close()
            cur = None
        if inserted:
            return 'new', None
        cur = conn.cursor(dictionary=True)
        cur.execute(
            "SELECT client_uuid, scope, display_id, doc_id, created_at "
            "FROM submit_idempotency WHERE client_uuid=%s", (token,))
        return 'replay', (cur.fetchone() or {})
    except Exception as exc:
        print(f"[idempotency] begin {scope}: {exc}")
        return 'skip', None
    finally:
        if cur:
            try:
                cur.close()
            except Exception:
                pass


def finish(cursor, client_uuid, display_id, doc_id):
    """Lengkapi kunci dengan dokumen yang lahir (sebelum commit)."""
    token = normalize(client_uuid)
    if not token:
        return False
    try:
        cursor.execute(
            "UPDATE submit_idempotency SET display_id=%s, doc_id=%s "
            "WHERE client_uuid=%s", (display_id or '', int(doc_id or 0), token))
        return True
    except Exception as exc:
        print(f"[idempotency] finish: {exc}")
        return False


def replay_payload(row, kind='transaction'):
    """Respons sukses untuk pengiriman ulang (bentuk sama seperti aslinya)."""
    row = row or {}
    display_id = row.get('display_id') or ''
    doc_id = int(row.get('doc_id') or 0)
    if not display_id:
        return {'status': 'error',
                'msg': 'Pengiriman ini sedang diproses. Tunggu sebentar lalu '
                       'muat ulang halaman — jangan kirim ulang.'}, 409
    body = {
        'status': 'success',
        'duplicate': True,
        'msg': f'Pengajuan {display_id} sudah tercatat — tidak dikirim dua kali.',
    }
    if kind == 'trip':
        body.update({'trip_id': display_id, 'numeric_id': doc_id})
    elif kind == 'cash':
        body.update({'cash_id': doc_id, 'display_id': display_id})
    elif kind == 'overtime':
        body.update({'display_id': display_id})
    else:
        body.update({'transaction_id': display_id, 'numeric_id': doc_id})
    return body, 200
