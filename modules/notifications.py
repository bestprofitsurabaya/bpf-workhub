"""Driver notification store + real-time push.

Notifications are persisted so the PWA can catch up on anything the driver
missed while offline, and pushed live via SocketIO when a driver device is open.
"""
from datetime import datetime

from modules.config import get_db_connection
from modules.realtime import emit_driver


def ensure_notifications_table(conn=None):
    """CREATE TABLE IF NOT EXISTS - safe to run at every startup.

    conn opsional: bila diberikan, dipakai langsung (mis. untuk DB cabang)
    dan tidak ditutup di sini.
    """
    own = conn is None
    try:
        if conn is None:
            conn = get_db_connection()
        if not conn:
            return
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS notifications (
                id INT AUTO_INCREMENT PRIMARY KEY,
                driver_name VARCHAR(100) NOT NULL,
                type VARCHAR(20) NOT NULL,
                action VARCHAR(30) NOT NULL,
                message VARCHAR(255) NOT NULL,
                ref_id VARCHAR(60) DEFAULT NULL,
                is_read TINYINT(1) DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                KEY idx_driver_read (driver_name, is_read),
                KEY idx_created (created_at)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """)
        conn.commit()
        # Prune read notifications older than 30 days
        try:
            cursor.execute("DELETE FROM notifications WHERE is_read=1 AND created_at < (NOW() - INTERVAL 30 DAY)")
            conn.commit()
        except Exception as pe:
            print(f"[notifications] prune error: {pe}")
        cursor.close()
        if own and conn:
            conn.close()
    except Exception as e:
        print(f"[notifications] ensure table error: {e}")


def push_driver_notification(driver_name, ntype, action, message, ref_id=None):
    """Persist a notification for a driver and push it live via SocketIO."""
    if not driver_name:
        return None
    driver = str(driver_name).strip().upper()
    notif_id = None
    created = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    conn = None
    cursor = None
    push_subs = []
    try:
        conn = get_db_connection()
        if conn:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO notifications (driver_name, type, action, message, ref_id, created_at) "
                "VALUES (%s, %s, %s, %s, %s, %s)",
                (driver, ntype, action, str(message)[:255], ref_id, created),
            )
            conn.commit()
            notif_id = cursor.lastrowid
            # v2.128.0: ambil langganan Web Push driver (best-effort; tabel
            # belum ada di DB lama → lewati). Dikirim di latar belakang agar
            # request bisnis tidak menunggu jaringan push.
            try:
                pc = conn.cursor(dictionary=True)
                pc.execute(
                    "SELECT endpoint, p256dh, auth FROM push_subscriptions WHERE driver_name=%s",
                    (driver,),
                )
                push_subs = pc.fetchall() or []
                pc.close()
            except Exception:
                push_subs = []
    except Exception as e:
        print(f"[notifications] push error: {e}")
    finally:
        if cursor:
            try: cursor.close()
            except Exception: pass
        if conn:
            try: conn.close()
            except Exception: pass

    emit_driver(driver, {
        'id': notif_id,
        'driver_name': driver,
        'type': ntype,
        'action': action,
        'message': str(message)[:255],
        'ref_id': ref_id,
        'created_at': created,
    })
    # v2.128.0: jangkau perangkat saat aplikasi tertutup (Android Chrome,
    # iOS >= 16.4 PWA). Kegagalan push tidak memengaruhi notifikasi in-app.
    if push_subs:
        try:
            from modules import webpush
            webpush.send_to_driver_async(driver, 'BPF WorkHub',
                                         str(message)[:255], '/app/driver',
                                         subs=push_subs)
        except Exception as e:
            print(f"[notifications] webpush hook: {e}")
    return notif_id


def push_marketing_notification(username, ntype, action, message, ref_id=None):
    """Persist + realtime-push notifikasi untuk user marketing (reuse tabel notifications).

    Emit ke room marketing_<username> sehingga halaman marketing menerima update langsung.
    """
    if not username:
        return None
    user = str(username).strip().lower()
    notif_id = None
    created = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        if conn:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO notifications (driver_name, type, action, message, ref_id, created_at) "
                "VALUES (%s, %s, %s, %s, %s, %s)",
                (user, ntype, action, str(message)[:255], ref_id, created),
            )
            conn.commit()
            notif_id = cursor.lastrowid
    except Exception as e:
        print(f"[notifications] push_marketing error: {e}")
    finally:
        if cursor:
            try: cursor.close()
            except Exception: pass
        if conn:
            try: conn.close()
            except Exception: pass

    from modules.realtime import emit_event
    emit_event('appointment_update', {
        'id': notif_id,
        'username': user,
        'type': ntype,
        'action': action,
        'message': str(message)[:255],
        'ref_id': ref_id,
        'created_at': created,
    }, room='marketing_' + user)
    return notif_id


def push_overtime_notification(ntype, action, message, ref_id=None, count=0):
    """Persist + realtime-push notifikasi untuk GA HR/Admin (tabel notifications).

    Dikirim saat sinkronisasi sheet Driver menemukan data baru (v2.22.1):
    GA HR yang sedang online menerima update langsung via room ga_hr_board;
    yang offline tetap bisa melihatnya di daftar notifikasi setelah login.
    """
    notif_id = None
    created = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        if conn:
            cursor = conn.cursor()
            # Simpan sekali dengan driver_name='GA HR' sebagai penampung umum
            cursor.execute(
                "INSERT INTO notifications (driver_name, type, action, message, ref_id, created_at) "
                "VALUES (%s, %s, %s, %s, %s, %s)",
                ('GA HR', ntype, action, str(message)[:255], ref_id, created),
            )
            conn.commit()
            notif_id = cursor.lastrowid
    except Exception as e:
        print(f"[notifications] push_overtime error: {e}")
    finally:
        if cursor:
            try: cursor.close()
            except Exception: pass
        if conn:
            try: conn.close()
            except Exception: pass

    from modules.realtime import emit_event
    emit_event('overtime_new', {
        'id': notif_id,
        'type': ntype,
        'action': action,
        'message': str(message)[:255],
        'ref_id': ref_id,
        'count': count,
        'created_at': created,
    }, room='ga_hr_board')
    return notif_id
