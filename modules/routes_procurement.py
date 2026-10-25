"""Procurement Routes (v2.70.0) — Modul Pengadaan / Purchase Order.

Alur (proposisi ERP dasar: dokumen pembelian terkontrol di BPF WorkHub):
1. Admin/Finance mengelola master Supplier (tambah/ubah/nonaktifkan).
2. GA (atau Finance/Admin) membuat Purchase Order: supplier, tanggal
   pengajuan, dan rincian item (deskripsi, qty, satuan, harga satuan).
   Nomor PO: PO-SBY-YYYYMMDD-NNNN (doc_sequences, prefix 'PO').
3. Penerimaan (Goods Receipt): pihak penerima (GA/Finance/Admin) mencatat
   qty diterima per item — bisa bertahap (parsial). PO otomatis 'partial'
   (sebagian terima) dan 'closed' saat semua item terpenuhi.
   Pembatalan PO 'open'/'partial' — wajib alasan, masuk audit log.

Konvensi mengikuti modul lain (air minum dsb.):
- Semua tabel per-cabang (CREATE TABLE IF NOT EXISTS di master + tiap DB
  cabang via app.py startup).
- role_required + log_activity_async (jejak audit lengkap).
- Step-up PIN untuk aksi destruktif (nonaktifkan supplier, batalkan PO).
"""
from datetime import datetime

from flask import request, jsonify, session

from modules.config import get_db_connection
from modules.helpers import (
    role_required, log_activity_async, generate_display_id, client_ip,
)
from modules.stepup import stepup_required

PROC_ROLES = ['ga', 'finance', 'admin']            # pemakai modul pengadaan
PROC_EDIT_ROLES = ['finance', 'admin']             # master supplier & batalkan PO
PROC_RECEIVE_ROLES = ['ga', 'finance', 'admin']    # catat penerimaan barang

VALID_SATUAN = {'pcs', 'unit', 'dus', 'box', 'kaleng', 'botol', 'galon',
                'karung', 'liter', 'kg', 'set', 'paket'}
PO_STATUSES = ('open', 'partial', 'closed', 'cancelled')


def _session_name():
    return (session.get('full_name') or session.get('user_name') or '').strip()


def _norm_items(raw):
    """Validasi & normalisasi rincian item PO dari klien. Returns (items, err)."""
    if not isinstance(raw, list) or not raw:
        return None, 'Rincian item kosong'
    items = []
    for idx, it in enumerate(raw, 1):
        desc = str((it or {}).get('description', '')).strip()
        if not desc or len(desc) > 200:
            return None, f'Item #{idx}: deskripsi wajib diisi (maks. 200 karakter)'
        try:
            qty = int(it.get('qty'))
        except (TypeError, ValueError):
            return None, f'Item #{idx}: jumlah (qty) harus bilangan positif'
        if qty < 1:
            return None, f'Item #{idx}: jumlah (qty) minimal 1'
        satuan = str(it.get('satuan') or 'unit').strip().lower()
        if satuan not in VALID_SATUAN:
            return None, f'Item #{idx}: satuan tidak dikenal ({satuan})'
        try:
            price = float(it.get('price') or 0)
        except (TypeError, ValueError):
            return None, f'Item #{idx}: harga harus angka'
        if price < 0:
            return None, f'Item #{idx}: harga tidak boleh negatif'
        items.append({'description': desc, 'qty': qty,
                      'satuan': satuan, 'price': round(price, 2)})
    return items, None


def ensure_procurement_schema(conn=None):
    """Migrasi skema pengadaan (idempoten) — dipanggil app.py di startup.

    Mengikuti pola ensure_* lain: conn opsional; bila diberikan dipakai
    langsung (mis. koneksi DB cabang dari loop startup branches) dan tidak
    ditutup di sini.
    """
    own = conn is None
    try:
        if conn is None:
            conn = get_db_connection()
        if not conn:
            print('[procurement-schema] DB unavailable, skip migration')
            return False
        cur = conn.cursor()

        # --- suppliers: master pemasok ---
        cur.execute("""
            CREATE TABLE IF NOT EXISTS suppliers (
                id INT AUTO_INCREMENT PRIMARY KEY,
                name VARCHAR(150) NOT NULL UNIQUE,
                category VARCHAR(100) DEFAULT '',
                contact_name VARCHAR(100) DEFAULT '',
                phone VARCHAR(50) DEFAULT '',
                address VARCHAR(300) DEFAULT '',
                is_active TINYINT(1) DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                INDEX idx_sup_active (is_active, name)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """)

        # --- purchase_orders: dokumen PO ---
        cur.execute("""
            CREATE TABLE IF NOT EXISTS purchase_orders (
                id INT AUTO_INCREMENT PRIMARY KEY,
                display_id VARCHAR(30) NOT NULL UNIQUE,
                supplier_id INT NULL,
                supplier_name VARCHAR(150) NOT NULL,
                order_date DATE NOT NULL,
                status ENUM('open','partial','closed','cancelled') DEFAULT 'open',
                notes VARCHAR(500) DEFAULT '',
                created_by VARCHAR(100) NOT NULL,
                cancelled_by VARCHAR(100) DEFAULT '',
                cancel_reason VARCHAR(500) DEFAULT '',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                INDEX idx_po_status (status),
                INDEX idx_po_date (order_date),
                INDEX idx_po_supplier (supplier_name)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """)

        # --- po_items: rincian barang PO ---
        cur.execute("""
            CREATE TABLE IF NOT EXISTS po_items (
                id INT AUTO_INCREMENT PRIMARY KEY,
                po_id INT NOT NULL,
                description VARCHAR(200) NOT NULL,
                qty INT NOT NULL DEFAULT 1,
                satuan VARCHAR(20) DEFAULT 'unit',
                price DECIMAL(12,2) DEFAULT 0,
                CONSTRAINT fk_poi_po FOREIGN KEY (po_id)
                    REFERENCES purchase_orders(id) ON DELETE CASCADE,
                INDEX idx_poi_po (po_id)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """)

        # --- po_receipts: jejak penerimaan per item (append-only) ---
        cur.execute("""
            CREATE TABLE IF NOT EXISTS po_receipts (
                id INT AUTO_INCREMENT PRIMARY KEY,
                po_id INT NOT NULL,
                item_id INT NOT NULL,
                qty INT NOT NULL,
                note VARCHAR(300) DEFAULT '',
                received_by VARCHAR(100) NOT NULL,
                received_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                CONSTRAINT fk_rec_po FOREIGN KEY (po_id)
                    REFERENCES purchase_orders(id) ON DELETE CASCADE,
                CONSTRAINT fk_rec_item FOREIGN KEY (item_id)
                    REFERENCES po_items(id) ON DELETE CASCADE,
                INDEX idx_rec_po (po_id)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """)

        try:
            conn.commit()
        except Exception:
            pass
        cur.close()
        print("✔ Procurement schema ready")
        return True
    except Exception as e:
        print(f"[procurement-schema] error: {e}")
        return False
    finally:
        if own and conn:
            try:
                conn.close()
            except Exception:
                pass


# ---------------------------------------------------------------------------
# Helpers query (dipakai ulang list & detail)
# ---------------------------------------------------------------------------

def _po_with_items(cur, po_row):
    """Lengkapi satu baris PO: items + total + qty diterima per item."""
    cur.execute("SELECT * FROM po_items WHERE po_id=%s ORDER BY id", (po_row['id'],))
    items = cur.fetchall()
    total = 0.0
    for it in items:
        total += float(it['qty']) * float(it['price'])
    cur.execute("""SELECT item_id, COALESCE(SUM(qty),0) AS received
                   FROM po_receipts WHERE po_id=%s GROUP BY item_id""", (po_row['id'],))
    received_map = {r['item_id']: int(r['received']) for r in cur.fetchall()}
    for it in items:
        it['received'] = received_map.get(it['id'], 0)
        it['outstanding'] = max(0, int(it['qty']) - it['received'])
    cur.execute("SELECT * FROM po_receipts WHERE po_id=%s ORDER BY id DESC",
                (po_row['id'],))
    receipts = cur.fetchall()
    po_row['items'] = items
    po_row['receipts'] = receipts
    po_row['total_amount'] = round(total, 2)
    return po_row


def _recompute_status(cur, po_id):
    """Hitung ulang status PO dari kuantitas terima. Return status baru."""
    cur.execute("""SELECT i.qty, COALESCE((SELECT SUM(r.qty) FROM po_receipts r
                   WHERE r.item_id=i.id),0) AS received
                   FROM po_items i WHERE i.po_id=%s""", (po_id,))
    rows = cur.fetchall()
    if not rows:
        return 'open'
    fully = all(int(r['received']) >= int(r['qty']) for r in rows)
    any_ = any(int(r['received']) > 0 for r in rows)
    if fully:
        return 'closed'
    return 'partial' if any_ else 'open'


def register_procurement_routes(app):
    # ============================================================
    # MASTER SUPPLIER
    # ============================================================
    @app.route('/api/procurement/suppliers')
    @role_required(PROC_ROLES)
    def api_proc_suppliers():
        """Daftar supplier. ?all=1 ikut sertakan yang nonaktif."""
        try:
            conn = get_db_connection()
            if not conn:
                return jsonify({'error': 'DB error'}), 500
            cur = conn.cursor(dictionary=True)
            show_all = (request.args.get('all') == '1')
            q = "SELECT * FROM suppliers"
            if not show_all:
                q += " WHERE is_active=1"
            q += " ORDER BY name"
            cur.execute(q)
            rows = cur.fetchall()
            cur.execute("""SELECT COUNT(*) AS n FROM purchase_orders
                           WHERE status IN ('open','partial')""")
            open_pos = cur.fetchone()['n']
            cur.close(); conn.close()
            return jsonify({'suppliers': rows, 'open_pos': int(open_pos)})
        except Exception as e:
            return jsonify({'error': str(e)}), 500

    @app.route('/api/procurement/suppliers', methods=['POST'])
    @role_required(PROC_EDIT_ROLES)
    def api_proc_supplier_create():
        """Tambah supplier baru (Finance/Admin)."""
        try:
            data = request.get_json(silent=True) or {}
            name = str(data.get('name') or '').strip()
            if not name or len(name) > 150:
                return jsonify({'error': 'Nama supplier wajib diisi (maks. 150 karakter)'}), 400
            conn = get_db_connection()
            if not conn:
                return jsonify({'error': 'DB error'}), 500
            cur = conn.cursor(dictionary=True)
            cur.execute("SELECT id FROM suppliers WHERE name=%s", (name,))
            if cur.fetchone():
                cur.close(); conn.close()
                return jsonify({'error': f'Supplier "{name}" sudah ada'}), 400
            cur.execute("""INSERT INTO suppliers
                           (name, category, contact_name, phone, address)
                           VALUES (%s,%s,%s,%s,%s)""",
                        (name, str(data.get('category') or '').strip()[:100],
                         str(data.get('contact_name') or '').strip()[:100],
                         str(data.get('phone') or '').strip()[:50],
                         str(data.get('address') or '').strip()[:300]))
            new_id = cur.lastrowid
            conn.commit(); cur.close(); conn.close()
            log_activity_async(0, 'procurement_supplier_create',
                               session.get('user_role', ''), _session_name(),
                               new_data={'name': name}, ip=client_ip())
            return jsonify({'status': 'success', 'id': new_id})
        except Exception as e:
            return jsonify({'error': str(e)}), 500

    @app.route('/api/procurement/suppliers/<int:supplier_id>', methods=['PUT'])
    @role_required(PROC_EDIT_ROLES)
    def api_proc_supplier_update(supplier_id):
        """Ubah data supplier (Finance/Admin)."""
        try:
            data = request.get_json(silent=True) or {}
            conn = get_db_connection()
            if not conn:
                return jsonify({'error': 'DB error'}), 500
            cur = conn.cursor(dictionary=True)
            cur.execute("SELECT * FROM suppliers WHERE id=%s", (supplier_id,))
            old = cur.fetchone()
            if not old:
                cur.close(); conn.close()
                return jsonify({'error': 'Supplier tidak ditemukan'}), 404
            name = str(data.get('name') or old['name']).strip()
            if not name or len(name) > 150:
                cur.close(); conn.close()
                return jsonify({'error': 'Nama supplier tidak valid'}), 400
            cur.execute("SELECT id FROM suppliers WHERE name=%s AND id<>%s",
                        (name, supplier_id))
            if cur.fetchone():
                cur.close(); conn.close()
                return jsonify({'error': f'Supplier "{name}" sudah ada'}), 400
            cur.execute("""UPDATE suppliers SET name=%s, category=%s,
                           contact_name=%s, phone=%s, address=%s WHERE id=%s""",
                        (name, str(data.get('category') or old['category']).strip()[:100],
                         str(data.get('contact_name') or old['contact_name']).strip()[:100],
                         str(data.get('phone') or old['phone']).strip()[:50],
                         str(data.get('address') or old['address']).strip()[:300],
                         supplier_id))
            conn.commit(); cur.close(); conn.close()
            log_activity_async(0, 'procurement_supplier_update',
                               session.get('user_role', ''), _session_name(),
                               old_data={'id': supplier_id, 'name': old['name']},
                               new_data={'name': name}, ip=client_ip())
            return jsonify({'status': 'success'})
        except Exception as e:
            return jsonify({'error': str(e)}), 500

    @app.route('/api/procurement/suppliers/<int:supplier_id>', methods=['DELETE'])
    @role_required(PROC_EDIT_ROLES)
    @stepup_required
    def api_proc_supplier_deactivate(supplier_id):
        """Nonaktifkan supplier (soft delete, step-up PIN, jejak audit)."""
        try:
            conn = get_db_connection()
            if not conn:
                return jsonify({'error': 'DB error'}), 500
            cur = conn.cursor(dictionary=True)
            cur.execute("SELECT * FROM suppliers WHERE id=%s", (supplier_id,))
            old = cur.fetchone()
            if not old:
                cur.close(); conn.close()
                return jsonify({'error': 'Supplier tidak ditemukan'}), 404
            if not old['is_active']:
                cur.close(); conn.close()
                return jsonify({'error': 'Supplier sudah nonaktif'}), 400
            cur.execute("UPDATE suppliers SET is_active=0 WHERE id=%s", (supplier_id,))
            conn.commit(); cur.close(); conn.close()
            log_activity_async(0, 'procurement_supplier_deactivate',
                               session.get('user_role', ''), _session_name(),
                               old_data=dict(old), ip=client_ip())
            return jsonify({'status': 'success'})
        except Exception as e:
            return jsonify({'error': str(e)}), 500

    # ============================================================
    # PURCHASE ORDER
    # ============================================================
    @app.route('/api/procurement/orders')
    @role_required(PROC_ROLES)
    def api_proc_orders():
        """Daftar PO ringkas + kartu ringkasan. ?status= memfilter."""
        try:
            status = (request.args.get('status') or 'all').strip().lower()
            if status not in PO_STATUSES + ('all',):
                status = 'all'
            conn = get_db_connection()
            if not conn:
                return jsonify({'error': 'DB error'}), 500
            cur = conn.cursor(dictionary=True)
            q = """SELECT po.*, (SELECT COALESCE(SUM(i.qty*i.price),0) FROM po_items i
                    WHERE i.po_id=po.id) AS total_amount
                   FROM purchase_orders po"""
            params = None
            if status != 'all':
                q += " WHERE po.status=%s"
                params = (status,)
            q += " ORDER BY po.id DESC LIMIT 200"
            if params:
                cur.execute(q, params)
            else:
                cur.execute(q)
            rows = cur.fetchall()
            cur.execute("""SELECT status, COUNT(*) AS n,
                           COALESCE(SUM((SELECT COALESCE(SUM(i.qty*i.price),0)
                             FROM po_items i WHERE i.po_id=po2.id)),0) AS amount
                           FROM purchase_orders po2 GROUP BY status""")
            summary_rows = cur.fetchall()
            summary = {r['status']: {'count': int(r['n']),
                                     'amount': round(float(r['amount']), 2)}
                       for r in summary_rows}
            cur.close(); conn.close()
            return jsonify({'orders': rows, 'summary': summary,
                            'filter': {'status': status}})
        except Exception as e:
            return jsonify({'error': str(e)}), 500

    @app.route('/api/procurement/orders', methods=['POST'])
    @role_required(PROC_ROLES)
    def api_proc_order_create():
        """Buat PO baru: supplier_id, order_date, notes, items."""
        try:
            data = request.get_json(silent=True) or {}
            supplier_id = data.get('supplier_id')
            tanggal = str(data.get('order_date') or '').strip()
            if not tanggal:
                return jsonify({'error': 'Tanggal PO wajib diisi'}), 400
            try:
                datetime.strptime(tanggal, '%Y-%m-%d')
            except ValueError:
                return jsonify({'error': 'Format tanggal harus YYYY-MM-DD'}), 400
            items, err = _norm_items(data.get('items'))
            if err:
                return jsonify({'error': err}), 400

            conn = get_db_connection()
            if not conn:
                return jsonify({'error': 'DB error'}), 500
            cur = conn.cursor(dictionary=True)
            cur.execute("SELECT * FROM suppliers WHERE id=%s", (supplier_id,))
            sup = cur.fetchone()
            if not sup or not sup['is_active']:
                cur.close(); conn.close()
                return jsonify({'error': 'Supplier tidak valid / nonaktif'}), 400

            cur.execute("SELECT COUNT(*) AS n FROM purchase_orders "
                        "WHERE supplier_id=%s AND status IN ('open','partial')",
                        (supplier_id,))
            open_count = cur.fetchone()['n']
            cur.close()

            display_id = generate_display_id('PO', conn)
            cur = conn.cursor(dictionary=True)
            cur.execute("""INSERT INTO purchase_orders
                           (display_id, supplier_id, supplier_name, order_date,
                            status, notes, created_by)
                           VALUES (%s,%s,%s,%s,'open',%s,%s)""",
                        (display_id, supplier_id, sup['name'], tanggal,
                         str(data.get('notes') or '').strip()[:500], _session_name()))
            po_id = cur.lastrowid
            for it in items:
                cur.execute("""INSERT INTO po_items
                               (po_id, description, qty, satuan, price)
                               VALUES (%s,%s,%s,%s,%s)""",
                            (po_id, it['description'], it['qty'],
                             it['satuan'], it['price']))
            conn.commit()
            cur.close(); conn.close()
            log_activity_async(0, 'procurement_po_create',
                               session.get('user_role', ''), _session_name(),
                               new_data={'display_id': display_id,
                                         'supplier': sup['name'], 'items': items},
                               ip=client_ip())
            try:
                from modules.realtime import emit_event
                emit_event('po_new', {
                    'id': po_id, 'display_id': display_id,
                    'supplier_name': sup['name'],
                    'items': len(items), 'order_date': tanggal,
                    'created_at': datetime.now().strftime('%d/%m/%Y %H:%M'),
                })
            except Exception:
                pass
            return jsonify({'status': 'success', 'id': po_id,
                            'display_id': display_id,
                            'warn_open_pos': int(open_count)})
        except Exception as e:
            return jsonify({'error': str(e)}), 500

    @app.route('/api/procurement/orders/<int:po_id>')
    @role_required(PROC_ROLES)
    def api_proc_order_detail(po_id):
        """Detail PO + items (qty terima & sisa) + riwayat penerimaan."""
        try:
            conn = get_db_connection()
            if not conn:
                return jsonify({'error': 'DB error'}), 500
            cur = conn.cursor(dictionary=True)
            cur.execute("SELECT * FROM purchase_orders WHERE id=%s", (po_id,))
            po = cur.fetchone()
            if not po:
                cur.close(); conn.close()
                return jsonify({'error': 'PO tidak ditemukan'}), 404
            po = _po_with_items(cur, po)
            cur.close(); conn.close()
            return jsonify(po)
        except Exception as e:
            return jsonify({'error': str(e)}), 500

    @app.route('/api/procurement/orders/<int:po_id>/receive', methods=['POST'])
    @role_required(PROC_RECEIVE_ROLES)
    def api_proc_order_receive(po_id):
        """Catat penerimaan barang per item: {receipts: [{item_id, qty, note}]}."""
        try:
            data = request.get_json(silent=True) or {}
            raw = data.get('receipts') or []
            if not raw:
                return jsonify({'error': 'Tidak ada item yang dicatat'}), 400
            entries = []
            for idx, it in enumerate(raw, 1):
                try:
                    item_id = int(it.get('item_id'))
                    qty = int(it.get('qty'))
                except (TypeError, ValueError):
                    return jsonify({'error': f'Baris #{idx}: item_id/qty tidak valid'}), 400
                if qty == 0:
                    continue
                if qty < 0:
                    return jsonify({'error': f'Baris #{idx}: qty tidak boleh negatif'}), 400
                note = str(it.get('note') or '').strip()[:300]
                entries.append((item_id, qty, note))
            if not entries:
                return jsonify({'error': 'Semua qty 0 — tidak ada yang dicatat'}), 400

            conn = get_db_connection()
            if not conn:
                return jsonify({'error': 'DB error'}), 500
            cur = conn.cursor(dictionary=True)
            cur.execute("SELECT * FROM purchase_orders WHERE id=%s", (po_id,))
            po = cur.fetchone()
            if not po:
                cur.close(); conn.close()
                return jsonify({'error': 'PO tidak ditemukan'}), 404
            if po['status'] == 'cancelled':
                cur.close(); conn.close()
                return jsonify({'error': 'PO sudah dibatalkan — tidak bisa menerima'}), 400
            cur.execute("SELECT * FROM po_items WHERE po_id=%s", (po_id,))
            items = {it['id']: it for it in cur.fetchall()}
            for item_id, qty, _note in entries:
                it = items.get(item_id)
                if not it or it['po_id'] != po_id:
                    cur.close(); conn.close()
                    return jsonify({'error': f'Item {item_id} bukan milik PO ini'}), 400
                cur.execute("""SELECT COALESCE(SUM(qty),0) AS received FROM po_receipts
                               WHERE item_id=%s""", (item_id,))
                received = int(cur.fetchone()['received'])
                outstanding = int(it['qty']) - received
                if qty > outstanding:
                    cur.close(); conn.close()
                    return jsonify({
                        'error': (f'Item "{it["description"]}" kelebihan: diterima {qty} '
                                  f'padahal sisa {outstanding}')}), 400
            for item_id, qty, note in entries:
                cur.execute("""INSERT INTO po_receipts (po_id, item_id, qty, note, received_by)
                               VALUES (%s,%s,%s,%s,%s)""",
                            (po_id, item_id, qty, note, _session_name()))
            new_status = _recompute_status(cur, po_id)
            cur.execute("UPDATE purchase_orders SET status=%s WHERE id=%s",
                        (new_status, po_id))
            conn.commit()
            cur.close(); conn.close()
            log_activity_async(0, 'procurement_po_receive',
                               session.get('user_role', ''), _session_name(),
                               new_data={'display_id': po['display_id'],
                                         'status': new_status,
                                         'entries': [{'item_id': i, 'qty': q} for i, q, _ in entries]},
                               ip=client_ip())
            try:
                from modules.realtime import emit_event
                emit_event('po_received', {'id': po_id,
                                           'display_id': po['display_id'],
                                           'status': new_status})
            except Exception:
                pass
            return jsonify({'status': 'success', 'po_status': new_status})
        except Exception as e:
            return jsonify({'error': str(e)}), 500

    @app.route('/api/procurement/orders/<int:po_id>/cancel', methods=['POST'])
    @role_required(PROC_EDIT_ROLES)
    @stepup_required
    def api_proc_order_cancel(po_id):
        """Batalkan PO (Finance/Admin, wajib alasan + step-up PIN)."""
        try:
            data = request.get_json(silent=True) or {}
            reason = str(data.get('reason') or '').strip()
            if not reason or len(reason) > 500:
                return jsonify({'error': 'Alasan pembatalan wajib diisi (maks. 500)'}), 400
            conn = get_db_connection()
            if not conn:
                return jsonify({'error': 'DB error'}), 500
            cur = conn.cursor(dictionary=True)
            cur.execute("SELECT * FROM purchase_orders WHERE id=%s", (po_id,))
            po = cur.fetchone()
            if not po:
                cur.close(); conn.close()
                return jsonify({'error': 'PO tidak ditemukan'}), 404
            if po['status'] == 'cancelled':
                cur.close(); conn.close()
                return jsonify({'error': 'PO sudah dibatalkan sebelumnya'}), 400
            cur.execute("""SELECT COALESCE(SUM(qty),0) AS total FROM po_receipts
                           WHERE po_id=%s""", (po_id,))
            received_total = int(cur.fetchone()['total'])
            if received_total > 0:
                cur.close(); conn.close()
                return jsonify({'error': ('PO sudah memiliki penerimaan '
                                          f'({received_total} unit) — tidak bisa '
                                          'dibatalkan; tutup manual via penerimaan')}), 400
            cur.execute("""UPDATE purchase_orders SET status='cancelled',
                           cancelled_by=%s, cancel_reason=%s WHERE id=%s""",
                        (_session_name(), reason, po_id))
            conn.commit()
            cur.close(); conn.close()
            log_activity_async(0, 'procurement_po_cancel',
                               session.get('user_role', ''), _session_name(),
                               old_data={'display_id': po['display_id'],
                                         'status': po['status']},
                               new_data={'status': 'cancelled', 'reason': reason},
                               ip=client_ip())
            try:
                from modules.realtime import emit_event
                emit_event('po_cancelled', {'id': po_id,
                                            'display_id': po['display_id']})
            except Exception:
                pass
            return jsonify({'status': 'success'})
        except Exception as e:
            return jsonify({'error': str(e)}), 500
