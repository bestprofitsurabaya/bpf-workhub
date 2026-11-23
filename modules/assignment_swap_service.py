"""Logika murni pengajuan ganti kendaraan (v2.132.0).

Bagian ini sengaja tidak menyentuh DB: validasi nilai, keputusan sisi serah
terima, dan penyusunan rencana approve. Semua query/transaksi ada di fungsi
berlapis DB pada modul yang sama, sehingga aturan bisnis bisa diuji cepat.
"""
from datetime import date

CATEGORIES = ('driver_request', 'vehicle_issue', 'mutasi', 'other')
SWAP_TYPES = ('exchange', 'move')
STATUSES = ('pending', 'approved', 'completed', 'rejected', 'cancelled',
            'superseded')
POOL = '- (Pool)'
MIN_REASON = 10
MAX_REASON = 500
MAX_ODOMETER = 2_000_000


class SwapError(Exception):
    def __init__(self, http_status, code, msg, extra=None):
        super().__init__(msg)
        self.http_status = http_status
        self.code = code
        self.msg = msg
        self.extra = extra or {}


def clean_reason(value):
    text = str(value or '').strip()
    if len(text) < MIN_REASON:
        raise SwapError(400, 'reason', f'Alasan minimal {MIN_REASON} karakter')
    if len(text) > MAX_REASON:
        raise SwapError(400, 'reason', f'Alasan maksimal {MAX_REASON} karakter')
    return text


def validate_category(value):
    cat = str(value or '').strip().lower()
    if cat not in CATEGORIES:
        raise SwapError(400, 'category', 'Kategori pengajuan tidak dikenal')
    return cat


def normalize_swap_type(value):
    swap_type = str(value or 'exchange').strip().lower()
    if swap_type not in SWAP_TYPES:
        raise SwapError(400, 'swap_type', 'Jenis pengajuan tidak dikenal')
    return swap_type


def validate_odometer(value):
    raw = str(value if value is not None else '').strip()
    if not raw:
        raise SwapError(400, 'odometer', 'Odometer wajib diisi')
    try:
        number = int(raw)
    except (TypeError, ValueError):
        raise SwapError(400, 'odometer', 'Odometer harus berupa angka')
    if number < 0 or number > MAX_ODOMETER:
        raise SwapError(400, 'odometer',
                        f'Odometer harus antara 0 dan {MAX_ODOMETER}')
    return number


def request_code(request_id, day=None):
    day = day or date.today()
    return f'SWR-{day.strftime("%Y%m%d")}-{int(request_id):04d}'


def handover_complete(swap_type, requester_at, target_at):
    if swap_type == 'move':
        return bool(requester_at)
    return bool(requester_at and target_at)


def handover_side(req, driver_name):
    name = str(driver_name or '').strip().upper()
    if not name:
        return None
    if str(req.get('requester_driver') or '').strip().upper() == name:
        return 'requester'
    target = str(req.get('target_driver') or '').strip().upper()
    if target and target == name:
        return 'target'
    return None


def received_nopol(req, side):
    if side == 'requester':
        return str(req.get('target_nopol') or '').strip().upper()
    if side == 'target':
        return str(req.get('requester_nopol') or '').strip().upper()
    raise SwapError(403, 'forbidden', 'Anda bukan pihak pada pengajuan ini')


def _state_changed(msg='Penugasan sudah berubah — batalkan pengajuan dan buat ulang'):
    return SwapError(409, 'state_changed', msg)


def _index(assignments):
    by_driver, by_nopol = {}, {}
    for row in assignments or []:
        by_driver.setdefault(row.get('driver_name'), []).append(row)
        by_nopol.setdefault(row.get('nopol'), []).append(row)
    return by_driver, by_nopol


def _single(by_driver, name):
    rows = by_driver.get(name) or []
    if len(rows) != 1:
        raise _state_changed(f'Penugasan aktif {name} tidak tunggal')
    return rows[0]


def _patch(driver, nopol, vtype, bbm):
    return {'name': driver, 'nopol': nopol, 'vehicle_type': vtype,
            'bbm_type': bbm}


def _new_assignment(driver, nopol, vtype, bbm, notes):
    return {'driver_name': driver, 'nopol': nopol, 'vehicle_type': vtype,
            'bbm_type': bbm, 'driver_notes': notes}


def build_approve_plan(req, assignments, vehicle=None):
    """Rencana tulis untuk approve; raises SwapError bila state tidak cocok."""
    swap_type = req.get('swap_type') or 'exchange'
    requester = str(req.get('requester_driver') or '').strip().upper()
    requester_nopol = str(req.get('requester_nopol') or '').strip().upper()
    target = str(req.get('target_driver') or '').strip().upper()
    target_nopol = str(req.get('target_nopol') or '').strip().upper()
    notes = str(req.get('reason') or '').strip()

    by_driver, by_nopol = _index(assignments)
    mine = _single(by_driver, requester)
    if str(mine.get('nopol') or '').strip().upper() != requester_nopol:
        raise _state_changed('Kendaraan pengaju sudah berubah')
    if len(by_nopol.get(requester_nopol) or []) != 1:
        raise _state_changed(f'{requester_nopol} dipakai lebih dari satu pengemudi')

    if swap_type == 'exchange':
        theirs = _single(by_driver, target)
        if str(theirs.get('nopol') or '').strip().upper() != target_nopol:
            raise _state_changed('Kendaraan rekan sudah berubah')
        if len(by_nopol.get(target_nopol) or []) != 1:
            raise _state_changed(f'{target_nopol} dipakai lebih dari satu pengemudi')
        close_ids = [mine['id'], theirs['id']]
        return {
            'close_ids': close_ids,
            'new_assignments': [
                _new_assignment(requester, target_nopol,
                                theirs.get('vehicle_type'), theirs.get('bbm_type'),
                                notes),
                _new_assignment(target, requester_nopol,
                                mine.get('vehicle_type'), mine.get('bbm_type'),
                                notes),
            ],
            'driver_updates': [
                _patch(requester, target_nopol, theirs.get('vehicle_type'),
                       theirs.get('bbm_type')),
                _patch(target, requester_nopol, mine.get('vehicle_type'),
                       mine.get('bbm_type')),
            ],
            'swap_logs': [
                {'nopol': requester_nopol, 'old_driver': requester,
                 'new_driver': target},
                {'nopol': target_nopol, 'old_driver': target,
                 'new_driver': requester},
            ],
        }

    if swap_type == 'move':
        if by_nopol.get(target_nopol):
            raise _state_changed(f'{target_nopol} sudah dipakai pengemudi lain')
        if not vehicle or str(vehicle.get('nopol') or '').strip().upper() != target_nopol:
            raise _state_changed(f'Data kendaraan {target_nopol} tidak ditemukan')
        if not vehicle.get('is_active'):
            raise _state_changed(f'Kendaraan {target_nopol} tidak aktif')
        vtype = vehicle.get('vehicle_type')
        bbm = vehicle.get('bbm_default') or 'PERTALITE'
        return {
            'close_ids': [mine['id']],
            'new_assignments': [
                _new_assignment(requester, target_nopol, vtype, bbm, notes),
            ],
            'driver_updates': [_patch(requester, target_nopol, vtype, bbm)],
            'swap_logs': [
                {'nopol': requester_nopol, 'old_driver': requester,
                 'new_driver': POOL},
                {'nopol': target_nopol, 'old_driver': POOL,
                 'new_driver': requester},
            ],
        }

    raise SwapError(400, 'swap_type', 'Jenis pengajuan tidak dikenal')


def supersede_conflicts(rows, req):
    """ID pengajuan `approved` lain yang belum lengkap buktinya."""
    own_id = req.get('id')
    out = []
    for row in rows or []:
        if row.get('id') == own_id:
            continue
        if handover_complete(row.get('swap_type'),
                             row.get('requester_handover_at'),
                             row.get('target_handover_at')):
            continue
        out.append(row.get('id'))
    return out


# ============================================================
# Lapisan DB (dipakai route; tidak diuji sebagai fungsi murni)
# ============================================================

def _autocommit_off(conn):
    try:
        conn.autocommit = False
    except Exception:
        pass


def _placeholders(values):
    return ','.join(['%s'] * len(values))


def _upper(value):
    return str(value or '').strip().upper()


def active_driver_accounts(conn, names, branch_code, master_conn=None):
    """Nama driver (dari `names`) yang punya akun login driver aktif.

    `drivers.user_id` (DB cabang) → `users` DB master, syarat role='driver',
    is_active=1, dan branch_code sama dengan cabang sesi. Akun inilah yang
    dipakai driver untuk login dan mengunggah bukti serah terima.
    """
    wanted = []
    for name in names or []:
        up = _upper(name)
        if up and up not in wanted:
            wanted.append(up)
    if not wanted:
        return set()

    cur = conn.cursor(dictionary=True)
    try:
        cur.execute(
            f'SELECT name, user_id FROM drivers WHERE name IN ({_placeholders(wanted)})',
            wanted)
        rows = cur.fetchall()
    finally:
        cur.close()

    by_uid = {}
    for row in rows:
        uid = row.get('user_id')
        if uid:
            by_uid[int(uid)] = _upper(row.get('name'))
    if not by_uid:
        return set()

    own_master = master_conn is None
    if own_master:
        from modules.config import get_master_connection
        master_conn = get_master_connection()
    if not master_conn:
        return set()

    try:
        mcur = master_conn.cursor(dictionary=True)
        try:
            params = list(by_uid.keys())
            sql = (f"SELECT id FROM users WHERE id IN ({_placeholders(params)}) "
                   "AND role = 'driver' AND is_active = 1")
            if branch_code:
                sql += ' AND branch_code = %s'
                params.append(_upper(branch_code))
            mcur.execute(sql, params)
            found = {int(r['id']) for r in mcur.fetchall()}
        finally:
            mcur.close()
    finally:
        if own_master:
            try:
                master_conn.close()
            except Exception:
                pass

    return {by_uid[uid] for uid in found if uid in by_uid}


def get_request(conn, request_id):
    cur = conn.cursor(dictionary=True)
    try:
        cur.execute('SELECT * FROM assignment_swap_requests WHERE id = %s',
                    (request_id,))
        return cur.fetchone()
    finally:
        cur.close()


def list_requests(conn, driver_name=None, status=None):
    cur = conn.cursor(dictionary=True)
    try:
        sql = 'SELECT * FROM assignment_swap_requests'
        where, params = [], []
        if driver_name:
            me = _upper(driver_name)
            where.append('(requester_driver = %s OR target_driver = %s)')
            params += [me, me]
        if status:
            where.append('status = %s')
            params.append(str(status).strip().lower())
        if where:
            sql += ' WHERE ' + ' AND '.join(where)
        sql += ' ORDER BY id DESC LIMIT 200'
        cur.execute(sql, params)
        return cur.fetchall()
    finally:
        cur.close()


def _active_assignment(cur, driver_name):
    cur.execute(
        'SELECT * FROM vehicle_assignments WHERE driver_name = %s AND is_current = 1 '
        'ORDER BY id DESC', (driver_name,))
    return cur.fetchall()


def create_request(conn, driver_name, swap_type='exchange', target_driver='',
                   target_nopol='', category='driver_request', reason='',
                   branch_code='', master_conn=None):
    swap_type = normalize_swap_type(swap_type)
    category = validate_category(category)
    reason = clean_reason(reason)
    me = _upper(driver_name)
    if not me:
        raise SwapError(401, 'unauthorized', 'Login driver diperlukan')

    _autocommit_off(conn)
    cur = conn.cursor(dictionary=True)
    try:
        mine = _active_assignment(cur, me)
        if len(mine) != 1:
            raise SwapError(409, 'no_assignment',
                            'Anda harus punya tepat satu kendaraan aktif')
        requester_nopol = _upper(mine[0].get('nopol'))
        target = _upper(target_driver)
        target_nopol = _upper(target_nopol)

        if swap_type == 'exchange':
            if not target:
                raise SwapError(400, 'target_driver', 'Pilih rekan yang diajak tukar')
            if target == me:
                raise SwapError(400, 'target_driver',
                                'Tidak bisa tukar dengan diri sendiri')
            theirs = _active_assignment(cur, target)
            if len(theirs) != 1:
                raise SwapError(409, 'state_changed',
                                'Rekan tidak punya tepat satu kendaraan aktif')
            target_nopol = _upper(theirs[0].get('nopol'))
            if not target_nopol or target_nopol == requester_nopol:
                raise SwapError(400, 'target_nopol', 'Kendaraan tujuan tidak valid')
            cur.execute('SELECT nopol, is_active FROM vehicles WHERE nopol IN (%s, %s)',
                        (requester_nopol, target_nopol))
            for vehicle in cur.fetchall():
                if not vehicle.get('is_active'):
                    raise SwapError(400, 'vehicle_inactive',
                                    f"Kendaraan {vehicle.get('nopol')} tidak aktif")
            accounts = active_driver_accounts(conn, [me, target], branch_code,
                                              master_conn)
            missing = [n for n in (me, target) if n not in accounts]
            if missing:
                raise SwapError(409, 'account',
                                'Akun login driver tidak aktif: ' + ', '.join(missing))
        elif swap_type == 'move':
            if target:
                raise SwapError(400, 'target_driver',
                                'Pindah kendaraan tidak memakai rekan')
            if not target_nopol:
                raise SwapError(400, 'target_nopol', 'Pilih kendaraan kosong')
            if target_nopol == requester_nopol:
                raise SwapError(400, 'target_nopol',
                                'Kendaraan tujuan sama dengan kendaraan saat ini')
            cur.execute('SELECT nopol, vehicle_type, bbm_default, is_active '
                        'FROM vehicles WHERE nopol = %s', (target_nopol,))
            vehicle = cur.fetchone()
            if not vehicle or not vehicle.get('is_active'):
                raise SwapError(400, 'vehicle_inactive',
                                'Kendaraan tidak aktif atau tidak ditemukan')
            cur.execute('SELECT id FROM vehicle_assignments WHERE nopol = %s '
                        'AND is_current = 1 FOR UPDATE', (target_nopol,))
            if cur.fetchone():
                raise SwapError(409, 'state_changed',
                                'Kendaraan sudah dipakai pengemudi lain')
            accounts = active_driver_accounts(conn, [me], branch_code, master_conn)
            if me not in accounts:
                raise SwapError(409, 'account', 'Akun login Anda tidak aktif')

        cur.execute(
            "SELECT id FROM assignment_swap_requests WHERE status = 'pending' AND "
            '(requester_driver IN (%s, %s) OR target_driver IN (%s, %s))',
            (me, target, me, target))
        if cur.fetchone():
            raise SwapError(409, 'duplicate',
                            'Masih ada pengajuan menunggu untuk driver ini')

        cur.execute(
            'INSERT INTO assignment_swap_requests '
            '(branch_code, swap_type, requester_driver, requester_nopol, '
            ' target_driver, target_nopol, category, reason, status) '
            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 'pending')",
            (branch_code or None, swap_type, me, requester_nopol,
             target or None, target_nopol, category, reason))
        new_id = cur.lastrowid
        cur.execute('UPDATE assignment_swap_requests SET request_code = %s '
                    'WHERE id = %s', (request_code(new_id), new_id))
        conn.commit()
        return get_request(conn, new_id)
    except Exception:
        conn.rollback()
        raise
    finally:
        cur.close()


def cancel_request(conn, request_id, driver_name):
    me = _upper(driver_name)
    _autocommit_off(conn)
    cur = conn.cursor(dictionary=True)
    try:
        cur.execute('SELECT * FROM assignment_swap_requests WHERE id = %s '
                    'FOR UPDATE', (request_id,))
        row = cur.fetchone()
        if not row:
            raise SwapError(404, 'not_found', 'Pengajuan tidak ditemukan')
        if _upper(row.get('requester_driver')) != me:
            raise SwapError(403, 'forbidden',
                            'Hanya pengaju yang bisa membatalkan pengajuan')
        if row.get('status') != 'pending':
            raise SwapError(409, 'state_changed', 'Pengajuan sudah diproses')
        cur.execute("UPDATE assignment_swap_requests SET status = 'cancelled', "
                    'decided_at = NOW() WHERE id = %s', (request_id,))
        conn.commit()
        return get_request(conn, request_id)
    except Exception:
        conn.rollback()
        raise
    finally:
        cur.close()


def _conflict_rows(cur, req, names, nopols):
    params = [req.get('id')] + names + names + nopols + nopols
    cur.execute(
        "SELECT * FROM assignment_swap_requests WHERE status = 'approved' AND id <> %s "
        f'AND (requester_driver IN ({_placeholders(names)}) '
        f'OR target_driver IN ({_placeholders(names)}) '
        f'OR requester_nopol IN ({_placeholders(nopols)}) '
        f'OR target_nopol IN ({_placeholders(nopols)}))', params)
    return cur.fetchall()


def approve_request(conn, request_id, ga_name, acknowledge_supersede=False,
                    master_conn=None):
    ga = str(ga_name or '').strip() or 'GA Officer'
    _autocommit_off(conn)
    cur = conn.cursor(dictionary=True)
    try:
        cur.execute('SELECT * FROM assignment_swap_requests WHERE id = %s '
                    'FOR UPDATE', (request_id,))
        req = cur.fetchone()
        if not req:
            raise SwapError(404, 'not_found', 'Pengajuan tidak ditemukan')
        if req.get('status') != 'pending':
            raise SwapError(409, 'state_changed', 'Pengajuan sudah diproses')

        swap_type = req.get('swap_type') or 'exchange'
        requester = _upper(req.get('requester_driver'))
        target = _upper(req.get('target_driver'))
        names = [requester]
        if swap_type == 'exchange' and target:
            names.append(target)
        nopols = [_upper(req.get('requester_nopol')), _upper(req.get('target_nopol'))]

        conflicts = supersede_conflicts(_conflict_rows(cur, req, names, nopols), req)
        if conflicts and not acknowledge_supersede:
            raise SwapError(
                409, 'supersede_required',
                'Ada serah terima sebelumnya yang belum selesai',
                {'conflicts': conflicts})

        accounts = active_driver_accounts(conn, names, req.get('branch_code'),
                                          master_conn)
        missing = [n for n in names if n not in accounts]
        if missing:
            raise SwapError(409, 'state_changed',
                            'Akun driver tidak aktif: ' + ', '.join(missing))

        cur.execute(
            'SELECT * FROM vehicle_assignments WHERE is_current = 1 AND '
            f'(driver_name IN ({_placeholders(names)}) '
            f'OR nopol IN ({_placeholders(nopols)})) FOR UPDATE',
            names + nopols)
        assignments = cur.fetchall()

        vehicle = None
        if swap_type == 'move':
            cur.execute('SELECT nopol, vehicle_type, bbm_default, is_active '
                        'FROM vehicles WHERE nopol = %s', (nopols[1],))
            vehicle = cur.fetchone()

        plan = build_approve_plan(req, assignments, vehicle)

        for assignment_id in plan['close_ids']:
            cur.execute('UPDATE vehicle_assignments SET is_current = 0, '
                        'unassigned_date = CURDATE() WHERE id = %s',
                        (assignment_id,))
        for new in plan['new_assignments']:
            cur.execute(
                'INSERT INTO vehicle_assignments (driver_name, nopol, vehicle_type, '
                'bbm_type, assigned_date, is_current, confirmed_by_driver, '
                'driver_notes) VALUES (%s, %s, %s, %s, CURDATE(), 1, 0, %s)',
                (new['driver_name'], new['nopol'], new['vehicle_type'],
                 new['bbm_type'], new['driver_notes']))
        for update in plan['driver_updates']:
            cur.execute('UPDATE drivers SET nopol = %s, vehicle_type = %s, '
                        'bbm_type = %s WHERE name = %s',
                        (update['nopol'], update['vehicle_type'],
                         update['bbm_type'], update['name']))
            if cur.rowcount == 0:
                raise SwapError(409, 'state_changed',
                                f"Data driver {update['name']} tidak ditemukan")

        code = req.get('request_code') or f'SWR-{request_id}'
        for log in plan['swap_logs']:
            cur.execute(
                'INSERT INTO assignment_swaps (nopol, old_driver, new_driver, '
                'category, reason, ga_name, request_id) '
                'VALUES (%s, %s, %s, %s, %s, %s, %s)',
                (log['nopol'], log['old_driver'], log['new_driver'],
                 req.get('category'), f"[{code}] {req.get('reason')}", ga,
                 request_id))

        note = req.get('ga_note')
        if conflicts:
            note = ((note + ' ') if note else '') + \
                'Menutup pengajuan: ' + ', '.join(f'#{c}' for c in conflicts)
        cur.execute(
            "UPDATE assignment_swap_requests SET status = 'approved', ga_name = %s, "
            'ga_note = %s, decided_at = NOW(), executed_at = NOW() WHERE id = %s',
            (ga, note, request_id))
        if conflicts:
            supersede_requests_for(cur, names, nopols,
                                   f'Ditutup karena {code} disetujui',
                                   ids=conflicts)

        assert_single_active(cur, names, nopols)
        conn.commit()
        return get_request(conn, request_id)
    except Exception:
        conn.rollback()
        raise
    finally:
        cur.close()


def reject_request(conn, request_id, ga_name, note):
    note = str(note or '').strip()
    if len(note) < 3:
        raise SwapError(400, 'note', 'Catatan penolakan wajib diisi')
    ga = str(ga_name or '').strip() or 'GA Officer'
    _autocommit_off(conn)
    cur = conn.cursor(dictionary=True)
    try:
        cur.execute('SELECT * FROM assignment_swap_requests WHERE id = %s '
                    'FOR UPDATE', (request_id,))
        row = cur.fetchone()
        if not row:
            raise SwapError(404, 'not_found', 'Pengajuan tidak ditemukan')
        if row.get('status') != 'pending':
            raise SwapError(409, 'state_changed', 'Pengajuan sudah diproses')
        cur.execute(
            "UPDATE assignment_swap_requests SET status = 'rejected', ga_name = %s, "
            'ga_note = %s, decided_at = NOW() WHERE id = %s',
            (ga, note, request_id))
        conn.commit()
        return get_request(conn, request_id)
    except Exception:
        conn.rollback()
        raise
    finally:
        cur.close()


def supersede_requests_for(cur, drivers, nopols, note, ids=None):
    """Tutup pengajuan pending/approved yang tersentuh perubahan assignment."""
    drivers = [_upper(d) for d in (drivers or []) if _upper(d)]
    nopols = [_upper(n) for n in (nopols or []) if _upper(n)]
    if not drivers and not nopols:
        return 0
    sql = ("UPDATE assignment_swap_requests SET status = 'superseded', "
           'ga_note = %s, decided_at = NOW() WHERE '
           "status IN ('pending', 'approved')")
    params = [note]
    if ids is not None:
        if not ids:
            return 0
        sql += f' AND id IN ({_placeholders(ids)})'
        params += list(ids)
    bits = []
    if drivers:
        bits.append(f'requester_driver IN ({_placeholders(drivers)})')
        bits.append(f'target_driver IN ({_placeholders(drivers)})')
        params += drivers + drivers
    if nopols:
        bits.append(f'requester_nopol IN ({_placeholders(nopols)})')
        bits.append(f'target_nopol IN ({_placeholders(nopols)})')
        params += nopols + nopols
    sql += ' AND (' + ' OR '.join(bits) + ')'
    cur.execute(sql, params)
    return cur.rowcount or 0


def assert_single_active(cur, drivers, nopols):
    """Gagal bila satu driver/nopol punya lebih dari satu assignment aktif."""
    drivers = [_upper(d) for d in (drivers or []) if _upper(d)]
    nopols = [_upper(n) for n in (nopols or []) if _upper(n)]
    if drivers:
        cur.execute(
            'SELECT 1 FROM vehicle_assignments WHERE is_current = 1 AND '
            f'driver_name IN ({_placeholders(drivers)}) '
            'GROUP BY driver_name HAVING COUNT(*) > 1', drivers)
        if cur.fetchall():
            raise SwapError(409, 'invariant_violation',
                            'Satu driver memiliki lebih dari satu kendaraan aktif')
    if nopols:
        cur.execute(
            'SELECT 1 FROM vehicle_assignments WHERE is_current = 1 AND '
            f'nopol IN ({_placeholders(nopols)}) '
            'GROUP BY nopol HAVING COUNT(*) > 1', nopols)
        if cur.fetchall():
            raise SwapError(409, 'invariant_violation',
                            'Satu kendaraan dipakai lebih dari satu driver')


def submit_handover(conn, request_id, driver_name, odometer, photo):
    odo = validate_odometer(odometer)
    me = _upper(driver_name)
    if not photo:
        raise SwapError(400, 'photo', 'Foto kendaraan wajib diunggah')
    _autocommit_off(conn)
    cur = conn.cursor(dictionary=True)
    try:
        cur.execute('SELECT * FROM assignment_swap_requests WHERE id = %s '
                    'FOR UPDATE', (request_id,))
        req = cur.fetchone()
        if not req:
            raise SwapError(404, 'not_found', 'Pengajuan tidak ditemukan')
        if req.get('status') != 'approved':
            raise SwapError(409, 'state_changed',
                            'Pengajuan belum disetujui atau sudah selesai')
        side = handover_side(req, me)
        if not side:
            raise SwapError(403, 'forbidden',
                            'Anda bukan pihak pada pengajuan ini')
        photo_col = f'{side}_photo'
        if req.get(photo_col):
            raise SwapError(409, 'already_submitted',
                            'Bukti sisi Anda sudah dikirim')
        nopol = received_nopol(req, side)
        cur.execute('SELECT id FROM vehicle_assignments WHERE driver_name = %s '
                    'AND nopol = %s AND is_current = 1 FOR UPDATE', (me, nopol))
        assignment = cur.fetchone()
        if not assignment:
            cur.execute(
                "UPDATE assignment_swap_requests SET status = 'superseded', "
                'ga_note = %s WHERE id = %s',
                ('Assignment berubah sebelum serah terima', request_id))
            conn.commit()
            raise SwapError(409, 'state_changed',
                            'Penugasan sudah berubah — pengajuan ditutup')

        cur.execute(
            f'UPDATE assignment_swap_requests SET {side}_odo = %s, '
            f'{side}_photo = %s, {side}_handover_at = NOW() WHERE id = %s',
            (odo, photo, request_id))
        cur.execute('UPDATE vehicle_assignments SET confirmed_by_driver = 1, '
                    'confirmed_at = NOW() WHERE id = %s', (assignment['id'],))

        req = get_request(conn, request_id)
        if handover_complete(req.get('swap_type'),
                             req.get('requester_handover_at'),
                             req.get('target_handover_at')):
            cur.execute("UPDATE assignment_swap_requests SET status = 'completed', "
                        'completed_at = NOW() WHERE id = %s', (request_id,))
        conn.commit()
        return get_request(conn, request_id)
    except Exception:
        conn.rollback()
        raise
    finally:
        cur.close()


def fetch_context(conn, driver_name, branch_code, master_conn=None):
    me = _upper(driver_name)
    cur = conn.cursor(dictionary=True)
    try:
        mine = _active_assignment(cur, me)
        cur.execute(
            'SELECT v.nopol, v.vehicle_type, '
            "COALESCE(v.bbm_default, 'PERTALITE') AS bbm_type FROM vehicles v "
            "WHERE v.is_active = 1 AND v.nopol IS NOT NULL AND v.nopol <> '' "
            'AND v.nopol NOT IN (SELECT nopol FROM vehicle_assignments '
            'WHERE is_current = 1) ORDER BY v.nopol')
        free_vehicles = cur.fetchall()
        cur.execute(
            'SELECT driver_name, nopol, vehicle_type FROM vehicle_assignments '
            'WHERE is_current = 1 AND driver_name <> %s ORDER BY driver_name',
            (me,))
        others = cur.fetchall()
    finally:
        cur.close()

    accounts = active_driver_accounts(conn, [r.get('driver_name') for r in others],
                                      branch_code, master_conn)
    partners = [r for r in others
                if _upper(r.get('driver_name')) in accounts]
    current = mine[0] if len(mine) == 1 else None
    return {
        'me': ({'driver': me, 'nopol': _upper(current.get('nopol')),
                'vehicle_type': current.get('vehicle_type')}
               if current else None),
        'free_vehicles': free_vehicles,
        'partners': partners,
        'requests': list_requests(conn, me),
    }


def handover_request_for(conn, driver_name, nopol):
    """ID pengajuan approved yang menunggu bukti sisi driver untuk nopol ini."""
    me = _upper(driver_name)
    nopol = _upper(nopol)
    cur = conn.cursor(dictionary=True)
    try:
        cur.execute("SELECT * FROM assignment_swap_requests WHERE status = 'approved' "
                    'ORDER BY id DESC LIMIT 200')
        for row in cur.fetchall():
            side = handover_side(row, me)
            if not side:
                continue
            if received_nopol(row, side) != nopol:
                continue
            if row.get(f'{side}_photo'):
                continue
            return row.get('id')
    finally:
        cur.close()
    return None
