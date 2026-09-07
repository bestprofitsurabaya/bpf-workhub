"""Air Minum Routes (v2.6) — Tanda Terima Pembelian Air Minum.

Alur:
1. Finance (atau admin) menyediakan master merk per tipe (gelas/botol/galon).
2. OB mengajukan pembelian: tanggal + item (tipe, merk, satuan, kuantitas) +
   foto timestamp "sebelum diisi" & "sesudah diisi".
3. Finance memverifikasi: approve (remark + note) atau tolak (alasan).
4. Pengajuan terverifikasi -> PDF tanda terima TTD Finance (menyerahkan)
   & GA (menerima); nama TTD di-set admin via system_config.

v2.37.0 — Edit & Hapus transaksi (fitur opsional, default NONAKTIF):
- Admin mengaktifkan per cabang via system_config key `water_edit_enabled`
  (halaman Pengaturan → seksi Air Minum). Nonaktif = perilaku lama.
- Aktif → Finance/admin bisa MENGEDIT (tanggal/item/remark/note) pengajuan
  berstatus `pending` & `verified` (bukan `rejected` — cukup alasan tolaknya),
  dan MENGHAPUS PERMANEN pengajuan (file foto ikut dihapus).
- Keduanya wajib step-up PIN (A.8.5) dan tercatat penuh di audit log
  (old_data = snapshot lengkap sebelum perubahan) — integritas audit trail
  tetap terjaga sekalipun data boleh dikoreksi.
"""
import os
import re as _re
from datetime import datetime, timedelta
from flask import request, jsonify, make_response, session
from modules.config import get_db_connection
from modules.helpers import (role_required, log_activity_async, save_file,
                             generate_display_id, client_ip)
from modules.stepup import stepup_required
from modules.admin_scope import assert_branch_row_scope

WATER_ROLES = ['ob', 'finance', 'admin']          # pengguna air minum
WATER_FINANCE_ROLES = ['finance', 'admin']        # kelola master + verifikasi
VALID_SATUAN = {'pcs', 'dus', 'karton', 'botol', 'gelas', 'galon', 'unit'}

# system_config key fitur edit/hapus transaksi air minum (v2.37.0).
# Default: 'false' (nonaktif) — perilaku lama sampai admin mengaktifkannya.
WATER_EDIT_CONFIG_KEY = 'water_edit_enabled'
EDITABLE_STATUSES = ('pending', 'verified')       # rejected tidak bisa diedit


def get_water_edit_enabled(conn=None):
    """Status fitur edit/hapus transaksi air minum (per cabang, system_config).

    Tanpa DB → False (fail-closed; API pun menolak bila DB mati).
    """
    own = conn is None
    if own:
        try:
            conn = get_db_connection()
        except Exception:
            conn = None
    if not conn:
        return False
    cur = conn.cursor(dictionary=True)
    try:
        cur.execute("SELECT config_value FROM system_config WHERE config_key=%s",
                    (WATER_EDIT_CONFIG_KEY,))
        row = cur.fetchone()
        return str((row or {}).get('config_value', '')).strip().lower() == 'true'
    except Exception:
        return False
    finally:
        cur.close()
        if own and conn:
            conn.close()


def set_water_edit_enabled(enabled, conn=None):
    """Simpan status fitur (system_config per DB cabang). Returns True bila ok."""
    own = conn is None
    if own:
        conn = get_db_connection()
    if not conn:
        return False
    cur = conn.cursor()
    try:
        cur.execute("INSERT INTO system_config (config_key, config_value) VALUES (%s,%s) "
                    "ON DUPLICATE KEY UPDATE config_value=VALUES(config_value)",
                    (WATER_EDIT_CONFIG_KEY, 'true' if enabled else 'false'))
        conn.commit()
        return True
    finally:
        cur.close()
        if own and conn:
            conn.close()


def ensure_water_edit_columns(conn):
    """Kolom jejak edit di water_purchases (v2.37.0) — idempoten, dipanggil
    saat startup (master + tiap DB cabang).

    edited_by/edited_at = jejak terakhir Finance mengedit; edit_count =
    berapa kali pernah diedit (tampil di detail & cetak audit).
    """
    cur = conn.cursor()
    try:
        for ddl in (
            "ALTER TABLE water_purchases ADD COLUMN edited_by VARCHAR(100) DEFAULT ''",
            "ALTER TABLE water_purchases ADD COLUMN edited_at DATETIME DEFAULT NULL",
            "ALTER TABLE water_purchases ADD COLUMN edit_count INT NOT NULL DEFAULT 0",
        ):
            try:
                cur.execute(ddl)
            except Exception:
                pass  # kolom sudah ada
        conn.commit()
        return True
    finally:
        cur.close()


def _water_edit_gate(conn=None):
    """Gerbang fitur edit/hapus: (None) bila boleh, atau (jsonify, status)."""
    if not get_water_edit_enabled(conn):
        return jsonify({'status': 'error',
                        'msg': 'Fitur edit/hapus transaksi air minum sedang nonaktif. '
                               'Hubungi Admin untuk mengaktifkannya.'}), 403
    return None


def _normalize_water_items(items):
    """Validasi & normalisasi daftar item (dipakai create & edit)."""
    if not isinstance(items, list) or not items:
        return None, 'Minimal satu item wajib diisi'
    if len(items) > 20:
        return None, 'Maksimal 20 item per pengajuan'
    normalized = []
    for it in items:
        tipe = str(it.get('drink_type', '') or '').strip()
        brand = str(it.get('brand', '') or '').strip()
        satuan = str(it.get('satuan', 'pcs') or 'pcs').strip().lower()
        try:
            qty = int(it.get('quantity', 0) or 0)
        except (TypeError, ValueError):
            return None, 'Kuantitas item harus berupa angka'
        if not tipe or not brand:
            return None, 'Setiap item wajib: jenis dan merk'
        if qty <= 0 or qty > 99999:
            return None, 'Kuantitas item harus 1–99.999'
        if satuan not in VALID_SATUAN:
            satuan = 'pcs'
        normalized.append({'drink_type': tipe, 'brand': brand,
                           'satuan': satuan, 'quantity': qty})
    return normalized, None


def _session_name():
    return (session.get('full_name') or session.get('user_name') or '').strip()


def _month_range(today=None):
    """(awal, akhir) bulan berjalan, INKLUSIF — default rentang daftar (v2.37.4).

    v2.37.6: akhir = hari terakhir bulan (inklusif, senada date picker UI).
    Sebelumnya eksklusif (tanggal 1 bulan berikutnya) — bug: filter UI
    "Sampai 31 Agustus" menyembunyikan transaksi 31 Agustus.
    """
    import calendar
    from datetime import date as _date
    t = today or _date.today()
    first = t.replace(day=1)
    last_day = calendar.monthrange(t.year, t.month)[1]
    return first, _date(t.year, t.month, last_day)  # akhir INKLUSIF — query pakai < akhir+1 hari


def _parse_ymd(s):
    """Parse YYYY-MM-DD → date, None bila tidak valid (aman utk query param)."""
    from datetime import datetime as _dt
    try:
        return _dt.strptime(str(s or '').strip()[:10], '%Y-%m-%d').date()
    except (ValueError, TypeError):
        return None


def _get_ttd_names():
    """Nama TTD dari system_config (di-set admin di /app/settings)."""
    ga = finance = head = ''
    try:
        conn = get_db_connection()
        if not conn:
            return ga, finance, head
        cur = conn.cursor(dictionary=True)
        cur.execute("SELECT config_key, config_value FROM system_config "
                    "WHERE config_key IN ('water_ga_name','water_finance_name','water_head_name')")
        for row in cur.fetchall():
            if row['config_key'] == 'water_ga_name':
                ga = (row['config_value'] or '').strip()
            elif row['config_key'] == 'water_finance_name':
                finance = (row['config_value'] or '').strip()
            elif row['config_key'] == 'water_head_name':
                head = (row['config_value'] or '').strip()
        cur.close()
        conn.close()
    except Exception as e:
        print(f"[water] get_ttd_names: {e}")
    return ga, finance, head


def _export_meta(d_from, d_to, status, q):
    """Meta laporan export (v2.37.6): rentang, filter, identitas CABANG, TTD.

    Kop laporan mengikuti cabang sesi (tabel branches di DB master:
    address/phone/company_subtitle). Fallback identitas global bila baris
    cabang tidak ada / DB master tak tersedia.
    """
    company = {}
    city = ''
    branch = (session.get('branch_code') or '').strip().upper() or 'JKT'
    try:
        conn = get_db_connection(master=True)
        if conn:
            cur = conn.cursor(dictionary=True)
            cur.execute(
                "SELECT company_name, company_subtitle, address, phone, city "
                "FROM branches WHERE code=%s", (branch,))
            row = cur.fetchone() or {}
            cur.close()
            conn.close()
            city = (row.get('city') or '').strip()
            name = (row.get('company_name') or '').strip() or 'PT BESTPROFIT FUTURES'
            subtitle = ((row.get('company_subtitle') or '').strip()
                        or (f'Cabang {city}' if city else f'Cabang {branch}'))
            company = {'company_name': name, 'company_subtitle': subtitle}
            if (row.get('address') or '').strip():
                company['company_address'] = row['address'].strip()
            if (row.get('phone') or '').strip():
                company['company_phone'] = row['phone'].strip()
    except Exception as e:
        print(f"[water] export_meta branch identity: {e}")
        company = {}
    if not company:
        try:
            from modules.company_identity import get_company_identity
            company = get_company_identity()
        except Exception:
            company = {}
    _, finance_name, head_name = _get_ttd_names()
    parts = []
    if status != 'all':
        parts.append('Status ' + STATUS_LABEL.get(status, status))
    if q:
        parts.append(f'Pencarian "{q}"')
    return {
        'from': d_from, 'to': d_to,
        'filters_text': ' · '.join(parts),
        'company': company,
        'city': city,
        'head_name': head_name,
        'finance_name': finance_name,
    }


def _query_purchases(d_from, d_to, status, q, role):
    """Query daftar pengajuan dengan filter — dipakai daftar & export (satu sumber).

    Return (rows, conn) — conn harus di-close pemanggil (dipakai lagi utk
    batch-load item).
    """
    conn = get_db_connection()
    if not conn:
        return None, None
    cur = conn.cursor(dictionary=True)
    # v2.37.6: `to` INKLUSIF (senada date picker UI) — query pakai
    # < (d_to + 1 hari). purchase_date bertipe DATE (tanpa jam), jadi
    # +1 hari = aman & tetap parameterized.
    from datetime import timedelta as _td
    to_excl = d_to + _td(days=1)
    where = ["wp.purchase_date >= %s", "wp.purchase_date < %s"]
    params = [d_from, to_excl]
    if status != 'all':
        where.append("wp.status = %s")
        params.append(status)
    if q:
        like = f"%{q}%"
        where.append("(wp.display_id LIKE %s OR wp.ob_name LIKE %s "
                     "OR EXISTS (SELECT 1 FROM water_purchase_items wpi "
                    "            WHERE wpi.purchase_id = wp.id "
                    "              AND wpi.brand LIKE %s))")
        params.extend([like, like, like])
    if role == 'ob':
        where.append("wp.ob_name = %s")
        params.append(_session_name())
    where_sql = ' AND '.join(where)
    limit = 200 if role == 'ob' else 500
    cur.execute(
        f"""SELECT wp.* FROM water_purchases wp
            WHERE {where_sql}
            ORDER BY wp.id DESC LIMIT {int(limit)}""",
        tuple(params))
    rows = cur.fetchall()
    if rows:
        ids = [r['id'] for r in rows]
        fmt = ','.join(['%s'] * len(ids))
        cur.execute(
            "SELECT purchase_id, drink_type, brand, satuan, quantity "
            f"FROM water_purchase_items WHERE purchase_id IN ({fmt}) ORDER BY id",
            tuple(ids))
        items_by_purchase = {}
        for it in cur.fetchall():
            items_by_purchase.setdefault(it['purchase_id'], []).append(it)
        for r in rows:
            r['items'] = items_by_purchase.get(r['id'], [])
            r['status_label'] = STATUS_LABEL.get(r['status'], r['status'])
    else:
        for r in rows:
            r['items'] = []
            r['status_label'] = STATUS_LABEL.get(r['status'], r['status'])
    return rows, conn


def _purchase_row(cur, p):
    """Perkaya satu baris pengajuan dengan rincian item (list)."""
    p = dict(p)
    cur.execute("SELECT drink_type, brand, satuan, quantity "
                "FROM water_purchase_items WHERE purchase_id=%s ORDER BY id", (p['id'],))
    p['items'] = cur.fetchall()
    p['status_label'] = STATUS_LABEL.get(p['status'], p['status'])
    return p


STATUS_LABEL = {'pending': 'Menunggu Verifikasi', 'verified': 'Terverifikasi',
                'rejected': 'Ditolak'}


def _aggregate_water_recap(rows, items_by, kas):
    """Agregasi rekap pengajuan air minum (murni, tanpa DB) — dipakai endpoint
    /api/water/recap dan /export. rows = baris pengajuan; items_by = {purchase_id: [item]};
    kas = hasil agregasi fuel_cash_requests (count/nominal status GA_APPROVED & LPJ_SUBMITTED)."""
    summary = {'total': 0, 'pending': 0, 'verified': 0, 'rejected': 0, 'qty': 0}
    per_ob, per_type, per_brand, queue = {}, {}, {}, []
    for r in rows:
        s = r.get('status') or 'pending'
        if s not in summary:
            s = 'pending'
        summary['total'] += 1
        summary[s] += 1
        ob = (str(r.get('ob_name') or '')).strip() or '-'
        po = per_ob.setdefault(ob, {'ob_name': ob, 'total': 0, 'pending': 0,
                                    'verified': 0, 'rejected': 0, 'qty': 0})
        po['total'] += 1
        po[s] += 1
        for it in items_by.get(r.get('id'), []):
            try:
                qty = int(it.get('quantity', 0) or 0)
            except (TypeError, ValueError):
                qty = 0
            summary['qty'] += qty
            po['qty'] += qty
            t = (str(it.get('drink_type') or '')).strip() or '-'
            b = (str(it.get('brand') or '')).strip() or '-'
            pt = per_type.setdefault(t, {'name': t, 'qty': 0, 'purchases': 0})
            pt['qty'] += qty
            pt['purchases'] += 1
            pb = per_brand.setdefault(b, {'name': b, 'qty': 0, 'purchases': 0})
            pb['qty'] += qty
            pb['purchases'] += 1
        if s == 'pending' and len(queue) < 20:
            queue.append({
                'id': r.get('id'),
                'display_id': r.get('display_id'),
                'ob_name': ob,
                'purchase_date': str(r.get('purchase_date') or ''),
                'item_count': len(items_by.get(r.get('id'), [])),
            })
    kasbon = {
        'waiting_approve': {
            'count': int(kas.get('waiting_approve_count') or 0),
            'nominal': float(kas.get('waiting_approve_nominal') or 0),
        },
        'waiting_lpj': {'count': int(kas.get('waiting_lpj_count') or 0)},
    }
    return {
        'summary': summary,
        'per_ob': sorted(per_ob.values(), key=lambda x: -x['total']),
        'per_type': sorted(per_type.values(), key=lambda x: -x['qty']),
        'per_brand': sorted(per_brand.values(), key=lambda x: -x['qty']),
        'queue': queue,
        'kasbon': kasbon,
    }


def _water_recap_data(from_date='', to_date=''):
    """Ambil data pengajuan + item + ringkasan kasbon utk rekap dashboard Finance.

    Filter rentang tanggal (format YYYY-MM-DD; nilai tak valid diabaikan).
    Tanpa filter, default 90 hari terakhir agar query tetap ringan seiring
    bertambahnya data."""
    def _valid_date(s):
        return bool(s and _re.fullmatch(r'\d{4}-\d{2}-\d{2}', s))
    conds, params = [], []
    lo = from_date if _valid_date(from_date) else ''
    hi = to_date if _valid_date(to_date) else ''
    if not lo:
        lo = (datetime.now() - timedelta(days=90)).strftime('%Y-%m-%d')
    conds.append("DATE(purchase_date) >= %s")
    params.append(lo)
    if hi:
        conds.append("DATE(purchase_date) <= %s")
        params.append(hi)
    conn = get_db_connection()
    if not conn:
        return None
    cur = conn.cursor(dictionary=True)
    cur.execute(
        "SELECT id, display_id, ob_name, purchase_date, status, remark, created_at "
        "FROM water_purchases WHERE " + ' AND '.join(conds) + " ORDER BY id DESC LIMIT 2000",
        params)
    rows = cur.fetchall()
    items_by = {}
    if rows:
        ids = [r['id'] for r in rows]
        fmt = ','.join(['%s'] * len(ids))
        cur.execute(
            "SELECT purchase_id, drink_type, brand, satuan, quantity "
            f"FROM water_purchase_items WHERE purchase_id IN ({fmt}) ORDER BY id",
            tuple(ids))
        for it in cur.fetchall():
            items_by.setdefault(it['purchase_id'], []).append(it)
    cur.execute("""SELECT
        SUM(CASE WHEN status='GA_APPROVED' THEN 1 ELSE 0 END) AS waiting_approve_count,
        SUM(CASE WHEN status='GA_APPROVED' THEN total_amount ELSE 0 END) AS waiting_approve_nominal,
        SUM(CASE WHEN status='LPJ_SUBMITTED' THEN 1 ELSE 0 END) AS waiting_lpj_count
        FROM fuel_cash_requests""")
    kas = cur.fetchone()
    cur.close()
    conn.close()
    result = _aggregate_water_recap(rows, items_by, kas)
    result['rows'] = rows
    result['items_by'] = items_by
    return result


def _build_water_csv(rows, items_by):
    """CSV (UTF-8 BOM agar terbuka rapi di Excel) — satu baris per item."""
    import csv
    import io as _io
    buf = _io.StringIO()
    w = csv.writer(buf)
    w.writerow(['Tanggal', 'Nomor', 'OB', 'Status', 'Jenis', 'Merk', 'Satuan', 'Kuantitas', 'Remark'])
    for r in rows:
        items = items_by.get(r.get('id'), []) or [{}]
        for it in items:
            w.writerow([
                str(r.get('purchase_date') or ''),
                r.get('display_id'),
                r.get('ob_name'),
                STATUS_LABEL.get(r.get('status'), r.get('status') or ''),
                it.get('drink_type') or '',
                it.get('brand') or '',
                it.get('satuan') or '',
                it.get('quantity') if it.get('quantity') is not None else '',
                (r.get('remark') or '') if it else '',
            ])
    return '\ufeff' + buf.getvalue()


def register_water_routes(app):

    # ============================================================
    # MASTER DATA — tipe & merk (dikelola Finance)
    # ============================================================
    @app.route('/api/water/brands')
    @role_required(WATER_ROLES)
    def api_water_brands():
        """Tipe + merk aktif untuk dropdown OB. Grouped per tipe."""
        try:
            conn = get_db_connection()
            if not conn:
                return jsonify({'error': 'DB error'}), 500
            cur = conn.cursor(dictionary=True)
            cur.execute("SELECT id, name FROM water_drink_types "
                        "WHERE is_active=1 ORDER BY FIELD(name,'Gelas','Botol','Galon'), name")
            types = cur.fetchall()
            cur.execute("""SELECT b.id, b.type_id, t.name AS drink_type, b.brand
                           FROM water_drink_brands b
                           JOIN water_drink_types t ON t.id=b.type_id
                           WHERE b.is_active=1 ORDER BY t.name, b.brand""")
            brands = cur.fetchall()
            cur.close(); conn.close()
            for t in types:
                t['brands'] = [b for b in brands if b['type_id'] == t['id']]
            return jsonify({'types': types, 'brands': brands})
        except Exception as e:
            return jsonify({'error': str(e)}), 500

    @app.route('/api/water/brands', methods=['POST'])
    @role_required(WATER_FINANCE_ROLES)
    def api_water_brand_add():
        try:
            data = request.get_json(silent=True) or {}
            type_id = data.get('type_id')
            brand = str(data.get('brand', '') or '').strip()
            if not type_id or not brand:
                return jsonify({'status': 'error', 'msg': 'Tipe dan merk wajib diisi'}), 400
            if len(brand) > 100:
                return jsonify({'status': 'error', 'msg': 'Merk maksimal 100 karakter'}), 400
            conn = get_db_connection()
            if not conn:
                return jsonify({'status': 'error', 'msg': 'DB error'}), 500
            cur = conn.cursor()
            cur.execute("INSERT INTO water_drink_brands (type_id, brand) VALUES (%s,%s) "
                        "ON DUPLICATE KEY UPDATE is_active=1, updated_at=NOW()",
                        (int(type_id), brand))
            new_id = cur.lastrowid  # baca SEBELUM commit (reliabel di MySQL/MariaDB)
            conn.commit()
            cur.close(); conn.close()
            log_activity_async(0, 'water_brand_add', session.get('user_role', ''),
                               _session_name() or 'Finance', new_data={'type_id': type_id, 'brand': brand},
                               ip=client_ip())
            return jsonify({'status': 'success', 'msg': f'Merk {brand} disimpan', 'id': new_id})
        except Exception as e:
            return jsonify({'status': 'error', 'msg': str(e)}), 500

    @app.route('/api/water/brands/<int:brand_id>', methods=['DELETE'])
    @role_required(WATER_FINANCE_ROLES)
    def api_water_brand_delete(brand_id):
        try:
            conn = get_db_connection()
            if not conn:
                return jsonify({'status': 'error', 'msg': 'DB error'}), 500
            cur = conn.cursor()
            cur.execute("UPDATE water_drink_brands SET is_active=0 WHERE id=%s", (brand_id,))
            affected = cur.rowcount
            conn.commit(); cur.close(); conn.close()
            if affected == 0:
                return jsonify({'status': 'error', 'msg': 'Merk tidak ditemukan'}), 404
            log_activity_async(0, 'water_brand_delete', session.get('user_role', ''),
                               _session_name() or 'Finance', new_data={'brand_id': brand_id},
                               ip=client_ip())
            return jsonify({'status': 'success', 'msg': 'Merk dinonaktifkan'})
        except Exception as e:
            return jsonify({'status': 'error', 'msg': str(e)}), 500

    # ============================================================
    # PENGAJUAN — diisi OB
    # ============================================================
    @app.route('/api/water/purchases', methods=['POST'])
    @role_required(['ob', 'admin'])
    def api_water_purchase_create():
        """Buat pengajuan (multipart): tanggal, items JSON, foto before & after."""
        try:
            ob_name = _session_name() or 'OB'
            tanggal = (request.form.get('purchase_date') or '').strip()
            items_raw = request.form.get('items') or '[]'
            import json as _json
            items = _json.loads(items_raw)
            normalized, n_err = _normalize_water_items(items)
            if n_err:
                return jsonify({'status': 'error', 'msg': n_err}), 400
            if not tanggal:
                return jsonify({'status': 'error', 'msg': 'Tanggal pengiriman wajib diisi'}), 400

            foto_before = save_file(request.files.get('foto_before'), 'WTR_BEFORE', ob_name, app.config['UPLOAD_FOLDER'])
            foto_after = save_file(request.files.get('foto_after'), 'WTR_AFTER', ob_name, app.config['UPLOAD_FOLDER'])
            if not foto_before or not foto_after:
                return jsonify({'status': 'error', 'msg': 'Foto "sebelum diisi" dan "sesudah diisi" wajib diunggah (JPG/PNG)'}), 400

            conn = get_db_connection()
            if not conn:
                return jsonify({'status': 'error', 'msg': 'DB error'}), 500
            cur = conn.cursor()
            display_id = generate_display_id('WTR', conn)
            cur.execute("""INSERT INTO water_purchases
                           (display_id, ob_name, purchase_date, status, foto_before, foto_after)
                           VALUES (%s,%s,%s,'pending',%s,%s)""",
                        (display_id, ob_name, tanggal, foto_before, foto_after))
            purchase_id = cur.lastrowid
            for it in normalized:
                cur.execute("""INSERT INTO water_purchase_items
                               (purchase_id, drink_type, brand, satuan, quantity)
                               VALUES (%s,%s,%s,%s,%s)""",
                            (purchase_id, it['drink_type'], it['brand'], it['satuan'], it['quantity']))
            conn.commit(); cur.close(); conn.close()
            log_activity_async(0, 'water_purchase_create', session.get('user_role', ''),
                               ob_name, new_data={'display_id': display_id, 'items': normalized},
                               ip=client_ip())
            # Realtime: beri tahu Finance/admin bahwa ada pengajuan baru (broadcast)
            try:
                from modules.realtime import emit_event
                emit_event('water_purchase_new', {
                    'id': purchase_id,
                    'display_id': display_id,
                    'ob_name': ob_name,
                    'item_count': len(normalized),
                    'purchase_date': tanggal,
                    'created_at': datetime.now().strftime('%d/%m/%Y %H:%M'),
                })
            except Exception:
                pass
            return jsonify({'status': 'success', 'msg': f'Pengajuan {display_id} dikirim ke Finance',
                            'display_id': display_id, 'id': purchase_id})
        except Exception as e:
            return jsonify({'status': 'error', 'msg': str(e)}), 500

    @app.route('/api/water/purchases')
    @role_required(WATER_ROLES)
    def api_water_purchases():
        """Daftar pengajuan. OB: hanya miliknya; Finance/admin: semua.

        v2.37.4: filter rentang tanggal + status + pencarian bebas.
        Default: pengajuan bulan berjalan (awal s/d akhir bulan). Kirim
        `from` & `to` (YYYY-MM-DD) utk rentang lain, `status` (pending/
        verified/rejected/all), `q` (cari display_id/ob_name/merk).
        """
        try:
            role = session.get('user_role', '')

            # ---- Filter (v2.37.4): default rentang bulan berjalan ----
            d_from = _parse_ymd(request.args.get('from'))
            d_to = _parse_ymd(request.args.get('to'))
            if d_from is None and d_to is None:
                d_from, d_to = _month_range()  # akhir bulan (inklusif)
            elif d_from is None:
                d_from = d_to
            elif d_to is None:
                d_to = d_from
            status = (request.args.get('status') or 'all').strip().lower()
            if status not in ('pending', 'verified', 'rejected', 'all'):
                status = 'all'
            q = (request.args.get('q') or '').strip()

            # v2.37.5: query dipindah ke _query_purchases (dipakai juga export)
            rows, conn = _query_purchases(d_from, d_to, status, q, role)
            if conn is None:
                return jsonify({'error': 'DB error'}), 500
            conn.close()
            return jsonify({
                'purchases': rows,
                'range': {'from': str(d_from), 'to': str(d_to), 'to_inclusive': True},
                'filters': {'status': status, 'q': q},
            })
        except Exception as e:
            return jsonify({'error': str(e)}), 500

    @app.route('/api/water/purchases/export')
    @role_required(WATER_ROLES)
    def api_water_purchases_export():
        """Export rekap pengajuan sesuai filter aktif (v2.37.5).

        ?format=xlsx (default) → Excel landscape; ?format=pdf → PDF landscape.
        Filter sama dengan daftar: from/to/status/q (default bulan berjalan).
        TTD: Finance (Dibuat oleh) & Kepala Cabang (Mengetahui) — nama dari
        system_config water_finance_name / water_head_name (di-set Admin di
        Pengaturan → 🚰 Air Minum).
        """
        try:
            role = session.get('user_role', '')
            d_from = _parse_ymd(request.args.get('from'))
            d_to = _parse_ymd(request.args.get('to'))
            if d_from is None and d_to is None:
                d_from, d_to = _month_range()
            elif d_from is None:
                d_from = d_to
            elif d_to is None:
                d_to = d_from
            status = (request.args.get('status') or 'all').strip().lower()
            if status not in ('pending', 'verified', 'rejected', 'all'):
                status = 'all'
            q = (request.args.get('q') or '').strip()

            rows, conn = _query_purchases(d_from, d_to, status, q, role)
            if conn is None:
                return jsonify({'error': 'DB error'}), 500
            conn.close()

            meta = _export_meta(d_from, d_to, status, q)
            fmt = (request.args.get('format') or 'xlsx').strip().lower()
            stamp = datetime.now().strftime('%Y%m%d_%H%M')
            if fmt == 'pdf':
                from modules.water_report import WaterReportPDF
                data = WaterReportPDF().generate(rows, meta)
                resp = make_response(data)
                resp.headers['Content-Type'] = 'application/pdf'
                resp.headers['Content-Disposition'] = \
                    f'attachment; filename=Rekap_AirMinum_{stamp}.pdf'
            else:
                from modules.water_report import generate_water_report_excel
                data = generate_water_report_excel(rows, meta)
                resp = make_response(data)
                resp.headers['Content-Type'] = \
                    'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
                resp.headers['Content-Disposition'] = \
                    f'attachment; filename=Rekap_AirMinum_{stamp}.xlsx'
            return resp
        except Exception as e:
            return jsonify({'error': str(e)}), 500

    @app.route('/api/water/purchases/<int:purchase_id>')
    @role_required(WATER_ROLES)
    def api_water_purchase_detail(purchase_id):
        try:
            conn = get_db_connection()
            if not conn:
                return jsonify({'error': 'DB error'}), 500
            cur = conn.cursor(dictionary=True)
            cur.execute("SELECT * FROM water_purchases WHERE id=%s", (purchase_id,))
            row = cur.fetchone()
            if not row:
                cur.close(); conn.close()
                return jsonify({'error': 'Pengajuan tidak ditemukan'}), 404
            role = session.get('user_role', '')
            if role == 'ob' and row['ob_name'] != _session_name():
                cur.close(); conn.close()
                return jsonify({'error': 'Akses ditolak'}), 403
            result = _purchase_row(cur, row)
            cur.close(); conn.close()
            return jsonify(result)
        except Exception as e:
            return jsonify({'error': str(e)}), 500

    # ============================================================
    # EDIT & HAPUS (v2.37.0) — fitur opsional, di-enable Admin per cabang
    # ============================================================
    @app.route('/api/water/edit-enabled')
    @role_required(WATER_ROLES)
    def api_water_edit_enabled():
        """Status fitur edit/hapus untuk UI (toggle tombol & pesan)."""
        return jsonify({'enabled': get_water_edit_enabled()})

    @app.route('/api/water/edit-enabled', methods=['PUT'])
    @role_required(['admin'])
    def api_water_edit_enabled_put():
        """Admin aktif/nonaktifkan fitur edit/hapus transaksi air minum.

        Disimpan di system_config DB cabang sesi → berlaku per cabang.
        Admin cabang hanya bisa mengubah cabangnya sendiri (DB-nya memang
        ter-scope via get_db_connection).
        """
        try:
            data = request.get_json(silent=True) or {}
            enabled = bool(data.get('enabled'))
            if not set_water_edit_enabled(enabled):
                return jsonify({'status': 'error', 'msg': 'DB error'}), 500
            actor = _session_name() or 'Admin'
            log_activity_async(0, 'water_edit_toggle', 'admin', actor,
                               new_data={'enabled': enabled}, ip=client_ip())
            return jsonify({'status': 'success', 'enabled': enabled,
                            'msg': 'Fitur edit/hapus transaksi air minum '
                                   f'{"DIAKTIFKAN" if enabled else "DINONAKTIFKAN"}'})
        except Exception as e:
            return jsonify({'status': 'error', 'msg': str(e)}), 500

    @app.route('/api/water/purchases/<int:purchase_id>', methods=['PUT'])
    @role_required(WATER_FINANCE_ROLES)
    @stepup_required
    def api_water_purchase_edit(purchase_id):
        """Edit pengajuan (Finance/admin, fitur aktif): tanggal + item + remark/note.

        Status boleh: pending & verified (rejected cukup dengan alasan tolak).
        Foto tidak diubah lewat endpoint ini (bukti OB tetap orisinal) —
        yang dikoreksi: tanggal, rincian item, remark & note verifikasi.
        Audit: old_data = snapshot lengkap sebelum edit.
        """
        gate = _water_edit_gate()
        if gate:
            return gate
        try:
            data = request.get_json(silent=True) or {}
            tanggal = str(data.get('purchase_date', '') or '').strip()
            if not tanggal:
                return jsonify({'status': 'error', 'msg': 'Tanggal pengiriman wajib diisi'}), 400
            normalized, n_err = _normalize_water_items(data.get('items'))
            if n_err:
                return jsonify({'status': 'error', 'msg': n_err}), 400
            remark = str(data.get('remark', '') or '').strip()
            note = str(data.get('note', '') or '').strip()

            who = _session_name() or 'Finance'
            conn = get_db_connection()
            if not conn:
                return jsonify({'status': 'error', 'msg': 'DB error'}), 500
            cur = conn.cursor(dictionary=True)
            cur.execute("SELECT * FROM water_purchases WHERE id=%s", (purchase_id,))
            row = cur.fetchone()
            if not row:
                cur.close(); conn.close()
                return jsonify({'status': 'error', 'msg': 'Pengajuan tidak ditemukan'}), 404
            # Admin cabang hanya boleh cabangnya sendiri; baris DB cabang sesi.
            denied = assert_branch_row_scope(row)
            if denied:
                cur.close(); conn.close()
                return denied
            if row['status'] not in EDITABLE_STATUSES:
                cur.close(); conn.close()
                return jsonify({'status': 'error',
                                'msg': 'Pengajuan berstatus Ditolak tidak dapat diedit'}), 400
            old_snapshot = {k: str(v) for k, v in row.items()}
            cur.execute("SELECT drink_type, brand, satuan, quantity "
                        "FROM water_purchase_items WHERE purchase_id=%s ORDER BY id", (purchase_id,))
            old_snapshot['items'] = [str(dict(i)) for i in cur.fetchall()]

            cur.execute("""UPDATE water_purchases
                           SET purchase_date=%s, remark=%s, note=%s,
                               edited_by=%s, edited_at=NOW(), edit_count=edit_count+1
                           WHERE id=%s""",
                        (tanggal, remark[:500], note[:2000], who, purchase_id))
            cur.execute("DELETE FROM water_purchase_items WHERE purchase_id=%s", (purchase_id,))
            for it in normalized:
                cur.execute("""INSERT INTO water_purchase_items
                               (purchase_id, drink_type, brand, satuan, quantity)
                               VALUES (%s,%s,%s,%s,%s)""",
                            (purchase_id, it['drink_type'], it['brand'], it['satuan'], it['quantity']))
            conn.commit()
            cur.close(); conn.close()
            log_activity_async(0, 'water_purchase_edit', session.get('user_role', ''), who,
                               old_data=old_snapshot,
                               new_data={'purchase_id': purchase_id,
                                         'purchase_date': tanggal,
                                         'items': normalized, 'remark': remark, 'note': note},
                               ip=client_ip())
            return jsonify({'status': 'success',
                            'msg': f'Pengajuan {row.get("display_id")} diperbarui'})
        except Exception as e:
            return jsonify({'status': 'error', 'msg': str(e)}), 500

    @app.route('/api/water/purchases/<int:purchase_id>', methods=['DELETE'])
    @role_required(WATER_FINANCE_ROLES)
    @stepup_required
    def api_water_purchase_delete(purchase_id):
        """Hapus PERMANEN pengajuan (Finance/admin, fitur aktif).

        Baris + item + file foto dihapus; snapshot lengkap disimpan di audit
        log (old_data) sebagai jejak satu-satunya — sesuai keputusan user
        "hapus permanen + audit".
        """
        gate = _water_edit_gate()
        if gate:
            return gate
        try:
            who = _session_name() or 'Finance'
            conn = get_db_connection()
            if not conn:
                return jsonify({'status': 'error', 'msg': 'DB error'}), 500
            cur = conn.cursor(dictionary=True)
            cur.execute("SELECT * FROM water_purchases WHERE id=%s", (purchase_id,))
            row = cur.fetchone()
            if not row:
                cur.close(); conn.close()
                return jsonify({'status': 'error', 'msg': 'Pengajuan tidak ditemukan'}), 404
            denied = assert_branch_row_scope(row)
            if denied:
                cur.close(); conn.close()
                return denied
            cur.execute("SELECT drink_type, brand, satuan, quantity "
                        "FROM water_purchase_items WHERE purchase_id=%s ORDER BY id", (purchase_id,))
            items = cur.fetchall()
            snapshot = {k: str(v) for k, v in row.items()}
            snapshot['items'] = [str(dict(i)) for i in items]
            cur.execute("DELETE FROM water_purchase_items WHERE purchase_id=%s", (purchase_id,))
            cur.execute("DELETE FROM water_purchases WHERE id=%s", (purchase_id,))
            conn.commit()
            cur.close(); conn.close()
            # File foto dihapus SETELAH commit DB — gagal hapus file tidak
            # mengembalikan data yang sudah terhapus (audit tetap mencatat namanya).
            upl = app.config.get('UPLOAD_FOLDER', 'uploads')
            for key in ('foto_before', 'foto_after'):
                fname = (row.get(key) or '').strip()
                if fname:
                    try:
                        fpath = os.path.join(upl, os.path.basename(fname))
                        if os.path.isfile(fpath):
                            os.remove(fpath)
                    except Exception as fe:
                        print(f'[water] hapus foto {fname}: {fe}')
            log_activity_async(0, 'water_purchase_delete', session.get('user_role', ''), who,
                               old_data=snapshot,
                               new_data={'purchase_id': purchase_id,
                                         'display_id': row.get('display_id'),
                                         'deleted': True},
                               ip=client_ip())
            return jsonify({'status': 'success',
                            'msg': f'Pengajuan {row.get("display_id")} dihapus permanen'})
        except Exception as e:
            return jsonify({'status': 'error', 'msg': str(e)}), 500

    # ============================================================
    # VERIFIKASI — oleh Finance
    # ============================================================
    @app.route('/api/water/purchases/<int:purchase_id>/verify', methods=['POST'])
    @role_required(WATER_FINANCE_ROLES)
    @stepup_required
    def api_water_purchase_verify(purchase_id):
        try:
            data = request.get_json(silent=True) or {}
            remark = str(data.get('remark', '') or '').strip()
            note = str(data.get('note', '') or '').strip()
            if not remark:
                return jsonify({'status': 'error', 'msg': 'Remark verifikasi wajib diisi'}), 400
            who = _session_name() or 'Finance'
            conn = get_db_connection()
            if not conn:
                return jsonify({'status': 'error', 'msg': 'DB error'}), 500
            cur = conn.cursor()
            cur.execute("""UPDATE water_purchases
                           SET status='verified', remark=%s, note=%s, verified_by=%s, verified_at=NOW(),
                               rejection_reason=''
                           WHERE id=%s AND status='pending'""",
                        (remark[:500], note[:2000], who, purchase_id))
            affected = cur.rowcount
            conn.commit(); cur.close(); conn.close()
            if affected == 0:
                return jsonify({'status': 'error', 'msg': 'Pengajuan tidak ditemukan atau sudah diproses'}), 404
            log_activity_async(0, 'water_purchase_verify', 'finance', who,
                               new_data={'purchase_id': purchase_id, 'remark': remark, 'note': note},
                               ip=client_ip())
            return jsonify({'status': 'success', 'msg': 'Pengajuan terverifikasi'})
        except Exception as e:
            return jsonify({'status': 'error', 'msg': str(e)}), 500

    @app.route('/api/water/purchases/<int:purchase_id>/reject', methods=['POST'])
    @role_required(WATER_FINANCE_ROLES)
    def api_water_purchase_reject(purchase_id):
        try:
            data = request.get_json(silent=True) or {}
            reason = str(data.get('reason', '') or '').strip()
            if not reason:
                return jsonify({'status': 'error', 'msg': 'Alasan penolakan wajib diisi'}), 400
            who = _session_name() or 'Finance'
            conn = get_db_connection()
            if not conn:
                return jsonify({'status': 'error', 'msg': 'DB error'}), 500
            cur = conn.cursor()
            cur.execute("""UPDATE water_purchases
                           SET status='rejected', rejection_reason=%s, verified_by=%s, verified_at=NOW(),
                               remark='', note=''
                           WHERE id=%s AND status='pending'""",
                        (reason[:500], who, purchase_id))
            affected = cur.rowcount
            conn.commit(); cur.close(); conn.close()
            if affected == 0:
                return jsonify({'status': 'error', 'msg': 'Pengajuan tidak ditemukan atau sudah diproses'}), 404
            log_activity_async(0, 'water_purchase_reject', 'finance', who,
                               new_data={'purchase_id': purchase_id, 'reason': reason},
                               ip=client_ip())
            return jsonify({'status': 'success', 'msg': 'Pengajuan ditolak'})
        except Exception as e:
            return jsonify({'status': 'error', 'msg': str(e)}), 500

    # ============================================================
    # REKAP — dashboard Finance
    # ============================================================
    @app.route('/api/water/recap')
    @role_required(WATER_FINANCE_ROLES)
    def api_water_recap():
        """Rekap pengajuan air minum: ringkasan, per-OB, per-jenis/merk, antrean verifikasi,
        dan ringkasan kasbon yang menunggu Finance. Filter rentang tanggal opsional."""
        data = _water_recap_data(request.args.get('from', ''), request.args.get('to', ''))
        if data is None:
            return jsonify({'error': 'DB error'}), 500
        log_activity_async(0, 'water_recap_view', session.get('user_role', ''),
                           _session_name(), ip=client_ip())
        return jsonify({k: v for k, v in data.items() if k not in ('rows', 'items_by')})

    @app.route('/api/water/recap/export')
    @role_required(WATER_FINANCE_ROLES)
    def api_water_recap_export():
        """Unduh rekap air minum sebagai CSV (satu baris per item, UTF-8 BOM)."""
        data = _water_recap_data(request.args.get('from', ''), request.args.get('to', ''))
        if data is None:
            return make_response('DB error', 500)
        csv_text = _build_water_csv(data['rows'], data['items_by'])
        resp = make_response(csv_text)
        resp.headers['Content-Type'] = 'text/csv; charset=utf-8'
        fname = f'Rekap_AirMinum_{datetime.now().strftime("%Y%m%d_%H%M")}.csv'
        resp.headers['Content-Disposition'] = f'attachment; filename={fname}'
        log_activity_async(0, 'water_recap_export', session.get('user_role', ''),
                           _session_name(), ip=client_ip())
        return resp

    # ============================================================
    # PDF TANDA TERIMA
    # ============================================================
    @app.route('/api/water/purchases/<int:purchase_id>/pdf')
    @role_required(WATER_ROLES)
    def api_water_purchase_pdf(purchase_id):
        try:
            conn = get_db_connection()
            if not conn:
                return make_response('DB error', 500)
            cur = conn.cursor(dictionary=True)
            cur.execute("SELECT * FROM water_purchases WHERE id=%s", (purchase_id,))
            row = cur.fetchone()
            if not row:
                cur.close(); conn.close()
                return make_response('Pengajuan tidak ditemukan', 404)
            role = session.get('user_role', '')
            if role == 'ob' and row['ob_name'] != _session_name():
                cur.close(); conn.close()
                return make_response('Akses ditolak', 403)
            cur.execute("SELECT drink_type, brand, satuan, quantity "
                        "FROM water_purchase_items WHERE purchase_id=%s ORDER BY id", (purchase_id,))
            items = cur.fetchall()
            cur.close(); conn.close()

            ga_name, finance_name, _head = _get_ttd_names()
            # v2.29.4: nama di blok TTD Finance ('Menyerahkan') = user yang
            # benar-benar memverifikasi (verified_by saat approve/tolak). Nama
            # TTD system_config dipakai hanya sebagai fallback (mis. pending).
            verified_by = (row.get('verified_by') or '').strip()
            if verified_by:
                finance_name = verified_by
            from modules.pdf_generator import WaterReceiptPDF
            pdf = WaterReceiptPDF()
            pdf.add_page()
            pdf.generate(row, items, ga_name=ga_name, finance_name=finance_name,
                         upload_folder=app.config['UPLOAD_FOLDER'])
            pdf_raw = pdf.output(dest='S')
            pdf_bytes = pdf_raw.encode('latin-1') if isinstance(pdf_raw, str) else bytes(pdf_raw)
            response = make_response(pdf_bytes)
            response.headers['Content-Type'] = 'application/pdf'
            fname = f'TandaTerima_AirMinum_{row.get("display_id", purchase_id)}.pdf'
            response.headers['Content-Disposition'] = f'attachment; filename={fname}'
            log_activity_async(0, 'water_purchase_pdf', role, _session_name(),
                               new_data={'display_id': row.get('display_id')}, ip=client_ip())
            # v2.35.0 (Tahap 6/6 ISO): catat integritas dokumen ke registri —
            # SHA-256 + penandatangan (TTD Finance) + timestamp (best-effort).
            try:
                from modules.doc_integrity import register_pdf
                register_pdf('water_receipt', row.get('display_id') or f'id-{purchase_id}',
                             pdf_bytes, signer_name=finance_name, signer_role='finance',
                             branch_code=session.get('branch_code') or '',
                             filename=fname, meta={'ga_name': ga_name,
                                                   'purchase_id': purchase_id,
                                                   'status': row.get('status')})
            except Exception:
                pass  # registri tidak boleh menggagalkan unduhan PDF
            return response
        except Exception as e:
            return make_response(f'Error: {str(e)}', 500)
