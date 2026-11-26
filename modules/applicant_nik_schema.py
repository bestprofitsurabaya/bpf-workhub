"""Skema NIK pelamar (Rilis C) — idempoten, DB cabang.

`applicants` berada di DB masing-masing cabang, sehingga penambahan kolom NIK
harus dijalankan untuk setiap cabang aktif. NIK menjadi tulang punggung
rekrutmen lintas cabang pada rilis berikutnya; baris lama tetap NULL dan aman
karena UNIQUE MySQL mengizinkan banyak NULL.

Dijalankan saat startup dari app.py setelah skema master siap. Kegagalan satu
cabang dicatat ke stdout, tidak menghentikan cabang lain maupun startup, dan
akan dicoba lagi pada startup berikutnya (seluruh DDL idempoten).
"""
import re

from modules.config import get_db_connection, get_master_connection


_COLUMNS = (
    ('nik',
     'ALTER TABLE applicants ADD COLUMN nik CHAR(16) NULL'),
    ('nik_source',
     "ALTER TABLE applicants ADD COLUMN nik_source "
     "VARCHAR(20) NOT NULL DEFAULT ''"),
    ('linked_at',
     'ALTER TABLE applicants ADD COLUMN linked_at DATETIME NULL'),
    ('link_status',
     "ALTER TABLE applicants ADD COLUMN link_status "
     "ENUM('linked','unlinked','ambiguous') NOT NULL DEFAULT 'unlinked'"),
)

_INDEXES = (
    ('uq_applicants_nik',
     'ALTER TABLE applicants ADD UNIQUE KEY uq_applicants_nik (nik)'),
    ('idx_applicants_link_status',
     'ALTER TABLE applicants ADD KEY idx_applicants_link_status (link_status)'),
)


def _count(cursor, sql, params):
    cursor.execute(sql, params)
    row = cursor.fetchone()
    if isinstance(row, dict):
        row = next(iter(row.values()), 0)
    elif isinstance(row, (tuple, list)):
        row = row[0] if row else 0
    try:
        return int(row or 0)
    except (TypeError, ValueError):
        return 0


def _column_exists(cursor, table, column):
    return _count(
        cursor,
        """SELECT COUNT(*) FROM information_schema.COLUMNS
           WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME=%s AND COLUMN_NAME=%s""",
        (table, column)) > 0


def _index_exists(cursor, table, index):
    return _count(
        cursor,
        """SELECT COUNT(*) FROM information_schema.STATISTICS
           WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME=%s AND INDEX_NAME=%s""",
        (table, index)) > 0


def _already_applied(error):
    """Error duplikat dari worker startup lain dianggap sukses."""
    text = str(error).lower()
    return ('1060' in text or 'duplicate column' in text or
            '1061' in text or 'duplicate key name' in text)


def _masked_error(error):
    """Mask NIK 16 digit yang mungkin muncul di pesan error DB (duplicate entry)."""
    return re.sub(r'\d{16}', lambda m: '****' + m.group(0)[-4:], str(error or ''))


def ensure_applicant_nik_schema(conn):
    """Pastikan kolom NIK + unique/index ada di `applicants` satu cabang.

    `conn` wajib koneksi DB cabang dan tidak ditutup di sini. Return True bila
    semua kolom/index ada setelah pemanggilan, False bila koneksi tidak ada.
    """
    if not conn:
        print('[applicant-nik-schema] koneksi cabang tidak tersedia, skip migrasi')
        return False

    cursor = None
    try:
        cursor = conn.cursor()
        results = []
        for column, ddl in _COLUMNS:
            if _column_exists(cursor, 'applicants', column):
                results.append(True)
                continue
            try:
                cursor.execute(ddl)
                results.append(True)
            except Exception as e:
                if _already_applied(e):
                    results.append(True)
                else:
                    print(f'[applicant-nik-schema] kolom {column}: '
                          f'{_masked_error(e)}')
                    results.append(False)
        for index, ddl in _INDEXES:
            if _index_exists(cursor, 'applicants', index):
                results.append(True)
                continue
            try:
                cursor.execute(ddl)
                results.append(True)
            except Exception as e:
                if _already_applied(e):
                    results.append(True)
                else:
                    print(f'[applicant-nik-schema] index {index}: '
                          f'{_masked_error(e)}')
                    results.append(False)
        conn.commit()
        return all(results)
    except Exception as e:
        print(f'[applicant-nik-schema] fatal: {_masked_error(e)}')
        return False
    finally:
        if cursor:
            try:
                cursor.close()
            except Exception:
                pass


def _active_branch_codes():
    """Daftar kode cabang aktif dari DB master (pola cv_online_schema)."""
    conn = None
    try:
        conn = get_master_connection()
        if not conn:
            print('[applicant-nik-schema] DB master tidak tersedia, '
                  'daftar cabang dilewati')
            return []
        cursor = conn.cursor()
        try:
            cursor.execute('SELECT code FROM branches WHERE is_active=1')
            rows = cursor.fetchall() or []
        finally:
            try:
                cursor.close()
            except Exception:
                pass
        codes = []
        for row in rows:
            if isinstance(row, dict):
                value = row.get('code')
            elif isinstance(row, (tuple, list)):
                value = row[0] if row else None
            else:
                value = row
            code = str(value or '').strip().upper()
            if code and code not in codes:
                codes.append(code)
        return codes
    except Exception as e:
        print(f'[applicant-nik-schema] daftar cabang gagal: {e}')
        return []
    finally:
        if conn:
            try:
                conn.close()
            except Exception:
                pass


def ensure_applicant_nik_schema_all(branch_codes=None):
    """Jalankan `ensure_applicant_nik_schema` untuk setiap cabang.

    `branch_codes` eksplisit dipakai tes; bila None daftar dibaca dari tabel
    `branches` di master. Return dict `{kode_cabang: bool}`. Satu cabang gagal
    dicatat ke stdout dan tidak menghentikan cabang lain.
    """
    if branch_codes is None:
        branch_codes = _active_branch_codes()

    results = {}
    for raw in branch_codes or []:
        code = str(raw or '').strip().upper()
        if not code or code in results:
            continue
        conn = None
        try:
            conn = get_db_connection(branch_code=code)
            if not conn:
                results[code] = False
                print(f'[applicant-nik-schema] cabang {code}: DB tidak tersedia')
                continue
            results[code] = ensure_applicant_nik_schema(conn)
        except Exception as e:
            results[code] = False
            print(f'[applicant-nik-schema] cabang {code} dilewati: {e}')
        finally:
            if conn:
                try:
                    conn.close()
                except Exception:
                    pass
    return results
