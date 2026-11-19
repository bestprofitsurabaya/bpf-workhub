"""Modul Agenda (v2.123.0) — kalender kegiatan WorkHub.

Satu sumber kebenaran agenda per cabang, dengan:
- tabel `agenda_items` di setiap DB cabang (isolasi data);
- pengingat hari H opsional per agenda (`notify_on_day`);
- pengulangan sederhana (mingguan/bulanan) yang diekspansi saat dibaca;
- fan-out batch lintas cabang (hanya admin_master);
- bridge read-only untuk aplikasi Cordova lama (`/api/state`, `/api/month`).

Aktor:
- `admin` (cabang)  → hanya cabangnya (admin_scope.admin_branches).
- `admin` + is_ho   → semua cabang, boleh terbit lintas cabang.
- `content_creator` → hanya cabang sesi, tidak boleh lintas cabang.
- role lain        → baca cabangnya.

Modul ini tidak menyimpan cache; semua query memakai koneksi pool yang
ditutup di sini. Route wajib menutup koneksi (lihat modules/config.py).
"""
import calendar as _calendar
import os
import re
import time as _time
import uuid
from datetime import date, datetime, time, timedelta, timezone

from modules.branch_manager import list_branches
from modules.config import get_db_connection, get_master_connection
from modules.helpers import log_activity_async

CATEGORIES = ('umum', 'rapat', 'libur', 'event', 'pengumuman')
AUDIENCES = ('all', 'marketing', 'backoffice', 'roles')
PUBLISH_MODES = ('now', 'scheduled')
REPEAT_RULES = ('none', 'weekly', 'monthly')

AGENDA_WRITE_ROLES = ('admin', 'content_creator')

RE_DATE = re.compile(r'^\d{4}-\d{2}-\d{2}$')
RE_MONTH = re.compile(r'^\d{4}-\d{2}$')
RE_DATETIME = re.compile(r'^\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}(:\d{2})?$')

UPLOAD_DIR_NAME = 'agenda'


# ---------------------------------------------------------------------------
# Skema
# ---------------------------------------------------------------------------

def ensure_agenda_schema(conn=None):
    """Buat tabel agenda_items di satu DB (master atau cabang). Idempoten."""
    own = conn is None
    conn = conn or get_master_connection()
    if not conn:
        return False
    cursor = conn.cursor()
    try:
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS agenda_items (
                id INT AUTO_INCREMENT PRIMARY KEY,
                batch_id CHAR(32) DEFAULT NULL,
                branch_code VARCHAR(20) NOT NULL DEFAULT '',
                agenda_date DATE NOT NULL,
                title VARCHAR(200) NOT NULL,
                body TEXT,
                category VARCHAR(30) NOT NULL DEFAULT 'umum',
                audience VARCHAR(20) NOT NULL DEFAULT 'all',
                audience_roles VARCHAR(200) DEFAULT '',
                publish_mode VARCHAR(20) NOT NULL DEFAULT 'now',
                publish_at DATETIME DEFAULT NULL,
                end_at DATETIME DEFAULT NULL,
                repeat_rule VARCHAR(20) NOT NULL DEFAULT 'none',
                repeat_until DATE DEFAULT NULL,
                media_url VARCHAR(2000) DEFAULT NULL,
                media_type VARCHAR(20) DEFAULT NULL,
                attachment_path VARCHAR(255) DEFAULT NULL,
                pinned TINYINT(1) NOT NULL DEFAULT 0,
                notify_on_day TINYINT(1) NOT NULL DEFAULT 0,
                active TINYINT(1) NOT NULL DEFAULT 1,
                legacy_id VARCHAR(64) DEFAULT NULL,
                created_by VARCHAR(100) DEFAULT '',
                updated_by VARCHAR(100) DEFAULT '',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                KEY idx_agenda_branch_date (branch_code, agenda_date),
                KEY idx_agenda_batch (batch_id),
                KEY idx_agenda_publish (publish_at),
                KEY idx_agenda_legacy (legacy_id)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """)
        # Migrasi kolom pengingat untuk tabel yang dibuat sebelum v2.123.0.
        try:
            cursor.execute("SHOW COLUMNS FROM agenda_items LIKE 'notify_on_day'")
            if not cursor.fetchone():
                cursor.execute("ALTER TABLE agenda_items "
                               "ADD COLUMN notify_on_day TINYINT(1) NOT NULL DEFAULT 0")
        except Exception as me:
            print(f'[agenda] migrate notify_on_day: {me}')
        conn.commit()
        return True
    except Exception as e:
        print(f'[agenda] ensure schema error: {e}')
        return False
    finally:
        cursor.close()
        if own and conn:
            conn.close()



# ---------------------------------------------------------------------------
# Utilitas waktu & validasi
# ---------------------------------------------------------------------------

def _as_date(v):
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, date):
        return v
    if not v:
        return None
    try:
        return datetime.strptime(str(v)[:10], '%Y-%m-%d').date()
    except ValueError:
        return None


def _as_dt(v):
    if v is None:
        return None
    if isinstance(v, datetime):
        return v
    if isinstance(v, date):
        return datetime.combine(v, time.min)
    s = str(v).strip().replace('T', ' ')
    for fmt in ('%Y-%m-%d %H:%M:%S', '%Y-%m-%d %H:%M', '%Y-%m-%d'):
        try:
            return datetime.strptime(s[:19] if fmt.endswith('%S') else s[:16], fmt)
        except ValueError:
            continue
    return None


def _dt_str(v):
    d = _as_dt(v)
    return d.strftime('%Y-%m-%d %H:%M') if d else None


def _month_bounds(month):
    """'YYYY-MM' → (awal, akhir) tanggal inklusif."""
    if not month or not RE_MONTH.match(str(month)):
        today = date.today()
        month = today.strftime('%Y-%m')
    y, m = (int(x) for x in str(month).split('-'))
    last = _calendar.monthrange(y, m)[1]
    return date(y, m, 1), date(y, m, last)


def _iso(d):
    return d.strftime('%Y-%m-%d') if d else None


def _local_now():
    return datetime.now()


def _local_now_str():
    return datetime.now().strftime('%Y-%m-%dT%H:%M')


def normalize_audience(a):
    a = str(a or 'all').strip().lower()
    if a in ('both', 'semua', ''):
        return 'all'
    return a


def media_kind(url):
    """Bentuk data untuk bridge aplikasi Android BPF Agenda."""
    u = str(url or '')
    if not u:
        return None
    if 'youtube.com' in u or 'youtu.be' in u:
        return {'kind': 'youtube', 'url': u}
    ext = ((u.split('?')[0].split('#')[0].split('.')[-1]) or '').lower()
    if ext in ('png', 'jpg', 'jpeg', 'webp', 'gif'):
        return {'kind': 'image', 'url': u}
    if ext in ('mp4', 'm4v', 'webm', 'mov'):
        return {'kind': 'video', 'url': u}
    return {'kind': 'link', 'url': u}


def validate_payload(data, existing=None):
    """Validasi & normalisasi payload agenda. Return (item, errors)."""
    item = dict(existing or {})
    errors = []

    if 'date' in data or 'agenda_date' in data:
        raw = data.get('agenda_date', data.get('date'))
        if not raw or not RE_DATE.match(str(raw)):
            errors.append('Tanggal harus format YYYY-MM-DD')
        else:
            item['agenda_date'] = str(raw)
    if 'title' in data:
        title = str(data.get('title') or '').strip()
        if not (1 <= len(title) <= 200):
            errors.append('Judul wajib 1..200 karakter')
        else:
            item['title'] = title
    if 'body' in data:
        body = str(data.get('body') or '').strip()
        if len(body) > 5000:
            errors.append('Isi maksimal 5000 karakter')
        else:
            item['body'] = body
    if 'category' in data:
        cat = str(data.get('category') or 'umum').strip().lower()
        if cat not in CATEGORIES:
            errors.append('Kategori tidak dikenal')
        else:
            item['category'] = cat
    if 'audience' in data:
        aud = normalize_audience(data.get('audience'))
        if aud not in AUDIENCES:
            errors.append('Audiens harus all/marketing/backoffice/roles')
        else:
            item['audience'] = aud
    if 'audience_roles' in data:
        raw = data.get('audience_roles')
        if isinstance(raw, (list, tuple)):
            raw = ','.join(str(x).strip() for x in raw if str(x).strip())
        item['audience_roles'] = str(raw or '').strip()[:200]
    if 'publish_mode' in data:
        mode = str(data.get('publish_mode') or 'now').strip().lower()
        if mode not in PUBLISH_MODES:
            errors.append('publish_mode harus now atau scheduled')
        else:
            item['publish_mode'] = mode
    if 'publish_at' in data:
        raw = data.get('publish_at')
        if raw in (None, ''):
            item['publish_at'] = None
        elif not RE_DATETIME.match(str(raw)):
            errors.append('publish_at harus YYYY-MM-DDTHH:mm')
        else:
            item['publish_at'] = _dt_str(raw)
    if 'end_at' in data:
        raw = data.get('end_at')
        if raw in (None, ''):
            item['end_at'] = None
        elif not RE_DATETIME.match(str(raw)):
            errors.append('end_at harus YYYY-MM-DDTHH:mm')
        else:
            item['end_at'] = _dt_str(raw)
    if 'repeat_rule' in data:
        rule = str(data.get('repeat_rule') or 'none').strip().lower()
        if rule not in REPEAT_RULES:
            errors.append('repeat_rule harus none/weekly/monthly')
        else:
            item['repeat_rule'] = rule
    if 'repeat_until' in data:
        raw = data.get('repeat_until')
        if raw in (None, ''):
            item['repeat_until'] = None
        elif not RE_DATE.match(str(raw)):
            errors.append('repeat_until harus YYYY-MM-DD')
        else:
            item['repeat_until'] = str(raw)
    if 'media_url' in data:
        mu = str(data.get('media_url') or '').strip()
        if not mu:
            item['media_url'] = None
            item['media_type'] = None
        elif len(mu) > 2000:
            errors.append('media_url maksimal 2000 karakter')
        elif not (re.match(r'^https?://', mu, re.I) or mu.startswith('/assets/')):
            errors.append('media_url harus http(s):// atau /assets/...')
        else:
            item['media_url'] = mu
            item['media_type'] = (media_kind(mu) or {}).get('kind')
    if 'attachment_path' in data:
        item['attachment_path'] = (str(data.get('attachment_path') or '').strip() or None)
    if 'pinned' in data:
        item['pinned'] = 1 if data.get('pinned') in (True, 1, '1', 'true', 'on') else 0
    if 'notify_on_day' in data:
        item['notify_on_day'] = 1 if data.get('notify_on_day') in (True, 1, '1', 'true', 'on') else 0
    if 'active' in data:
        item['active'] = 1 if data.get('active') in (True, 1, '1', 'true', 'on') else 0

    if existing is None:
        item.setdefault('body', '')
        item.setdefault('category', 'umum')
        item.setdefault('audience', 'all')
        item.setdefault('audience_roles', '')
        item.setdefault('publish_mode', 'now')
        item.setdefault('publish_at', None)
        item.setdefault('end_at', None)
        item.setdefault('repeat_rule', 'none')
        item.setdefault('repeat_until', None)
        item.setdefault('media_url', None)
        item.setdefault('media_type', None)
        item.setdefault('attachment_path', None)
        item.setdefault('pinned', 0)
        item.setdefault('notify_on_day', 0)
        item.setdefault('active', 1)

    if not item.get('agenda_date'):
        errors.append('Tanggal wajib')
    if not item.get('title'):
        errors.append('Judul wajib')

    mode = item.get('publish_mode') or 'now'
    pub = _as_dt(item.get('publish_at'))
    end = _as_dt(item.get('end_at'))
    if mode == 'scheduled' and not pub:
        errors.append('publish_at wajib untuk mode terjadwal')
    if mode == 'now':
        item['publish_at'] = None
    if pub and end and end <= pub:
        errors.append('end_at harus setelah publish_at')
    if item.get('repeat_rule') in ('weekly', 'monthly'):
        if not item.get('repeat_until'):
            # default setahun agar tidak menggantung
            d = _as_date(item.get('agenda_date'))
            if d:
                item['repeat_until'] = _iso(d + timedelta(days=365))
        ru = _as_date(item.get('repeat_until'))
        d = _as_date(item.get('agenda_date'))
        if ru and d and ru < d:
            errors.append('repeat_until tidak boleh sebelum tanggal agenda')
        if ru and d and (ru - d).days > 730:
            errors.append('repeat_until maksimal 2 tahun')
    if item.get('repeat_rule') == 'none':
        item['repeat_until'] = None

    return item, errors


# ---------------------------------------------------------------------------
# Cakupan cabang
# ---------------------------------------------------------------------------

def _norm(code):
    return str(code or '').strip().upper()


def active_branch_codes():
    codes = []
    try:
        for b in list_branches() or []:
            if b.get('is_active') and b.get('code'):
                codes.append(_norm(b['code']))
    except Exception as e:
        print(f'[agenda] list branches error: {e}')
    return codes or ['SBY']


def session_branch(fallback='SBY'):
    """Kode cabang sesi aktif (fallback cabang utama)."""
    try:
        from flask import has_request_context, session
        if has_request_context():
            code = _norm(session.get('branch_code'))
            if code:
                return code
    except Exception:
        pass
    return _norm(fallback) or 'SBY'


def branch_for_write(role, requested=None):
    """Cabang yang boleh ditulis aktor. Return (code|None, errors).

    content_creator selalu cabang sesi. Admin memakai admin_scope.
    """
    from modules.admin_scope import admin_branches, is_ho_admin

    role = str(role or '')
    req = _norm(requested)
    if role == 'content_creator':
        own = session_branch()
        if req and req != own:
            return None, ['Content creator hanya boleh mengelola cabangnya sendiri']
        return own, []
    if role == 'admin':
        codes, all_b = admin_branches()
        if all_b:
            return (req or session_branch()), []
        allowed = sorted({_norm(c) for c in codes if c})
        if req:
            if req not in allowed:
                return None, ['Cabang di luar kewenangan admin']
            return req, []
        if not allowed:
            return None, ['Admin tidak memiliki cabang']
        return allowed[0], []
    return None, ['Role tidak berwenang mengelola agenda']


def writable_branches(role, requested=None):
    """Untuk fan-out: daftar cabang yang boleh ditulis aktor."""
    from modules.admin_scope import admin_branches, is_ho_admin

    role = str(role or '')
    if role == 'content_creator':
        return [session_branch()]
    if role == 'admin':
        codes, all_b = admin_branches()
        if all_b:
            req = _norm(requested)
            if req:
                return [req]
            return active_branch_codes()
        return sorted({_norm(c) for c in codes if c}) or [session_branch()]
    return []


def read_branches(role, requested=None, scope_all=False):
    """Cabang yang boleh DIBACA aktor. Admin HO/content creator? → semua.

    Content creator tetap cabangnya sendiri (koreksi 19 Nov 2026).
    """
    from modules.admin_scope import is_ho_admin
    role = str(role or '')
    if role == 'admin' and is_ho_admin():
        req = _norm(requested)
        return [req] if req else (active_branch_codes() if scope_all else [session_branch()])
    return [session_branch()]


# ---------------------------------------------------------------------------
# Query & ekspansi
# ---------------------------------------------------------------------------

def _fetch_rows(conn, start, end):
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute("""
            SELECT * FROM agenda_items
            WHERE active=1
              AND (agenda_date <= %s)
              AND (repeat_rule <> 'none' OR agenda_date >= %s)
              AND (repeat_until IS NULL OR repeat_until >= %s)
        """, (_iso(end), _iso(start), _iso(start)))
        return cursor.fetchall() or []
    finally:
        cursor.close()


def occurrences(row, start, end):
    """Daftar tanggal kemunculan agenda dalam rentang [start, end]."""
    base = _as_date(row.get('agenda_date'))
    if not base:
        return []
    rule = str(row.get('repeat_rule') or 'none')
    until = _as_date(row.get('repeat_until')) or date(9999, 12, 31)
    out = []
    if rule == 'none':
        if start <= base <= end and base <= until:
            out.append(base)
        return out
    if rule == 'weekly':
        d = base
        if d < start:
            d += timedelta(days=((start - d).days // 7) * 7)
        while d <= end and d <= until and len(out) < 400:
            if d >= start:
                out.append(d)
            d += timedelta(days=7)
        return out
    if rule == 'monthly':
        y, m = base.year, base.month
        for _ in range(400):
            day = min(base.day, _calendar.monthrange(y, m)[1])
            d = date(y, m, day)
            if d > end or d > until:
                break
            if d >= start:
                out.append(d)
            m += 1
            if m > 12:
                m = 1
                y += 1
        return out
    return out


def _audience_ok(row, role, audience_filter=None):
    """Cek audiens item terhadap role user / filter bridge."""
    aud = normalize_audience(row.get('audience'))
    if audience_filter:
        f = normalize_audience(audience_filter)
        if f == 'all':
            return True
        return aud == 'all' or aud == f
    if not role or role == 'admin' or role == 'content_creator':
        return True
    if aud == 'all':
        return True
    if aud == 'marketing':
        return role == 'marketing'
    if aud == 'backoffice':
        return role != 'marketing'
    if aud == 'roles':
        roles = [x.strip() for x in str(row.get('audience_roles') or '').split(',') if x.strip()]
        return role in roles
    return True


def _window(row, occ):
    """Jendela tayang untuk satu kemunculan (tanggal occ)."""
    pub = _as_dt(row.get('publish_at'))
    end = _as_dt(row.get('end_at'))
    if pub:
        pub = datetime.combine(occ, pub.time())
    if end:
        end = datetime.combine(occ, end.time())
    return pub, end


def is_visible(row, occ, now=None, role='', audience_filter=None):
    if not row.get('active', 1):
        return False
    if not _audience_ok(row, role, audience_filter):
        return False
    now = now or _local_now()
    pub, end = _window(row, occ)
    if str(row.get('publish_mode') or 'now') == 'scheduled':
        if not pub or now < pub:
            return False
        if end and now >= end:
            return False
    return True


def item_shape(row, occ, branches=None):
    return {
        'id': row.get('id'),
        'batch_id': row.get('batch_id'),
        'legacy_id': row.get('legacy_id'),
        'branch_code': row.get('branch_code'),
        'branches': branches or [row.get('branch_code')],
        'date': _iso(occ),
        'title': row.get('title'),
        'body': row.get('body') or '',
        'category': row.get('category') or 'umum',
        'audience': normalize_audience(row.get('audience')),
        'audience_roles': row.get('audience_roles') or '',
        'publish_mode': row.get('publish_mode') or 'now',
        'publish_at': _dt_str(row.get('publish_at')),
        'end_at': _dt_str(row.get('end_at')),
        'repeat_rule': row.get('repeat_rule') or 'none',
        'repeat_until': _iso(_as_date(row.get('repeat_until'))),
        'media_url': row.get('media_url'),
        'media_type': row.get('media_type'),
        'pinned': bool(row.get('pinned')),
        'notify_on_day': bool(row.get('notify_on_day')),
        'created_by': row.get('created_by') or '',
        'updated_by': row.get('updated_by') or '',
    }


def legacy_shape(row, occ):
    media = media_kind(row.get('media_url')) if row.get('media_url') else None
    out = {
        'id': row.get('id'),
        'date': _iso(occ),
        'title': row.get('title'),
        'body': row.get('body') or '',
        'media_url': row.get('media_url') or None,
    }
    if media:
        out['media'] = media
    return out


def _dedupe_key(row):
    return (row.get('batch_id') or row.get('legacy_id')
            or f"{row.get('branch_code')}|{row.get('agenda_date')}|{row.get('title')}")


def visible_items(branches, start, end, role='', audience_filter=None,
                  now=None, merge_batches=False):
    """Ambil item terlihat dari beberapa cabang dalam rentang tanggal."""
    now = now or _local_now()
    out = []
    merged = {}
    for code in branches:
        conn = None
        try:
            conn = get_db_connection(branch_code=code)
            if not conn:
                continue
            for row in _fetch_rows(conn, start, end):
                for occ in occurrences(row, start, end):
                    if not is_visible(row, occ, now=now, role=role,
                                      audience_filter=audience_filter):
                        continue
                    if merge_batches:
                        key = _dedupe_key(row)
                        if key in merged:
                            merged[key]['branches'].append(row.get('branch_code'))
                            continue
                        shaped = item_shape(row, occ)
                        merged[key] = shaped
                        out.append(shaped)
                    else:
                        out.append(item_shape(row, occ))
        except Exception as e:
            print(f'[agenda] read {code} error: {e}')
        finally:
            if conn:
                try:
                    conn.close()
                except Exception:
                    pass
    out.sort(key=lambda x: (x['date'], 0 if x.get('pinned') else 1,
                            x.get('publish_at') or '', x.get('id') or 0))
    return out


def month_days(branches, month, role='', audience_filter=None, merge_batches=False):
    start, end = _month_bounds(month)
    items = visible_items(branches, start, end, role=role,
                          audience_filter=audience_filter,
                          merge_batches=merge_batches)
    days = {}
    for it in items:
        d = it['date']
        rec = days.setdefault(d, {'date': d, 'count': 0, 'titles': []})
        rec['count'] += 1
        if it.get('title'):
            rec['titles'].append(it['title'])
        if it.get('pinned'):
            rec['pinned'] = True
    return [days[k] for k in sorted(days)]


def items_on_day(branches, day, role='', audience_filter=None,
                 merge_batches=False):
    d = _as_date(day) or date.today()
    return visible_items(branches, d, d, role=role,
                         audience_filter=audience_filter,
                         merge_batches=merge_batches)


def upcoming_items(branches, days=7, role='', merge_batches=False):
    start = date.today()
    end = start + timedelta(days=max(1, min(int(days or 7), 60)))
    items = visible_items(branches, start, end, role=role,
                          merge_batches=merge_batches)
    return [it for it in items if it['date'] >= _iso(start)]


# ---------------------------------------------------------------------------
# Tulis (admin / content creator)
# ---------------------------------------------------------------------------

def _insert(conn, row):
    cursor = conn.cursor()
    try:
        cursor.execute("""
            INSERT INTO agenda_items
                (batch_id, branch_code, agenda_date, title, body, category,
                 audience, audience_roles, publish_mode, publish_at, end_at,
                 repeat_rule, repeat_until, media_url, media_type,
                 attachment_path, pinned, notify_on_day, active, legacy_id,
                 created_by, updated_by)
            VALUES (%(batch_id)s, %(branch_code)s, %(agenda_date)s, %(title)s,
                    %(body)s, %(category)s, %(audience)s, %(audience_roles)s,
                    %(publish_mode)s, %(publish_at)s, %(end_at)s,
                    %(repeat_rule)s, %(repeat_until)s, %(media_url)s,
                    %(media_type)s, %(attachment_path)s, %(pinned)s,
                    %(notify_on_day)s, %(active)s, %(legacy_id)s,
                    %(created_by)s, %(updated_by)s)
        """, row)
        conn.commit()
        return cursor.lastrowid
    finally:
        cursor.close()


def create_items(payload, actor, role, requested_branch=None, legacy_id=None):
    """Buat agenda. Bila `scope='all'` (admin HO) → fan-out semua cabang.

    Return (items, errors). `items` = daftar dict hasil item_shape.
    """
    item, errors = validate_payload(payload)
    if errors:
        return [], errors

    scope_all = str(payload.get('scope') or '').lower() == 'all'
    if scope_all and role != 'admin':
        return [], ['Hanya admin master yang boleh menerbitkan ke semua cabang']

    if scope_all:
        from modules.admin_scope import is_ho_admin
        if not is_ho_admin():
            return [], ['Hanya admin master yang boleh menerbitkan ke semua cabang']
        branches = active_branch_codes()
    else:
        code, errs = branch_for_write(role, requested_branch)
        if errs:
            return [], errs
        branches = [code]

    batch_id = uuid.uuid4().hex if len(branches) > 1 else None
    created = []
    for code in branches:
        row = dict(item)
        row.update({
            'batch_id': batch_id,
            'branch_code': code,
            'legacy_id': legacy_id,
            'created_by': actor or '',
            'updated_by': actor or '',
        })
        row['agenda_date'] = _iso(_as_date(row['agenda_date']))
        conn = None
        try:
            conn = get_db_connection(branch_code=code)
            new_id = _insert(conn, row)
            shaped = item_shape({**row, 'id': new_id}, _as_date(row['agenda_date']))
            created.append(shaped)
        except Exception as e:
            print(f'[agenda] create {code} error: {e}')
            return created, [f'Gagal menyimpan di cabang {code}: {e}']
        finally:
            if conn:
                try:
                    conn.close()
                except Exception:
                    pass

    if created:
        clear_bridge_cache()
        log_activity_async(None, 'agenda_create', 'user', actor or '',
                           new_data={'id': created[0]['id'],
                                     'batch_id': batch_id,
                                     'branches': branches,
                                     'date': created[0]['date'],
                                     'title': created[0]['title']},
                           branch_code=created[0]['branch_code'])
    return created, []


def _load_item(conn, item_id):
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute("SELECT * FROM agenda_items WHERE id=%s", (item_id,))
        return cursor.fetchone()
    finally:
        cursor.close()


def update_item(item_id, payload, actor, role, branch_code, apply_batch=True):
    """Update satu item (dan seluruh batch bila diizinkan)."""
    code, errs = branch_for_write(role, branch_code)
    if errs:
        return [], errs
    conn = None
    try:
        conn = get_db_connection(branch_code=code)
        existing = _load_item(conn, item_id)
        if not existing:
            return [], ['Agenda tidak ditemukan']
        item, errors = validate_payload(payload, existing=existing)
        if errors:
            return [], errors

        targets = [(code, item_id, existing)]
        if apply_batch and existing.get('batch_id'):
            for c in writable_branches(role):
                if c == code:
                    continue
                c2 = None
                try:
                    c2 = get_db_connection(branch_code=c)
                    cur = c2.cursor(dictionary=True)
                    cur.execute("SELECT * FROM agenda_items WHERE batch_id=%s", (existing['batch_id'],))
                    for r in cur.fetchall() or []:
                        targets.append((c, r['id'], r))
                    cur.close()
                except Exception as e:
                    print(f'[agenda] batch load {c} error: {e}')
                finally:
                    if c2:
                        try:
                            c2.close()
                        except Exception:
                            pass

        updated = []
        for c, iid, old in targets:
            c3 = get_db_connection(branch_code=c)
            cur = c3.cursor()
            try:
                cur.execute("""
                    UPDATE agenda_items SET
                        agenda_date=%(agenda_date)s, title=%(title)s, body=%(body)s,
                        category=%(category)s, audience=%(audience)s,
                        audience_roles=%(audience_roles)s, publish_mode=%(publish_mode)s,
                        publish_at=%(publish_at)s, end_at=%(end_at)s,
                        repeat_rule=%(repeat_rule)s, repeat_until=%(repeat_until)s,
                        media_url=%(media_url)s, media_type=%(media_type)s,
                        attachment_path=%(attachment_path)s, pinned=%(pinned)s,
                        notify_on_day=%(notify_on_day)s,
                        active=%(active)s, updated_by=%(updated_by)s
                    WHERE id=%(id)s
                """, {
                    **{k: item.get(k) for k in
                       ('agenda_date', 'title', 'body', 'category', 'audience',
                        'audience_roles', 'publish_mode', 'publish_at', 'end_at',
                        'repeat_rule', 'repeat_until', 'media_url', 'media_type',
                        'attachment_path', 'pinned', 'notify_on_day', 'active')},
                    'updated_by': actor or '',
                    'id': iid,
                })
                c3.commit()
                updated.append(item_shape({**old, **item, 'id': iid},
                                          _as_date(item['agenda_date'])))
            except Exception as e:
                print(f'[agenda] update {c}/{iid} error: {e}')
                return updated, [f'Gagal memperbarui di cabang {c}: {e}']
            finally:
                cur.close()
                try:
                    c3.close()
                except Exception:
                    pass

        if updated:
            clear_bridge_cache()
            log_activity_async(None, 'agenda_update', 'user', actor or '',
                               old_data={'id': item_id, 'title': existing.get('title')},
                               new_data={'id': item_id, 'title': item.get('title'),
                                         'branches': [t[0] for t in targets]},
                               branch_code=code)
        return updated, []
    finally:
        if conn:
            try:
                conn.close()
            except Exception:
                pass


def delete_items(item_id, actor, role, branch_code, apply_batch=True):
    """Soft-delete agenda (dan batch). Return (jumlah, errors)."""
    code, errs = branch_for_write(role, branch_code)
    if errs:
        return 0, errs
    conn = None
    try:
        conn = get_db_connection(branch_code=code)
        existing = _load_item(conn, item_id)
        if not existing:
            return 0, ['Agenda tidak ditemukan']

        targets = [(code, item_id)]
        if apply_batch and existing.get('batch_id'):
            for c in writable_branches(role):
                if c == code:
                    continue
                c2 = None
                try:
                    c2 = get_db_connection(branch_code=c)
                    cur = c2.cursor(dictionary=True)
                    cur.execute("SELECT id FROM agenda_items WHERE batch_id=%s", (existing['batch_id'],))
                    for r in cur.fetchall() or []:
                        targets.append((c, r['id']))
                    cur.close()
                except Exception as e:
                    print(f'[agenda] batch delete {c} error: {e}')
                finally:
                    if c2:
                        try:
                            c2.close()
                        except Exception:
                            pass

        n = 0
        for c, iid in targets:
            c3 = get_db_connection(branch_code=c)
            cur = c3.cursor()
            try:
                cur.execute("UPDATE agenda_items SET active=0, updated_by=%s WHERE id=%s",
                            (actor or '', iid))
                c3.commit()
                n += 1
            except Exception as e:
                print(f'[agenda] delete {c}/{iid} error: {e}')
            finally:
                cur.close()
                try:
                    c3.close()
                except Exception:
                    pass

        if n:
            clear_bridge_cache()
        log_activity_async(None, 'agenda_delete', 'user', actor or '',
                           old_data={'id': item_id, 'title': existing.get('title'),
                                     'batch_id': existing.get('batch_id')},
                           new_data={'deleted': n},
                           branch_code=code)
        return n, []
    finally:
        if conn:
            try:
                conn.close()
            except Exception:
                pass


# ---------------------------------------------------------------------------
# Cakupan (admin master)
# ---------------------------------------------------------------------------

def coverage(month):
    """Matriks jumlah agenda per cabang per minggu (ISO) dalam bulan."""
    start, end = _month_bounds(month)
    weeks = []
    cur = start - timedelta(days=start.weekday())
    while cur <= end:
        w_end = min(cur + timedelta(days=6), end)
        weeks.append((max(cur, start), w_end))
        cur += timedelta(days=7)

    rows = []
    for b in sorted(list_branches() or [], key=lambda x: x.get('name') or ''):
        if not b.get('is_active'):
            continue
        code = _norm(b.get('code'))
        items = visible_items([code], start, end, role=None)
        counts = []
        for w_start, w_end in weeks:
            counts.append(sum(1 for it in items
                              if w_start <= _as_date(it['date']) <= w_end))
        rows.append({
            'branch_code': code,
            'branch_name': b.get('name') or code,
            'weeks': counts,
            'total': len(items),
        })
    return {
        'month': start.strftime('%Y-%m'),
        'weeks': [{'start': _iso(a), 'end': _iso(b)} for a, b in weeks],
        'branches': rows,
        'total': sum(r['total'] for r in rows),
    }


# ---------------------------------------------------------------------------
# ICS
# ---------------------------------------------------------------------------

def _ics_escape(text):
    return (str(text or '')
            .replace('\\', '\\\\')
            .replace(';', '\\;')
            .replace(',', '\\,')
            .replace('\r', '')
            .replace('\n', '\\n'))


def build_ics(branches, month, role='', audience_filter=None, stamp=None):
    start, end = _month_bounds(month)
    items = visible_items(branches, start, end, role=role,
                          audience_filter=audience_filter)
    stamp = (stamp or datetime.now(timezone.utc)).strftime('%Y%m%dT%H%M%SZ')
    lines = [
        'BEGIN:VCALENDAR', 'VERSION:2.0',
        'PRODID:-//BPF WorkHub//Agenda//ID',
        'CALSCALE:GREGORIAN', 'METHOD:PUBLISH',
        'X-WR-CALNAME:Agenda BPF',
    ]
    for it in items:
        d = it['date'].replace('-', '')
        lines += [
            'BEGIN:VEVENT',
            f"UID:agenda-{it['id']}-{d}@bpf-workhub",
            f'DTSTAMP:{stamp}',
            f'DTSTART;VALUE=DATE:{d}',
            f"SUMMARY:{_ics_escape(it['title'])}",
            f"DESCRIPTION:{_ics_escape(it['body'])}",
            f"CATEGORIES:{_ics_escape(it.get('category') or 'umum')}",
            'END:VEVENT',
        ]
    lines.append('END:VCALENDAR')
    return '\r\n'.join(lines) + '\r\n'


# ---------------------------------------------------------------------------
# Bridge untuk aplikasi Cordova lama
# ---------------------------------------------------------------------------

def bridge_branches():
    """Bridge tidak punya konteks cabang: baca semua cabang, dedupe batch."""
    codes = active_branch_codes()
    return codes or [session_branch()]


# Cache singkat untuk bridge: TV/tablet lama melakukan polling/SSE; jangan
# membuka 12 DB untuk setiap klien setiap 25 detik. TTL 15 detik.
_BRIDGE_CACHE = {}
_BRIDGE_TTL = 15


def _cache_get(key):
    hit = _BRIDGE_CACHE.get(key)
    if hit and (_time.time() - hit[0]) < _BRIDGE_TTL:
        return hit[1]
    return None


def _cache_put(key, value):
    if len(_BRIDGE_CACHE) > 32:
        _BRIDGE_CACHE.clear()
    _BRIDGE_CACHE[key] = (_time.time(), value)
    return value


def clear_bridge_cache():
    """Dipanggil setelah aksi tulis agar TV/app lama cepat melihat perubahan."""
    _BRIDGE_CACHE.clear()


def bridge_state(day=None, audience='all', now=None):
    d = _as_date(day) or date.today()
    aud = audience if audience in ('marketing', 'backoffice', 'all') else 'all'
    key = ('state', _iso(d), aud)
    if now is None:
        cached = _cache_get(key)
        if cached is not None:
            return cached
    items = visible_items(bridge_branches(), d, d, role=None,
                          audience_filter=aud, merge_batches=True)
    payload = {
        'ok': True,
        'date': _iso(d),
        'now': (now or _local_now()).strftime('%Y-%m-%dT%H:%M'),
        'server_time': datetime.now(timezone.utc).isoformat(),
        'audience': aud,
        'items': [legacy_shape_from_shaped(it) for it in items],
    }
    return payload if now is not None else _cache_put(key, payload)


def legacy_shape_from_shaped(it):
    media = media_kind(it.get('media_url')) if it.get('media_url') else None
    out = {
        'id': it.get('id'),
        'date': it.get('date'),
        'title': it.get('title'),
        'body': it.get('body') or '',
        'media_url': it.get('media_url') or None,
    }
    if media:
        out['media'] = media
    return out


def bridge_month(month=None, audience='all', include_items=False):
    start, end = _month_bounds(month)
    key = ('month', start.strftime('%Y-%m'), audience, include_items)
    cached = _cache_get(key)
    if cached is not None:
        return cached
    items = visible_items(bridge_branches(), start, end, role=None,
                          audience_filter=audience, merge_batches=True)
    days = {}
    for it in items:
        rec = days.setdefault(it['date'], {'date': it['date'], 'count': 0})
        rec['count'] += 1
        if include_items:
            rec.setdefault('items', []).append(legacy_shape_from_shaped(it))
    return _cache_put(key, {'ok': True, 'dates': [days[k] for k in sorted(days)]})
