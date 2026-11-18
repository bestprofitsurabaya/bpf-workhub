"""Laporan bulanan lintas cabang untuk Admin Pusat (v2.118.0 — Fase 3c).

Satu berkas per bulan yang menjawab "berapa uang & volume kerja tiap cabang
bulan lalu" tanpa membuka 12 dashboard:

- Klaim BBM: jumlah + nominal (transaksi non-dummy yang dibuat bulan itu).
- Kasbon: jumlah + nominal pengajuan.
- Air minum: jumlah + yang sudah terverifikasi.
- CV Online & FirstWork: jumlah pendaftar baru (DB master, per `branch_code`).

Format CSV (UTF-8 BOM) supaya langsung rapi di Excel — sama dengan ekspor
lain. Email **opsional**: hanya dikirim bila `SMTP_HOST` (dan kredensial bila
dibutuhkan) diisi di environment. Bila belum, endpoint menjawab 503 dengan
kode `EMAIL_NOT_CONFIGURED` — tidak berpura-pura mengirim.

Fan-out memakai prinsip panel Pusat: DB satu cabang gagal → baris cabang itu
ditandai error, cabang lain tetap dilaporkan.
"""
import csv
import io as _io
import os
import smtplib
from datetime import datetime
from email.message import EmailMessage

from flask import jsonify, make_response, request, session

from modules import branch_manager as bm
from modules.admin_scope import is_ho_admin, scope_denied_response
from modules.config import get_master_connection
from modules.helpers import client_ip, log_activity_async, role_required

MONTH_FMT = '%Y-%m'
DEFAULT_DAYS = 31


def _connect_db(db_name):
    from modules.config import DB_CONFIG, _pool_for
    if not db_name:
        return None
    if db_name == DB_CONFIG['database']:
        return get_master_connection()
    pool = _pool_for(db_name)
    return pool.get_connection() if pool else None


def _month(value):
    raw = str(value or '').strip()
    try:
        return datetime.strptime(raw, MONTH_FMT).strftime(MONTH_FMT)
    except (TypeError, ValueError):
        return datetime.now().strftime(MONTH_FMT)


def _branch_month(conn, month):
    """Angka satu DB cabang untuk bulan tertentu (kegagalan per metrik diisolasi)."""
    out = {'bbm_count': 0, 'bbm_amount': 0.0, 'bbm_archived': 0,
           'kasbon_count': 0, 'kasbon_amount': 0.0,
           'water_count': 0, 'water_verified': 0}
    errs = []
    cur = conn.cursor(dictionary=True)
    try:
        cur.execute(
            "SELECT COUNT(*) AS n, COALESCE(SUM(nominal), 0) AS amount, "
            "COALESCE(SUM(status='archived'), 0) AS archived "
            "FROM transactions WHERE DATE_FORMAT(created_at, '%%Y-%%m')=%s "
            "AND (is_dummy=0 OR is_dummy IS NULL)", (month,))
        row = cur.fetchone() or {}
        out['bbm_count'] = int(row.get('n') or 0)
        out['bbm_amount'] = float(row.get('amount') or 0)
        out['bbm_archived'] = int(row.get('archived') or 0)
    except Exception as exc:
        errs.append(f'bbm: {str(exc)[:60]}')
    try:
        cur.execute(
            "SELECT COUNT(*) AS n, COALESCE(SUM(total_amount), 0) AS amount "
            "FROM fuel_cash_requests WHERE DATE_FORMAT(created_at, '%%Y-%%m')=%s",
            (month,))
        row = cur.fetchone() or {}
        out['kasbon_count'] = int(row.get('n') or 0)
        out['kasbon_amount'] = float(row.get('amount') or 0)
    except Exception as exc:
        errs.append(f'kasbon: {str(exc)[:60]}')
    try:
        cur.execute(
            "SELECT COUNT(*) AS n, COALESCE(SUM(status='verified'), 0) AS v "
            "FROM water_purchases WHERE DATE_FORMAT(created_at, '%%Y-%%m')=%s",
            (month,))
        row = cur.fetchone() or {}
        out['water_count'] = int(row.get('n') or 0)
        out['water_verified'] = int(row.get('v') or 0)
    except Exception as exc:
        errs.append(f'air: {str(exc)[:60]}')
    finally:
        cur.close()
    return out, errs


def _master_month(month):
    """CV Online & FirstWork per cabang (DB master)."""
    per = {'cv_new': {}, 'first_work_new': {}}
    conn = get_master_connection()
    if not conn:
        return per, ['DB master tidak tersedia']
    errors = []
    cur = conn.cursor(dictionary=True)
    try:
        for key, table in (('cv_new', 'cv_online_submissions'),
                           ('first_work_new', 'first_work_submissions')):
            try:
                cur.execute(
                    f"SELECT branch_code, COUNT(*) AS n FROM {table} "
                    "WHERE DATE_FORMAT(submitted_at, '%Y-%m')=%s "
                    "GROUP BY branch_code", (month,))
                for row in cur.fetchall() or []:
                    code = str(row.get('branch_code') or '').strip().upper()
                    per[key][code] = int(row.get('n') or 0)
            except Exception as exc:
                errors.append(f'{table}: {str(exc)[:100]}')
    finally:
        cur.close()
        conn.close()
    return per, errors


def build_report(month):
    """Susun laporan bulanan. Selalu mengembalikan struktur walau DB mati."""
    master = get_master_connection()
    if not master:
        return {'month': month, 'branches': [], 'totals': {}, 'errors':
                [{'branch': '-', 'error': 'DB master tidak tersedia'}]}
    try:
        branches = bm.list_branches(conn=master)
    finally:
        try:
            master.close()
        except Exception:
            pass
    per_master, master_errors = _master_month(month)

    rows, errors = [], []
    totals = {'bbm_count': 0, 'bbm_amount': 0.0, 'bbm_archived': 0,
              'kasbon_count': 0, 'kasbon_amount': 0.0, 'water_count': 0,
              'water_verified': 0, 'cv_new': 0, 'first_work_new': 0}
    for b in branches:
        code = str(b.get('code') or '').strip().upper()
        if not b.get('is_active'):
            continue
        row = {'code': code, 'name': b.get('name') or code,
               'status': 'ok', 'error': ''}
        conn = None
        try:
            conn = _connect_db(b.get('db_name'))
            if not conn:
                raise RuntimeError('DB tidak dapat dihubungi')
            metrics, metric_errors = _branch_month(conn, month)
            row.update(metrics)
            if metric_errors:
                row['status'] = 'partial'
                row['error'] = '; '.join(metric_errors)[:160]
                errors.append({'branch': code, 'error': row['error']})
        except Exception as exc:
            row.update({'bbm_count': 0, 'bbm_amount': 0.0, 'bbm_archived': 0,
                        'kasbon_count': 0, 'kasbon_amount': 0.0,
                        'water_count': 0, 'water_verified': 0})
            row['status'] = 'error'
            row['error'] = str(exc)[:160]
            errors.append({'branch': code, 'error': row['error']})
        finally:
            if conn:
                try:
                    conn.close()
                except Exception:
                    pass
        row['cv_new'] = int(per_master['cv_new'].get(code) or 0)
        row['first_work_new'] = int(per_master['first_work_new'].get(code) or 0)
        for key in totals:
            totals[key] += row.get(key) or 0
        rows.append(row)

    for key, value in (('cv_new', 'cv_online_submissions'),
                       ('first_work_new', 'first_work_submissions')):
        if value in ' '.join(master_errors):
            errors.append({'branch': '-', 'error': f'{key}: tidak tersedia'})

    return {
        'month': month, 'branches': rows, 'totals': totals,
        'summary': {'branches': len(rows), 'errors': len(errors),
                    'generated_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S')},
        'errors': errors,
    }


def _csv(report):
    buf = _io.StringIO()
    w = csv.writer(buf)
    w.writerow(['Bulan', report['month']])
    w.writerow([])
    w.writerow(['Cabang', 'Nama', 'Status DB', 'Klaim BBM', 'Nilai BBM (Rp)',
                'Arsip', 'Kasbon', 'Nilai Kasbon (Rp)', 'Air Minum',
                'Air Terverifikasi', 'CV Baru', 'FirstWork Baru'])
    for r in report['branches']:
        w.writerow([r['code'], r['name'], r['status'], r['bbm_count'],
                    int(r['bbm_amount']), r['bbm_archived'], r['kasbon_count'],
                    int(r['kasbon_amount']), r['water_count'],
                    r['water_verified'], r['cv_new'], r['first_work_new']])
    t = report['totals']
    w.writerow(['TOTAL', '', '', t['bbm_count'], int(t['bbm_amount']),
                t['bbm_archived'], t['kasbon_count'], int(t['kasbon_amount']),
                t['water_count'], t['water_verified'], t['cv_new'],
                t['first_work_new']])
    if report['errors']:
        w.writerow([])
        w.writerow(['Catatan: cabang berikut tidak terbaca penuh'])
        for e in report['errors']:
            w.writerow([e['branch'], e['error']])
    return '\ufeff' + buf.getvalue()


def _smtp_ready():
    return bool(os.environ.get('SMTP_HOST'))


def send_email(report, to_addr):
    """Kirim CSV terlampir. Return (ok, msg, code)."""
    if not _smtp_ready():
        return False, ('Email belum dikonfigurasi: isi SMTP_HOST/PORT/USER/PASS '
                       'di environment server.'), 'EMAIL_NOT_CONFIGURED'
    host = os.environ.get('SMTP_HOST')
    port = int(os.environ.get('SMTP_PORT', '587') or 587)
    user = os.environ.get('SMTP_USER', '')
    password = os.environ.get('SMTP_PASS', '')
    sender = os.environ.get('SMTP_FROM', user or 'no-reply@localhost')
    use_ssl = os.environ.get('SMTP_SSL', '').lower() in ('1', 'true', 'yes')
    msg = EmailMessage()
    msg['Subject'] = f'Laporan Bulanan Pusat — {report["month"]}'
    msg['From'] = sender
    msg['To'] = to_addr
    msg.set_content(
        f'Laporan bulanan BPF WorkHub untuk {report["month"]} terlampir.\n'
        f'Cabang: {report["summary"]["branches"]}, '
        f'error DB: {report["summary"]["errors"]}.\n')
    msg.add_attachment(_csv(report).encode('utf-8'),
                       maintype='text', subtype='csv',
                       filename=f'laporan-bulanan-{report["month"]}.csv')
    try:
        if use_ssl:
            server = smtplib.SMTP_SSL(host, port, timeout=20)
        else:
            server = smtplib.SMTP(host, port, timeout=20)
            server.starttls()
        if user:
            server.login(user, password)
        server.send_message(msg)
        server.quit()
        return True, f'Laporan {report["month"]} dikirim ke {to_addr}', 'OK'
    except Exception as exc:
        return False, f'Gagal mengirim email: {str(exc)[:140]}', 'EMAIL_FAILED'


def _record(key, value):
    conn = get_master_connection()
    if not conn:
        return
    cur = conn.cursor()
    try:
        cur.execute(
            "INSERT INTO system_config (config_key, config_value) VALUES (%s,%s) "
            "ON DUPLICATE KEY UPDATE config_value=VALUES(config_value)",
            (key, value))
        conn.commit()
    finally:
        cur.close()
        conn.close()


def _who():
    return (session.get('full_name') or session.get('user_name') or '').strip()


def register_monthly_report_routes(app):

    @app.route('/api/admin/monthly-report')
    @role_required(['admin'])
    def api_monthly_report():
        if not is_ho_admin():
            return scope_denied_response()
        report = build_report(_month(request.args.get('month')))
        return jsonify(report)

    @app.route('/api/admin/monthly-report/export')
    @role_required(['admin'])
    def api_monthly_report_export():
        if not is_ho_admin():
            return scope_denied_response()
        report = build_report(_month(request.args.get('month')))
        text = _csv(report)
        resp = make_response(text)
        resp.headers['Content-Type'] = 'text/csv; charset=utf-8'
        filename = f'Laporan_Bulanan_Pusat_{report["month"]}.csv'
        resp.headers['Content-Disposition'] = f'attachment; filename={filename}'
        _record(f'monthly_report_downloaded_{report["month"]}',
                f'{datetime.now().strftime("%Y-%m-%d %H:%M:%S")}|{_who()}')
        log_activity_async(None, 'monthly_report_download', 'admin', _who(),
                           new_data={'month': report['month'],
                                     'branches': report['summary']['branches']},
                           ip=client_ip())
        return resp

    @app.route('/api/admin/monthly-report/email', methods=['POST'])
    @role_required(['admin'])
    def api_monthly_report_email():
        if not is_ho_admin():
            return scope_denied_response()
        data = request.get_json(silent=True) or {}
        month = _month(data.get('month'))
        to_addr = str(data.get('to') or '').strip()[:200]
        if '@' not in to_addr:
            return jsonify({'status': 'error', 'msg': 'Alamat email tidak valid'}), 400
        report = build_report(month)
        ok, msg, code = send_email(report, to_addr)
        if not ok:
            return jsonify({'status': 'error', 'msg': msg, 'code': code}), (
                503 if code == 'EMAIL_NOT_CONFIGURED' else 502)
        _record(f'monthly_report_emailed_{month}',
                f'{datetime.now().strftime("%Y-%m-%d %H:%M:%S")}|{_who()}|{to_addr}')
        log_activity_async(None, 'monthly_report_email', 'admin', _who(),
                           new_data={'month': month, 'to': to_addr}, ip=client_ip())
        return jsonify({'status': 'success', 'msg': msg, 'month': month})

    @app.route('/api/admin/monthly-report/status')
    @role_required(['admin'])
    def api_monthly_report_status():
        """Status unduh/kirim bulan lalu — pengingat "laporan belum dibuat"."""
        if not is_ho_admin():
            return scope_denied_response()
        month = _month(request.args.get('month'))
        conn = get_master_connection()
        if not conn:
            return jsonify({'status': 'error', 'msg': 'DB master tidak tersedia'}), 500
        keys = (f'monthly_report_downloaded_{month}',
                f'monthly_report_emailed_{month}')
        cur = conn.cursor(dictionary=True)
        try:
            cur.execute("SELECT config_key, config_value FROM system_config "
                        "WHERE config_key IN (%s, %s)", keys)
            found = {r['config_key']: r['config_value'] for r in cur.fetchall() or []}
        finally:
            cur.close()
            conn.close()
        return jsonify({
            'month': month,
            'downloaded_at': found.get(keys[0], ''),
            'emailed_at': found.get(keys[1], ''),
            'email_configured': _smtp_ready(),
            'due': not (found.get(keys[0]) or found.get(keys[1])),
        })
