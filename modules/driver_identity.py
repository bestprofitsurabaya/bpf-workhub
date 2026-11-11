"""Ikat identitas driver ke akun user (v2.78.0).

Latar masalah
-------------
`users` (DB master) dan `drivers` (DB cabang) dulu dua dunia terpisah:
- login driver memakai `users.username` (identitas = username di-UPPER-kan),
- data operasional memakai `drivers.name` (dulu diisi manual, tanpa relasi),
- nama tampilan ada di `users.full_name` tetapi `drivers` menyimpan nama
  sendiri sehingga perubahan nama akun TIDAK ikut ke tabel driver.

Akibatnya muncul driver tanpa akun (RIVAN/WICAK), akun driver tanpa profil
(WAHYU), dan nama yang tidak sinkron.

Aturan baru (satu sumber kebenaran)
-----------------------------------
1. `drivers.user_id` = kunci relasi ke `users.id` (unik, boleh NULL untuk
   profil historis yang belum punya akun).
2. `drivers.name` = `UPPER(users.username)` — dipakai semua kode lama sebagai
   kunci operasional (transactions.driver_name, vehicle_assignments, dst).
   Saat username diubah, SEMUA referensi nama ikut di-rename (cascade).
3. `drivers.display_name` = `users.full_name` — nama manusia untuk tampilan.
4. Status aktif akun dicerminkan ke profil driver.

Modul ini murni backend dan idempoten; aman dipanggil tiap startup.
"""
import os

# Tabel yang menyimpan nama driver sebagai teks (kunci operasional lama).
DRIVER_REF_TABLES = (
    'transactions',
    'vehicle_assignments',
    'trip_masters',
    'appointments',
    'fuel_cash_requests',
    'proof_registry',
    'notifications',
)

# Hanya role 'driver' yang butuh profil operasional. `chief_driver` adalah
# atasan/supervisor (tidak login ke PWA driver, tidak punya kendaraan).
DRIVER_ROLES = ('driver',)


def default_branch_code():
    return os.environ.get('BRANCH_MAIN_CODE', 'SBY')


def _columns(cursor, table):
    cursor.execute(f"SHOW COLUMNS FROM {table}")
    return {r[0] if not isinstance(r, dict) else r['Field'] for r in cursor.fetchall()}


def ensure_driver_user_schema(conn):
    """Tambah kolom penghubung pada tabel `drivers` (idempoten).

    Returns True bila skema siap.
    """
    if not conn:
        return False
    cursor = conn.cursor()
    try:
        cols = _columns(cursor, 'drivers')
        if 'user_id' not in cols:
            cursor.execute("ALTER TABLE drivers ADD COLUMN user_id INT NULL")
        if 'display_name' not in cols:
            cursor.execute("ALTER TABLE drivers ADD COLUMN display_name VARCHAR(100) DEFAULT ''")
        try:
            cursor.execute("ALTER TABLE drivers ADD UNIQUE KEY uq_drivers_user (user_id)")
        except Exception:
            pass  # index sudah ada / nama bentrok → abaikan
        conn.commit()
        return True
    except Exception as e:
        try:
            conn.rollback()
        except Exception:
            pass
        print(f'[driver-identity] ensure schema error: {e}')
        return False
    finally:
        cursor.close()


def _user_index(users):
    """Map username UPPER → user dict."""
    return {str(u.get('username') or '').strip().upper(): u
            for u in (users or []) if str(u.get('username') or '').strip()}


def backfill_driver_links(conn, users):
    """Isi `drivers.user_id`/`display_name` dari daftar user (idempoten).

    Pencocokan lama memakai `UPPER(users.username) = UPPER(drivers.name)`.
    Hanya role driver/chief_driver yang diikat; baris lain dibiarkan NULL
    (profil historis tanpa akun) dan akan muncul di laporan audit.
    """
    if not conn:
        return {'linked': 0, 'named': 0}
    index = _user_index(users)
    cursor = conn.cursor(dictionary=True)
    linked = named = 0
    try:
        cursor.execute("SELECT id, name, user_id, display_name FROM drivers")
        rows = cursor.fetchall()
        for d in rows:
            uid = d.get('user_id')
            user = index.get(str(d.get('name') or '').strip().upper())
            if user and user.get('role') in DRIVER_ROLES:
                if uid != user['id']:
                    cursor.execute("UPDATE drivers SET user_id=%s WHERE id=%s", (user['id'], d['id']))
                    uid = user['id']
                    linked += 1
            if uid:
                user = next((u for u in users or [] if u.get('id') == uid), None)
                full = (user or {}).get('full_name') or ''
                if full and full != (d.get('display_name') or ''):
                    cursor.execute("UPDATE drivers SET display_name=%s WHERE id=%s", (full[:100], d['id']))
                    named += 1
        conn.commit()
        return {'linked': linked, 'named': named}
    except Exception as e:
        try:
            conn.rollback()
        except Exception:
            pass
        print(f'[driver-identity] backfill error: {e}')
        return {'linked': 0, 'named': 0, 'error': str(e)}
    finally:
        cursor.close()


def rename_driver(conn, old_name, new_name):
    """Ganti nama driver + seluruh referensi teks (transactions, assignment, dst).

    Harus dipanggil sebelum baris `drivers` di-update agar tidak bentrok unik.
    Returns jumlah baris referensi yang diubah.
    """
    old_name = (old_name or '').strip().upper()
    new_name = (new_name or '').strip().upper()
    if not old_name or not new_name or old_name == new_name:
        return 0
    cursor = conn.cursor()
    changed = 0
    try:
        for table in DRIVER_REF_TABLES:
            try:
                cursor.execute(f"UPDATE {table} SET driver_name=%s WHERE driver_name=%s", (new_name, old_name))
                changed += cursor.rowcount or 0
            except Exception:
                continue  # tabel tidak ada di DB ini
        try:
            cursor.execute("UPDATE assignment_swaps SET old_driver=%s WHERE old_driver=%s", (new_name, old_name))
            cursor.execute("UPDATE assignment_swaps SET new_driver=%s WHERE new_driver=%s", (new_name, old_name))
        except Exception:
            pass
        return changed
    finally:
        cursor.close()


def sync_driver_for_user(user_id, username, full_name, role, branch_code=None,
                         is_active=True, conn=None):
    """Cerminkan satu baris `users` ke tabel `drivers` di DB cabang user.

    - role driver/chief_driver  → pastikan profil ada, nama = UPPER(username),
      nama tampilan = full_name, status mengikuti akun, dan rename cascade bila
      username berubah.
    - role lain                  → profil (bila ada) dinonaktifkan, tautan
      dilepas? Tidak: tautan dipertahankan agar riwayat tetap terbaca, hanya
      is_active=0.

    `conn` opsional (koneksi DB cabang yang sudah dibuka pemanggil). Bila
    tidak diberikan, koneksi dibuka sendiri berdasarkan branch_code.

    Returns dict: {'ok': bool, 'name': str, 'action': str, 'renamed_refs': int}
    """
    from modules.config import get_db_connection

    own_conn = conn is None
    if own_conn:
        conn = get_db_connection(branch_code=branch_code or default_branch_code())
    if not conn:
        return {'ok': False, 'error': 'DB error'}
    ensure_driver_user_schema(conn)
    cursor = conn.cursor(dictionary=True)
    try:
        name = str(username or '').strip().upper()
        full = str(full_name or '').strip()[:100]
        if role in DRIVER_ROLES:
            if not name:
                return {'ok': False, 'error': 'username kosong'}
            cursor.execute("SELECT id, name, user_id FROM drivers WHERE user_id=%s", (user_id,))
            row = cursor.fetchone()
            renamed = 0
            if row:
                if (row['name'] or '').strip().upper() != name:
                    # Ada baris lain dengan nama tujuan? Adopsi baris itu,
                    # nonaktifkan baris lama supaya tidak ada nama ganda.
                    cursor.execute("SELECT id, user_id FROM drivers WHERE name=%s AND id<>%s", (name, row['id']))
                    clash = cursor.fetchone()
                    if clash:
                        cursor.execute("UPDATE drivers SET user_id=%s, display_name=%s, is_active=%s WHERE id=%s",
                                       (user_id, full, 1 if is_active else 0, clash['id']))
                        cursor.execute("UPDATE drivers SET user_id=NULL, is_active=0 WHERE id=%s", (row['id'],))
                    else:
                        renamed = rename_driver(conn, row['name'], name)
                        cursor.execute("UPDATE drivers SET name=%s, display_name=%s, is_active=%s WHERE id=%s",
                                       (name, full, 1 if is_active else 0, row['id']))
                else:
                    cursor.execute("UPDATE drivers SET display_name=%s, is_active=%s WHERE id=%s",
                                   (full, 1 if is_active else 0, row['id']))
                action = 'rename' if renamed else 'update'
            else:
                cursor.execute("SELECT id, user_id FROM drivers WHERE name=%s", (name,))
                clash = cursor.fetchone()
                if clash:
                    cursor.execute("UPDATE drivers SET user_id=%s, display_name=%s, is_active=%s WHERE id=%s",
                                   (user_id, full, 1 if is_active else 0, clash['id']))
                    action = 'link'
                else:
                    cursor.execute(
                        "INSERT INTO drivers (name, nopol, vehicle_type, bbm_type, is_active, user_id, display_name) "
                        "VALUES (%s, '', 'AVANZA', 'PERTALITE', %s, %s, %s)",
                        (name, 1 if is_active else 0, user_id, full))
                    action = 'create'
            conn.commit()
            return {'ok': True, 'name': name, 'action': action, 'renamed_refs': renamed}
        # bukan driver: pertahankan tautan, matikan profil
        cursor.execute("UPDATE drivers SET is_active=0 WHERE user_id=%s", (user_id,))
        conn.commit()
        return {'ok': True, 'name': str(username or ''), 'action': 'deactivate'}
    except Exception as e:
        try:
            conn.rollback()
        except Exception:
            pass
        print(f'[driver-identity] sync error ({username}): {e}')
        return {'ok': False, 'error': str(e)}
    finally:
        cursor.close()
        if own_conn:
            try:
                conn.close()
            except Exception:
                pass


def get_driver_profile(branch_code, user_id):
    """Profil driver untuk satu user (dipakai /api/users). None bila belum ada."""
    from modules.config import get_db_connection
    conn = get_db_connection(branch_code=branch_code or default_branch_code())
    if not conn:
        return None
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute(
            "SELECT d.user_id, d.name, d.display_name, d.nopol, d.vehicle_type, d.bbm_type, d.is_active "
            "FROM drivers d WHERE d.user_id=%s LIMIT 1", (user_id,))
        return cursor.fetchone()
    except Exception:
        return None
    finally:
        cursor.close()
        try:
            conn.close()
        except Exception:
            pass


def driver_ref_counts(conn, name):
    """Jumlah baris historis yang memakai nama driver (untuk cegah hapus)."""
    cursor = conn.cursor()
    total = 0
    try:
        for table in DRIVER_REF_TABLES:
            try:
                cursor.execute(f"SELECT COUNT(*) FROM {table} WHERE driver_name=%s", (name,))
                total += int(cursor.fetchone()[0] or 0)
            except Exception:
                continue
    finally:
        cursor.close()
    return total


def audit_driver_identity(conn, users):
    """Audit konsistensi akun ↔ driver ↔ kendaraan pada satu DB cabang.

    Returns dict berisi daftar temuan (list of dict) dan ringkasan angka.
    Tidak mengubah data.
    """
    findings = []
    if not conn:
        return {'ok': False, 'findings': [], 'summary': {}}
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute("SHOW COLUMNS FROM drivers LIKE 'user_id'")
        has_user_id = cursor.fetchone() is not None
        cursor.execute("SELECT * FROM drivers ORDER BY name")
        drivers = cursor.fetchall()
        users_by_id = {u['id']: u for u in (users or []) if u.get('role') in DRIVER_ROLES}
        users_by_name = {str(u.get('username') or '').upper(): u
                         for u in users_by_id.values()}

        linked_user_ids = set()
        for d in drivers:
            name = (d.get('name') or '').strip()
            uid = d.get('user_id') if has_user_id else None
            if not name:
                findings.append({'type': 'driver_tanpa_nama', 'driver_id': d['id'],
                                 'detail': 'Baris drivers dengan nama kosong'})
                continue
            user = users_by_id.get(uid) if uid else users_by_name.get(name.upper())
            if not user:
                # Profil nonaktif tanpa akun = arsip historis (mis. driver
                # yang sudah keluar) — bukan temuan yang perlu ditindak.
                if d.get('is_active'):
                    findings.append({'type': 'driver_tanpa_akun', 'driver_id': d['id'], 'driver': name,
                                     'detail': f'Profil driver {name} tidak punya akun user aktif'})
            else:
                if uid:
                    linked_user_ids.add(uid)
                if name.upper() != str(user.get('username') or '').upper():
                    findings.append({'type': 'nama_tidak_sinkron', 'driver_id': d['id'], 'driver': name,
                                     'username': user.get('username'),
                                     'detail': f'drivers.name={name} ≠ UPPER(users.username)={str(user.get("username") or "").upper()}'})
                if (d.get('display_name') or '') != (user.get('full_name') or ''):
                    findings.append({'type': 'nama_tampilan_beda', 'driver_id': d['id'], 'driver': name,
                                     'display_name': d.get('display_name'),
                                     'full_name': user.get('full_name'),
                                     'detail': 'Nama tampilan driver berbeda dengan nama lengkap akun'})
                if bool(d.get('is_active')) != bool(user.get('is_active')):
                    findings.append({'type': 'status_beda', 'driver_id': d['id'], 'driver': name,
                                     'detail': f"Status driver={d.get('is_active')} akun={user.get('is_active')}"})
            # kendaraan: cache nopol harus ada di master kendaraan & assignment aktif
            nopol = (d.get('nopol') or '').strip().upper()
            if nopol and d.get('is_active'):
                cursor.execute("SELECT COUNT(*) c FROM vehicles WHERE UPPER(nopol)=%s AND is_active=1", (nopol,))
                if not int(cursor.fetchone()['c'] or 0):
                    findings.append({'type': 'nopol_tidak_terdaftar', 'driver_id': d['id'], 'driver': name,
                                     'nopol': nopol, 'detail': f'Nopol {nopol} tidak ada di master kendaraan'})
        for uid, u in users_by_id.items():
            if uid not in linked_user_ids:
                findings.append({'type': 'akun_tanpa_profil_driver', 'user_id': uid,
                                 'username': u.get('username'),
                                 'detail': f'Akun {u.get("username")} ber-role driver tapi belum punya profil driver'})

        cursor.execute("""SELECT driver_name, COUNT(*) c FROM vehicle_assignments
                          WHERE is_current=1 GROUP BY driver_name HAVING c > 1""")
        for r in cursor.fetchall():
            findings.append({'type': 'assignment_ganda', 'driver': r['driver_name'],
                             'count': r['c'],
                             'detail': f'{r["driver_name"]} punya {r["c"]} penugasan aktif sekaligus'})
        cursor.execute("""SELECT nopol, COUNT(*) c FROM vehicle_assignments
                          WHERE is_current=1 GROUP BY nopol HAVING c > 1""")
        for r in cursor.fetchall():
            findings.append({'type': 'kendaraan_ganda', 'nopol': r['nopol'],
                             'count': r['c'],
                             'detail': f'Kendaraan {r["nopol"]} dipakai {r["c"]} driver sekaligus'})
        cursor.execute("""SELECT d.name FROM drivers d
                          LEFT JOIN vehicles v ON UPPER(v.nopol)=UPPER(d.nopol) AND v.is_active=1
                          WHERE d.is_active=1 AND (d.nopol IS NULL OR d.nopol='' OR v.id IS NULL)""")
        for r in cursor.fetchall():
            findings.append({'type': 'driver_tanpa_kendaraan', 'driver': r['name'],
                             'detail': f'{r["name"]} aktif tetapi tidak punya kendaraan terdaftar'})

        summary = {}
        for f in findings:
            summary[f['type']] = summary.get(f['type'], 0) + 1
        return {'ok': True, 'findings': findings, 'summary': summary}
    finally:
        cursor.close()
