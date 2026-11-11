"""Inventaris IT (v2.78.0) — aset non-jaringan, label QR, kondisi, discovery.

Kenapa modul terpisah dari `routes_assets.py` (AC & kendaraan, role GA):
- pemilik datanya IT per cabang (`it_<kode>`), bukan GA;
- siklusnya berbeda: tag/label, kondisi, penemuan jaringan, stok opname;
- mencampur keduanya akan membuat filter role & UI saling mengunci.

Pola mengikuti modul lain: `register_it_asset_routes(app)` dipanggil app.py,
tabel di-ensure oleh `it_inventory_schema.ensure_it_inventory_schema()`.

Semua endpoint di-scope ke `session['branch_code']` (admin pusat boleh
meminta `?all=1` untuk ringkasan lintas cabang).
"""
import csv
import hmac
import io
import json
import os
import re
import socket
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta

from flask import request, jsonify, make_response, session

from modules.config import get_db_connection
from modules.helpers import role_required, log_activity_async, save_file
from modules.it_classifier import classify, normalize_mac, mac_vendor
from modules.it_inventory_schema import (
    IT_CATEGORIES, IT_CATEGORY_CODES, IT_STATUSES, IT_CONDITIONS,
)

IT_ROLES = [
    'it_sby', 'it_hu', 'it_jkt2', 'it_bdg', 'it_smg', 'it_mlg', 'it_mdn',
    'it_bjm', 'it_plm', 'it_lpg',
]
ALLOWED = IT_ROLES + ['admin']

# Port yang diprobe saat sapuan. Sengaja pendek & tanpa Nmap.
SWEEP_PORTS = [135, 445, 139, 3389, 5985, 9100, 631, 515, 80, 443, 22, 53, 554, 8000]

# Kunci global agar hanya satu sapuan berjalan (proses web bisa 1 worker,
# tetapi tetap aman bila dijalankan dari thread/CLI).
_SCAN_LOCK = threading.Lock()

def _asset_report_pdf(rows, branch, generated_by=''):
    """Laporan inventaris PDF (landscape A4) — dipisah agar mudah diuji."""
    from fpdf import FPDF
    from fpdf.enums import XPos, YPos

    pdf = FPDF(orientation='L', unit='mm', format='A4')
    pdf.set_auto_page_break(True, margin=12)
    pdf.add_page()
    pdf.set_font('helvetica', 'B', 14)
    pdf.cell(0, 8, f'LAPORAN INVENTARIS IT - CABANG {branch}', align='C',
             new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.set_font('helvetica', '', 8.5)
    pdf.cell(0, 5, f'Dicetak {datetime.now():%d/%m/%Y %H:%M} oleh {generated_by or "-"} '
                   f'· {len(rows)} aset', align='C', new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.ln(3)

    widths = [30, 24, 44, 20, 26, 34, 34, 22]
    headers = ['Tag', 'Kategori', 'Merek / Model', 'Status', 'Kondisi',
               'Ruangan', 'PIC', 'Garansi']
    pdf.set_font('helvetica', 'B', 8)
    pdf.set_fill_color(235, 239, 246)
    for w, h in zip(widths, headers):
        pdf.cell(w, 6, h, border=1, align='C', fill=True)
    pdf.ln()

    pdf.set_font('helvetica', '', 7.5)
    for r in rows:
        name = ' '.join(filter(None, [r.get('brand'), r.get('model')]))[:34]
        values = [
            r.get('asset_tag') or '', CATEGORY_LABEL.get(r.get('category'), r.get('category') or ''),
            name, r.get('status') or '',
            COND_LABEL_ID.get(r.get('cond'), r.get('cond') or ''),
            (r.get('location_room') or '')[:26], (r.get('assigned_to') or '')[:26],
            _jsonable(r.get('warranty_until')) or '-',
        ]
        for w, v in zip(widths, values):
            pdf.cell(w, 5.4, str(v), border=1)
        pdf.ln()

    out = io.BytesIO()
    pdf.output(out)
    out.seek(0)
    return out


CATEGORY_LABEL = {c[0]: c[1] for c in IT_CATEGORIES}
COND_LABEL_ID = {'baik': 'Baik', 'rusak_ringan': 'Rusak Ringan', 'rusak_berat': 'Rusak Berat'}


# ------------------------------------------------------------------ routes

# ---------------------------------------------------------------- util umum


def _user():
    return (session.get('user_name') or '').strip()


def _full_name():
    return (session.get('full_name') or session.get('user_name') or '').strip()


def _branch():
    return (session.get('branch_code') or 'SBY').strip().upper()


def _is_admin():
    return (session.get('user_role') or '') == 'admin'


def _jsonable(value):
    if isinstance(value, (datetime, date)):
        return value.strftime('%Y-%m-%d %H:%M:%S') if isinstance(value, datetime) else value.isoformat()
    return value


def _loads(value, default=None):
    """Kolom JSON MariaDB bisa datang sebagai str/bytes/dict."""
    if value is None:
        return default
    if isinstance(value, (dict, list)):
        return value
    try:
        return json.loads(value)
    except Exception:
        return default


def _serialize(row):
    if not row:
        return row
    out = {k: _jsonable(v) for k, v in dict(row).items()}
    for key in ('specs', 'reasons', 'before_json', 'after_json'):
        if key in out:
            out[key] = _loads(out[key], out[key])
    return out


def _parse_date(value, label='Tanggal'):
    if not value:
        return None
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    try:
        return datetime.strptime(str(value).strip()[:10], '%Y-%m-%d').date()
    except ValueError:
        raise ValueError(f'{label} harus format YYYY-MM-DD')


def _money(value):
    if value in (None, ''):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        raise ValueError('Harga harus berupa angka')


def _like(value):
    return f"%{str(value or '').strip()}%"


def _tag_prefix(branch, category):
    return f"{str(branch).upper()}-IT-{str(category).upper()}-"


def _next_tag(cur, branch, category, width=4):
    prefix = _tag_prefix(branch, category)
    cur.execute(
        "SELECT asset_tag FROM it_assets WHERE asset_tag LIKE %s "
        "ORDER BY LENGTH(asset_tag) DESC, asset_tag DESC LIMIT 1", (prefix + '%',))
    row = cur.fetchone()
    seq = 1
    if row:
        last = (row[0] if isinstance(row, (tuple, list)) else row.get('asset_tag')) or ''
        m = re.search(r'(\d+)$', str(last))
        if m:
            seq = int(m.group(1)) + 1
    return f"{prefix}{seq:0{width}d}"


def _event(cur, asset_id, branch, kind, before, after, note='', photo='', actor=''):
    cur.execute(
        "INSERT INTO it_asset_events "
        "(asset_id, branch_code, kind, before_json, after_json, note, photo_path, actor) "
        "VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
        (asset_id, branch, kind,
         json.dumps(before, default=str) if before is not None else None,
         json.dumps(after, default=str) if after is not None else None,
         (note or '')[:500], photo or '', actor or ''))


def _get_asset(cur, tag, branch, for_update=False):
    sql = ("SELECT * FROM it_assets WHERE asset_tag=%s AND branch_code=%s"
           + (" FOR UPDATE" if for_update else ""))
    cur.execute(sql, (tag, branch))
    return cur.fetchone()


def _valid_category(value):
    return str(value or '').strip().lower() in IT_CATEGORY_CODES


def _clean_fields(data, partial=False):
    """Ambil field yang boleh diubah dari body; validasi enum & tanggal."""
    allowed = {
        'category': str, 'brand': str, 'model': str, 'serial_number': str,
        'status': str, 'cond': str, 'location_room': str, 'location_detail': str,
        'assigned_to': str, 'vendor': str, 'hostname': str, 'ip_address': str,
        'mac_address': str, 'os_name': str, 'notes': str,
    }
    out = {}
    for key, caster in allowed.items():
        if key not in data:
            continue
        value = data.get(key)
        out[key] = '' if value is None else str(value).strip()
    if 'category' in out:
        out['category'] = out['category'].lower()
        if out['category'] not in IT_CATEGORY_CODES:
            raise ValueError('Kategori tidak dikenal')
    if 'status' in out:
        out['status'] = out['status'].lower()
        if out['status'] not in IT_STATUSES:
            raise ValueError('Status tidak dikenal')
    if 'cond' in out:
        out['cond'] = out['cond'].lower()
        if out['cond'] not in IT_CONDITIONS:
            raise ValueError('Kondisi tidak dikenal')
    if 'mac_address' in out:
        out['mac_address'] = normalize_mac(out['mac_address']) or ''
    for key, label in (('purchase_date', 'Tanggal beli'), ('warranty_until', 'Garansi')):
        if key in data:
            out[key] = _parse_date(data.get(key), label)
    if 'purchase_price' in data:
        out['purchase_price'] = _money(data.get('purchase_price'))
    if 'specs' in data:
        specs = data.get('specs')
        if isinstance(specs, str):
            specs = _loads(specs, None)
        out['specs'] = json.dumps(specs, ensure_ascii=False) if specs else None
    if not partial and 'category' not in out:
        raise ValueError('Kategori wajib diisi')
    return out


def _csv_response(rows, filename):
    buf = io.StringIO()
    writer = csv.writer(buf, delimiter=';')
    headers = [
        'asset_tag', 'kategori', 'merek', 'model', 'serial', 'status', 'kondisi',
        'ruangan', 'detail_lokasi', 'pic', 'hostname', 'ip', 'mac', 'os',
        'tanggal_beli', 'garansi', 'harga', 'vendor', 'catatan', 'sumber',
        'terakhir_dilihat',
    ]
    writer.writerow(headers)
    for r in rows:
        writer.writerow([
            r.get('asset_tag'), r.get('category'), r.get('brand'), r.get('model'),
            r.get('serial_number'), r.get('status'), r.get('cond'),
            r.get('location_room'), r.get('location_detail'), r.get('assigned_to'),
            r.get('hostname'), r.get('ip_address'), r.get('mac_address'), r.get('os_name'),
            _jsonable(r.get('purchase_date')), _jsonable(r.get('warranty_until')),
            r.get('purchase_price'), r.get('vendor'),
            (r.get('notes') or '').replace('\n', ' '), r.get('source'),
            _jsonable(r.get('last_seen_at')),
        ])
    resp = make_response('\ufeff' + buf.getvalue())
    resp.headers['Content-Type'] = 'text/csv; charset=utf-8'
    resp.headers['Content-Disposition'] = f'attachment; filename={filename}'
    return resp


# ------------------------------------------------------- lapisan discovery


def _expand_cidr(cidr):
    """'192.168.2.0/24' → daftar IP host (tanpa network/broadcast)."""
    parts = str(cidr).strip().split('/')
    base = socket.inet_aton(parts[0])
    prefix = int(parts[1]) if len(parts) > 1 else 32
    if prefix < 16 or prefix > 32:
        raise ValueError('Prefix /16../32 yang didukung')
    base_int = int.from_bytes(base, 'big')
    mask = (0xFFFFFFFF << (32 - prefix)) & 0xFFFFFFFF if prefix else 0
    network = base_int & mask
    count = 1 << (32 - prefix)
    first, last = (1, count - 2) if prefix <= 30 else (0, count - 1)
    return [socket.inet_ntoa(((network + i) & 0xFFFFFFFF).to_bytes(4, 'big'))
            for i in range(first, last + 1)]


def _probe(ip, timeout=0.35):
    open_ports = []
    for port in SWEEP_PORTS:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(timeout)
        try:
            if s.connect_ex((ip, port)) == 0:
                open_ports.append(port)
        except OSError:
            pass
        finally:
            s.close()
    return open_ports


def _reverse_name(ip):
    try:
        return socket.gethostbyaddr(ip)[0].split('.')[0]
    except Exception:
        return ''


def _dedupe_key(branch, mac, ip):
    return f"{branch}|{mac}" if mac else f"{branch}|ip:{ip}"


def _upsert_device(conn, branch, run_id, dev):
    """Simpan/merge satu perangkat hasil temuan. Return True bila baru."""
    result = classify(
        ip=dev.get('ip', ''), mac=dev.get('mac', ''),
        hostname=dev.get('hostname', ''), vendor=dev.get('vendor', ''),
        ports=dev.get('ports') or [], ad_os=dev.get('ad_os', ''),
        dhcp_hostname=dev.get('dhcp_hostname', ''))
    mac = normalize_mac(dev.get('mac')) or ''
    key = _dedupe_key(branch, mac, dev.get('ip', ''))
    cur = conn.cursor(dictionary=True)
    try:
        cur.execute("SELECT id, state FROM it_discovered_devices WHERE dedupe_key=%s", (key,))
        existing = cur.fetchone()
        payload = (
            dev.get('ip', ''), mac, dev.get('hostname', '')[:120],
            (dev.get('vendor') or mac_vendor(mac))[:80],
            ','.join(str(p) for p in (dev.get('ports') or [])),
            result['category_suggest'], float(result['confidence']),
            json.dumps(result['reasons'], ensure_ascii=False),
            json.dumps(dev.get('specs'), ensure_ascii=False) if dev.get('specs') else None,
            result['non_asset_reason'],
        )
        if existing:
            # Jangan bangkitkan kembali perangkat yang sudah diabaikan/diadopsi.
            cur.execute(
                "UPDATE it_discovered_devices SET run_id=%s, ip=%s, mac=%s, hostname=%s, "
                "vendor=%s, open_ports=%s, category_suggest=%s, confidence=%s, reasons=%s, "
                "specs=COALESCE(%s, specs), note=%s, last_seen=NOW(), "
                "state=IF(state='new','new',state) WHERE id=%s",
                (run_id,) + payload + (existing['id'],))
            conn.commit()
            return False
        cur.execute(
            "INSERT INTO it_discovered_devices "
            "(run_id, branch_code, dedupe_key, ip, mac, hostname, vendor, open_ports, "
            " category_suggest, confidence, reasons, specs, note) "
            "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
            (run_id, branch, key) + payload)
        conn.commit()
        return True
    finally:
        cur.close()


def _run_sweep(branch, subnets, run_id, actor):
    conn = None
    try:
        conn = get_db_connection(branch_code=branch)
        if not conn:
            raise RuntimeError('DB tidak tersedia')
        found = 0
        new = 0
        for cidr in subnets:
            ips = _expand_cidr(cidr)
            with ThreadPoolExecutor(max_workers=64) as pool:
                for ip, ports in zip(ips, pool.map(_probe, ips)):
                    if not ports:
                        continue
                    found += 1
                    dev = {'ip': ip, 'ports': ports, 'hostname': _reverse_name(ip)}
                    if _upsert_device(conn, branch, run_id, dev):
                        new += 1
        cur = conn.cursor()
        cur.execute(
            "UPDATE it_discovery_runs SET finished_at=NOW(), found=%s, new_count=%s, "
            "status='ok' WHERE id=%s", (found, new, run_id))
        conn.commit()
        cur.close()
    except Exception as e:
        print(f'[it-discovery] sweep error: {e}')
        try:
            if conn:
                cur = conn.cursor()
                cur.execute("UPDATE it_discovery_runs SET finished_at=NOW(), status='error', "
                            "error=%s WHERE id=%s", (str(e)[:500], run_id))
                conn.commit()
                cur.close()
        except Exception:
            pass
    finally:
        if conn:
            try:
                conn.close()
            except Exception:
                pass
        _SCAN_LOCK.release()


def _label_pdf(assets, layout='a4-24', base_url=''):
    """Bangkitkan PDF label QR. Dipisah agar bisa diuji tanpa Flask."""
    import segno
    from fpdf import FPDF
    from fpdf.enums import XPos, YPos

    layouts = {
        # kode: (kolom, baris, margin_x, margin_y, qr_mm, font_mm)
        'a4-24': (3, 8, 8, 8, 24, 2.8),
        'a4-16': (2, 8, 8, 8, 30, 3.2),
        'a4-12': (2, 6, 8, 8, 34, 3.4),
    }
    if layout not in layouts:
        raise ValueError('Layout label tidak dikenal')
    cols, rows, mx, my, qr_mm, font_mm = layouts[layout]

    pdf = FPDF(orientation='P', unit='mm', format='A4')
    pdf.set_auto_page_break(False)
    pdf.set_margins(mx, my, mx)
    page_w, page_h = 210, 297
    cell_w = (page_w - 2 * mx) / cols
    cell_h = (page_h - 2 * my) / rows
    per_page = cols * rows

    qr_cache = {}
    for idx, asset in enumerate(assets):
        if idx % per_page == 0:
            pdf.add_page()
        slot = idx % per_page
        c, r = slot % cols, slot // cols
        x = mx + c * cell_w
        y = my + r * cell_h

        pdf.set_draw_color(205, 213, 225)
        pdf.rect(x, y, cell_w, cell_h)

        tag = asset['asset_tag']
        if tag not in qr_cache:
            payload = f"{base_url.rstrip('/')}/app/it/assets/{tag}" if base_url else f"BPFIT:{tag}"
            buf = io.BytesIO()
            segno.make(payload, error='m').save(buf, kind='png', scale=10, border=1)
            buf.seek(0)
            qr_cache[tag] = buf

        qr_size = min(qr_mm, cell_h - 4, cell_w - 30)
        pdf.image(qr_cache[tag], x=x + 2, y=y + (cell_h - qr_size) / 2, w=qr_size)

        text_x = x + qr_size + 4
        pdf.set_xy(text_x, y + 3)
        pdf.set_font('helvetica', 'B', font_mm + 1.2)
        pdf.cell(cell_w - qr_size - 6, 4, 'BPF IT ASSET', new_x=XPos.LMARGIN, new_y=YPos.NEXT)

        pdf.set_x(text_x)
        pdf.set_font('helvetica', 'B', font_mm + 0.8)
        pdf.cell(cell_w - qr_size - 6, 4, tag, new_x=XPos.LMARGIN, new_y=YPos.NEXT)

        pdf.set_x(text_x)
        pdf.set_font('helvetica', '', font_mm)
        name = ' '.join(filter(None, [asset.get('brand'), asset.get('model')])) or CATEGORY_LABEL.get(asset.get('category'), '')
        pdf.cell(cell_w - qr_size - 6, 3.6, name[:38], new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        if asset.get('location_room'):
            pdf.set_x(text_x)
            pdf.cell(cell_w - qr_size - 6, 3.4, str(asset['location_room'])[:40], new_x=XPos.LMARGIN, new_y=YPos.NEXT)

        pdf.set_xy(x + 2, y + cell_h - 4)
        pdf.set_font('helvetica', '', max(4.0, font_mm - 0.6))
        pdf.cell(cell_w - 4, 3, 'PT Bestprofit Futures', align='L')

    out = io.BytesIO()
    pdf.output(out)
    out.seek(0)
    return out


# ------------------------------------------------------------------ routes


# ------------------------------------------------------- agen inventaris
# Versi agen WAJIB sama dengan $AgentVersion di scripts/it_inventory_agent.ps1
# (dijaga oleh tests/test_it_agent_rollout.py).
AGENT_VERSION = '1.1.0'
AGENT_SCRIPT = 'it_inventory_agent.ps1'
AGENT_STALE_DAYS = int(os.environ.get('IT_AGENT_STALE_DAYS', '7') or 7)
_AGENT_STATUSES = ('pending', 'installed', 'failed', 'unreachable', 'ignored')


def _agent_script_path():
    return os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        'scripts', AGENT_SCRIPT,
    )


def _version_tuple(value):
    """'1.10.2' -> (1, 10, 2). Nilai aneh -> (0,) agar selalu 'lebih tua'."""
    parts = []
    for chunk in str(value or '').strip().lstrip('vV').split('.'):
        digits = re.match(r'\d+', chunk)
        parts.append(int(digits.group()) if digits else 0)
    return tuple(parts) or (0,)


def _agent_host_key(hostname, ip):
    """Kunci unik registry: hostname lebih stabil daripada IP (DHCP)."""
    host = str(hostname or '').strip().lower()
    if host:
        return host[:120]
    ipv = str(ip or '').strip().lower()
    return ('ip:' + ipv)[:120] if ipv else ''


def _normalize_agent_status(value):
    value = str(value or '').strip().lower()
    return value if value in _AGENT_STATUSES else 'installed'


def _target_display(row):
    return {
        'asset_tag': row.get('asset_tag') or '',
        'host': row.get('hostname') or row.get('ip') or row.get('ip_address') or '',
        'ip': row.get('ip') or row.get('ip_address') or '',
        'mac': row.get('mac') or row.get('mac_address') or '',
    }


def _host_flags(row, stale_days=AGENT_STALE_DAYS, now=None):
    """Tambahkan umur laporan, status basi, dan status versi agen."""
    now = now or datetime.now()
    last = row.get('last_report_at')
    days = None
    if isinstance(last, datetime):
        days = max(0, (now - last).days)
    elif isinstance(last, str) and last.strip():
        try:
            days = max(0, (now - datetime.strptime(last[:19], '%Y-%m-%d %H:%M:%S')).days)
        except ValueError:
            days = None
    installed = row.get('deploy_status') == 'installed'
    stale = bool(days is None or days > stale_days)
    return dict(row, days_since_report=days, is_stale=(installed and stale),
                outdated=(_version_tuple(row.get('agent_version')) < _version_tuple(AGENT_VERSION)))


def _targets_csv_response(rows, filename):
    """CSV target deployment (dipakai scripts/deploy_it_agent.ps1)."""
    buf = io.StringIO()
    writer = csv.writer(buf, delimiter=',')
    writer.writerow(['host', 'ip', 'mac', 'source', 'asset_tag', 'note'])
    for r in rows:
        writer.writerow([r.get('host'), r.get('ip'), r.get('mac'),
                         r.get('source'), r.get('asset_tag'), r.get('note')])
    resp = make_response(buf.getvalue())
    resp.headers['Content-Type'] = 'text/csv; charset=utf-8'
    resp.headers['Content-Disposition'] = f'attachment; filename={filename}'
    resp.headers['Cache-Control'] = 'no-store'
    return resp


def _coverage_payload(target_rows, host_rows, stale_days=AGENT_STALE_DAYS, now=None):
    """Hitung cakupan agen. Murni (tanpa DB) supaya mudah diuji.

    `target_rows`: aset kategori pc/laptop (hostname/ip_address/mac_address).
    `host_rows`  : isi it_agent_hosts.
    Sebuah target dianggap TERCakup bila ada host berstatus installed, laporannya
    belum basi, dan hostname/IP/MAC-nya cocok.
    """
    now = now or datetime.now()
    hosts = []
    covered = set()
    for h in host_rows:
        flags = _host_flags(h, stale_days, now)
        hosts.append(flags)
        if flags['deploy_status'] == 'installed' and not flags['is_stale']:
            for k in (h.get('host_key'), h.get('hostname'), h.get('ip'), h.get('mac')):
                k = str(k or '').strip().lower()
                if k:
                    covered.add(k)

    missing = []
    covered_targets = 0
    for t in target_rows:
        keys = {str(t.get(k) or '').strip().lower()
                for k in ('hostname', 'ip_address', 'mac_address')}
        keys.discard('')
        if keys & covered:
            covered_targets += 1
        else:
            missing.append(t)

    targets = len(target_rows)
    return {
        'targets': targets,
        'covered': covered_targets,
        'missing': len(missing),
        'percent': round(covered_targets * 100.0 / targets, 1) if targets else 0.0,
        'stale_days': stale_days,
        'hosts_total': len(hosts),
        'hosts_installed': sum(1 for h in hosts if h['deploy_status'] == 'installed'),
        'hosts_stale': sum(1 for h in hosts if h['is_stale']),
        'hosts_failed': sum(1 for h in hosts if h['deploy_status'] in ('failed', 'unreachable')),
        'hosts_outdated': sum(1 for h in hosts if h['outdated']),
        'agent_version': AGENT_VERSION,
        'missing_hosts': [_target_display(t) for t in missing][:50],
        'hosts': hosts,
    }


def _targets_rows(candidates, assets, covered_keys):
    """Daftar target siap-pakai untuk scripts/deploy_it_agent.ps1 (CSV)."""
    covered = {str(k or '').strip().lower() for k in covered_keys if str(k or '').strip()}
    rows, seen = [], set()

    def add(host, ip, mac, source, note='', asset_tag=''):
        keys = {str(v or '').strip().lower() for v in (host, ip, mac)}
        keys.discard('')
        if not keys or (keys & covered):
            return
        key = next(iter(sorted(keys)))
        if key in seen:
            return
        seen.add(key)
        rows.append({'host': host or ip, 'ip': ip, 'mac': mac,
                     'source': source, 'asset_tag': asset_tag, 'note': note[:120]})

    for c in candidates:
        add(c.get('hostname') or '', c.get('ip') or '', c.get('mac') or '',
            'discovery',
            ' '.join(filter(None, [c.get('vendor'), c.get('category_suggest'),
                                   'port ' + str(c.get('open_ports')) if c.get('open_ports') else ''])),
            '')
    for a in assets:
        add(a.get('hostname') or '', a.get('ip_address') or '', a.get('mac_address') or '',
            'inventaris',
            ' '.join(filter(None, [a.get('brand'), a.get('model')])),
            a.get('asset_tag') or '')
    return rows


def register_it_asset_routes(app):

    # ---------------------------------------------------------- master data
    @app.route('/api/it/meta')
    @role_required(ALLOWED)
    def api_it_meta():
        return jsonify({
            'categories': [{'code': c, 'label': l, 'icon': i} for c, l, i in IT_CATEGORIES],
            'statuses': IT_STATUSES,
            'conditions': IT_CONDITIONS,
            'branch': _branch(),
        })

    # --------------------------------------------------------------- ringkasan
    @app.route('/api/it/summary')
    @role_required(ALLOWED)
    def api_it_summary():
        try:
            branch = _branch()
            conn = get_db_connection()
            if not conn:
                return jsonify({'error': 'DB error'}), 500
            cur = conn.cursor(dictionary=True)
            cur.execute("SELECT COUNT(*) c FROM it_assets WHERE branch_code=%s AND status<>'disposed'", (branch,))
            total = cur.fetchone()['c']
            cur.execute("SELECT status, COUNT(*) c FROM it_assets WHERE branch_code=%s GROUP BY status", (branch,))
            by_status = {r['status']: r['c'] for r in cur.fetchall()}
            cur.execute("SELECT category, COUNT(*) c FROM it_assets WHERE branch_code=%s "
                        "AND status<>'disposed' GROUP BY category", (branch,))
            by_category = {r['category']: r['c'] for r in cur.fetchall()}
            cur.execute("SELECT COUNT(*) c FROM it_assets WHERE branch_code=%s "
                        "AND label_printed_at IS NULL AND status<>'disposed'", (branch,))
            unlabeled = cur.fetchone()['c']
            cur.execute("SELECT COUNT(*) c FROM it_assets WHERE branch_code=%s "
                        "AND warranty_until IS NOT NULL AND warranty_until BETWEEN CURDATE() "
                        "AND DATE_ADD(CURDATE(), INTERVAL 30 DAY)", (branch,))
            warranty_soon = cur.fetchone()['c']
            cur.execute("SELECT COUNT(*) c FROM it_discovered_devices "
                        "WHERE branch_code=%s AND state='new'", (branch,))
            candidates = cur.fetchone()['c']
            cur.execute("SELECT COUNT(*) c FROM it_assets WHERE branch_code=%s "
                        "AND cond='rusak_berat' AND status<>'disposed'", (branch,))
            broken = cur.fetchone()['c']
            cur.execute(
                "SELECT e.kind, e.note, e.created_at, e.actor, a.asset_tag, a.category "
                "FROM it_asset_events e JOIN it_assets a ON a.id=e.asset_id "
                "WHERE a.branch_code=%s ORDER BY e.created_at DESC LIMIT 8", (branch,))
            recent = [_serialize(r) for r in cur.fetchall()]
            cur.close(); conn.close()
            return jsonify({
                'total': total, 'by_status': by_status, 'by_category': by_category,
                'unlabeled': unlabeled, 'warranty_soon': warranty_soon,
                'candidates': candidates, 'broken': broken, 'recent': recent,
            })
        except Exception as e:
            return jsonify({'error': str(e)}), 500

    # ---------------------------------------------------------------- daftar
    @app.route('/api/it/assets')
    @role_required(ALLOWED)
    def api_it_asset_list():
        try:
            branch = _branch()
            q = str(request.args.get('q', '') or '').strip()
            category = str(request.args.get('category', '') or '').strip()
            status = str(request.args.get('status', '') or '').strip()
            cond = str(request.args.get('cond', '') or '').strip()
            room = str(request.args.get('room', '') or '').strip()
            page = max(1, int(request.args.get('page', 1) or 1))
            per_page = min(200, max(5, int(request.args.get('per_page', 50) or 50)))

            where = ["branch_code=%s"]
            params = [branch]
            if q:
                where.append("(asset_tag LIKE %s OR brand LIKE %s OR model LIKE %s "
                             "OR serial_number LIKE %s OR hostname LIKE %s OR assigned_to LIKE %s)")
                params += [_like(q)] * 6
            if category:
                where.append("category=%s"); params.append(category)
            if status:
                where.append("status=%s"); params.append(status)
            if cond:
                where.append("cond=%s"); params.append(cond)
            if room:
                where.append("location_room LIKE %s"); params.append(_like(room))
            clause = " AND ".join(where)

            conn = get_db_connection()
            if not conn:
                return jsonify({'error': 'DB error'}), 500
            cur = conn.cursor(dictionary=True)
            cur.execute(f"SELECT COUNT(*) c FROM it_assets WHERE {clause}", params)
            total = cur.fetchone()['c']
            cur.execute(
                f"SELECT * FROM it_assets WHERE {clause} ORDER BY asset_tag LIMIT %s OFFSET %s",
                params + [per_page, (page - 1) * per_page])
            rows = [_serialize(r) for r in cur.fetchall()]
            cur.close(); conn.close()
            return jsonify({'data': rows, 'total': total, 'page': page, 'per_page': per_page})
        except Exception as e:
            return jsonify({'error': str(e)}), 500

    # ------------------------------------------------------------ tambah aset
    @app.route('/api/it/assets', methods=['POST'])
    @role_required(ALLOWED)
    def api_it_asset_create():
        try:
            data = request.get_json(silent=True) or {}
            fields = _clean_fields(data)
            branch = _branch()
            actor = _user()

            conn = get_db_connection()
            if not conn:
                return jsonify({'error': 'DB error'}), 500
            cur = conn.cursor(dictionary=True)
            tag = str(data.get('asset_tag') or '').strip().upper()
            if not tag:
                last_error = None
                for _ in range(5):
                    tag = _next_tag(cur, branch, fields['category'])
                    try:
                        _insert_asset(cur, branch, tag, fields, 'manual', None, actor)
                        conn.commit()
                        last_error = None
                        break
                    except Exception as e:
                        conn.rollback()
                        last_error = e
                        if 'Duplicate' not in str(e):
                            raise
                if last_error:
                    raise last_error
            else:
                _insert_asset(cur, branch, tag, fields, 'manual', None, actor)
                conn.commit()

            cur.execute("SELECT * FROM it_assets WHERE asset_tag=%s AND branch_code=%s", (tag, branch))
            asset = _serialize(cur.fetchone())
            cur.close(); conn.close()
            log_activity_async(0, 'it_asset_create', 'it', _full_name(),
                               new_data={'asset_tag': tag, 'category': fields['category']},
                               ip=request.remote_addr)
            return jsonify({'status': 'success', 'msg': f'Aset {tag} ditambahkan', 'data': asset}), 201
        except ValueError as e:
            return jsonify({'status': 'error', 'msg': str(e)}), 400
        except Exception as e:
            return jsonify({'status': 'error', 'msg': str(e)}), 500

    def _insert_asset(cur, branch, tag, fields, source, discovery_id, actor):
        cols = ['asset_tag', 'branch_code', 'source', 'discovery_id', 'created_by']
        vals = [tag, branch, source, discovery_id, actor]
        for key, value in fields.items():
            cols.append(key); vals.append(value)
        placeholders = ','.join(['%s'] * len(cols))
        cur.execute(f"INSERT INTO it_assets ({','.join(cols)}) VALUES ({placeholders})", vals)
        cur.execute("SELECT LAST_INSERT_ID() AS id")
        asset_id = cur.fetchone()['id']
        _event(cur, asset_id, branch, 'created', None, fields, note='Aset dibuat', actor=actor)
        return asset_id

    # ------------------------------------------------------------- detail aset
    @app.route('/api/it/assets/<tag>')
    @role_required(ALLOWED)
    def api_it_asset_detail(tag):
        try:
            branch = _branch()
            conn = get_db_connection()
            if not conn:
                return jsonify({'error': 'DB error'}), 500
            cur = conn.cursor(dictionary=True)
            asset = _get_asset(cur, tag, branch)
            if not asset:
                cur.close(); conn.close()
                return jsonify({'error': 'Aset tidak ditemukan'}), 404
            cur.execute(
                "SELECT * FROM it_asset_events WHERE asset_id=%s ORDER BY created_at DESC, id DESC LIMIT 200",
                (asset['id'],))
            events = [_serialize(r) for r in cur.fetchall()]
            cur.close(); conn.close()
            data = _serialize(asset)
            data['events'] = events
            data['label_url'] = f"/app/it/assets/{asset['asset_tag']}"
            return jsonify({'data': data})
        except Exception as e:
            return jsonify({'error': str(e)}), 500

    # -------------------------------------------------------------- ubah aset
    @app.route('/api/it/assets/<tag>', methods=['PATCH'])
    @role_required(ALLOWED)
    def api_it_asset_update(tag):
        try:
            data = request.get_json(silent=True) or {}
            fields = _clean_fields(data, partial=True)
            if not fields:
                return jsonify({'status': 'error', 'msg': 'Tidak ada data yang diubah'}), 400
            branch = _branch()
            conn = get_db_connection()
            if not conn:
                return jsonify({'error': 'DB error'}), 500
            cur = conn.cursor(dictionary=True)
            asset = _get_asset(cur, tag, branch)
            if not asset:
                cur.close(); conn.close()
                return jsonify({'status': 'error', 'msg': 'Aset tidak ditemukan'}), 404
            before = {k: _jsonable(asset.get(k)) for k in fields}
            sets = ', '.join(f"{k}=%s" for k in fields)
            cur.execute(f"UPDATE it_assets SET {sets} WHERE id=%s",
                        list(fields.values()) + [asset['id']])
            kind = 'updated'
            if 'cond' in fields and str(asset.get('cond')) != str(fields['cond']):
                kind = 'condition'
            if 'status' in fields and str(asset.get('status')) != str(fields['status']):
                kind = 'status'
            _event(cur, asset['id'], branch, kind, before, fields,
                   note=str(data.get('note') or ''), actor=_user())
            conn.commit()
            cur.execute("SELECT * FROM it_assets WHERE id=%s", (asset['id'],))
            updated = _serialize(cur.fetchone())
            cur.close(); conn.close()
            log_activity_async(0, f'it_asset_{kind}', 'it', _full_name(),
                               old_data=before, new_data=fields, ip=request.remote_addr)
            return jsonify({'status': 'success', 'msg': 'Perubahan disimpan', 'data': updated})
        except ValueError as e:
            return jsonify({'status': 'error', 'msg': str(e)}), 400
        except Exception as e:
            return jsonify({'status': 'error', 'msg': str(e)}), 500

    # ---------------------------------------------------------- ubah kondisi
    @app.route('/api/it/assets/<tag>/condition', methods=['POST'])
    @role_required(ALLOWED)
    def api_it_asset_condition(tag):
        """Update kondisi cepat (dipakai halaman scan). Menerima JSON atau form."""
        try:
            branch = _branch()
            form = request.form
            data = request.get_json(silent=True) or (form.to_dict() if form else {})
            cond = str(data.get('cond') or '').strip()
            if cond not in IT_CONDITIONS:
                return jsonify({'status': 'error', 'msg': 'Kondisi tidak dikenal'}), 400
            new_status = str(data.get('status') or '').strip()
            if new_status and new_status not in IT_STATUSES:
                return jsonify({'status': 'error', 'msg': 'Status tidak dikenal'}), 400

            photo = ''
            uploaded = request.files.get('photo') if request.files else None
            if uploaded:
                photo = save_file(uploaded, 'IT_ASSET', tag, app.config['UPLOAD_FOLDER']) or ''

            conn = get_db_connection()
            if not conn:
                return jsonify({'error': 'DB error'}), 500
            cur = conn.cursor(dictionary=True)
            asset = _get_asset(cur, tag, branch)
            if not asset:
                cur.close(); conn.close()
                return jsonify({'status': 'error', 'msg': 'Aset tidak ditemukan'}), 404

            before = {'cond': asset.get('cond'), 'status': asset.get('status')}
            after = {'cond': cond}
            cur.execute("UPDATE it_assets SET cond=%s WHERE id=%s", (cond, asset['id']))
            if new_status:
                after['status'] = new_status
                cur.execute("UPDATE it_assets SET status=%s WHERE id=%s", (new_status, asset['id']))
            _event(cur, asset['id'], branch, 'condition', before, after,
                   note=str(data.get('note') or ''), photo=photo, actor=_user())
            conn.commit()
            cur.execute("SELECT * FROM it_assets WHERE id=%s", (asset['id'],))
            updated = _serialize(cur.fetchone())
            cur.close(); conn.close()
            log_activity_async(0, 'it_asset_condition', 'it', _full_name(),
                               old_data=before, new_data=after, ip=request.remote_addr)
            return jsonify({'status': 'success', 'msg': 'Kondisi diperbarui', 'data': updated})
        except Exception as e:
            return jsonify({'status': 'error', 'msg': str(e)}), 500

    # ------------------------------------------------------ catatan/riwayat
    @app.route('/api/it/assets/<tag>/events', methods=['POST'])
    @role_required(ALLOWED)
    def api_it_asset_add_event(tag):
        try:
            branch = _branch()
            data = request.get_json(silent=True) or {}
            kind = str(data.get('kind') or 'note').strip().lower()
            if kind not in ('note', 'repair', 'service', 'assign', 'transfer', 'scan', 'label'):
                return jsonify({'status': 'error', 'msg': 'Jenis catatan tidak dikenal'}), 400
            note = str(data.get('note') or '').strip()
            if not note:
                return jsonify({'status': 'error', 'msg': 'Catatan wajib diisi'}), 400
            conn = get_db_connection()
            if not conn:
                return jsonify({'error': 'DB error'}), 500
            cur = conn.cursor(dictionary=True)
            asset = _get_asset(cur, tag, branch)
            if not asset:
                cur.close(); conn.close()
                return jsonify({'status': 'error', 'msg': 'Aset tidak ditemukan'}), 404
            _event(cur, asset['id'], branch, kind, None, None, note=note, actor=_user())
            conn.commit()
            cur.close(); conn.close()
            log_activity_async(0, f'it_asset_{kind}', 'it', _full_name(),
                               new_data={'asset_tag': tag, 'note': note}, ip=request.remote_addr)
            return jsonify({'status': 'success', 'msg': 'Catatan ditambahkan'})
        except Exception as e:
            return jsonify({'status': 'error', 'msg': str(e)}), 500

    # ------------------------------------------------------------- label PDF
    @app.route('/api/it/assets/labels.pdf', methods=['POST'])
    @role_required(ALLOWED)
    def api_it_labels_pdf():
        try:
            data = request.get_json(silent=True) or {}
            tags = data.get('tags') or []
            layout = str(data.get('layout') or 'a4-24')
            branch = _branch()
            conn = get_db_connection()
            if not conn:
                return jsonify({'error': 'DB error'}), 500
            cur = conn.cursor(dictionary=True)
            if tags:
                placeholders = ','.join(['%s'] * len(tags))
                cur.execute(f"SELECT * FROM it_assets WHERE branch_code=%s AND asset_tag IN ({placeholders}) "
                            "ORDER BY asset_tag", [branch] + list(tags))
            else:
                cur.execute("SELECT * FROM it_assets WHERE branch_code=%s AND label_printed_at IS NULL "
                            "AND status<>'disposed' ORDER BY asset_tag LIMIT 120", (branch,))
            assets = [_serialize(r) for r in cur.fetchall()]
            if not assets:
                cur.close(); conn.close()
                return jsonify({'status': 'error', 'msg': 'Tidak ada aset untuk dicetak'}), 400
            base = os.environ.get('IT_ASSET_PUBLIC_BASE', '').strip() or request.host_url.rstrip('/')
            pdf = _label_pdf(assets, layout, base)
            ids = [a['id'] for a in assets]
            placeholders = ','.join(['%s'] * len(ids))
            cur.execute(f"UPDATE it_assets SET label_printed_at=NOW() WHERE id IN ({placeholders})", ids)
            for a in assets:
                _event(cur, a['id'], branch, 'label', None, None,
                       note=f'Label dicetak ({layout})', actor=_user())
            conn.commit()
            cur.close(); conn.close()
            log_activity_async(0, 'it_label_print', 'it', _full_name(),
                               new_data={'count': len(assets), 'layout': layout},
                               ip=request.remote_addr)
            resp = make_response(pdf.getvalue())
            resp.headers['Content-Type'] = 'application/pdf'
            resp.headers['Content-Disposition'] = (
                f"attachment; filename=label_aset_{branch}_{datetime.now():%Y%m%d_%H%M}.pdf")
            return resp
        except Exception as e:
            return jsonify({'status': 'error', 'msg': str(e)}), 500

    @app.route('/api/it/assets/<tag>/label.pdf')
    @role_required(ALLOWED)
    def api_it_label_single(tag):
        try:
            branch = _branch()
            conn = get_db_connection()
            if not conn:
                return jsonify({'error': 'DB error'}), 500
            cur = conn.cursor(dictionary=True)
            asset = _get_asset(cur, tag, branch)
            if not asset:
                cur.close(); conn.close()
                return jsonify({'status': 'error', 'msg': 'Aset tidak ditemukan'}), 404
            base = os.environ.get('IT_ASSET_PUBLIC_BASE', '').strip() or request.host_url.rstrip('/')
            pdf = _label_pdf([_serialize(asset)], 'a4-24', base)
            cur.execute("UPDATE it_assets SET label_printed_at=NOW() WHERE id=%s", (asset['id'],))
            _event(cur, asset['id'], branch, 'label', None, None, note='Label tunggal dicetak', actor=_user())
            conn.commit()
            cur.close(); conn.close()
            resp = make_response(pdf.getvalue())
            resp.headers['Content-Type'] = 'application/pdf'
            resp.headers['Content-Disposition'] = f'attachment; filename=label_{tag}.pdf'
            return resp
        except Exception as e:
            return jsonify({'status': 'error', 'msg': str(e)}), 500

    # -------------------------------------------------------------- lookup QR
    @app.route('/api/it/assets/lookup')
    @role_required(ALLOWED)
    def api_it_asset_lookup():
        tag = str(request.args.get('tag', '') or '').strip().upper()
        if not tag:
            return jsonify({'status': 'error', 'msg': 'Tag kosong'}), 400
        conn = get_db_connection()
        if not conn:
            return jsonify({'error': 'DB error'}), 500
        cur = conn.cursor(dictionary=True)
        asset = _get_asset(cur, tag, _branch())
        cur.close(); conn.close()
        if not asset:
            return jsonify({'status': 'error', 'msg': f'Tag {tag} tidak terdaftar di cabang ini'}), 404
        return jsonify({'data': _serialize(asset)})

    # ----------------------------------------------------------------- ekspor
    @app.route('/api/it/assets/export.csv')
    @role_required(ALLOWED)
    def api_it_export():
        try:
            branch = _branch()
            conn = get_db_connection()
            if not conn:
                return jsonify({'error': 'DB error'}), 500
            cur = conn.cursor(dictionary=True)
            cur.execute("SELECT * FROM it_assets WHERE branch_code=%s ORDER BY asset_tag", (branch,))
            rows = [_serialize(r) for r in cur.fetchall()]
            cur.close(); conn.close()
            log_activity_async(0, 'it_export_csv', 'it', _full_name(),
                               new_data={'count': len(rows)}, ip=request.remote_addr)
            return _csv_response(rows, f"inventaris_it_{branch}_{datetime.now():%Y%m%d}.csv")
        except Exception as e:
            return jsonify({'error': str(e)}), 500

    # ---------------------------------------------------------------- impor
    @app.route('/api/it/assets/import', methods=['POST'])
    @role_required(ALLOWED)
    def api_it_import():
        """Impor CSV/XLSX. Default dry-run; `?commit=1` menulis."""
        try:
            upload = request.files.get('file')
            if not upload or not upload.filename:
                return jsonify({'status': 'error', 'msg': 'File wajib diunggah'}), 400
            name = upload.filename.lower()
            rows = []
            if name.endswith('.csv'):
                raw = upload.read().decode('utf-8-sig', errors='replace')
                delimiter = ';' if raw.count(';') > raw.count(',') else ','
                rows = list(csv.DictReader(io.StringIO(raw), delimiter=delimiter))
            elif name.endswith(('.xlsx', '.xlsm')):
                from openpyxl import load_workbook
                wb = load_workbook(io.BytesIO(upload.read()), read_only=True, data_only=True)
                ws = wb.active
                headers = [str(c.value or '').strip().lower() for c in next(ws.iter_rows(max_row=1))]
                for values in ws.iter_rows(min_row=2, values_only=True):
                    rows.append({headers[i]: values[i] for i in range(min(len(headers), len(values)))})
            else:
                return jsonify({'status': 'error', 'msg': 'Format harus CSV atau XLSX'}), 400

            result = _validate_import_rows(rows)
            commit = str(request.args.get('commit', '') or '') in ('1', 'true', 'yes')
            if not commit:
                return jsonify({'status': 'success', 'dry_run': True, **result})

            created, errors = _commit_import_rows(result['valid'], _branch(), _user())
            log_activity_async(0, 'it_import', 'it', _full_name(),
                               new_data={'created': created, 'errors': len(errors)},
                               ip=request.remote_addr)
            return jsonify({'status': 'success', 'dry_run': False, 'created': created,
                            'errors': result['errors'] + errors})
        except Exception as e:
            return jsonify({'status': 'error', 'msg': str(e)}), 500

    # -------------------------------------------------------------- discovery
    @app.route('/api/it/discovery/candidates')
    @role_required(ALLOWED)
    def api_it_candidates():
        try:
            branch = _branch()
            state = str(request.args.get('state', 'new') or 'new')
            where = ["branch_code=%s"]
            params = [branch]
            if state != 'all':
                where.append("state=%s"); params.append(state)
            conn = get_db_connection()
            if not conn:
                return jsonify({'error': 'DB error'}), 500
            cur = conn.cursor(dictionary=True)
            cur.execute("SELECT * FROM it_discovered_devices WHERE " + " AND ".join(where) +
                        " ORDER BY confidence DESC, last_seen DESC LIMIT 500", params)
            rows = [_serialize(r) for r in cur.fetchall()]
            cur.close(); conn.close()
            return jsonify({'data': rows, 'total': len(rows)})
        except Exception as e:
            return jsonify({'error': str(e)}), 500

    @app.route('/api/it/discovery/runs')
    @role_required(ALLOWED)
    def api_it_runs():
        conn = get_db_connection()
        if not conn:
            return jsonify({'error': 'DB error'}), 500
        cur = conn.cursor(dictionary=True)
        cur.execute("SELECT * FROM it_discovery_runs WHERE branch_code=%s "
                    "ORDER BY id DESC LIMIT 30", (_branch(),))
        rows = [_serialize(r) for r in cur.fetchall()]
        cur.close(); conn.close()
        return jsonify({'data': rows})

    @app.route('/api/it/discovery/scan', methods=['POST'])
    @role_required(ALLOWED)
    def api_it_scan():
        """Mulai sapuan TCP dari server (tanpa MAC; agen host menambah ARP)."""
        if not _SCAN_LOCK.acquire(blocking=False):
            return jsonify({'status': 'error', 'msg': 'Sapuan lain sedang berjalan'}), 409
        try:
            data = request.get_json(silent=True) or {}
            subnets = data.get('subnets') or os.environ.get(
                'IT_DISCOVERY_SUBNETS', '192.168.2.0/23').split(',')
            subnets = [s.strip() for s in subnets if str(s).strip()]
            branch = _branch()
            conn = get_db_connection()
            cur = conn.cursor()
            cur.execute("INSERT INTO it_discovery_runs (branch_code, method, subnet, started_at, status, actor) "
                        "VALUES (%s,'sweep',%s,NOW(),'running',%s)",
                        (branch, ','.join(subnets), _user()))
            run_id = cur.lastrowid
            conn.commit(); cur.close(); conn.close()
            threading.Thread(target=_run_sweep, args=(branch, subnets, run_id, _user()),
                             daemon=True).start()
            log_activity_async(0, 'it_discovery_scan', 'it', _full_name(),
                               new_data={'subnets': subnets}, ip=request.remote_addr)
            return jsonify({'status': 'success', 'run_id': run_id,
                            'msg': f'Sapuan dimulai untuk {", ".join(subnets)}'}), 202
        except Exception as e:
            _SCAN_LOCK.release()
            return jsonify({'status': 'error', 'msg': str(e)}), 500

    @app.route('/api/it/discovery/candidates/<int:cid>/adopt', methods=['POST'])
    @role_required(ALLOWED)
    def api_it_adopt(cid):
        try:
            branch = _branch()
            data = request.get_json(silent=True) or {}
            conn = get_db_connection()
            if not conn:
                return jsonify({'error': 'DB error'}), 500
            cur = conn.cursor(dictionary=True)
            cur.execute("SELECT * FROM it_discovered_devices WHERE id=%s AND branch_code=%s", (cid, branch))
            dev = cur.fetchone()
            if not dev:
                cur.close(); conn.close()
                return jsonify({'status': 'error', 'msg': 'Kandidat tidak ditemukan'}), 404
            if dev['state'] == 'adopted' and dev.get('asset_id'):
                cur.close(); conn.close()
                return jsonify({'status': 'error', 'msg': 'Kandidat sudah menjadi aset'}), 409

            category = str(data.get('category') or dev.get('category_suggest') or 'other').lower()
            if category not in IT_CATEGORY_CODES:
                category = 'other'
            specs = _loads(dev.get('specs'), None) or {}
            specs = specs if isinstance(specs, dict) else {}
            fields = {
                'category': category,
                'brand': str(data.get('brand') or dev.get('vendor') or '').strip(),
                'model': str(data.get('model') or specs.get('model') or '').strip(),
                'serial_number': str(data.get('serial_number') or specs.get('serial_number') or '').strip(),
                'status': 'aktif',
                'cond': 'baik',
                'location_room': str(data.get('location_room') or '').strip(),
                'location_detail': str(data.get('location_detail') or '').strip(),
                'assigned_to': str(data.get('assigned_to') or '').strip(),
                'hostname': (dev.get('hostname') or '')[:80],
                'ip_address': dev.get('ip') or '',
                'mac_address': dev.get('mac') or '',
                'os_name': str(data.get('os_name') or '').strip(),
                'specs': _loads(dev.get('specs'), None),
                'notes': f"Terdeteksi otomatis {dev.get('last_seen') or ''}".strip(),
            }
            fields_json = {k: (json.dumps(v, ensure_ascii=False) if k == 'specs' and v else v)
                           for k, v in fields.items()}
            fields_json = {k: v for k, v in fields_json.items() if v not in (None, '')}
            tag = _next_tag(cur, branch, category)
            asset_id = _insert_asset(cur, branch, tag, fields_json, 'discovery', cid, _user())
            cur.execute("UPDATE it_assets SET last_seen_at=NOW() WHERE id=%s", (asset_id,))
            cur.execute("UPDATE it_discovered_devices SET state='adopted', asset_id=%s WHERE id=%s",
                        (asset_id, cid))
            conn.commit()
            cur.execute("SELECT * FROM it_assets WHERE id=%s", (asset_id,))
            asset = _serialize(cur.fetchone())
            cur.close(); conn.close()
            log_activity_async(0, 'it_discovery_adopt', 'it', _full_name(),
                               new_data={'asset_tag': tag, 'ip': dev.get('ip')},
                               ip=request.remote_addr)
            return jsonify({'status': 'success', 'msg': f'{tag} dibuat dari perangkat jaringan',
                            'data': asset}), 201
        except Exception as e:
            return jsonify({'status': 'error', 'msg': str(e)}), 500

    @app.route('/api/it/discovery/candidates/<int:cid>/ignore', methods=['POST'])
    @role_required(ALLOWED)
    def api_it_ignore(cid):
        try:
            data = request.get_json(silent=True) or {}
            conn = get_db_connection()
            if not conn:
                return jsonify({'error': 'DB error'}), 500
            cur = conn.cursor()
            cur.execute("UPDATE it_discovered_devices SET state='ignored', note=%s "
                        "WHERE id=%s AND branch_code=%s",
                        (str(data.get('note') or 'Diabaikan IT')[:300], cid, _branch()))
            conn.commit(); cur.close(); conn.close()
            return jsonify({'status': 'success', 'msg': 'Kandidat diabaikan'})
        except Exception as e:
            return jsonify({'status': 'error', 'msg': str(e)}), 500

    # ------------------------------------------------ push dari agen host
    @app.route('/api/it/discovery/agent', methods=['POST'])
    def api_it_discovery_agent():
        """Endpoint mesin (host agent): token, bukan sesi.

        Header: X-IT-TOKEN = env IT_DISCOVERY_TOKEN.
        Body: {branch_code, method, subnet, devices:[{ip,mac,hostname,ports,vendor,ad_os,specs}]}
        """
        expected = os.environ.get('IT_DISCOVERY_TOKEN', '').strip()
        provided = str(request.headers.get('X-IT-TOKEN', '') or '').strip()
        if not expected or not hmac.compare_digest(expected, provided):
            return jsonify({'status': 'error', 'msg': 'Token tidak valid'}), 401
        try:
            data = request.get_json(silent=True) or {}
            branch = str(data.get('branch_code') or 'SBY').strip().upper()
            devices = data.get('devices') or []
            if not isinstance(devices, list):
                return jsonify({'status': 'error', 'msg': 'devices harus list'}), 400
            conn = get_db_connection(branch_code=branch)
            if not conn:
                return jsonify({'status': 'error', 'msg': 'DB tidak tersedia'}), 500
            cur = conn.cursor()
            cur.execute("INSERT INTO it_discovery_runs (branch_code, method, subnet, started_at, status, actor) "
                        "VALUES (%s,%s,%s,NOW(),'running','agent')",
                        (branch, str(data.get('method') or 'agent')[:30],
                         ','.join(data.get('subnets') or [])[:80]))
            run_id = cur.lastrowid
            conn.commit(); cur.close()
            new = 0
            for dev in devices[:2000]:
                if not isinstance(dev, dict):
                    continue
                try:
                    if _upsert_device(conn, branch, run_id, dev):
                        new += 1
                except Exception as e:
                    print(f'[it-discovery] device gagal: {e}')
            cur = conn.cursor()
            cur.execute("UPDATE it_discovery_runs SET finished_at=NOW(), found=%s, new_count=%s, "
                        "status='ok' WHERE id=%s", (len(devices), new, run_id))
            conn.commit(); cur.close(); conn.close()
            return jsonify({'status': 'success', 'run_id': run_id,
                            'found': len(devices), 'new': new})
        except Exception as e:
            return jsonify({'status': 'error', 'msg': str(e)}), 500

    # ------------------------------------------------------- agen: registry
    def _agent_token_ok():
        expected = os.environ.get('IT_DISCOVERY_TOKEN', '').strip()
        provided = str(request.headers.get('X-IT-TOKEN', '') or '').strip()
        return bool(expected) and hmac.compare_digest(expected, provided)

    def _agent_session_ok():
        return bool(session.get('user_role')) and session.get('user_role') in ALLOWED

    @app.route('/api/it/agents/report', methods=['POST'])
    def api_it_agents_report():
        """Laporan agen/deployer (token) atau IT (sesi).

        Body tunggal {hostname, ip, status, agent_version, ...} atau
        {branch_code, hosts:[...]} untuk hasil push massal.
        """
        token_ok = _agent_token_ok()
        sess_ok = _agent_session_ok()
        if not (token_ok or sess_ok):
            return jsonify({'status': 'error', 'msg': 'Token tidak valid'}), 401
        data = request.get_json(silent=True) or {}
        items = data.get('hosts') if isinstance(data.get('hosts'), list) else [data]
        default_branch = (_branch() if sess_ok
                          else str(data.get('branch_code') or 'SBY').strip().upper())
        actor = _user() if sess_ok else 'agent'
        conns, results = {}, []
        try:
            for item in items[:500]:
                if not isinstance(item, dict):
                    continue
                branch = str(item.get('branch_code') or default_branch or 'SBY').strip().upper()[:10]
                hostname = str(item.get('hostname') or '').strip()[:120]
                ip = str(item.get('ip') or '').strip()[:45]
                mac = normalize_mac(item.get('mac')) or ''
                key = _agent_host_key(hostname, ip)
                if not key:
                    results.append({'host': '', 'status': 'error', 'msg': 'hostname/ip kosong'})
                    continue
                status = _normalize_agent_status(item.get('status') or item.get('deploy_status'))
                version = str(item.get('agent_version') or item.get('version') or '')[:20]
                method = str(item.get('install_method') or item.get('method') or '')[:30]
                os_name = str(item.get('os_name') or item.get('ad_os') or '')[:120]
                message = str(item.get('message') or item.get('deploy_message') or '')[:300]
                if branch not in conns:
                    conns[branch] = get_db_connection(branch_code=branch)
                conn = conns[branch]
                if not conn:
                    results.append({'host': key, 'status': 'error', 'msg': 'DB tidak tersedia'})
                    continue
                cur = conn.cursor(dictionary=True)
                asset_tag = str(item.get('asset_tag') or '').strip()[:40]
                if not asset_tag and (hostname or mac):
                    cur.execute(
                        "SELECT asset_tag FROM it_assets WHERE branch_code=%s AND "
                        "(LOWER(hostname)=LOWER(%s) OR (mac_address<>'' AND mac_address=%s)) "
                        "ORDER BY id LIMIT 1", (branch, hostname, mac))
                    asset_tag = ((cur.fetchone() or {}).get('asset_tag') or '')[:40]
                cur.execute(
                    "INSERT INTO it_agent_hosts (branch_code, host_key, hostname, ip, mac, os_name, "
                    "agent_version, install_method, deploy_status, deploy_message, asset_tag, "
                    "first_installed_at, last_report_at, last_deploy_at, deployed_by) "
                    "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,"
                    "IF(%s='installed', NOW(), NULL), IF(%s='installed', NOW(), NULL), NOW(), %s) "
                    "ON DUPLICATE KEY UPDATE ip=VALUES(ip), "
                    "hostname=IF(VALUES(hostname)='', hostname, VALUES(hostname)), "
                    "mac=IF(VALUES(mac)='', mac, VALUES(mac)), "
                    "os_name=IF(VALUES(os_name)='', os_name, VALUES(os_name)), "
                    "agent_version=IF(VALUES(agent_version)='', agent_version, VALUES(agent_version)), "
                    "install_method=IF(VALUES(install_method)='', install_method, VALUES(install_method)), "
                    "deploy_status=VALUES(deploy_status), deploy_message=VALUES(deploy_message), "
                    "asset_tag=IF(VALUES(asset_tag)='', asset_tag, VALUES(asset_tag)), "
                    "first_installed_at=IF(first_installed_at IS NULL AND VALUES(deploy_status)='installed', "
                    "NOW(), first_installed_at), "
                    "last_report_at=IF(VALUES(deploy_status)='installed', NOW(), last_report_at), "
                    "last_deploy_at=NOW(), deployed_by=VALUES(deployed_by)",
                    (branch, key, hostname, ip, mac, os_name, version, method, status, message,
                     asset_tag, status, status, actor))
                if status == 'installed' and asset_tag:
                    cur.execute(
                        "UPDATE it_assets SET last_seen_at=NOW(), "
                        "ip_address=IF(%s<>'', %s, ip_address), "
                        "mac_address=IF(%s<>'', %s, mac_address), "
                        "os_name=IF(%s<>'', %s, os_name) "
                        "WHERE branch_code=%s AND asset_tag=%s",
                        (ip, ip, mac, mac, os_name, os_name, branch, asset_tag))
                conn.commit()
                cur.close()
                results.append({'host': key, 'hostname': hostname, 'status': status,
                                'asset_tag': asset_tag})
            log_activity_async(0, 'it_agent_report', 'it', actor,
                               new_data={'hosts': len(results)}, ip=request.remote_addr)
            return jsonify({'status': 'success', 'updated': len(results),
                            'results': results, 'agent_version': AGENT_VERSION})
        except Exception as e:
            return jsonify({'status': 'error', 'msg': str(e)}), 500
        finally:
            for c in conns.values():
                try:
                    c.close()
                except Exception:
                    pass

    @app.route('/api/it/agents')
    @role_required(ALLOWED)
    def api_it_agents_list():
        branch = _branch()
        conn = get_db_connection()
        if not conn:
            return jsonify({'error': 'DB error'}), 500
        cur = conn.cursor(dictionary=True)
        try:
            status = str(request.args.get('status') or '').strip().lower()
            q = str(request.args.get('q') or '').strip()
            where, params = ["branch_code=%s"], [branch]
            if status in _AGENT_STATUSES:
                where.append('deploy_status=%s')
                params.append(status)
            if q:
                like = _like(q)
                where.append('(hostname LIKE %s OR ip LIKE %s OR mac LIKE %s OR asset_tag LIKE %s)')
                params.extend([like] * 4)
            clause = ' AND '.join(where)
            cur.execute(f"SELECT COUNT(*) c FROM it_agent_hosts WHERE {clause}", params)
            total = cur.fetchone()['c']
            page = max(1, request.args.get('page', 1, type=int) or 1)
            per_page = min(200, max(10, request.args.get('per_page', 50, type=int) or 50))
            cur.execute(
                f"SELECT * FROM it_agent_hosts WHERE {clause} "
                "ORDER BY FIELD(deploy_status,'failed','unreachable','pending','installed','ignored'), "
                "hostname, ip LIMIT %s OFFSET %s",
                params + [per_page, (page - 1) * per_page])
            hosts = [_host_flags(_serialize(r)) for r in cur.fetchall()]
            cur.close(); conn.close()
            return jsonify({'data': hosts, 'total': total, 'page': page,
                            'per_page': per_page, 'agent_version': AGENT_VERSION,
                            'stale_days': AGENT_STALE_DAYS})
        except Exception as e:
            cur.close(); conn.close()
            return jsonify({'error': str(e)}), 500

    @app.route('/api/it/agents/coverage')
    @role_required(ALLOWED)
    def api_it_agents_coverage():
        branch = _branch()
        conn = get_db_connection()
        if not conn:
            return jsonify({'error': 'DB error'}), 500
        cur = conn.cursor(dictionary=True)
        try:
            cur.execute(
                "SELECT asset_tag, hostname, ip_address, mac_address FROM it_assets "
                "WHERE branch_code=%s AND category IN ('pc','laptop') AND status<>'disposed' "
                "ORDER BY asset_tag", (branch,))
            targets = cur.fetchall()
            cur.execute("SELECT * FROM it_agent_hosts WHERE branch_code=%s", (branch,))
            hosts = [_serialize(r) for r in cur.fetchall()]
            cur.execute(
                "SELECT COUNT(*) c FROM it_discovered_devices WHERE branch_code=%s AND state='new' "
                "AND (category_suggest IN ('pc','laptop') OR open_ports REGEXP '445|3389|5985')",
                (branch,))
            discovered = cur.fetchone()['c']
            cur.close(); conn.close()
            payload = _coverage_payload(targets, hosts)
            payload['discovered_windows'] = discovered
            return jsonify(payload)
        except Exception as e:
            cur.close(); conn.close()
            return jsonify({'error': str(e)}), 500

    @app.route('/api/it/agents/targets.csv')
    @role_required(ALLOWED)
    def api_it_agents_targets_csv():
        branch = _branch()
        conn = get_db_connection()
        if not conn:
            return jsonify({'error': 'DB error'}), 500
        cur = conn.cursor(dictionary=True)
        try:
            cur.execute(
                "SELECT hostname, ip, mac, vendor, category_suggest, open_ports "
                "FROM it_discovered_devices WHERE branch_code=%s AND state='new' "
                "AND (category_suggest IN ('pc','laptop') OR open_ports REGEXP '445|3389|5985') "
                "ORDER BY ip", (branch,))
            candidates = cur.fetchall()
            cur.execute(
                "SELECT asset_tag, hostname, ip_address, mac_address, brand, model "
                "FROM it_assets WHERE branch_code=%s AND category IN ('pc','laptop') "
                "AND status<>'disposed' ORDER BY asset_tag", (branch,))
            assets = cur.fetchall()
            cur.execute(
                "SELECT host_key, hostname, ip, mac FROM it_agent_hosts "
                "WHERE branch_code=%s AND deploy_status='installed'", (branch,))
            covered = set()
            for h in cur.fetchall():
                for k in (h.get('host_key'), h.get('hostname'), h.get('ip'), h.get('mac')):
                    k = str(k or '').strip().lower()
                    if k:
                        covered.add(k)
            cur.close(); conn.close()
            rows = _targets_rows(candidates, assets, covered)
            log_activity_async(0, 'it_agent_targets_csv', 'it', _full_name(),
                               new_data={'rows': len(rows)}, ip=request.remote_addr)
            return _targets_csv_response(
                rows, f"target_agen_it_{branch}_{datetime.now():%Y%m%d}.csv")
        except Exception as e:
            cur.close(); conn.close()
            return jsonify({'error': str(e)}), 500

    @app.route('/api/it/agents/version')
    def api_it_agents_version():
        if not (_agent_token_ok() or _agent_session_ok()):
            return jsonify({'status': 'error', 'msg': 'Token tidak valid'}), 401
        path = _agent_script_path()
        if not os.path.isfile(path):
            return jsonify({'status': 'error', 'msg': 'Paket agen tidak ditemukan'}), 404
        return jsonify({'status': 'success', 'version': AGENT_VERSION,
                        'file': AGENT_SCRIPT, 'size': os.path.getsize(path)})

    @app.route('/api/it/agents/package')
    def api_it_agents_package():
        """Unduh skrip agen (untuk self-update). Token, bukan sesi browser."""
        if not (_agent_token_ok() or _agent_session_ok()):
            return jsonify({'status': 'error', 'msg': 'Token tidak valid'}), 401
        path = _agent_script_path()
        if not os.path.isfile(path):
            return jsonify({'status': 'error', 'msg': 'Paket agen tidak ditemukan'}), 404
        with open(path, 'rb') as fh:
            body = fh.read()
        resp = make_response(body)
        resp.headers['Content-Type'] = 'text/plain; charset=utf-8'
        resp.headers['Content-Disposition'] = f'attachment; filename={AGENT_SCRIPT}'
        resp.headers['Cache-Control'] = 'no-store'
        return resp

    # ------------------------------------------------------------ stok opname
    @app.route('/api/it/stocktake', methods=['GET', 'POST'])
    @role_required(ALLOWED)
    def api_it_stocktake():
        branch = _branch()
        conn = get_db_connection()
        if not conn:
            return jsonify({'error': 'DB error'}), 500
        cur = conn.cursor(dictionary=True)
        try:
            if request.method == 'POST':
                data = request.get_json(silent=True) or {}
                room = str(data.get('location_room') or '').strip()
                cur.execute("INSERT INTO it_stocktake_sessions (branch_code, location_room, started_by) "
                            "VALUES (%s,%s,%s)", (branch, room, _user()))
                session_id = cur.lastrowid
                sql = "SELECT id FROM it_assets WHERE branch_code=%s AND status<>'disposed'"
                params = [branch]
                if room:
                    sql += " AND location_room=%s"; params.append(room)
                cur.execute(sql, params)
                ids = [r['id'] for r in cur.fetchall()]
                for aid in ids:
                    cur.execute("INSERT IGNORE INTO it_stocktake_items (session_id, asset_id, branch_code) "
                                "VALUES (%s,%s,%s)", (session_id, aid, branch))
                cur.execute("UPDATE it_stocktake_sessions SET total_expected=%s WHERE id=%s",
                            (len(ids), session_id))
                conn.commit()
                return jsonify({'status': 'success', 'data': {'id': session_id, 'expected': len(ids)}}), 201
            cur.execute("SELECT * FROM it_stocktake_sessions WHERE branch_code=%s ORDER BY id DESC LIMIT 40",
                        (branch,))
            rows = [_serialize(r) for r in cur.fetchall()]
            return jsonify({'data': rows})
        finally:
            cur.close(); conn.close()

    @app.route('/api/it/stocktake/<int:sid>')
    @role_required(ALLOWED)
    def api_it_stocktake_detail(sid):
        conn = get_db_connection()
        if not conn:
            return jsonify({'error': 'DB error'}), 500
        cur = conn.cursor(dictionary=True)
        cur.execute("SELECT * FROM it_stocktake_sessions WHERE id=%s AND branch_code=%s", (sid, _branch()))
        header = cur.fetchone()
        if not header:
            cur.close(); conn.close()
            return jsonify({'error': 'Sesi tidak ditemukan'}), 404
        cur.execute(
            "SELECT i.*, a.asset_tag, a.category, a.brand, a.model, a.location_room "
            "FROM it_stocktake_items i JOIN it_assets a ON a.id=i.asset_id "
            "WHERE i.session_id=%s ORDER BY a.asset_tag", (sid,))
        items = [_serialize(r) for r in cur.fetchall()]
        cur.close(); conn.close()
        return jsonify({'data': {'session': _serialize(header), 'items': items}})

    @app.route('/api/it/stocktake/<int:sid>/scan', methods=['POST'])
    @role_required(ALLOWED)
    def api_it_stocktake_scan(sid):
        try:
            data = request.get_json(silent=True) or {}
            tag = str(data.get('tag') or '').strip().upper()
            note = str(data.get('note') or '')[:200]
            conn = get_db_connection()
            if not conn:
                return jsonify({'error': 'DB error'}), 500
            cur = conn.cursor(dictionary=True)
            cur.execute("SELECT * FROM it_stocktake_sessions WHERE id=%s AND branch_code=%s",
                        (sid, _branch()))
            header = cur.fetchone()
            if not header:
                cur.close(); conn.close()
                return jsonify({'status': 'error', 'msg': 'Sesi tidak ditemukan'}), 404
            if header.get('closed_at'):
                cur.close(); conn.close()
                return jsonify({'status': 'error', 'msg': 'Sesi sudah ditutup'}), 400
            asset = _get_asset(cur, tag, _branch())
            if not asset:
                cur.close(); conn.close()
                return jsonify({'status': 'error', 'msg': f'Tag {tag} bukan aset cabang ini'}), 404
            cur.execute("INSERT INTO it_stocktake_items (session_id, asset_id, branch_code, result, note) "
                        "VALUES (%s,%s,%s,'found',%s) "
                        "ON DUPLICATE KEY UPDATE scanned_at=NOW(), result='found', note=VALUES(note)",
                        (sid, asset['id'], _branch(), note))
            cur.execute("UPDATE it_stocktake_sessions SET total_found="
                        "(SELECT COUNT(*) FROM it_stocktake_items WHERE session_id=%s AND result='found') "
                        "WHERE id=%s", (sid, sid))
            _event(cur, asset['id'], _branch(), 'scan', None, None,
                   note=f'Stok opname #{sid}', actor=_user())
            conn.commit()
            cur.close(); conn.close()
            return jsonify({'status': 'success', 'msg': f'{tag} tercatat ditemukan',
                            'data': _serialize(asset)})
        except Exception as e:
            return jsonify({'status': 'error', 'msg': str(e)}), 500

    @app.route('/api/it/stocktake/<int:sid>/close', methods=['POST'])
    @role_required(ALLOWED)
    def api_it_stocktake_close(sid):
        conn = get_db_connection()
        if not conn:
            return jsonify({'error': 'DB error'}), 500
        cur = conn.cursor(dictionary=True)
        cur.execute("SELECT * FROM it_stocktake_sessions WHERE id=%s AND branch_code=%s", (sid, _branch()))
        header = cur.fetchone()
        if not header:
            cur.close(); conn.close()
            return jsonify({'status': 'error', 'msg': 'Sesi tidak ditemukan'}), 404
        cur.execute("UPDATE it_stocktake_items SET result='missing' "
                    "WHERE session_id=%s AND result='found' AND scanned_at IS NULL", (sid,))
        cur.execute("UPDATE it_stocktake_sessions SET closed_at=NOW(), "
                    "total_found=(SELECT COUNT(*) FROM it_stocktake_items WHERE session_id=%s AND result='found') "
                    "WHERE id=%s", (sid, sid))
        conn.commit()
        cur.execute("SELECT total_expected, total_found FROM it_stocktake_sessions WHERE id=%s", (sid,))
        row = cur.fetchone()
        cur.close(); conn.close()
        log_activity_async(0, 'it_stocktake_close', 'it', _full_name(),
                           new_data={'session': sid, **row}, ip=request.remote_addr)
        return jsonify({'status': 'success', 'msg': 'Sesi ditutup', 'data': _serialize(row)})

    # -------------------------------------------------------------- laporan PDF
    @app.route('/api/it/reports/assets.pdf')
    @role_required(ALLOWED)
    def api_it_assets_report_pdf():
        try:
            branch = _branch()
            where = ["branch_code=%s"]
            params = [branch]
            for key, col in (('category', 'category'), ('status', 'status'),
                             ('cond', 'cond'), ('room', 'location_room')):
                value = str(request.args.get(key, '') or '').strip()
                if value:
                    if key == 'room':
                        where.append(f"{col} LIKE %s"); params.append(_like(value))
                    else:
                        where.append(f"{col}=%s"); params.append(value)
            conn = get_db_connection()
            if not conn:
                return jsonify({'error': 'DB error'}), 500
            cur = conn.cursor(dictionary=True)
            cur.execute("SELECT * FROM it_assets WHERE " + " AND ".join(where) +
                        " ORDER BY category, asset_tag", params)
            rows = [_serialize(r) for r in cur.fetchall()]
            cur.close(); conn.close()
            pdf = _asset_report_pdf(rows, branch, _full_name())
            log_activity_async(0, 'it_report_pdf', 'it', _full_name(),
                               new_data={'count': len(rows)}, ip=request.remote_addr)
            resp = make_response(pdf.getvalue())
            resp.headers['Content-Type'] = 'application/pdf'
            resp.headers['Content-Disposition'] = (
                f"attachment; filename=laporan_inventaris_it_{branch}_{datetime.now():%Y%m%d}.pdf")
            return resp
        except Exception as e:
            return jsonify({'status': 'error', 'msg': str(e)}), 500

    # -------------------------------------------------------------- laporan
    @app.route('/api/it/reports/warranty')
    @role_required(ALLOWED)
    def api_it_warranty():
        try:
            days = min(365, max(1, int(request.args.get('days', 30) or 30)))
            conn = get_db_connection()
            if not conn:
                return jsonify({'error': 'DB error'}), 500
            cur = conn.cursor(dictionary=True)
            cur.execute(
                "SELECT * FROM it_assets WHERE branch_code=%s AND warranty_until IS NOT NULL "
                "AND warranty_until BETWEEN CURDATE() AND DATE_ADD(CURDATE(), INTERVAL %s DAY) "
                "AND status<>'disposed' ORDER BY warranty_until", (_branch(), days))
            rows = [_serialize(r) for r in cur.fetchall()]
            cur.close(); conn.close()
            return jsonify({'data': rows, 'days': days})
        except Exception as e:
            return jsonify({'error': str(e)}), 500


# ------------------------------------------------------- impor: validasi


_IMPORT_ALIASES = {
    'asset_tag': 'asset_tag', 'tag': 'asset_tag', 'nomor_inventaris': 'asset_tag',
    'kategori': 'category', 'category': 'category',
    'merek': 'brand', 'brand': 'brand', 'merk': 'brand',
    'model': 'model', 'tipe': 'model',
    'serial': 'serial_number', 'serial_number': 'serial_number', 'sn': 'serial_number',
    'status': 'status',
    'kondisi': 'cond', 'cond': 'cond', 'condition': 'cond',
    'ruangan': 'location_room', 'location_room': 'location_room', 'lokasi': 'location_room',
    'detail_lokasi': 'location_detail', 'location_detail': 'location_detail',
    'pic': 'assigned_to', 'assigned_to': 'assigned_to', 'pemakai': 'assigned_to',
    'hostname': 'hostname', 'ip': 'ip_address', 'ip_address': 'ip_address',
    'mac': 'mac_address', 'mac_address': 'mac_address', 'os': 'os_name',
    'tanggal_beli': 'purchase_date', 'purchase_date': 'purchase_date',
    'garansi': 'warranty_until', 'warranty_until': 'warranty_until',
    'harga': 'purchase_price', 'purchase_price': 'purchase_price',
    'vendor': 'vendor', 'catatan': 'notes', 'notes': 'notes',
}

_IMPORT_REQUIRED = ('category',)


def _validate_import_rows(rows):
    valid, errors = [], []
    for idx, raw in enumerate(rows, start=2):
        row = {}
        for key, value in (raw or {}).items():
            canonical = _IMPORT_ALIASES.get(str(key or '').strip().lower())
            if canonical and value not in (None, ''):
                row[canonical] = value.strip() if isinstance(value, str) else value
        if not row:
            continue
        try:
            if not _valid_category(row.get('category')):
                raise ValueError('kategori kosong/tidak dikenal')
            fields = _clean_fields(row)
            tag = str(row.get('asset_tag') or '').strip().upper()
            valid.append({'row': idx, 'tag': tag, 'fields': {k: _jsonable(v) for k, v in fields.items()}})
        except Exception as e:
            errors.append({'row': idx, 'msg': str(e)})
    return {'valid': valid, 'errors': errors, 'total': len(rows)}


def _commit_import_rows(valid_rows, branch, actor):
    conn = get_db_connection()
    if not conn:
        raise RuntimeError('DB tidak tersedia')
    created, errors = 0, []
    cur = conn.cursor(dictionary=True)
    try:
        for item in valid_rows:
            tag = item['tag']
            try:
                fields = dict(item['fields'])
                if not tag:
                    tag = _next_tag(cur, branch, fields['category'])
                cols = ['asset_tag', 'branch_code', 'source', 'created_by'] + list(fields.keys())
                vals = [tag, branch, 'import', actor] + list(fields.values())
                cur.execute(f"INSERT INTO it_assets ({','.join(cols)}) "
                            f"VALUES ({','.join(['%s'] * len(cols))})", vals)
                cur.execute("SELECT LAST_INSERT_ID() AS id")
                aid = cur.fetchone()['id']
                _event(cur, aid, branch, 'import', None, fields, note='Impor massal', actor=actor)
                conn.commit()
                created += 1
            except Exception as e:
                conn.rollback()
                errors.append({'row': item['row'], 'msg': str(e)})
        return created, errors
    finally:
        cur.close(); conn.close()
