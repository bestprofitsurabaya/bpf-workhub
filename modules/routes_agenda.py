"""Routes modul Agenda (v2.123.0).

Menggabungkan:
- API baca untuk SPA (`/api/agenda/*`) — semua role, dibatasi cabang;
- API kelola (`/api/admin/agenda/*`) — admin & content_creator;
- bridge aplikasi Cordova lama (`/api/state`, `/api/month`, `/api/stream`,
  `/assets/up/*`) — publik, read-only, bentuk respons dipertahankan.

Catatan keamanan:
- Setiap aksi tulis memakai `@role_required(['admin','content_creator'])`
  dan scope cabang ditegakkan di `modules.agenda` (bukan hanya UI).
- Hapus agenda memakai step-up PIN (`@stepup_required`, 428).
- Upload dibatasi ekstensi media, ukuran, nama file dibuat server-side.
"""
import io
import json
import os
import re
import secrets
import time
from datetime import date, datetime

from flask import (Response, jsonify, request, send_from_directory, session,
                   stream_with_context)
from werkzeug.utils import secure_filename

from modules import agenda as ag
from modules.admin_scope import (admin_branches, admin_can_operate_branch,
                                 is_ho_admin)
from modules.config import get_db_connection
from modules.helpers import log_activity_async, role_required
from modules.stepup import stepup_required

AGENDA_WRITE_ROLES = ['admin', 'content_creator']

# Disimpan di volume `uploads` (sudah persisten di docker-compose). Jangan
# pakai data/ karena hanya sebagian subfolder data/ yang di-mount.
MEDIA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                         'uploads', 'agenda')
os.makedirs(MEDIA_DIR, exist_ok=True)

MEDIA_EXT = {'png', 'jpg', 'jpeg', 'webp', 'gif', 'mp4', 'm4v', 'webm', 'mov',
             'pdf', 'mp3', 'm4a'}
# Selaras dengan MAX_CONTENT_LENGTH global (16 MB) — sisakan margin.
MAX_UPLOAD_BYTES = 15 * 1024 * 1024

RE_SAFE_MEDIA = re.compile(r'^[A-Za-z0-9._-]+$')


def _role():
    return session.get('user_role') or ''


def _actor():
    return session.get('user_name') or ''


def _branch():
    return str(session.get('branch_code') or '').strip().upper()


def _requested_branch(data=None):
    raw = ''
    if isinstance(data, dict):
        raw = data.get('branch_code') or data.get('branch') or ''
    if not raw:
        raw = request.args.get('branch') or request.args.get('branch_code') or ''
    return str(raw or '').strip().upper()


def _read_scope():
    """Daftar cabang yang boleh dibaca sesi ini."""
    role = _role()
    req = _requested_branch()
    if role == 'admin':
        if is_ho_admin():
            # Tanpa filter cabang = semua cabang (admin master).
            return [req] if req and req not in ('ALL', '*') else ag.active_branch_codes()
        codes, _all = admin_branches()
        allowed = [_norm(c) for c in codes if _norm(c)]
        if req and req in allowed:
            return [req]
        return allowed or [_branch()]
    # content_creator dan role lain: hanya cabang sesi.
    return [_branch()]


def _norm(code):
    return str(code or '').strip().upper()


def _can_manage_branch(code):
    """True bila sesi boleh menulis agenda cabang `code`."""
    role = _role()
    if role == 'content_creator':
        return _norm(code) == _branch()
    if role == 'admin':
        return admin_can_operate_branch(code)
    return False


def _json_error(msg, status=400):
    return jsonify({'status': 'error', 'ok': False, 'msg': msg}), status


def _month_arg():
    month = request.args.get('month') or date.today().strftime('%Y-%m')
    if not ag.RE_MONTH.match(str(month)):
        return None
    return str(month)


def _audience_arg():
    return ag.normalize_audience(request.args.get('audience') or 'all')


def register_agenda_routes(app):

    # ==================================================================
    # BACA (SPA) — semua role
    # ==================================================================
    @app.route('/api/agenda/month')
    @role_required(['admin', 'ga', 'finance', 'marketing', 'chief_driver',
                    'driver', 'ob', 'receptionist', 'traineer', 'ga_hr',
                    'security', 'content_creator',
                    'it_sby', 'it_hu', 'it_jkt2', 'it_bdg', 'it_smg',
                    'it_mlg', 'it_mdn', 'it_bjm', 'it_plm', 'it_lpg'])
    def api_agenda_month():
        month = _month_arg()
        if not month:
            return _json_error('Format bulan harus YYYY-MM')
        branches = _read_scope()
        raw_month = request.args.get('month') or ''
        items = ag.visible_items(branches, *ag._month_bounds(month),
                                 role=_role(),
                                 audience_filter=request.args.get('audience'),
                                 merge_batches=len(branches) > 1)
        days = {}
        for it in items:
            rec = days.setdefault(it['date'], {'date': it['date'], 'count': 0,
                                               'titles': [], 'pinned': False})
            rec['count'] += 1
            if it.get('title'):
                rec['titles'].append(it['title'])
            if it.get('pinned'):
                rec['pinned'] = True
        return jsonify({
            'ok': True,
            'month': month,
            'branches': branches,
            'days': [days[k] for k in sorted(days)],
            'items': items,
            'server_time': datetime.now().strftime('%Y-%m-%dT%H:%M'),
            'raw_month': raw_month,
        })

    @app.route('/api/agenda/day')
    @role_required(['admin', 'ga', 'finance', 'marketing', 'chief_driver',
                    'driver', 'ob', 'receptionist', 'traineer', 'ga_hr',
                    'security', 'content_creator',
                    'it_sby', 'it_hu', 'it_jkt2', 'it_bdg', 'it_smg',
                    'it_mlg', 'it_mdn', 'it_bjm', 'it_plm', 'it_lpg'])
    def api_agenda_day():
        day = request.args.get('date') or date.today().isoformat()
        if not ag.RE_DATE.match(str(day)):
            return _json_error('Format tanggal harus YYYY-MM-DD')
        branches = _read_scope()
        items = ag.items_on_day(branches, day, role=_role(),
                                audience_filter=request.args.get('audience'),
                                merge_batches=len(branches) > 1)
        return jsonify({'ok': True, 'date': day, 'branches': branches,
                        'items': items})

    @app.route('/api/agenda/upcoming')
    @role_required(['admin', 'ga', 'finance', 'marketing', 'chief_driver',
                    'driver', 'ob', 'receptionist', 'traineer', 'ga_hr',
                    'security', 'content_creator',
                    'it_sby', 'it_hu', 'it_jkt2', 'it_bdg', 'it_smg',
                    'it_mlg', 'it_mdn', 'it_bjm', 'it_plm', 'it_lpg'])
    def api_agenda_upcoming():
        try:
            days = int(request.args.get('days') or 7)
        except (TypeError, ValueError):
            days = 7
        branches = _read_scope()
        items = ag.upcoming_items(branches, days=days, role=_role(),
                                  merge_batches=len(branches) > 1)
        return jsonify({'ok': True, 'days': days, 'branches': branches,
                        'items': items})

    @app.route('/api/agenda/item/<int:item_id>')
    @role_required(['admin', 'ga', 'finance', 'marketing', 'chief_driver',
                    'driver', 'ob', 'receptionist', 'traineer', 'ga_hr',
                    'security', 'content_creator',
                    'it_sby', 'it_hu', 'it_jkt2', 'it_bdg', 'it_smg',
                    'it_mlg', 'it_mdn', 'it_bjm', 'it_plm', 'it_lpg'])
    def api_agenda_item(item_id):
        for code in _read_scope():
            conn = None
            try:
                conn = get_db_connection(branch_code=code)
                row = ag._load_item(conn, item_id)
                if row:
                    return jsonify({'ok': True,
                                    'item': ag.item_shape(row, ag._as_date(row['agenda_date']))})
            except Exception as e:
                print(f'[agenda] item {item_id}/{code}: {e}')
            finally:
                if conn:
                    try:
                        conn.close()
                    except Exception:
                        pass
        return _json_error('Agenda tidak ditemukan', 404)

    @app.route('/api/agenda/ics')
    @role_required(['admin', 'ga', 'finance', 'marketing', 'chief_driver',
                    'driver', 'ob', 'receptionist', 'traineer', 'ga_hr',
                    'security', 'content_creator',
                    'it_sby', 'it_hu', 'it_jkt2', 'it_bdg', 'it_smg',
                    'it_mlg', 'it_mdn', 'it_bjm', 'it_plm', 'it_lpg'])
    def api_agenda_ics():
        month = _month_arg()
        if not month:
            return _json_error('Format bulan harus YYYY-MM')
        body = ag.build_ics(_read_scope(), month, role=_role(),
                            audience_filter=request.args.get('audience'))
        resp = Response(body, mimetype='text/calendar; charset=utf-8')
        resp.headers['Content-Disposition'] = (
            f'attachment; filename=agenda-{month}.ics')
        return resp

    @app.route('/api/agenda/export.pdf')
    @role_required(['admin', 'ga', 'finance', 'marketing', 'chief_driver',
                    'driver', 'ob', 'receptionist', 'traineer', 'ga_hr',
                    'security', 'content_creator',
                    'it_sby', 'it_hu', 'it_jkt2', 'it_bdg', 'it_smg',
                    'it_mlg', 'it_mdn', 'it_bjm', 'it_plm', 'it_lpg'])
    def api_agenda_pdf():
        month = _month_arg()
        if not month:
            return _json_error('Format bulan harus YYYY-MM')
        branches = _read_scope()
        items = ag.visible_items(branches, *ag._month_bounds(month),
                                 role=_role(),
                                 audience_filter=request.args.get('audience'),
                                 merge_batches=len(branches) > 1)
        try:
            data = _build_pdf(month, branches, items)
        except Exception as e:
            print(f'[agenda] pdf error: {e}')
            return _json_error('Gagal membuat PDF', 500)
        resp = Response(data, mimetype='application/pdf')
        resp.headers['Content-Disposition'] = (
            f'inline; filename=agenda-{month}.pdf')
        return resp

    # ==================================================================
    # KELOLA (admin cabang, admin master, content creator)
    # ==================================================================
    @app.route('/api/admin/agenda/items', methods=['POST'])
    @role_required(AGENDA_WRITE_ROLES)
    def api_admin_agenda_create():
        data = request.get_json(silent=True) or {}
        created, errors = ag.create_items(data, _actor(), _role(),
                                          requested_branch=_requested_branch(data))
        if errors:
            return _json_error('; '.join(errors))
        return jsonify({'ok': True, 'status': 'ok', 'items': created})

    @app.route('/api/admin/agenda/items/<int:item_id>', methods=['PUT'])
    @role_required(AGENDA_WRITE_ROLES)
    def api_admin_agenda_update(item_id):
        data = request.get_json(silent=True) or {}
        branch = _requested_branch(data) or _branch()
        apply_batch = data.get('apply_batch', True) not in (False, 0, '0', 'false')
        updated, errors = ag.update_item(item_id, data, _actor(), _role(),
                                         branch, apply_batch=apply_batch)
        if errors:
            return _json_error('; '.join(errors))
        return jsonify({'ok': True, 'status': 'ok', 'items': updated})

    @app.route('/api/admin/agenda/items/<int:item_id>', methods=['DELETE'])
    @role_required(AGENDA_WRITE_ROLES)
    @stepup_required
    def api_admin_agenda_delete(item_id):
        data = request.get_json(silent=True) or {}
        branch = _requested_branch(data) or _branch()
        apply_batch = data.get('apply_batch', True) not in (False, 0, '0', 'false')
        n, errors = ag.delete_items(item_id, _actor(), _role(), branch,
                                    apply_batch=apply_batch)
        if errors:
            return _json_error('; '.join(errors))
        return jsonify({'ok': True, 'status': 'ok', 'deleted': n})

    @app.route('/api/admin/agenda/items/<int:item_id>/duplicate', methods=['POST'])
    @role_required(AGENDA_WRITE_ROLES)
    def api_admin_agenda_duplicate(item_id):
        data = request.get_json(silent=True) or {}
        branch = _requested_branch(data) or _branch()
        if not _can_manage_branch(branch):
            return _json_error('Cabang di luar kewenangan', 403)
        payload = None
        for code in _read_scope():
            conn = None
            try:
                conn = get_db_connection(branch_code=code)
                row = ag._load_item(conn, item_id)
                if row:
                    payload = {k: row.get(k) for k in (
                        'title', 'body', 'category', 'audience', 'audience_roles',
                        'publish_mode', 'publish_at', 'end_at', 'repeat_rule',
                        'repeat_until', 'media_url', 'attachment_path', 'pinned')}
                    payload['agenda_date'] = data.get('agenda_date') or row.get('agenda_date')
                    break
            except Exception as e:
                print(f'[agenda] duplicate load {code}: {e}')
            finally:
                if conn:
                    try:
                        conn.close()
                    except Exception:
                        pass
        if not payload:
            return _json_error('Agenda tidak ditemukan', 404)
        payload['branch_code'] = branch
        created, errors = ag.create_items(payload, _actor(), _role(),
                                          requested_branch=branch)
        if errors:
            return _json_error('; '.join(errors))
        return jsonify({'ok': True, 'status': 'ok', 'items': created})

    @app.route('/api/admin/agenda/upload', methods=['POST'])
    @role_required(AGENDA_WRITE_ROLES)
    def api_admin_agenda_upload():
        f = request.files.get('file')
        raw_name = ''
        if f is not None:
            raw_name = f.filename or ''
            blob = f.read(MAX_UPLOAD_BYTES + 1)
        else:
            raw_name = request.headers.get('X-Filename', '') or 'upload.bin'
            blob = request.get_data(cache=False, as_text=False) or b''
        if not blob:
            return _json_error('File kosong')
        if len(blob) > MAX_UPLOAD_BYTES:
            return _json_error('Ukuran file maksimal 15 MB', 413)
        safe = secure_filename(raw_name) or 'upload'
        ext = safe.rsplit('.', 1)[1].lower() if '.' in safe else ''
        if ext not in MEDIA_EXT:
            return _json_error('Ekstensi file tidak diizinkan')
        filename = f"agenda_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{secrets.token_hex(6)}.{ext}"
        path = os.path.join(MEDIA_DIR, filename)
        with open(path, 'wb') as out:
            out.write(blob)
        url = f'/assets/up/{filename}'
        log_activity_async(None, 'agenda_upload', 'user', _actor(),
                           new_data={'file': filename, 'bytes': len(blob)},
                           branch_code=_branch())
        return jsonify({'ok': True, 'status': 'ok', 'url': url,
                        'filename': filename,
                        'media_type': (ag.media_kind(url) or {}).get('kind')})

    @app.route('/api/admin/agenda/coverage')
    @role_required(['admin'])
    def api_admin_agenda_coverage():
        if not is_ho_admin():
            return _json_error('Matriks cakupan hanya untuk Admin Pusat', 403)
        month = _month_arg()
        if not month:
            return _json_error('Format bulan harus YYYY-MM')
        return jsonify({'ok': True, 'coverage': ag.coverage(month)})

    # ==================================================================
    # BRIDGE Cordova lama — publik, read-only
    # ==================================================================
    @app.route('/api/state')
    def api_bridge_state():
        day = request.args.get('date')
        audience = request.args.get('audience') or 'all'
        return jsonify(ag.bridge_state(day=day, audience=audience))

    @app.route('/api/month')
    def api_bridge_month():
        month = request.args.get('month')
        audience = request.args.get('audience') or 'all'
        include = request.args.get('items') in ('1', 'true', 'yes')
        data = ag.bridge_month(month=month, audience=audience,
                               include_items=include)
        return jsonify(data)

    @app.route('/api/stream')
    def api_bridge_stream():
        """SSE ringkas: satu event `state` lalu tutup (klien lama reconnect).

        Sengaja tidak menahan worker: aplikasi Cordova sudah punya fallback
        polling 15 detik bila SSE gagal/terputus.
        """
        audience = request.args.get('audience') or 'all'

        def gen():
            yield 'retry: 15000\n\n'
            yield ('event: hello\ndata: '
                   + json.dumps({'date': date.today().isoformat(),
                                 'now': datetime.now().strftime('%Y-%m-%dT%H:%M'),
                                 'audience': audience}) + '\n\n')
            last = None
            # Tahan stream ±5 menit lalu putus; EventSource akan menyambung
            # lagi. Loop memakai sleep kooperatif di worker gevent produksi.
            for _ in range(12):
                try:
                    payload = ag.bridge_state(audience=audience)
                except Exception as e:
                    print(f'[agenda] bridge stream error: {e}')
                    payload = {'date': date.today().isoformat(), 'items': []}
                body = json.dumps(payload, ensure_ascii=False, sort_keys=True)
                if body != last:
                    last = body
                    yield 'event: state\ndata: ' + body + '\n\n'
                else:
                    yield ': keep-alive\n\n'
                time.sleep(25)

        resp = Response(stream_with_context(gen()),
                        mimetype='text/event-stream; charset=utf-8')
        resp.headers['Cache-Control'] = 'no-cache'
        resp.headers['X-Accel-Buffering'] = 'no'
        return resp

    @app.route('/assets/up/<path:filename>')
    def api_bridge_asset(filename):
        name = os.path.basename(filename)
        if not RE_SAFE_MEDIA.match(name or ''):
            return _json_error('Nama file tidak valid', 400)
        full = os.path.join(MEDIA_DIR, name)
        if not os.path.isfile(full):
            return _json_error('File tidak ditemukan', 404)
        resp = send_from_directory(MEDIA_DIR, name, conditional=True)
        resp.headers.setdefault('Cache-Control', 'public, max-age=86400')
        return resp

    @app.route('/assets/logo.png')
    def api_bridge_logo():
        """Logo untuk aplikasi Cordova lama (API_BASE/assets/logo.png)."""
        folder = os.path.join(os.path.dirname(__file__), '..', 'static')
        if not os.path.isfile(os.path.join(folder, 'bpf-logo.png')):
            return _json_error('Logo tidak tersedia', 404)
        resp = send_from_directory(folder, 'bpf-logo.png', conditional=True)
        resp.headers.setdefault('Cache-Control', 'public, max-age=86400')
        return resp


# ---------------------------------------------------------------------------
# PDF
# ---------------------------------------------------------------------------
def _build_pdf(month, branches, items):
    from modules.pdf_generator import BPFBasePDF

    branch_label = branches[0] if len(branches) == 1 else 'Semua Cabang'
    pdf = BPFBasePDF(orientation='P', unit='mm', format='A4')
    try:
        pdf.set_identity(branch_code=branches[0] if len(branches) == 1 else None)
    except Exception:
        pass
    pdf.set_auto_page_break(auto=True, margin=18)
    pdf.add_page()
    pdf.set_font(pdf._font(), 'B', 13)
    pdf.cell(0, 8, 'AGENDA KEGIATAN', align='C', new_x='LMARGIN', new_y='NEXT')
    pdf.set_font(pdf._font(), '', 9)
    pdf.cell(0, 5, f'Periode: {month}', align='C', new_x='LMARGIN', new_y='NEXT')
    pdf.cell(0, 5, f'Cabang: {branch_label}', align='C', new_x='LMARGIN', new_y='NEXT')
    pdf.ln(3)

    if not items:
        pdf.set_font(pdf._font(), 'I', 10)
        pdf.cell(0, 8, 'Tidak ada agenda pada periode ini.', align='C',
                 new_x='LMARGIN', new_y='NEXT')
    else:
        widths = [24, 52, 74, 34]
        pdf._table_header(['TANGGAL', 'JUDUL', 'ISI', 'KATEGORI'], widths, font_size=8)
        fill = False
        for it in items:
            title = str(it.get('title') or '')
            body = str(it.get('body') or '')
            row_h = 6
            lines = max(1, (len(title) // 34) + 1, (len(body) // 50) + 1)
            row_h = min(28, 6 * lines)
            pdf._table_row([
                it.get('date') or '-',
                title[:120],
                body[:240],
                it.get('category') or 'umum',
            ], widths, aligns=['C', 'L', 'L', 'C'], row_h=row_h, fill=fill)
            fill = not fill

    pdf.ln(3)
    pdf.set_font(pdf._font(), 'I', 8)
    pdf.cell(0, 5, f'Dicetak: {datetime.now().strftime("%d-%m-%Y %H:%M")}',
             align='R', new_x='LMARGIN', new_y='NEXT')
    out = pdf.output()
    return bytes(out)
