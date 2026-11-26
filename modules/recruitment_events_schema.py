"""Skema linimasa event rekrutmen (Rilis C) — idempoten, DB master.

Tabel `recruitment_events` menyimpan riwayat aksi lintas modul (pelamar, CV,
training, TKD, FirstWork, karyawan). UNIQUE KEY membuat penulisan ulang
idempoten. Sumber kebenaran tetap tabel masing-masing modul; tabel ini dapat
dibangun ulang oleh skrip rebuild.

Dijalankan saat startup dari app.py tepat setelah ensure_recruitment_schema().
"""
_EVENTS_DDL = """
    CREATE TABLE IF NOT EXISTS recruitment_events (
        id BIGINT AUTO_INCREMENT PRIMARY KEY,
        case_id VARCHAR(40) NOT NULL DEFAULT '',
        nik CHAR(16) NULL,
        event_type VARCHAR(40) NOT NULL,
        event_at DATETIME NOT NULL,
        branch_code VARCHAR(10) NOT NULL DEFAULT '',
        actor_role VARCHAR(50) NOT NULL DEFAULT '',
        actor_name VARCHAR(150) NOT NULL DEFAULT '',
        source_module VARCHAR(30) NOT NULL DEFAULT '',
        source_id VARCHAR(64) NOT NULL DEFAULT '',
        note VARCHAR(500) NOT NULL DEFAULT '',
        metadata_json TEXT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        UNIQUE KEY uq_re_event (source_module, branch_code, source_id, event_type),
        KEY idx_re_case_event (case_id, event_at),
        KEY idx_re_nik_event (nik, event_at),
        KEY idx_re_branch_event (branch_code, event_at)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
"""


def ensure_recruitment_events_schema(conn=None):
    """Pastikan tabel `recruitment_events` ada di DB master (idempoten).

    `conn` opsional: bila diberikan dipakai langsung dan tidak ditutup di sini.
    Return True bila tabel siap, False bila koneksi tidak tersedia/gagal.
    """
    own = conn is None
    try:
        if conn is None:
            from modules.config import get_master_connection
            conn = get_master_connection()
        if not conn:
            print('[recruitment-events-schema] DB master unavailable, '
                  'skip migration')
            return False

        cursor = conn.cursor()
        try:
            cursor.execute(_EVENTS_DDL)
            conn.commit()
            return True
        except Exception as e:
            print(f'[recruitment-events-schema] recruitment_events: {e}')
            return False
        finally:
            try:
                cursor.close()
            except Exception:
                pass
    except Exception as e:
        print(f'[recruitment-events-schema] fatal: {e}')
        return False
    finally:
        if own and conn:
            try:
                conn.close()
            except Exception:
                pass
