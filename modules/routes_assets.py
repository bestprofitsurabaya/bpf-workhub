"""Sistem Aset & Pemeliharaan (v2.18) — migrasi dari bpf-asset-system.

Menggantikan aplikasi Streamlit "BPF Asset Management System" dengan modul
terintegrasi di BPF WorkHub untuk role GA & Admin:

  - Master unit AC kantor (15 unit) + log servis AC (parameter teknikal,
    health score, biaya sparepart, jadwal servis berikutnya).
  - Master kendaraan ASLI kantor (8 unit: Innova + 7 Avanza) — terhubung ke
    tabel `vehicles` (BBM) via vehicle_id; + log servis per komponen.
  - Master komponen kendaraan + standar umur pakai (km & bulan).
  - Rekomendasi maintenance OTOMATIS berbasis aturan (bukan ML berat):
    AC -> selisih hari dari servis terakhir & health score; kendaraan ->
    pemakaian km/bulan sejak servis terakhir per komponen vs standar.
  - Laporan PDF resmi berlogo BPF (laporan AC / kendaraan).

Role: ga (pemeliharaan aset), admin.
"""
import io
from datetime import date, datetime, timedelta

from flask import request, jsonify, make_response
from modules.config import get_db_connection
from modules.helpers import (role_required, log_activity_async)
from modules.pdf_generator import AssetReportPDF

ASSET_ROLES = ['ga', 'admin']

AC_STATUS = ('Aktif', 'Rusak', 'Maintenance', 'Nonaktif')
VH_STATUS = ('Aktif', 'Rusak', 'Nonaktif')
REC_STATUS = ('Pending', 'Selesai', 'Dibatalkan')
REC_PRIORITY = ('Kritis', 'Tinggi', 'Sedang', 'Rutin')
VALID_STAGES = None  # placeholder agar tidak bentrok dengan modul lain


def _serialize(row):
    if not row:
        return row
    row = dict(row)
    for k, v in row.items():
        if isinstance(v, datetime):
            row[k] = v.strftime('%Y-%m-%d %H:%M:%S')
        elif isinstance(v, date):
            row[k] = v.isoformat()
    return row


def _parse_date(value, label='Tanggal'):
    if not value:
        return None
    try:
        return datetime.strptime(str(value).strip(), '%Y-%m-%d').date()
    except ValueError:
        raise ValueError(f'{label} harus format YYYY-MM-DD')


def _num(value, default=0):
    try:
        return int(float(value or default))
    except (TypeError, ValueError):
        return default


def _money(value, default=0):
    try:
        return float(value or default)
    except (TypeError, ValueError):
        return default


def _current_user():
    return _session_user()


def _session_user():
    from flask import session
    return {
        'username': session.get('user_name', ''),
        'full_name': session.get('full_name', session.get('user_name', '')),
        'role': session.get('user_role', ''),
    }


# ================================================================
# REKOMENDASI OTOMATIS (aturan)
# ================================================================
def _ac_health_score(log):
    """Health score 0-100 dari parameter teknikal log AC (sederhana)."""
    if not log:
        return None
    score = 100.0
    amp = log.get('amp_kompresor')
    if amp is not None:
        if amp > 8:
            score -= 30
        elif amp > 6:
            score -= 15
    delta = log.get('delta_t')
    if delta is not None:
        if delta < 8:
            score -= 20
        elif delta < 10:
            score -= 10
    low_p = log.get('low_p')
    if low_p is not None and low_p < 60:
        score -= 15
    score = max(0, min(100, score))
    return int(score)


def _compute_ac_recommendations(conn, cursor):
    """Rekomendasi AC: servis rutin bila sudah >90 hari / health rendah."""
    today = date.today()
    cursor.execute(
        "SELECT asset_id, merk, lokasi, last_maintenance, status FROM asset_ac")
    acs = cursor.fetchall()
    recs = []
    for a in acs:
        if a['status'] == 'Nonaktif':
            continue
        last = a['last_maintenance'] or (today - timedelta(days=120))
        days = (today - last).days if last else 120
        if days >= 90:
            recs.append({
                'asset_type': 'ac', 'asset_ref': a['asset_id'],
                'priority': 'Tinggi' if days >= 180 else 'Sedang',
                'urgency_days': 7 if days >= 180 else 30,
                'actions': f"Servis rutin AC {a['asset_id']} ({a['lokasi']}) "
                           f"— terakhir {last.isoformat() if hasattr(last, 'isoformat') else last} ({days} hari lalu)",
                'estimated_cost': 0,
            })
        # health score rendah dari log terakhir
        cursor.execute(
            "SELECT health_score FROM asset_ac_logs WHERE asset_id=%s "
            "ORDER BY tanggal DESC, id DESC LIMIT 1", (a['asset_id'],))
        lg = cursor.fetchone()
        if lg and lg['health_score'] is not None and lg['health_score'] < 60:
            recs.append({
                'asset_type': 'ac', 'asset_ref': a['asset_id'],
                'priority': 'Kritis' if lg['health_score'] < 40 else 'Tinggi',
                'urgency_days': 1 if lg['health_score'] < 40 else 7,
                'actions': f"Periksa AC {a['asset_id']} ({a['lokasi']}) — "
                           f"health score {lg['health_score']}/100",
                'estimated_cost': 0,
            })
    return recs


def _compute_vehicle_recommendations(conn, cursor):
    """Rekomendasi kendaraan: pemakaian km/bulan vs standar umur komponen."""
    today = date.today()
    cursor.execute(
        "SELECT id, nopol, vehicle_type, last_odometer, status FROM vehicle_assets")
    vhs = cursor.fetchall()
    recs = []
    for v in vhs:
        if v['status'] == 'Nonaktif':
            continue
        # servis terakhir per komponen untuk kendaraan ini
        cursor.execute(
            """SELECT component_name, service_date, odometer, component_life_km,
                      component_life_months, current_usage_km, current_usage_months
               FROM vehicle_service_logs WHERE vehicle_asset_id=%s
               ORDER BY service_date DESC, id DESC""", (v['id'],))
        logs = cursor.fetchall()
        seen = set()
        for lg in logs:
            comp = lg['component_name']
            if comp in seen:
                continue
            seen.add(comp)
            # standar dari master komponen
            cursor.execute(
                "SELECT standard_life_km, standard_life_months FROM vehicle_components "
                "WHERE component_name=%s", (comp,))
            std = cursor.fetchone()
            if not std:
                continue
            std_km = std['standard_life_km'] or 0
            std_mon = std['standard_life_months'] or 0
            # pemakaian sejak servis terakhir
            days_since = (today - lg['service_date']).days if lg['service_date'] else 9999
            km_since = (v['last_odometer'] or 0) - (lg['odometer'] or 0)
            months_since = days_since / 30.0
            due_km = std_km > 0 and km_since >= std_km
            due_mon = std_mon > 0 and months_since >= std_mon
            if due_km or due_mon:
                pct_km = (km_since / std_km * 100) if std_km else 0
                pct_mon = (months_since / std_mon * 100) if std_mon else 0
                pct = max(pct_km, pct_mon)
                prio = 'Kritis' if pct >= 120 else 'Tinggi' if pct >= 100 else 'Sedang'
                urgency = 1 if pct >= 120 else 7 if pct >= 100 else 30
                reason = []
                if due_km:
                    reason.append(f"km {km_since}/{std_km}")
                if due_mon:
                    reason.append(f"{int(months_since)}/{std_mon} bln")
                recs.append({
                    'asset_type': 'vehicle', 'asset_ref': v['nopol'],
                    'priority': prio,
                    'urgency_days': urgency,
                    'actions': f"Servis {comp} — {v['nopol']} ({v['vehicle_type']}) "
                               f"pemakaian {'; '.join(reason)}",
                    'estimated_cost': std['standard_life_km'] or 0,
                })
    return recs


def _refresh_recommendations(conn, cursor, user):
    """Hapus rekomendasi Pending lama, isi ulang dari aturan, log audit."""
    cursor.execute("DELETE FROM maintenance_recommendations WHERE status='Pending'")
    recs = _compute_ac_recommendations(conn, cursor) + \
        _compute_vehicle_recommendations(conn, cursor)
    for r in recs:
        cursor.execute(
            """INSERT INTO maintenance_recommendations
               (asset_type, asset_ref, recommendation_date, priority,
                urgency_days, actions, estimated_cost)
               VALUES (%s,%s,%s,%s,%s,%s,%s)""",
            (r['asset_type'], r['asset_ref'], date.today().isoformat(),
             r['priority'], r['urgency_days'], r['actions'], r['estimated_cost']))
    conn.commit()
    log_activity_async(None, 'asset_recommendations', user['role'], user['full_name'],
                       new_data={'count': len(recs)}, ip=request.remote_addr)
    return recs


def register_asset_routes(app):

    # ================================================================
    # SUMMARY — ringkasan dashboard aset
    # ================================================================
    @app.route('/api/assets/summary')
    @role_required(ASSET_ROLES)
    def api_assets_summary():
        try:
            conn = get_db_connection()
            if not conn:
                return jsonify({'error': 'DB error'}), 500
            cursor = conn.cursor(dictionary=True)
            cursor.execute("SELECT COUNT(*) c FROM asset_ac")
            ac_total = cursor.fetchone()['c']
            cursor.execute("SELECT COUNT(*) c FROM asset_ac WHERE status='Aktif'")
            ac_aktif = cursor.fetchone()['c']
            cursor.execute("SELECT COUNT(*) c FROM vehicle_assets")
            vh_total = cursor.fetchone()['c']
            cursor.execute("SELECT COUNT(*) c FROM vehicle_assets WHERE status='Aktif'")
            vh_aktif = cursor.fetchone()['c']
            cursor.execute(
                "SELECT COUNT(*) c FROM maintenance_recommendations WHERE status='Pending'")
            pending = cursor.fetchone()['c']
            cursor.execute(
                "SELECT COUNT(*) c FROM maintenance_recommendations "
                "WHERE status='Pending' AND priority IN ('Kritis','Tinggi')")
            urgent = cursor.fetchone()['c']
            cursor.close(); conn.close()
            return jsonify({
                'ac_total': ac_total, 'ac_aktif': ac_aktif,
                'vehicle_total': vh_total, 'vehicle_aktif': vh_aktif,
                'pending': pending, 'urgent': urgent,
            })
        except Exception as e:
            return jsonify({'error': str(e)}), 500

    # ================================================================
    # MASTER AC — CRUD
    # ================================================================
    @app.route('/api/assets/ac')
    @role_required(ASSET_ROLES)
    def api_assets_ac_list():
        try:
            search = str(request.args.get('search', '') or '').strip()
            status = str(request.args.get('status', '') or '').strip()
            where, params = [], []
            if search:
                where.append("(asset_id LIKE %s OR merk LIKE %s OR lokasi LIKE %s)")
                params += [f'%{search}%'] * 3
            if status:
                where.append("status=%s"); params.append(status)
            conn = get_db_connection()
            if not conn:
                return jsonify({'error': 'DB error'}), 500
            cursor = conn.cursor(dictionary=True)
            sql = "SELECT * FROM asset_ac"
            if where:
                sql += " WHERE " + " AND ".join(where)
            sql += " ORDER BY asset_id"
            cursor.execute(sql, params)
            rows = cursor.fetchall()
            # log terakhir per AC
            for r in rows:
                cursor.execute(
                    "SELECT * FROM asset_ac_logs WHERE asset_id=%s "
                    "ORDER BY tanggal DESC, id DESC LIMIT 1", (r['asset_id'],))
                last = cursor.fetchone()
                r['last_log'] = _serialize(last)
            cursor.close(); conn.close()
            return jsonify({'data': [_serialize(r) for r in rows]})
        except Exception as e:
            return jsonify({'error': str(e)}), 500

    @app.route('/api/assets/ac', methods=['POST'])
    @role_required(ASSET_ROLES)
    def api_assets_ac_add():
        try:
            data = request.get_json(silent=True) or {}
            asset_id = str(data.get('asset_id', '') or '').strip()[:50]
            merk = str(data.get('merk', '') or '').strip()[:50]
            tipe = str(data.get('tipe', '') or '').strip()[:50]
            kapasitas = str(data.get('kapasitas', '') or '').strip()[:50]
            lokasi = str(data.get('lokasi', '') or '').strip()[:150]
            if not asset_id or not merk or not lokasi:
                return jsonify({'status': 'error',
                                'msg': 'Asset ID, Merk, dan Lokasi wajib diisi'}), 400
            conn = get_db_connection()
            if not conn:
                return jsonify({'status': 'error', 'msg': 'DB error'}), 500
            cursor = conn.cursor(dictionary=True)
            cursor.execute(
                """INSERT INTO asset_ac
                   (asset_id, merk, tipe, kapasitas, lokasi, refrigerant,
                    installation_date, warranty_until, last_maintenance, status)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                (asset_id, merk, tipe, kapasitas, lokasi,
                 str(data.get('refrigerant', '') or '').strip()[:50],
                 _parse_date(data.get('installation_date')), _parse_date(data.get('warranty_until')),
                 _parse_date(data.get('last_maintenance')),
                 str(data.get('status', 'Aktif') or 'Aktif')[:20]))
            conn.commit()
            user = _current_user()
            log_activity_async(None, 'asset_ac_add', user['role'], user['full_name'],
                               new_data={'asset_id': asset_id}, ip=request.remote_addr)
            cursor.close(); conn.close()
            return jsonify({'status': 'success', 'msg': f'AC {asset_id} ditambahkan'})
        except ValueError as e:
            return jsonify({'status': 'error', 'msg': str(e)}), 400
        except Exception as e:
            if 'Duplicate' in str(e):
                return jsonify({'status': 'error', 'msg': 'Asset ID sudah ada'}), 409
            return jsonify({'status': 'error', 'msg': str(e)}), 500

    @app.route('/api/assets/ac/<asset_id>', methods=['PATCH'])
    @role_required(ASSET_ROLES)
    def api_assets_ac_patch(asset_id):
        try:
            data = request.get_json(silent=True) or {}
            conn = get_db_connection()
            if not conn:
                return jsonify({'status': 'error', 'msg': 'DB error'}), 500
            cursor = conn.cursor(dictionary=True)
            cursor.execute("SELECT asset_id FROM asset_ac WHERE asset_id=%s", (asset_id,))
            if not cursor.fetchone():
                cursor.close(); conn.close()
                return jsonify({'status': 'error', 'msg': 'AC tidak ditemukan'}), 404
            fields, params = [], []
            for f in ('merk', 'tipe', 'kapasitas', 'lokasi', 'refrigerant', 'status'):
                if f in data:
                    fields.append(f'{f}=%s'); params.append(str(data[f] or '').strip()[:150])
            for f in ('installation_date', 'warranty_until', 'last_maintenance'):
                if f in data:
                    fields.append(f'{f}=%s'); params.append(_parse_date(data.get(f), f))
            if not fields:
                cursor.close(); conn.close()
                return jsonify({'status': 'error', 'msg': 'Tidak ada field yang diubah'}), 400
            params.append(asset_id)
            cursor.execute("UPDATE asset_ac SET " + ", ".join(fields) +
                           ", updated_at=NOW() WHERE asset_id=%s", params)
            conn.commit()
            user = _current_user()
            log_activity_async(None, 'asset_ac_edit', user['role'], user['full_name'],
                               new_data={'asset_id': asset_id}, ip=request.remote_addr)
            cursor.close(); conn.close()
            return jsonify({'status': 'success', 'msg': 'Data AC diperbarui'})
        except ValueError as e:
            return jsonify({'status': 'error', 'msg': str(e)}), 400
        except Exception as e:
            return jsonify({'status': 'error', 'msg': str(e)}), 500

    @app.route('/api/assets/ac/<asset_id>', methods=['DELETE'])
    @role_required(ASSET_ROLES)
    def api_assets_ac_delete(asset_id):
        try:
            conn = get_db_connection()
            if not conn:
                return jsonify({'status': 'error', 'msg': 'DB error'}), 500
            cursor = conn.cursor(dictionary=True)
            cursor.execute("DELETE FROM asset_ac WHERE asset_id=%s", (asset_id,))
            conn.commit()
            user = _current_user()
            log_activity_async(None, 'asset_ac_delete', user['role'], user['full_name'],
                               new_data={'asset_id': asset_id}, ip=request.remote_addr)
            cursor.close(); conn.close()
            return jsonify({'status': 'success', 'msg': f'{asset_id} dihapus'})
        except Exception as e:
            return jsonify({'status': 'error', 'msg': str(e)}), 500

    # ================================================================
    # LOG SERVIS AC
    # ================================================================
    @app.route('/api/assets/ac/<asset_id>/logs')
    @role_required(ASSET_ROLES)
    def api_assets_ac_logs(asset_id):
        try:
            conn = get_db_connection()
            if not conn:
                return jsonify({'error': 'DB error'}), 500
            cursor = conn.cursor(dictionary=True)
            cursor.execute(
                "SELECT * FROM asset_ac_logs WHERE asset_id=%s "
                "ORDER BY tanggal DESC, id DESC LIMIT 500", (asset_id,))
            rows = cursor.fetchall()
            cursor.close(); conn.close()
            return jsonify({'data': [_serialize(r) for r in rows]})
        except Exception as e:
            return jsonify({'error': str(e)}), 500

    @app.route('/api/assets/ac/<asset_id>/logs', methods=['POST'])
    @role_required(ASSET_ROLES)
    def api_assets_ac_log_add(asset_id):
        try:
            data = request.get_json(silent=True) or {}
            tanggal = _parse_date(data.get('tanggal'), 'Tanggal servis') or date.today()
            teknisi = str(data.get('teknisi', '') or '').strip()[:100]
            if not teknisi:
                return jsonify({'status': 'error', 'msg': 'Nama teknisi wajib diisi'}), 400
            # health score otomatis dari parameter teknikal
            log_row = {
                'amp_kompresor': data.get('amp_kompresor'),
                'delta_t': data.get('delta_t'),
                'low_p': data.get('low_p'),
            }
            health = _ac_health_score(log_row) if any(
                v is not None for v in log_row.values()) else None
            conn = get_db_connection()
            if not conn:
                return jsonify({'status': 'error', 'msg': 'DB error'}), 500
            cursor = conn.cursor(dictionary=True)
            cursor.execute("SELECT asset_id FROM asset_ac WHERE asset_id=%s", (asset_id,))
            if not cursor.fetchone():
                cursor.close(); conn.close()
                return jsonify({'status': 'error', 'msg': 'AC tidak ditemukan'}), 404
            cursor.execute(
                """INSERT INTO asset_ac_logs
                   (asset_id, tanggal, teknisi, v_supply, amp_kompresor, low_p, high_p,
                    temp_ret, temp_sup, temp_outdoor, delta_t, drainage, test_run,
                    health_score, sparepart_cost, catatan, next_service_date)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                (asset_id, tanggal.isoformat(), teknisi,
                 data.get('v_supply'), data.get('amp_kompresor'), data.get('low_p'),
                 data.get('high_p'), data.get('temp_ret'), data.get('temp_sup'),
                 data.get('temp_outdoor'), data.get('delta_t'),
                 str(data.get('drainage', '') or '').strip()[:20],
                 str(data.get('test_run', '') or '').strip()[:20],
                 data.get('health_score') if data.get('health_score') is not None else health,
                 _money(data.get('sparepart_cost')),
                 str(data.get('catatan', '') or '').strip()[:500],
                 _parse_date(data.get('next_service_date'))))
            # update last_maintenance di master
            cursor.execute(
                "UPDATE asset_ac SET last_maintenance=%s, updated_at=NOW() "
                "WHERE asset_id=%s", (tanggal.isoformat(), asset_id))
            conn.commit()
            user = _current_user()
            log_activity_async(None, 'asset_ac_log', user['role'], user['full_name'],
                               new_data={'asset_id': asset_id, 'tanggal': tanggal.isoformat()},
                               ip=request.remote_addr)
            cursor.close(); conn.close()
            return jsonify({'status': 'success',
                            'msg': f'Log servis {asset_id} ({tanggal}) tercatat',
                            'health_score': health})
        except ValueError as e:
            return jsonify({'status': 'error', 'msg': str(e)}), 400
        except Exception as e:
            return jsonify({'status': 'error', 'msg': str(e)}), 500

    @app.route('/api/assets/ac-logs/<int:log_id>', methods=['DELETE'])
    @role_required(ASSET_ROLES)
    def api_assets_ac_log_delete(log_id):
        try:
            conn = get_db_connection()
            if not conn:
                return jsonify({'status': 'error', 'msg': 'DB error'}), 500
            cursor = conn.cursor(dictionary=True)
            cursor.execute("SELECT asset_id FROM asset_ac_logs WHERE id=%s", (log_id,))
            row = cursor.fetchone()
            if not row:
                cursor.close(); conn.close()
                return jsonify({'status': 'error', 'msg': 'Log tidak ditemukan'}), 404
            cursor.execute("DELETE FROM asset_ac_logs WHERE id=%s", (log_id,))
            conn.commit()
            user = _current_user()
            log_activity_async(None, 'asset_ac_log_delete', user['role'], user['full_name'],
                               new_data={'log_id': log_id, 'asset_id': row['asset_id']},
                               ip=request.remote_addr)
            cursor.close(); conn.close()
            return jsonify({'status': 'success', 'msg': 'Log servis dihapus'})
        except Exception as e:
            return jsonify({'status': 'error', 'msg': str(e)}), 500

    # ================================================================
    # MASTER KENDARAAN — CRUD (terhubung tabel vehicles via vehicle_id)
    # ================================================================
    @app.route('/api/assets/vehicles')
    @role_required(ASSET_ROLES)
    def api_assets_vehicles_list():
        try:
            conn = get_db_connection()
            if not conn:
                return jsonify({'error': 'DB error'}), 500
            cursor = conn.cursor(dictionary=True)
            cursor.execute("SELECT * FROM vehicle_assets ORDER BY vehicle_type, nopol")
            rows = cursor.fetchall()
            for r in rows:
                cursor.execute(
                    "SELECT * FROM vehicle_service_logs WHERE vehicle_asset_id=%s "
                    "ORDER BY service_date DESC, id DESC LIMIT 1", (r['id'],))
                last = cursor.fetchone()
                r['last_service'] = _serialize(last)
            cursor.close(); conn.close()
            return jsonify({'data': [_serialize(r) for r in rows]})
        except Exception as e:
            return jsonify({'error': str(e)}), 500

    @app.route('/api/assets/vehicles', methods=['POST'])
    @role_required(ASSET_ROLES)
    def api_assets_vehicles_add():
        try:
            data = request.get_json(silent=True) or {}
            nopol = str(data.get('nopol', '') or '').strip().upper()[:20]
            vehicle_type = str(data.get('vehicle_type', '') or '').strip()[:50]
            if not nopol or not vehicle_type:
                return jsonify({'status': 'error',
                                'msg': 'No. Polisi dan tipe kendaraan wajib diisi'}), 400
            conn = get_db_connection()
            if not conn:
                return jsonify({'status': 'error', 'msg': 'DB error'}), 500
            cursor = conn.cursor(dictionary=True)
            # cari vehicle_id di tabel vehicles (BBM) bila ada
            vehicle_id = data.get('vehicle_id')
            if not vehicle_id:
                cursor.execute("SELECT id FROM vehicles WHERE nopol=%s", (nopol,))
                v = cursor.fetchone()
                vehicle_id = v['id'] if v else None
            cursor.execute(
                """INSERT INTO vehicle_assets
                   (vehicle_id, nopol, vehicle_type, brand, model, year, color,
                    fuel_type, status, purchase_date, last_odometer,
                    insurance_until, tax_until, notes)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                (vehicle_id, nopol, vehicle_type,
                 str(data.get('brand', '') or '').strip()[:50],
                 str(data.get('model', '') or '').strip()[:50],
                 _num(data.get('year'), 0) or None,
                 str(data.get('color', '') or '').strip()[:30],
                 str(data.get('fuel_type', 'Bensin') or 'Bensin')[:30],
                 str(data.get('status', 'Aktif') or 'Aktif')[:20],
                 _parse_date(data.get('purchase_date')), _num(data.get('last_odometer')),
                 _parse_date(data.get('insurance_until')), _parse_date(data.get('tax_until')),
                 str(data.get('notes', '') or '').strip()[:500]))
            # v2.108.0: odometer aset = KM awal kendaraan di master, supaya
            # form BBM/Trip punya acuan walau belum ada transaksi.
            if _num(data.get('last_odometer')):
                cursor.execute(
                    "UPDATE vehicles SET initial_odo_km=%s WHERE nopol=%s "
                    "AND (initial_odo_km=0 OR initial_odo_km IS NULL)",
                    (_num(data.get('last_odometer')), nopol))
            conn.commit()
            user = _current_user()
            log_activity_async(None, 'asset_vehicle_add', user['role'], user['full_name'],
                               new_data={'nopol': nopol}, ip=request.remote_addr)
            cursor.close(); conn.close()
            return jsonify({'status': 'success', 'msg': f'Kendaraan {nopol} ditambahkan'})
        except ValueError as e:
            return jsonify({'status': 'error', 'msg': str(e)}), 400
        except Exception as e:
            if 'Duplicate' in str(e):
                return jsonify({'status': 'error', 'msg': 'No. Polisi sudah terdaftar'}), 409
            return jsonify({'status': 'error', 'msg': str(e)}), 500

    @app.route('/api/assets/vehicles/<int:vh_id>', methods=['PATCH'])
    @role_required(ASSET_ROLES)
    def api_assets_vehicles_patch(vh_id):
        try:
            data = request.get_json(silent=True) or {}
            conn = get_db_connection()
            if not conn:
                return jsonify({'status': 'error', 'msg': 'DB error'}), 500
            cursor = conn.cursor(dictionary=True)
            cursor.execute("SELECT id, nopol FROM vehicle_assets WHERE id=%s", (vh_id,))
            _vh = cursor.fetchone()
            if not _vh:
                cursor.close(); conn.close()
                return jsonify({'status': 'error', 'msg': 'Kendaraan tidak ditemukan'}), 404
            fields, params = [], []
            for f in ('nopol', 'vehicle_type', 'brand', 'model', 'color',
                      'fuel_type', 'status', 'notes'):
                if f in data:
                    fields.append(f'{f}=%s'); params.append(str(data[f] or '').strip()[:500])
            for f in ('year', 'last_odometer'):
                if f in data:
                    fields.append(f'{f}=%s'); params.append(_num(data[f], 0) or None)
            for f in ('purchase_date', 'insurance_until', 'tax_until'):
                if f in data:
                    fields.append(f'{f}=%s'); params.append(_parse_date(data.get(f), f))
            if not fields:
                cursor.close(); conn.close()
                return jsonify({'status': 'error', 'msg': 'Tidak ada field yang diubah'}), 400
            params.append(vh_id)
            cursor.execute("UPDATE vehicle_assets SET " + ", ".join(fields) +
                           ", updated_at=NOW() WHERE id=%s", params)
            if 'last_odometer' in data and _num(data.get('last_odometer')):
                cursor.execute(
                    "UPDATE vehicles SET initial_odo_km=%s WHERE nopol=%s",
                    (_num(data.get('last_odometer')), _vh.get('nopol')))
            conn.commit()
            user = _current_user()
            log_activity_async(None, 'asset_vehicle_edit', user['role'], user['full_name'],
                               new_data={'id': vh_id}, ip=request.remote_addr)
            cursor.close(); conn.close()
            return jsonify({'status': 'success', 'msg': 'Data kendaraan diperbarui'})
        except ValueError as e:
            return jsonify({'status': 'error', 'msg': str(e)}), 400
        except Exception as e:
            return jsonify({'status': 'error', 'msg': str(e)}), 500

    @app.route('/api/assets/vehicles/<int:vh_id>', methods=['DELETE'])
    @role_required(ASSET_ROLES)
    def api_assets_vehicles_delete(vh_id):
        try:
            conn = get_db_connection()
            if not conn:
                return jsonify({'status': 'error', 'msg': 'DB error'}), 500
            cursor = conn.cursor(dictionary=True)
            cursor.execute("DELETE FROM vehicle_assets WHERE id=%s", (vh_id,))
            conn.commit()
            user = _current_user()
            log_activity_async(None, 'asset_vehicle_delete', user['role'], user['full_name'],
                               new_data={'id': vh_id}, ip=request.remote_addr)
            cursor.close(); conn.close()
            return jsonify({'status': 'success', 'msg': 'Kendaraan dihapus'})
        except Exception as e:
            return jsonify({'status': 'error', 'msg': str(e)}), 500

    # ================================================================
    # LOG SERVIS KENDARAAN
    # ================================================================
    @app.route('/api/assets/vehicles/<int:vh_id>/services')
    @role_required(ASSET_ROLES)
    def api_assets_vehicle_services(vh_id):
        try:
            conn = get_db_connection()
            if not conn:
                return jsonify({'error': 'DB error'}), 500
            cursor = conn.cursor(dictionary=True)
            cursor.execute(
                "SELECT * FROM vehicle_service_logs WHERE vehicle_asset_id=%s "
                "ORDER BY service_date DESC, id DESC LIMIT 500", (vh_id,))
            rows = cursor.fetchall()
            cursor.close(); conn.close()
            return jsonify({'data': [_serialize(r) for r in rows]})
        except Exception as e:
            return jsonify({'error': str(e)}), 500

    @app.route('/api/assets/vehicles/<int:vh_id>/services', methods=['POST'])
    @role_required(ASSET_ROLES)
    def api_assets_vehicle_service_add(vh_id):
        try:
            data = request.get_json(silent=True) or {}
            service_date = _parse_date(data.get('service_date'), 'Tanggal servis') or date.today()
            component_name = str(data.get('component_name', '') or '').strip()[:100]
            service_type = str(data.get('service_type', 'Servis Rutin') or 'Servis Rutin')[:50]
            if not component_name:
                return jsonify({'status': 'error', 'msg': 'Komponen wajib diisi'}), 400
            conn = get_db_connection()
            if not conn:
                return jsonify({'status': 'error', 'msg': 'DB error'}), 500
            cursor = conn.cursor(dictionary=True)
            cursor.execute("SELECT id, last_odometer FROM vehicle_assets WHERE id=%s", (vh_id,))
            vh = cursor.fetchone()
            if not vh:
                cursor.close(); conn.close()
                return jsonify({'status': 'error', 'msg': 'Kendaraan tidak ditemukan'}), 404
            odometer = _num(data.get('odometer'), vh['last_odometer'] or 0)
            # standar umur dari master komponen
            std_km = std_mon = 0
            cursor.execute("SELECT standard_life_km, standard_life_months "
                           "FROM vehicle_components WHERE component_name=%s",
                           (component_name,))
            std = cursor.fetchone()
            if std:
                std_km = std['standard_life_km'] or 0
                std_mon = std['standard_life_months'] or 0
            cursor.execute(
                """INSERT INTO vehicle_service_logs
                   (vehicle_asset_id, service_date, odometer, service_type,
                    component_name, component_life_km, component_life_months,
                    current_usage_km, current_usage_months,
                    next_service_km, next_service_months,
                    cost, mechanic_name, parts_replaced, invoice_number, notes)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                (vh_id, service_date.isoformat(), odometer, service_type,
                 component_name, std_km, std_mon,
                 _num(data.get('current_usage_km')), _num(data.get('current_usage_months')),
                 _num(data.get('next_service_km')), _num(data.get('next_service_months')),
                 _money(data.get('cost')),
                 str(data.get('mechanic_name', '') or '').strip()[:100],
                 str(data.get('parts_replaced', '') or '').strip()[:500],
                 str(data.get('invoice_number', '') or '').strip()[:50],
                 str(data.get('notes', '') or '').strip()[:500]))
            # update odometer master
            if odometer > (vh['last_odometer'] or 0):
                cursor.execute("UPDATE vehicle_assets SET last_odometer=%s, "
                               "updated_at=NOW() WHERE id=%s", (odometer, vh_id))
            conn.commit()
            user = _current_user()
            log_activity_async(None, 'asset_vehicle_service', user['role'], user['full_name'],
                               new_data={'vh_id': vh_id, 'component': component_name},
                               ip=request.remote_addr)
            cursor.close(); conn.close()
            return jsonify({'status': 'success',
                            'msg': f'Servis {component_name} tercatat ({service_date})'})
        except ValueError as e:
            return jsonify({'status': 'error', 'msg': str(e)}), 400
        except Exception as e:
            return jsonify({'status': 'error', 'msg': str(e)}), 500

    @app.route('/api/assets/vehicle-services/<int:svc_id>', methods=['DELETE'])
    @role_required(ASSET_ROLES)
    def api_assets_vehicle_service_delete(svc_id):
        try:
            conn = get_db_connection()
            if not conn:
                return jsonify({'status': 'error', 'msg': 'DB error'}), 500
            cursor = conn.cursor(dictionary=True)
            cursor.execute("SELECT vehicle_asset_id FROM vehicle_service_logs WHERE id=%s",
                           (svc_id,))
            row = cursor.fetchone()
            if not row:
                cursor.close(); conn.close()
                return jsonify({'status': 'error', 'msg': 'Log tidak ditemukan'}), 404
            cursor.execute("DELETE FROM vehicle_service_logs WHERE id=%s", (svc_id,))
            conn.commit()
            user = _current_user()
            log_activity_async(None, 'asset_vehicle_service_delete', user['role'],
                               user['full_name'], new_data={'svc_id': svc_id},
                               ip=request.remote_addr)
            cursor.close(); conn.close()
            return jsonify({'status': 'success', 'msg': 'Log servis dihapus'})
        except Exception as e:
            return jsonify({'status': 'error', 'msg': str(e)}), 500

    # ================================================================
    # MASTER KOMPONEN KENDARAAN — CRUD
    # ================================================================
    @app.route('/api/assets/components')
    @role_required(ASSET_ROLES)
    def api_assets_components_list():
        try:
            conn = get_db_connection()
            if not conn:
                return jsonify({'error': 'DB error'}), 500
            cursor = conn.cursor(dictionary=True)
            cursor.execute("SELECT * FROM vehicle_components ORDER BY category, component_name")
            rows = cursor.fetchall()
            cursor.close(); conn.close()
            return jsonify({'data': [_serialize(r) for r in rows]})
        except Exception as e:
            return jsonify({'error': str(e)}), 500

    @app.route('/api/assets/components', methods=['POST'])
    @role_required(ASSET_ROLES)
    def api_assets_components_add():
        try:
            data = request.get_json(silent=True) or {}
            name = str(data.get('component_name', '') or '').strip()[:100]
            if not name:
                return jsonify({'status': 'error', 'msg': 'Nama komponen wajib diisi'}), 400
            conn = get_db_connection()
            if not conn:
                return jsonify({'status': 'error', 'msg': 'DB error'}), 500
            cursor = conn.cursor(dictionary=True)
            cursor.execute(
                """INSERT INTO vehicle_components
                   (component_name, standard_life_km, standard_life_months, category,
                    priority, estimated_cost, is_active, notes)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s)""",
                (name, _num(data.get('standard_life_km')), _num(data.get('standard_life_months')),
                 str(data.get('category', '') or '').strip()[:50],
                 _num(data.get('priority'), 1), _money(data.get('estimated_cost')),
                 1 if data.get('is_active', True) else 0,
                 str(data.get('notes', '') or '').strip()[:500]))
            conn.commit()
            user = _current_user()
            log_activity_async(None, 'asset_component_add', user['role'], user['full_name'],
                               new_data={'component': name}, ip=request.remote_addr)
            cursor.close(); conn.close()
            return jsonify({'status': 'success', 'msg': f'Komponen {name} ditambahkan'})
        except Exception as e:
            if 'Duplicate' in str(e):
                return jsonify({'status': 'error', 'msg': 'Komponen sudah ada'}), 409
            return jsonify({'status': 'error', 'msg': str(e)}), 500

    @app.route('/api/assets/components/<int:comp_id>', methods=['PATCH'])
    @role_required(ASSET_ROLES)
    def api_assets_components_patch(comp_id):
        try:
            data = request.get_json(silent=True) or {}
            conn = get_db_connection()
            if not conn:
                return jsonify({'status': 'error', 'msg': 'DB error'}), 500
            cursor = conn.cursor(dictionary=True)
            cursor.execute("SELECT id FROM vehicle_components WHERE id=%s", (comp_id,))
            if not cursor.fetchone():
                cursor.close(); conn.close()
                return jsonify({'status': 'error', 'msg': 'Komponen tidak ditemukan'}), 404
            fields, params = [], []
            for f in ('component_name', 'category', 'notes'):
                if f in data:
                    fields.append(f'{f}=%s'); params.append(str(data[f] or '').strip()[:500])
            for f in ('standard_life_km', 'standard_life_months', 'priority'):
                if f in data:
                    fields.append(f'{f}=%s'); params.append(_num(data[f]))
            if 'estimated_cost' in data:
                fields.append('estimated_cost=%s'); params.append(_money(data['estimated_cost']))
            if 'is_active' in data:
                fields.append('is_active=%s'); params.append(1 if data['is_active'] else 0)
            if not fields:
                cursor.close(); conn.close()
                return jsonify({'status': 'error', 'msg': 'Tidak ada field yang diubah'}), 400
            params.append(comp_id)
            cursor.execute("UPDATE vehicle_components SET " + ", ".join(fields) +
                           ", updated_at=NOW() WHERE id=%s", params)
            conn.commit()
            user = _current_user()
            log_activity_async(None, 'asset_component_edit', user['role'], user['full_name'],
                               new_data={'id': comp_id}, ip=request.remote_addr)
            cursor.close(); conn.close()
            return jsonify({'status': 'success', 'msg': 'Komponen diperbarui'})
        except Exception as e:
            return jsonify({'status': 'error', 'msg': str(e)}), 500

    @app.route('/api/assets/components/<int:comp_id>', methods=['DELETE'])
    @role_required(ASSET_ROLES)
    def api_assets_components_delete(comp_id):
        try:
            conn = get_db_connection()
            if not conn:
                return jsonify({'status': 'error', 'msg': 'DB error'}), 500
            cursor = conn.cursor(dictionary=True)
            cursor.execute("DELETE FROM vehicle_components WHERE id=%s", (comp_id,))
            conn.commit()
            user = _current_user()
            log_activity_async(None, 'asset_component_delete', user['role'], user['full_name'],
                               new_data={'id': comp_id}, ip=request.remote_addr)
            cursor.close(); conn.close()
            return jsonify({'status': 'success', 'msg': 'Komponen dihapus'})
        except Exception as e:
            return jsonify({'status': 'error', 'msg': str(e)}), 500

    # ================================================================
    # REKOMENDASI MAINTENANCE
    # ================================================================
    @app.route('/api/assets/recommendations', methods=['GET'])
    @role_required(ASSET_ROLES)
    def api_assets_recommendations_list():
        try:
            conn = get_db_connection()
            if not conn:
                return jsonify({'error': 'DB error'}), 500
            cursor = conn.cursor(dictionary=True)
            # auto-refresh bila belum ada
            cursor.execute("SELECT COUNT(*) c FROM maintenance_recommendations")
            if cursor.fetchone()['c'] == 0:
                _refresh_recommendations(conn, cursor, _current_user())
            cursor.execute(
                "SELECT * FROM maintenance_recommendations "
                "ORDER BY status='Pending' DESC, "
                "FIELD(priority,'Kritis','Tinggi','Sedang','Rutin'), recommendation_date")
            rows = cursor.fetchall()
            cursor.close(); conn.close()
            return jsonify({'data': [_serialize(r) for r in rows]})
        except Exception as e:
            return jsonify({'error': str(e)}), 500

    @app.route('/api/assets/recommendations/refresh', methods=['POST'])
    @role_required(ASSET_ROLES)
    def api_assets_recommendations_refresh():
        try:
            conn = get_db_connection()
            if not conn:
                return jsonify({'status': 'error', 'msg': 'DB error'}), 500
            cursor = conn.cursor(dictionary=True)
            recs = _refresh_recommendations(conn, cursor, _current_user())
            cursor.close(); conn.close()
            return jsonify({'status': 'success', 'count': len(recs),
                            'msg': f'{len(recs)} rekomendasi diperbarui'})
        except Exception as e:
            return jsonify({'status': 'error', 'msg': str(e)}), 500

    @app.route('/api/assets/recommendations/<int:rec_id>', methods=['PATCH'])
    @role_required(ASSET_ROLES)
    def api_assets_recommendations_patch(rec_id):
        try:
            data = request.get_json(silent=True) or {}
            conn = get_db_connection()
            if not conn:
                return jsonify({'status': 'error', 'msg': 'DB error'}), 500
            cursor = conn.cursor(dictionary=True)
            status = str(data.get('status', '') or '').strip()
            if status and status not in REC_STATUS:
                cursor.close(); conn.close()
                return jsonify({'status': 'error', 'msg': 'Status tidak valid'}), 400
            fields, params = [], []
            if status:
                fields.append('status=%s'); params.append(status)
                if status == 'Selesai':
                    fields.append('completed_date=%s')
                    params.append(date.today().isoformat())
            if 'priority' in data and str(data['priority']) in REC_PRIORITY:
                fields.append('priority=%s'); params.append(str(data['priority']))
            if 'actions' in data:
                fields.append('actions=%s'); params.append(str(data['actions'] or '').strip()[:500])
            if not fields:
                cursor.close(); conn.close()
                return jsonify({'status': 'error', 'msg': 'Tidak ada field yang diubah'}), 400
            params.append(rec_id)
            cursor.execute("UPDATE maintenance_recommendations SET " + ", ".join(fields) +
                           ", updated_at=NOW() WHERE id=%s", params)
            conn.commit()
            user = _current_user()
            log_activity_async(None, 'asset_recommendation_update', user['role'],
                               user['full_name'], new_data={'id': rec_id, 'status': status},
                               ip=request.remote_addr)
            cursor.close(); conn.close()
            return jsonify({'status': 'success', 'msg': 'Rekomendasi diperbarui'})
        except Exception as e:
            return jsonify({'status': 'error', 'msg': str(e)}), 500

    # ================================================================
    # LAPORAN PDF — laporan AC / kendaraan berlogo BPF
    # ================================================================
    @app.route('/api/assets/report')
    @role_required(ASSET_ROLES)
    def api_assets_report():
        try:
            kind = str(request.args.get('kind', 'ac') or '').strip()
            if kind not in ('ac', 'vehicle'):
                return jsonify({'error': 'kind harus ac / vehicle'}), 400
            conn = get_db_connection()
            if not conn:
                return jsonify({'error': 'DB error'}), 500
            cursor = conn.cursor(dictionary=True)
            rows = []
            if kind == 'ac':
                cursor.execute("SELECT * FROM asset_ac ORDER BY asset_id")
                for a in cursor.fetchall():
                    cursor.execute(
                        "SELECT tanggal, teknisi, health_score, sparepart_cost, "
                        "next_service_date FROM asset_ac_logs WHERE asset_id=%s "
                        "ORDER BY tanggal DESC, id DESC LIMIT 5", (a['asset_id'],))
                    a['logs'] = cursor.fetchall()
                    rows.append(a)
            else:
                cursor.execute("SELECT * FROM vehicle_assets ORDER BY vehicle_type, nopol")
                for v in cursor.fetchall():
                    cursor.execute(
                        "SELECT service_date, component_name, odometer, cost, "
                        "next_service_km, next_service_months FROM vehicle_service_logs "
                        "WHERE vehicle_asset_id=%s ORDER BY service_date DESC, id DESC "
                        "LIMIT 5", (v['id'],))
                    v['services'] = cursor.fetchall()
                    rows.append(v)
            cursor.close(); conn.close()
            user = _current_user()
            pdf = AssetReportPDF(kind=kind)
            pdf.generate(rows, generated_by=user['full_name'])
            buf = io.BytesIO()
            pdf.output(buf)
            buf.seek(0)
            fname = f'Laporan_Aset_{kind}_{date.today().isoformat()}.pdf'
            response = make_response(buf.read())
            response.headers['Content-Type'] = 'application/pdf'
            response.headers['Content-Disposition'] = f'attachment; filename={fname}'
            return response
        except Exception as e:
            return jsonify({'error': str(e)}), 500
