"""Guard anti-kecurangan BBM yang dipakai bersama klaim & LPJ (v2.120.0).

Sebelum v2.120.0 endpoint LPJ (`/api/cash/submit-lpj/<id>`) menyimpan bukti
tanpa melewati guard yang sama dengan klaim BBM: foto rusak, foto yang pernah
dipakai, ODO mundur, dan kapasitas tangki hanya diperiksa di jalur klaim.

Modul ini menaruh satu definisi untuk kedua jalur. Perbedaan sengaja hanya
pada SEVERITY:

- Klaim BBM: pelanggaran fisik (ODO mundur, liter > kapasitas) DITOLAK.
- LPJ kasbon: satu kasbon bisa menutup beberapa pengisian, jadi ODO/ kapasitas
  hanya menjadi *anomali* (flag untuk GA), bukan penolakan. Yang tetap
  DITOLAK: file foto rusak dan hash foto yang sudah pernah dipakai.

Semua fungsi best-effort: kegagalan DB (mis. proof_registry belum siap)
mengembalikan hasil netral, tidak menggagalkan transaksi bisnis.
"""
import os

from modules.helpers import sha256_file, extract_photo_meta

# Status klaim yang dianggap bukti valid untuk baseline ODO.
VALID_CLAIM_STATUSES = ('verified_ga', 'os_finance', 'archived')

PROOF_WINDOW_DAYS = 30


def invalid_saved_photos(upload_dir, saved):
    """Field yang tersimpan tetapi isinya bukan gambar sah.

    `saved` = {field: nama_file|None}. Ekstensi saja tidak cukup: file teks
    bernama .jpg pernah lolos dan tersimpan sebagai bukti rusak.
    """
    bad = []
    for field, filename in (saved or {}).items():
        if not filename:
            continue
        try:
            from PIL import Image
            with Image.open(os.path.join(upload_dir, filename)) as im:
                im.verify()
        except Exception:
            bad.append(field)
    return bad


def delete_saved_photos(upload_dir, filenames):
    """Hapus file bukti yang sudah terlanjur disimpan (best-effort)."""
    for filename in filenames or ():
        if not filename:
            continue
        try:
            path = os.path.join(upload_dir, filename)
            if os.path.exists(path):
                os.remove(path)
        except OSError:
            pass


def previous_valid_claim(cursor, nopol):
    """Klaim tervalidasi terakhir untuk nopol (baseline ODO)."""
    cursor.execute(
        "SELECT odo_km, display_id FROM transactions "
        "WHERE nopol=%s AND status IN ('verified_ga','os_finance','archived') "
        "ORDER BY created_at DESC LIMIT 1", (nopol,))
    return cursor.fetchone()


def odo_backward_message(previous, odo_km, label='klaim valid terakhir'):
    """Pesan penolakan bila ODO lebih kecil dari baseline, else None."""
    try:
        prev_odo = int((previous or {}).get('odo_km') or 0)
    except (TypeError, ValueError):
        return None
    try:
        odo_km = int(odo_km or 0)
    except (TypeError, ValueError):
        return None
    if previous and odo_km < prev_odo:
        display_id = (previous or {}).get('display_id') or '?'
        return (f"ODO mundur: {odo_km} km < {label} "
                f"{prev_odo} km ({display_id}). Periksa pembacaan odometer; "
                "bila meter baru dipasang, laporkan GA/Admin untuk kalibrasi.")
    return None


def fuel_capacity(cursor, vehicle_type):
    """Kapasitas tangki kendaraan; 0 bila tidak diketahui."""
    try:
        cursor.execute(
            "SELECT fuel_capacity FROM vehicles WHERE vehicle_type=%s LIMIT 1",
            (vehicle_type,))
        row = cursor.fetchone()
        return float((row or {}).get('fuel_capacity') or 0)
    except Exception:
        return 0.0


def capacity_reject_message(liter, capacity, vehicle_type):
    """Penolakan klaim bila liter > kapasitas fisik tangki."""
    if capacity and capacity > 0 and liter > capacity:
        return (f"Klaim {liter:.1f} L melebihi kapasitas tangki "
                f"{vehicle_type} ({capacity:.0f} L) — tidak mungkin fisik. "
                "Periksa nominal/odometer.")
    return None


def hashes_and_meta(photo_paths):
    """{field: path} -> (hashes, meta) untuk file yang benar-benar ada."""
    hashes, meta = {}, {}
    for field, path in (photo_paths or {}).items():
        if not path or not os.path.exists(path):
            continue
        digest = sha256_file(path)
        if not digest:
            continue
        hashes[field] = digest
        info = extract_photo_meta(path)
        info['sha256'] = digest
        info['bytes'] = os.path.getsize(path)
        meta[field] = info
    return hashes, meta


def find_duplicate_proofs(hashes, days=PROOF_WINDOW_DAYS):
    """Cari hash yang sudah dipakai klaim/LPJ lain dalam `days` hari.

    Butuh DB master (registry lintas cabang). Kegagalan DB -> [] (fail-open).
    """
    if not hashes:
        return []
    from modules.config import get_master_connection
    conn = None
    try:
        conn = get_master_connection()
        if not conn:
            return []
        cur = conn.cursor(dictionary=True)
        try:
            values = list(hashes.values())
            placeholders = ','.join(['%s'] * len(values))
            cur.execute(
                "SELECT sha256, display_id, created_at FROM proof_registry "
                f"WHERE sha256 IN ({placeholders}) "
                "AND created_at >= DATE_SUB(NOW(), INTERVAL %s DAY)",
                tuple(values) + (int(days),))
            return cur.fetchall() or []
        finally:
            cur.close()
    except Exception as exc:
        print(f"[bbm-guard] proof registry check: {exc}")
        return []
    finally:
        if conn:
            try:
                conn.close()
            except Exception:
                pass


def register_proof_hashes(tx_id, display_id, driver_name, nopol, photo_meta,
                          branch_db=''):
    """Catat hash bukti ke proof_registry (master) — best-effort.

    Dipanggil klaim BBM (sejak v2.49.3) dan LPJ kasbon (v2.120.0) supaya foto
    yang sama tidak bisa dipakai ulang di jalur mana pun.
    """
    if not photo_meta:
        return False
    from modules.config import get_master_connection
    conn = None
    try:
        conn = get_master_connection()
        if not conn:
            return False
        cur = conn.cursor()
        try:
            for field, meta in photo_meta.items():
                digest = (meta or {}).get('sha256')
                if not digest:
                    continue
                cur.execute(
                    "INSERT INTO proof_registry (sha256, field, tx_id, display_id, "
                    "driver_name, nopol, branch_db) VALUES (%s,%s,%s,%s,%s,%s,%s)",
                    (digest, field, tx_id, display_id, driver_name, nopol, branch_db))
            conn.commit()
            return True
        finally:
            try:
                cur.close()
            except Exception:
                pass
    except Exception as exc:
        print(f"[proof_registry] gagal catat hash #{display_id}: {exc}")
        return False
    finally:
        if conn:
            try:
                conn.close()
            except Exception:
                pass


def anomaly_reasons(cursor, driver_name, previous, odo_km, liter, capacity,
                    photo_meta, nominal, odo_backward=False):
    """Alasan anomali (soft flag) — dipakai klaim & LPJ.

    Cap harian/mingguan dibaca dari system_config; bila belum diatur (0)
    pemeriksaan dilewati.
    """
    reasons = []
    try:
        prev_odo = int((previous or {}).get('odo_km') or 0)
    except (TypeError, ValueError):
        prev_odo = 0
    if odo_backward:
        reasons.append('ODO lebih rendah dari klaim valid terakhir')
    elif previous and prev_odo == int(odo_km or 0):
        reasons.append('ODO tidak berubah dari klaim terakhir')

    if capacity and capacity > 0 and liter > capacity * 0.9:
        reasons.append(f"Pengisian {liter:.1f} L > 90% kapasitas tangki "
                       f"({capacity:.0f} L) — verifikasi fisik struk")

    if not (photo_meta or {}).get('foto_struk', {}).get('exif_datetime') and \
       not (photo_meta or {}).get('foto_struk_dispenser', {}).get('exif_datetime'):
        reasons.append('Foto struk tanpa data exif kamera (periksa asal foto)')

    for cfg_key, days, label in (('bbm_daily_cap_driver', 1, 'harian'),
                                 ('bbm_weekly_cap_driver', 7, 'mingguan')):
        try:
            cursor.execute(
                "SELECT config_value FROM system_config WHERE config_key=%s",
                (cfg_key,))
            row = cursor.fetchone()
            cap = float((row or {}).get('config_value') or 0)
            if cap <= 0:
                continue
            cursor.execute(
                "SELECT COALESCE(SUM(nominal),0) AS total FROM transactions "
                "WHERE driver_name=%s AND transaction_type='CLAIM' "
                "AND status <> 'rejected' "
                f"AND created_at >= DATE_SUB(NOW(), INTERVAL {int(days)} DAY)",
                (driver_name,))
            total_row = cursor.fetchone()
            total = float((total_row or {}).get('total') or 0)
            if total + nominal > cap:
                reasons.append(
                    f"Total klaim {label} akan melewati batas Rp{cap:,.0f} "
                    f"(Rp{total + nominal:,.0f})")
        except Exception as exc:
            print(f"[bbm-guard] cap check: {exc}")
    return reasons
