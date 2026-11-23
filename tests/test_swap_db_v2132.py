"""v2.132.0 — uji service terhadap MariaDB scratch (bukan DB produksi)."""
import re
import sys
import os
import uuid
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import pytest

from modules.config import get_master_connection, get_db_connection_by_name
from modules import assignment_swap_service as svc

INIT = Path(__file__).resolve().parent.parent / 'init.sql'


def _ddl(table):
    sql = INIT.read_text(encoding='utf-8')
    m = re.search(
        r'(CREATE TABLE IF NOT EXISTS %s.*?ENGINE=InnoDB[^;]*;)' % table,
        sql, re.S)
    assert m, table
    return m.group(1)


@pytest.fixture()
def db():
    try:
        admin = get_master_connection()
    except Exception as exc:  # DB tidak tersedia di lingkungan ini
        pytest.skip(f'DB tidak tersedia: {exc}')
    name = f'bpf_test_swap_{uuid.uuid4().hex[:8]}'
    cur = admin.cursor()
    cur.execute(f'CREATE DATABASE `{name}`')
    conn = get_db_connection_by_name(name)
    c = conn.cursor()
    c.execute('''CREATE TABLE users (
        id INT PRIMARY KEY, username VARCHAR(50), full_name VARCHAR(100),
        role VARCHAR(30), branch_code VARCHAR(20), is_active TINYINT(1))''')
    c.execute('''CREATE TABLE drivers (
        id INT AUTO_INCREMENT PRIMARY KEY, name VARCHAR(100), nopol VARCHAR(20),
        vehicle_type VARCHAR(50), bbm_type VARCHAR(50), is_active TINYINT(1),
        user_id INT NULL)''')
    c.execute('''CREATE TABLE vehicles (
        id INT AUTO_INCREMENT PRIMARY KEY, nopol VARCHAR(20),
        vehicle_type VARCHAR(50), bbm_default VARCHAR(50),
        is_active TINYINT(1))''')
    c.execute('''CREATE TABLE vehicle_assignments (
        id INT AUTO_INCREMENT PRIMARY KEY, driver_name VARCHAR(100),
        nopol VARCHAR(20), vehicle_type VARCHAR(50), bbm_type VARCHAR(50),
        assigned_date DATE, unassigned_date DATE, is_current TINYINT(1),
        confirmed_by_driver TINYINT(1) DEFAULT 0, confirmed_at DATETIME NULL,
        driver_notes TEXT NULL)''')
    c.execute(_ddl('assignment_swaps'))
    c.execute(_ddl('assignment_swap_requests'))
    c.execute('''INSERT INTO users VALUES
        (1,'a','A','driver','SBY',1),
        (2,'b','B','driver','SBY',1),
        (3,'x','X','driver','SBY',0),
        (4,'ga','GA','ga','SBY',1)''')
    c.execute('''INSERT INTO drivers (id,name,nopol,vehicle_type,bbm_type,is_active,user_id) VALUES
        (1,'A','X','AVANZA','PERTALITE',1,1),
        (2,'B','Y','INNOVA','PERTAMAX',1,2),
        (3,'X','Z','AVANZA','PERTALITE',1,3)''')
    c.execute('''INSERT INTO vehicles (nopol,vehicle_type,bbm_default,is_active) VALUES
        ('X','AVANZA','PERTALITE',1),('Y','INNOVA','PERTAMAX',1),
        ('Z','AVANZA','PERTALITE',1),('OLD','AVANZA','PERTALITE',0)''')
    c.execute('''INSERT INTO vehicle_assignments
        (id,driver_name,nopol,vehicle_type,bbm_type,assigned_date,is_current,confirmed_by_driver)
        VALUES (1,'A','X','AVANZA','PERTALITE',CURDATE(),1,1),
               (2,'B','Y','INNOVA','PERTAMAX',CURDATE(),1,1)''')
    conn.commit()
    c.close()
    try:
        yield conn
    finally:
        try:
            conn.close()
        except Exception:
            pass
        cur.execute(f'DROP DATABASE IF EXISTS `{name}`')
        cur.close()
        admin.close()


def create(conn, **over):
    args = dict(driver_name='A', swap_type='exchange', target_driver='B',
                target_nopol='', category='driver_request',
                reason='ban depan sudah aus', branch_code='SBY',
                master_conn=conn)
    args.update(over)
    return svc.create_request(conn, **args)


def ids(cur, sql, params=()):
    cur.execute(sql, params)
    return [r['id'] if isinstance(r, dict) else r[0] for r in cur.fetchall()]


class TestCreate:
    def test_exchange_sukses_dan_terlihat_dua_pihak(self, db):
        row = create(db)
        assert row['swap_type'] == 'exchange'
        assert row['requester_nopol'] == 'X'
        assert row['target_nopol'] == 'Y'
        assert row['status'] == 'pending'
        assert re.fullmatch(r'SWR-\d{8}-0001', row['request_code'])
        assert len(svc.list_requests(db, 'A')) == 1
        assert len(svc.list_requests(db, 'B')) == 1
        assert svc.list_requests(db, 'Z') == []

    def test_move_ke_kendaraan_kosong(self, db):
        row = create(db, swap_type='move', target_driver='', target_nopol='Z')
        assert row['target_driver'] is None
        assert row['target_nopol'] == 'Z'
        assert row['requester_nopol'] == 'X'

    def test_move_ke_kendaraan_terisi_ditolak(self, db):
        with pytest.raises(svc.SwapError) as e:
            create(db, swap_type='move', target_driver='', target_nopol='Y')
        assert e.value.http_status == 409

    def test_target_tanpa_akun_aktif_ditolak(self, db):
        c = db.cursor()
        c.execute("UPDATE users SET is_active=0 WHERE id=2")
        db.commit()
        with pytest.raises(svc.SwapError) as e:
            create(db)
        assert e.value.code == 'account'
        c.close()

    def test_duplikat_pending_ditolak(self, db):
        create(db)
        with pytest.raises(svc.SwapError) as e:
            create(db)
        assert e.value.http_status == 409

    def test_alasan_pendek_ditolak(self, db):
        with pytest.raises(svc.SwapError) as e:
            create(db, reason='pendek')
        assert e.value.code == 'reason'


class TestCancel:
    def test_pengaju_bisa_batalkan(self, db):
        row = create(db)
        out = svc.cancel_request(db, row['id'], 'A')
        assert out['status'] == 'cancelled'

    def test_bukan_pengaju_tidak_bisa(self, db):
        row = create(db)
        with pytest.raises(svc.SwapError) as e:
            svc.cancel_request(db, row['id'], 'B')
        assert e.value.http_status == 403


class TestApprove:
    def test_exchange_memindahkan_dua_kendaraan(self, db):
        row = create(db)
        out = svc.approve_request(db, row['id'], 'GA', master_conn=db)
        assert out['status'] == 'approved'
        c = db.cursor(dictionary=True)
        c.execute('''SELECT driver_name,nopol FROM vehicle_assignments
                     WHERE is_current=1 ORDER BY driver_name''')
        assert c.fetchall() == [{'driver_name': 'A', 'nopol': 'Y'},
                                {'driver_name': 'B', 'nopol': 'X'}]
        c.execute('SELECT nopol,old_driver,new_driver,request_id FROM assignment_swaps ORDER BY id')
        logs = c.fetchall()
        assert logs == [
            {'nopol': 'X', 'old_driver': 'A', 'new_driver': 'B', 'request_id': row['id']},
            {'nopol': 'Y', 'old_driver': 'B', 'new_driver': 'A', 'request_id': row['id']},
        ]
        c.execute('SELECT name,nopol,vehicle_type,bbm_type FROM drivers ORDER BY name')
        assert c.fetchall() == [
            {'name': 'A', 'nopol': 'Y', 'vehicle_type': 'INNOVA', 'bbm_type': 'PERTAMAX'},
            {'name': 'B', 'nopol': 'X', 'vehicle_type': 'AVANZA', 'bbm_type': 'PERTALITE'},
            {'name': 'X', 'nopol': 'Z', 'vehicle_type': 'AVANZA', 'bbm_type': 'PERTALITE'},
        ]
        c.close()

    def test_move_melepas_kendaraan_lama_ke_pool(self, db):
        row = create(db, swap_type='move', target_driver='', target_nopol='Z')
        svc.approve_request(db, row['id'], 'GA', master_conn=db)
        c = db.cursor(dictionary=True)
        c.execute("SELECT driver_name,nopol FROM vehicle_assignments WHERE is_current=1 ORDER BY driver_name")
        assert c.fetchall() == [{'driver_name': 'A', 'nopol': 'Z'},
                                {'driver_name': 'B', 'nopol': 'Y'}]
        c.execute('SELECT nopol,old_driver,new_driver FROM assignment_swaps ORDER BY id')
        assert c.fetchall() == [
            {'nopol': 'X', 'old_driver': 'A', 'new_driver': '- (Pool)'},
            {'nopol': 'Z', 'old_driver': '- (Pool)', 'new_driver': 'A'},
        ]
        c.close()

    def test_state_berubah_ditolak(self, db):
        row = create(db)
        c = db.cursor()
        c.execute("UPDATE vehicle_assignments SET nopol='Z' WHERE id=2")
        db.commit()
        with pytest.raises(svc.SwapError) as e:
            svc.approve_request(db, row['id'], 'GA', master_conn=db)
        assert e.value.code == 'state_changed'
        c.close()

    def test_konflik_butuh_acknowledge(self, db):
        first = create(db)
        svc.approve_request(db, first['id'], 'GA', master_conn=db)
        second = create(db)
        with pytest.raises(svc.SwapError) as e:
            svc.approve_request(db, second['id'], 'GA', master_conn=db)
        assert e.value.code == 'supersede_required'
        assert e.value.extra['conflicts']
        out = svc.approve_request(db, second['id'], 'GA',
                                  acknowledge_supersede=True, master_conn=db)
        assert out['status'] == 'approved'
        c = db.cursor(dictionary=True)
        c.execute('SELECT status FROM assignment_swap_requests WHERE id=%s', (first['id'],))
        assert c.fetchone()['status'] == 'superseded'
        c.close()


class TestReject:
    def test_catatan_wajib(self, db):
        row = create(db)
        with pytest.raises(svc.SwapError):
            svc.reject_request(db, row['id'], 'GA', '  ')
        out = svc.reject_request(db, row['id'], 'GA', 'kendaraan masih dipakai')
        assert out['status'] == 'rejected'


class TestHandover:
    def test_exchange_butuh_dua_bukti(self, db):
        row = create(db)
        svc.approve_request(db, row['id'], 'GA', master_conn=db)
        first = svc.submit_handover(db, row['id'], 'A', 1000, 'a.jpg')
        assert first['status'] == 'approved'
        second = svc.submit_handover(db, row['id'], 'B', 2000, 'b.jpg')
        assert second['status'] == 'completed'

    def test_move_cukup_satu_bukti(self, db):
        row = create(db, swap_type='move', target_driver='', target_nopol='Z')
        svc.approve_request(db, row['id'], 'GA', master_conn=db)
        out = svc.submit_handover(db, row['id'], 'A', 1234, 'a.jpg')
        assert out['status'] == 'completed'

    def test_bukan_pihak_ditolak(self, db):
        row = create(db)
        svc.approve_request(db, row['id'], 'GA', master_conn=db)
        with pytest.raises(svc.SwapError) as e:
            svc.submit_handover(db, row['id'], 'X', 1000, 'x.jpg')
        assert e.value.http_status == 403

    def test_kirim_ganda_ditolak(self, db):
        row = create(db)
        svc.approve_request(db, row['id'], 'GA', master_conn=db)
        svc.submit_handover(db, row['id'], 'A', 1000, 'a.jpg')
        with pytest.raises(svc.SwapError) as e:
            svc.submit_handover(db, row['id'], 'A', 1001, 'a2.jpg')
        assert e.value.http_status == 409


class TestInvariant:
    def test_assignment_ganda_terdeteksi(self, db):
        c = db.cursor()
        c.execute("""INSERT INTO vehicle_assignments
            (driver_name,nopol,vehicle_type,bbm_type,assigned_date,is_current)
            VALUES ('A','Z','AVANZA','PERTALITE',CURDATE(),1)""")
        db.commit()
        with pytest.raises(svc.SwapError) as e:
            svc.assert_single_active(c, ['A'], ['X', 'Z'])
        assert e.value.code == 'invariant_violation'
        c.close()

    def test_supersede_alur_lama(self, db):
        row = create(db)
        c = db.cursor()
        n = svc.supersede_requests_for(c, ['A', 'B'], ['X', 'Y'],
                                       'Penugasan diubah oleh GA')
        db.commit()
        c.close()
        assert n == 1
        c = db.cursor(dictionary=True)
        c.execute('SELECT status, ga_note FROM assignment_swap_requests WHERE id=%s', (row['id'],))
        got = c.fetchone()
        assert got['status'] == 'superseded'
        assert 'GA' in got['ga_note']
        c.close()
