"""Helper parsing data Google Sheet untuk sistem Overtime (v2.22).

Dipakai bersama oleh:
- modules/routes_overtime.py  (refresh sinkronisasi + form publik OB/Security)
- scripts/migrate_overtime_ob_security.py (migrasi penuh data lama)
- scripts/migrate_overtime_driver.py (migrasi penuh data Driver via Apps Script)

Fokus: memetakan kolom Google Sheet (header bebas, sering berganti ejaan)
ke field database secara toleran, plus parsing tanggal (M/D/YYYY) & jam
(12 jam: "6:29:00 PM") seperti format response Google Form.

Khusus sheet DRIVER via Google Apps Script: nilai dikirim sebagai ISO 8601
UTC (mis. "2020-12-12T07:08:54.000Z" / "1899-12-30T11:47:56.000Z"). Karena
sheet diisi dalam zona WIB (UTC+7), semua nilai UTC dikonversi +7 jam.

v2.39.0 — KONTRAK BARU (waktu sesuai sheet):
Jembatan Apps Script kini MENYERIALKAN tanggal/jam sebagai TEKS sesuai tampilan
sheet (Utilities.formatDate + zona waktu SPREADSHEET), bukan Date UTC.
Penyebab: +7 jam mengasumsikan sheet berzona WIB — sheet dengan zona lain
(mis. GMT+8 Jakarta default lama / zona acct diubah) menghasilkan tanggal &
jam bergeser di DB ("jam tidak sesuai sumber"). Parser baru
(parse_date_wall / parse_time_wall / parse_submitted_at_wall) menerima teks
wall-clock apa adanya TANPA offset; parser ISO UTC (+7) dipertahankan hanya
sebagai fallback untuk feed Apps Script lama yang belum di-deploy ulang.
"""
import re
from datetime import datetime, timedelta

# Sheet Driver diisi dalam zona WIB (Asia/Jakarta, UTC+7) — Apps Script
# mengembalikan Date sebagai ISO UTC, jadi tambahkan 7 jam untuk nilai lokal.
WIB_OFFSET = timedelta(hours=7)

# ============================================================
# Normalisasi teks
# ============================================================
def clean(s):
    """Trim + normalisasi spasi ganda + whitespace aneh."""
    return re.sub(r'\s+', ' ', (s or '').strip())


def norm_key(s):
    """Normalisasi untuk pencocokan header/nama: huruf kecil, tanpa aksen/spasi."""
    s = clean(s).lower()
    s = s.replace('á', 'a').replace('é', 'e').replace('í', 'i').replace('ó', 'o').replace('ú', 'u')
    s = s.replace('ä', 'a').replace('ö', 'o').replace('ü', 'u')
    return re.sub(r'[^a-z0-9]', '', s)


# ============================================================
# Pemetaan header sheet -> field DB (toleran ejaan)
# Setiap field punya daftar kata kunci (sudah di-norm_key).
# ============================================================
HEADER_MAP = {
    'submitted_at': ['timestamp', 'submittedat', 'tanggalwaktupengiriman', 'waktupengiriman'],
    'email': ['emailaddress', 'email', 'alamatemail'],
    'nama': ['namalengkap', 'nama', 'name', 'namakaryawan', 'karyawan', 'namapegawai'],
    'tanggal': ['tanggal', 'date', 'tanggalovertime', 'haritanggal'],
    'waktu_mulai': ['waktumulaiovertime', 'waktumulai', 'mulai', 'starttime', 'jamawal', 'jammulai', 'waktuawal',
                    'dariin', 'dari', 'jammasuk'],
    'waktu_selesai': ['waktuselesaiovertime', 'waktuselesai', 'selesai', 'endtime', 'jamakhir', 'jamselesai', 'waktuakhir',
                      'sampaiout', 'sampai', 'jamkeluar'],
    'keterangan': ['keterangan', 'notes', 'note', 'catatan', 'deskripsi', 'shift', 'uraian'],
    'foto_mulai': ['uploadfotomulaiot', 'fotomulai', 'uploadfotomulai', 'fotoawal',
                   'fotoselfieoffice', 'fotoselfie', 'selfieoffice'],
    'foto_selesai': ['uploadfotoselesaiot', 'fotoselesai', 'uploadfotoselesai', 'fotoakhir',
                     'fotoditujuan', 'fototujuan', 'ditujuan'],
    'posisi': ['posisi', 'jabatan', 'bagian', 'divisi'],
    # --- kolom khusus sheet DRIVER (Google Form lama) ---
    'no_kendaraan': ['nokendaraan', 'noplat', 'nopol', 'nomorkendaraan', 'nokendaraanot'],
    'broker': ['namabrokermarketing', 'broker', 'marketing', 'namabroker'],
    'manager': ['namamanagerteamleader', 'manager', 'teamleader', 'namamanager'],
    'doc_url': ['mergeddocurlotdriver', 'mergedocurl', 'mergedoclink', 'linkmergedoc',
                'mergeddocurl'],
}


def map_headers(headers):
    """Petakan daftar header sheet ke {field: index}. Header tak dikenal diabaikan.

    Strategi two-pass:
      1. Pencocokan PERSIS (key == keyword) — header pendek standar.
      2. Header panjang/berisik (cth 'Upload Foto Mulai OT menggunakan
         Timestamp. ') dicocokkan dengan KEYWORD TERPANJANG yang merupakan
         substring key — paling spesifik, paling aman dari false-positive.

    >>> m = map_headers(['Timestamp', 'Email Address', 'Nama Lengkap', 'Tanggal',
    ...                  'Waktu Mulai Overtime', 'Waktu Selesai Overtime', 'Keterangan',
    ...                  'Upload Foto Mulai OT menggunakan Timestamp. ',
    ...                  'Upload Foto Selesai OT menggunakan Timestamp. '])
    >>> m['nama'] == 2 and m['tanggal'] == 3 and m['waktu_mulai'] == 4
    True
    >>> m['waktu_selesai'] == 5 and m['foto_mulai'] == 7 and m['foto_selesai'] == 8
    True
    """
    keys = [norm_key(h) for h in headers]
    out = {}
    # Pass 1: persis
    for idx, key in enumerate(keys):
        for field, kws in HEADER_MAP.items():
            if field in out:
                continue
            if key in kws:
                out[field] = idx
                break
    # Pass 2: keyword terpanjang yang menjadi substring key
    for idx, key in enumerate(keys):
        if not key:
            continue
        best_field, best_len = None, -1
        for field, kws in HEADER_MAP.items():
            if field in out:
                continue
            for kw in kws:
                if kw and kw in key and len(kw) > best_len:
                    best_field, best_len = field, len(kw)
        if best_field is not None:
            out[best_field] = idx
    return out


# ============================================================
# Parsing tanggal & jam (format Google Form)
# ============================================================
def parse_date_mdy(value):
    """Tanggal 'M/D/YYYY' -> 'YYYY-MM-DD' atau None. Toleran 'M/D/YYYY HH:MM:SS'."""
    s = clean(value)
    if not s:
        return None
    m = re.match(r'^(\d{1,2})/(\d{1,2})/(\d{4})', s)
    if not m:
        return None
    try:
        return datetime(int(m.group(3)), int(m.group(1)), int(m.group(2))).date().isoformat()
    except ValueError:
        return None


def parse_iso_dt(value):
    """ISO 8601 UTC ('2020-12-12T07:08:54.000Z') -> datetime WIB (+7 jam).

    Dipakai untuk nilai dari Google Apps Script Web App (sheet DRIVER),
    termasuk nilai waktu murni ('1899-12-30T11:47:56.000Z' = basis epoch
    Google Sheets). None bila bukan format ISO UTC.
    """
    s = clean(value)
    if not s:
        return None
    m = re.match(r'^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})(?::(\d{2}))?(?:\.\d+)?Z$', s)
    if not m:
        return None
    try:
        dt = datetime(int(m.group(1)), int(m.group(2)), int(m.group(3)),
                      int(m.group(4)), int(m.group(5)), int(m.group(6) or 0))
    except ValueError:
        return None
    return dt + WIB_OFFSET


def parse_date_wall(value):
    """Tanggal wall-clock dari Apps Script v2.39 ('2020-12-12' / '1/5/2026')
    -> 'YYYY-MM-DD' TANPA offset apa pun — persis seperti tampil di sheet.

    Sengaja TIDAK memakai parse_iso_dt & menolak format ISO-UTC ('T…Z') agar
    feed script LAMA tetap masuk jalur +7 jam (fallback). String polos tanpa
    'Z' justru dilarikan ke parser lain dan berisiko digeser zona.

    >>> parse_date_wall('2020-12-12')
    '2020-12-12'
    >>> parse_date_wall('1/5/2026')
    '2026-01-05'
    >>> parse_date_wall('2026-08-14 00:00:00')
    '2026-08-14'
    >>> parse_date_wall('2020-12-11T17:00:00.000Z') is None
    True
    """
    s = clean(value)
    if not s:
        return None
    # Wall-clock murni: 'YYYY-MM-DD' atau 'YYYY-MM-DD HH:MM[:SS]' — TANPA
    # penanda ISO ('T' pemisah / 'Z' zona). ISO-UTC diserahkan ke parse_iso_dt.
    m = re.match(r'^(\d{4})-(\d{2})-(\d{2})(?: \d{1,2}:\d{2}(?::\d{2})?)?$', s)
    if m:
        try:
            return datetime(int(m.group(1)), int(m.group(2)),
                            int(m.group(3))).date().isoformat()
        except ValueError:
            return None
    return parse_date_mdy(s)


def parse_time_wall(value):
    """Jam wall-clock Apps Script v2.39 ('14:24' / '2:24:00 PM') -> 'HH:MM'
    TANPA offset — persis seperti tampil di sheet. None bila tak dikenal.

    >>> parse_time_wall('14:24')
    '14:24'
    >>> parse_time_wall('6:29:00 PM')
    '18:29'
    """
    s = clean(value)
    if not s:
        return None
    if re.match(r'^\d{1,2}:\d{2}(:\d{2})?$', s):
        # 24-jam polos — normalisasi saja zero-padding.
        m = re.match(r'^(\d{1,2}):(\d{2})', s)
        hh, mm = int(m.group(1)), int(m.group(2))
        if hh > 23 or mm > 59:
            return None
        return f'{hh:02d}:{mm:02d}'
    return parse_time_12h(s)


def parse_submitted_at_wall(value):
    """Timestamp submit wall-clock Apps Script v2.39 ('2020-12-12 14:08:54')
    -> 'YYYY-MM-DD HH:MM:SS' TANPA offset. None bila tak dikenal.

    >>> parse_submitted_at_wall('2020-12-12 14:08:54')
    '2020-12-12 14:08:54'
    >>> parse_submitted_at_wall('2020-12-12 14:08')
    '2020-12-12 14:08:00'
    """
    s = clean(value)
    if not s:
        return None
    m = re.match(r'^(\d{4})-(\d{2})-(\d{2})[ T](\d{1,2}):(\d{2})(?::(\d{2}))?$', s)
    if not m:
        return None
    try:
        dt = datetime(int(m.group(1)), int(m.group(2)), int(m.group(3)),
                      int(m.group(4)), int(m.group(5)), int(m.group(6) or 0))
    except ValueError:
        return None
    return dt.strftime('%Y-%m-%d %H:%M:%S')


def parse_date_any(value):
    """Tanggal dari format apa pun: ISO UTC -> WIB, M/D/YYYY, atau YYYY-MM-DD.

    v2.39: string wall-clock Apps Script baru ('YYYY-MM-DD' / 'M/D/YYYY')
    diprioritaskan — tanpa offset — sehingga nilai tidak lagi digeser +7 jam.
    """
    s = clean(value)
    if not s:
        return None
    # v2.39: feed Apps Script baru mengirim wall-clock polos — NOL offset.
    wall = parse_date_wall(s)
    if wall:
        return wall
    dt = parse_iso_dt(s)
    if dt:
        return dt.date().isoformat()
    return parse_date_mdy(s)


def parse_time_any(value):
    """Jam dari format apa pun: ISO UTC ('1899-12-30T07:24:56Z') -> HH:MM WIB,
    atau jam 12/24 jam biasa. None bila tidak dikenal.

    v2.39: jam wall-clock polos ('14:24') diprioritaskan — tanpa offset.
    """
    s = clean(value)
    if not s:
        return None
    # v2.39: feed Apps Script baru mengirim wall-clock polos — NOL offset.
    if re.match(r'^\d{1,2}:\d{2}(:\d{2})?$', s):
        return parse_time_wall(s)
    dt = parse_iso_dt(s)
    if dt:
        return dt.strftime('%H:%M')
    return parse_time_12h(s)


def parse_submitted_at_any(value):
    """Timestamp submit: ISO UTC -> WIB ('YYYY-MM-DD HH:MM:SS'), atau format lama.

    v2.39: timestamp wall-clock Apps Script baru diprioritaskan — tanpa offset.
    """
    s = clean(value)
    if not s:
        return None
    # v2.39: feed Apps Script baru mengirim wall-clock polos — NOL offset.
    wall = parse_submitted_at_wall(s)
    if wall:
        return wall
    dt = parse_iso_dt(s)
    if dt:
        return dt.strftime('%Y-%m-%d %H:%M:%S')
    return parse_submitted_at(s)


def parse_time_12h(value):
    """Jam '6:29:00 PM' -> '18:29' atau '06:29'. Return string HH:MM 24 jam / None."""
    s = clean(value)
    if not s:
        return None
    m = re.match(r'^(\d{1,2}):(\d{2})(?::(\d{2}))?\s*([AP]M)?$', s, re.I)
    if not m:
        return None
    hh, mm = int(m.group(1)), int(m.group(2))
    ampm = (m.group(4) or '').upper()
    if ampm == 'PM' and hh < 12:
        hh += 12
    elif ampm == 'AM' and hh == 12:
        hh = 0
    if mm > 59:
        return None
    return f'{hh:02d}:{mm:02d}'


def parse_submitted_at(value):
    """Timestamp submit '1/5/2026 20:32:44' -> 'YYYY-MM-DD HH:MM:SS' / None."""
    s = clean(value)
    if not s:
        return None
    for fmt in ('%m/%d/%Y %H:%M:%S', '%m/%d/%Y %H:%M', '%m/%d/%Y'):
        try:
            return datetime.strptime(s, fmt).strftime('%Y-%m-%d %H:%M:%S')
        except ValueError:
            continue
    return None


# ============================================================
# Normalisasi nama karyawan (typo dari input manual Google Form)
# ============================================================
# Peta ejaan salah -> ejaan baku. Kunci di-norm_key.
NAME_CANONICAL = {
    'edwinp': 'Edwin P',
    'muhajir': 'Muhajir',
    'febri': 'Febri',
    'febru': 'Febri',
    'febrj': 'Febri',
    'faisol': 'Faisol',
    'faissol': 'Faisol',
    'faisool': 'Faisol',
    'faiso l': 'Faisol',
    'fasol': 'Faisol',
    'faisok': 'Faisol',
    'fausol': 'Faisol',
    'faisl': 'Faisol',
    'faiisl': 'Faisol',
    'faisoll': 'Faisol',
}


def normalize_name(value):
    """Bakukan ejaan nama; kembalikan versi bersih bila tidak dikenal."""
    s = clean(value)
    if not s:
        return ''
    return NAME_CANONICAL.get(norm_key(s), s)


# ============================================================
# Posisi (OB / Security) — pemetaan nama dari data sheet lama.
# Konfirmasi pengguna (14/8/2026): Muhajir = Security, sisanya OB.
# ============================================================
SECURITY_NAMES = {'muhajir'}


def guess_position(nama):
    """Tebak posisi dari nama. 'Security' untuk daftar keamanan, default 'OB'."""
    return 'Security' if norm_key(nama) in SECURITY_NAMES else 'OB'


# ============================================================
# Baris sheet DRIVER -> dict siap insert/upsert ke overtime_driver
# ============================================================
def normalize_driver_row(row, headers, idx, n):
    """Ubah satu baris sheet Driver menjadi dict kolom DB (atau None bila
    nama kosong / baris kosong). `n` = indeks baris 0-based; sheet_row = n+2
    (baris 1 di spreadsheet = header).

    Kolom baru (v2.22.1): no_kendaraan, broker, manager, doc_url.
    """
    def g(field):
        i = idx.get(field)
        return clean(row.get(headers[i], '')) if i is not None and i < len(headers) else ''

    nama = g('nama')
    if not nama:
        return None
    return {
        'sheet_row': n + 2,
        'submitted_at': parse_submitted_at_any(g('submitted_at')),
        'email': g('email')[:150],
        'nama': nama[:150],
        'tanggal': parse_date_any(g('tanggal')),
        'waktu_mulai': (parse_time_any(g('waktu_mulai')) or g('waktu_mulai'))[:20],
        'waktu_selesai': (parse_time_any(g('waktu_selesai')) or g('waktu_selesai'))[:20],
        'keterangan': g('keterangan')[:500],
        'foto_mulai': g('foto_mulai')[:600],
        'foto_selesai': g('foto_selesai')[:600],
        'notes': g('notes')[:500],
        'no_kendaraan': g('no_kendaraan')[:30],
        'broker': g('broker')[:150],
        'manager': g('manager')[:150],
        'doc_url': g('doc_url')[:600],
    }
