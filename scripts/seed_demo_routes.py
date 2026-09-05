#!/usr/bin/env python3
"""Seed data demo rute appointment (v2.19).

Memperkaya data demo rute untuk demo Chief Driver (auto & manual) dan PWA
driver: kota Surabaya (pusat/barat/utara/timur/selatan), sekitarnya (Sidoarjo,
Gresik, Mojokerto, Lamongan) dan luar kota (Madura, Jember, Probolinggo,
Pasuruan). Koordinat ditanam langsung (tanpa geocoding) agar langsung bisa
dioptimasi oleh route optimizer.

Idempoten: appointment dengan display_id yang sama dilewati.

Jalankan di dalam jaringan docker (web container — kredensial dari env compose):
    docker compose exec web python3 scripts/seed_demo_routes.py

atau dari host (password dari .env):
    set -a; source .env; set +a
    DB_HOST=127.0.0.1 DB_PORT=3307 python3 scripts/seed_demo_routes.py
"""
import os
import sys
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from modules.config import get_db_connection  # noqa: E402

# (display_id, nasabah, no_hp, alamat, area, sesi, jam, lat, lng, status, driver)
DEMO = [
    # ---------- Surabaya (dalam kota) ----------
    ('DEMO-R01', 'PT Sinar Abadi', '081234560001', 'Jl. Tunjungan 88, Surabaya Pusat', 'Surabaya Pusat', '1', '08:30', -7.2575, 112.7370, 'scheduled', None),
    ('DEMO-R02', 'Toko Jaya Sentosa', '081234560002', 'Jl. Pasar Kembang 15, Surabaya Pusat', 'Surabaya Pusat', '1', '09:15', -7.2460, 112.7380, 'scheduled', None),
    ('DEMO-R03', 'Hotel Graha Timur', '081234560003', 'Jl. Darmo Baru 21, Surabaya Barat', 'Surabaya Barat', '1', '10:00', -7.2825, 112.7250, 'assigned', 'RIVAN'),
    ('DEMO-R04', 'Rumah Makan Mbok Sri', '081234560004', 'Jl. Raya Wiyung 45, Surabaya Barat', 'Surabaya Barat', '1', '10:45', -7.3220, 112.6830, 'scheduled', None),
    ('DEMO-R05', 'PT Pelabuhan Nusantara', '081234560005', 'Jl. Perak Barat 120, Surabaya Utara', 'Surabaya Utara', '1', '11:30', -7.2020, 112.7350, 'scheduled', None),
    ('DEMO-R06', 'Toko Perabot Kenjeran', '081234560006', 'Jl. Kenjeran 350, Surabaya Utara', 'Surabaya Utara', '2', '13:30', -7.2350, 112.7950, 'scheduled', None),
    ('DEMO-R07', 'CV Karya Mulyorejo', '081234560007', 'Jl. Mulyorejo Indah 3, Surabaya Timur', 'Surabaya Timur', '1', '12:15', -7.2830, 112.7930, 'assigned', 'AKHAD'),
    ('DEMO-R08', 'Bengkel Mitra Rungkut', '081234560008', 'Jl. Rungkut Industri 12, Surabaya Timur', 'Surabaya Timur', '2', '14:15', -7.3334, 112.7530, 'scheduled', None),
    ('DEMO-R09', 'Klinik Sehat Wonokromo', '081234560009', 'Jl. Wonokromo 77, Surabaya Selatan', 'Surabaya Selatan', '2', '15:00', -7.3110, 112.7440, 'scheduled', None),
    ('DEMO-R10', 'Universitas Nusantara', '081234560010', 'Jl. Siwalankerto 22, Surabaya Selatan', 'Surabaya Selatan', '2', '15:45', -7.3350, 112.7420, 'assigned', 'GURUH'),
    # ---------- Sekitar Surabaya ----------
    ('DEMO-R11', 'PT Sentosa Sidoarjo', '081234560011', 'Jl. Raya Waru 15, Sidoarjo', 'Sidoarjo', '1', '09:30', -7.3550, 112.7570, 'scheduled', None),
    ('DEMO-R12', 'Pabrik Sepatu Jaya', '081234560012', 'Jl. Raya Gedangan 8, Sidoarjo', 'Sidoarjo', '2', '14:00', -7.3920, 112.7270, 'scheduled', None),
    ('DEMO-R13', 'PT Petrokimia Supplier', '081234560013', 'Jl. Raya Kebomas 30, Gresik', 'Gresik', '1', '11:00', -7.1530, 112.6520, 'scheduled', None),
    ('DEMO-R14', 'Toko Mekar Mojokerto', '081234560014', 'Jl. Raya Mojosari 60, Mojokerto', 'Mojokerto', '2', '16:00', -7.4700, 112.4330, 'scheduled', None),
    ('DEMO-R15', 'CV Agro Lamongan', '081234560015', 'Jl. Raya Lamongan 40, Lamongan', 'Lamongan', '2', '16:45', -7.1170, 112.4170, 'scheduled', None),
    # ---------- Luar kota ----------
    ('DEMO-R16', 'PT Madura Logistik', '081234560016', 'Jl. Raya Kamal, Bangkalan, Madura', 'Lainnya', '1', '08:45', -7.0460, 112.7350, 'scheduled', None),
    ('DEMO-R17', 'Koperasi Tani Sampang', '081234560017', 'Jl. Raya Sampang, Madura', 'Lainnya', '2', '13:45', -7.1870, 113.2390, 'scheduled', None),
    ('DEMO-R18', 'PT Perkebunan Jember', '081234560018', 'Jl. Gajah Mada 55, Jember', 'Lainnya', '1', '10:15', -8.1850, 113.6680, 'scheduled', None),
    ('DEMO-R19', 'Hotel Bromo View', '081234560019', 'Jl. Raya Panglima Sudirman 9, Probolinggo', 'Lainnya', '2', '15:15', -7.7540, 113.2160, 'scheduled', None),
    ('DEMO-R20', 'PT Gula Pasuruan', '081234560020', 'Jl. Raya Dr. Wahidin 21, Pasuruan', 'Pasuruan', '1', '11:45', -7.6450, 112.9070, 'scheduled', None),
]


def seed_demo_appointments(conn=None, commit=True):
    """Buat appointment demo rute (idempoten) — dipakai CLI & API admin.

    Args:
        conn: koneksi DB yang sudah terbuka (bila None, dibuka sendiri).
        commit: True untuk commit otomatis (bila conn dibuka sendiri).

    Returns:
        dict {'created': int, 'skipped': int, 'error': str|None}
    """
    own_conn = conn is None
    if conn is None:
        conn = get_db_connection()
    if not conn:
        return {'created': 0, 'skipped': 0, 'error': 'DB tidak tersedia'}
    cursor = conn.cursor(dictionary=True)
    try:
        # Prasyarat: akun marketing Yusie — users tinggal di DB MASTER
        # (multi-cabang: DB cabang tidak punya tabel users terisi).
        # Konvensi username v2.29.7: marketing_yusie_sby.
        from modules.config import get_master_connection
        mconn = get_master_connection()
        mcur = mconn.cursor(dictionary=True) if mconn else None
        yusie_ok = False
        if mcur:
            try:
                mcur.execute("SELECT id FROM users WHERE username='marketing_yusie_sby' AND is_active=1")
                yusie_ok = bool(mcur.fetchone())
            finally:
                mcur.close()
                if mconn:
                    mconn.close()
        if not yusie_ok:
            return {'created': 0, 'skipped': 0,
                    'error': 'User marketing "marketing_yusie_sby" belum ada — buat dulu di menu Users (role marketing, tim "Yusie").'}
        cursor.execute(
            "INSERT INTO marketing_members (team_name, member_name, is_active) "
            "VALUES ('Yusie','Icang',1) ON DUPLICATE KEY UPDATE is_active=1")

        today = date.today().isoformat()
        created = skipped = 0
        for row in DEMO:
            display_id, nasabah, phone, alamat, area, sesi, jam, lat, lng, status, driver = row
            cursor.execute("SELECT id FROM appointments WHERE display_id=%s", (display_id,))
            if cursor.fetchone():
                skipped += 1
                continue
            cursor.execute(
                """INSERT INTO appointments
                   (display_id, marketing_username, marketing_name, marketing_member, team_name,
                    nasabah_name, nasabah_phone, alamat, area, appointment_date, sesi, visit_time,
                    lat, lng, status, driver_name, route_order, notes)
                   VALUES (%s,'marketing_yusie_sby','Yusie Marlina','Icang','Yusie',
                           %s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                (display_id, nasabah, phone, alamat, area, today, sesi, jam,
                 lat, lng, status, driver, 1 if driver else None,
                 'Data demo rute (seed) — untuk pengujian otomatis & manual.'))
            created += 1
        if commit:
            conn.commit()
        return {'created': created, 'skipped': skipped, 'error': None}
    finally:
        cursor.close()
        if own_conn:
            conn.close()


def clean_demo_appointments(conn=None, commit=True):
    """Hapus appointment demo rute (display_id berawalan 'DEMO-').

    Dipakai API admin ('Bersihkan Data Demo') — idempoten.
    Returns: dict {'deleted': int, 'error': str|None}
    """
    own_conn = conn is None
    if conn is None:
        conn = get_db_connection()
    if not conn:
        return {'deleted': 0, 'error': 'DB tidak tersedia'}
    cursor = conn.cursor()
    try:
        cursor.execute("DELETE FROM appointments WHERE display_id LIKE 'DEMO-%'")
        deleted = cursor.rowcount
        if commit:
            conn.commit()
        return {'deleted': deleted, 'error': None}
    finally:
        cursor.close()
        if own_conn:
            conn.close()


def main():
    result = seed_demo_appointments()
    if result['error']:
        print(f'❌ {result["error"]}')
        return 1
    print(f'✅ {result["created"]} appointment demo rute dibuat untuk hari ini ({date.today().isoformat()}); {result["skipped"]} sudah ada (dilewati).')
    return 0


if __name__ == '__main__':
    sys.exit(main())
