"""Admin Legacy Redirects & Trip Logsheet Export.

v2.5: seluruh antarmuka klasik dipensiunkan. Endpoint di bawah ini hanya untuk
kepentingan kompatibilitas (bookmark lama) dan export dokumen logsheet yang
belum punya pengganti di SPA:

- `/admin` , `/admin/queue-fragment/<tab>` , `/admin/trips` , `/ga/assignments`
  → redirect ke halaman SPA sesuai fungsinya.
- `/admin/trips/export/<id>` (Excel) & `/admin/trips/export-pdf/<id>` (PDF)
  → tetap aktif (dipakai via URL langsung; TripsView SPA belum punya tombolnya).

Endpoint aksi klasik lainnya (ga_approve, finance_payout, finance_archive,
reject, unverify, delete, edit-odo, trips verify/reject) DIHAPUS — semua sudah
punya pengganti resmi di SPA: `/api/queue/*` dan `/api/trips/*`.
"""
from flask import redirect, make_response
from modules.config import get_db_connection
from modules.helpers import role_required


def register_admin_routes(app):

    @app.route('/admin', methods=['GET', 'POST'])
    @role_required(['ga', 'finance', 'admin'])
    def admin_dashboard():
        return redirect('/app/dashboard')

    @app.route('/admin/queue-fragment/<tab>')
    @role_required(['ga', 'finance', 'admin'])
    def queue_fragment(tab):
        return redirect('/app/dashboard')

    @app.route('/admin/trips')
    @role_required(['ga', 'finance', 'admin'])
    def admin_trips():
        return redirect('/app/trips')

    @app.route('/admin/trips/export/<int:trip_id>')
    @role_required(['ga', 'finance', 'admin'])
    def export_trip_excel(trip_id):
        from modules.excel_generator import generate_trip_logsheet
        from modules.company_identity import get_branch_identity
        try:
            conn = get_db_connection()
            cursor = conn.cursor(dictionary=True)
            cursor.execute("SELECT * FROM trip_masters WHERE id=%s", (trip_id,))
            master = cursor.fetchone()
            if not master:
                cursor.close(); conn.close()
                return "Trip not found", 404
            cursor.execute("SELECT * FROM trip_details WHERE trip_master_id=%s ORDER BY no_urut", (trip_id,))
            details = cursor.fetchall()
            cursor.close(); conn.close()
            # v2.37.7: kop logsheet mengikuti cabang sesi (tabel branches).
            try:
                identity = get_branch_identity()
            except Exception:
                identity = None
            excel_bytes = generate_trip_logsheet(master, details, identity=identity)
            response = make_response(excel_bytes)
            response.headers['Content-Type'] = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
            response.headers['Content-Disposition'] = f'attachment; filename=Logsheet_{master["nopol"]}_{master["trip_date"]}.xlsx'
            return response
        except Exception as e:
            return f"Error: {str(e)}", 500

    @app.route('/admin/trips/export-pdf/<int:trip_id>')
    @role_required(['ga', 'finance', 'admin'])
    def export_trip_pdf(trip_id):
        from modules.pdf_generator import BPFBasePDF, INK, BORDER, HEADER_FILL, ZEBRA_FILL
        try:
            conn = get_db_connection()
            cursor = conn.cursor(dictionary=True)
            cursor.execute("SELECT * FROM trip_masters WHERE id=%s", (trip_id,))
            master = cursor.fetchone()
            if not master:
                cursor.close(); conn.close()
                return "Trip not found", 404
            cursor.execute("SELECT * FROM trip_details WHERE trip_master_id=%s ORDER BY no_urut", (trip_id,))
            details = cursor.fetchall()
            cursor.close(); conn.close()

            pdf = BPFBasePDF()
            pdf.add_page()
            pdf.set_font(pdf._font(), 'B', 12)
            pdf.cell(0, 8, f'LOG PERJALANAN #{master["display_id"]}', align='C', new_x="LMARGIN", new_y="NEXT")
            pdf.ln(4)

            # Info header
            pdf.set_font(pdf._font(), '', 8)
            info = [
                ('Driver', master['driver_name']),
                ('Nopol', master['nopol']),
                ('Tanggal', str(master['trip_date'])),
                ('Jam Berangkat', master['jam_keberangkatan'] or '-'),
                ('Jam Tiba', master['jam_tiba'] or '-'),
                ('KM Awal', str(master['km_awal'])),
                ('KM Akhir', str(master['km_akhir'] or 0)),
                ('Status', master['status']),
            ]
            for label, value in info:
                pdf.set_font(pdf._font(), 'B', 8)
                pdf.cell(35, 5, label)
                pdf.set_font(pdf._font(), '', 8)
                pdf.cell(0, 5, ': ' + str(value), new_x="LMARGIN", new_y="NEXT")
            pdf.ln(4)

            # Rute
            pdf.set_font(pdf._font(), 'B', 9)
            pdf.cell(0, 6, 'RUTE PERJALANAN', new_x="LMARGIN", new_y="NEXT")
            pdf.ln(2)

            headers = ['NO', 'LOKASI BERANGKAT', 'PUKUL', 'KM', 'LOKASI TUJUAN', 'PUKUL', 'KM']
            widths = [8, 40, 18, 14, 40, 18, 14]
            pdf.set_fill_color(*INK)
            pdf.set_text_color(255, 255, 255)
            pdf.set_font(pdf._font(), 'B', 7)
            for i, h in enumerate(headers):
                pdf.cell(widths[i], 6, h, border=1, align='C', fill=True)
            pdf.ln()

            pdf.set_font(pdf._font(), '', 7)
            fill = False
            for i, d in enumerate(details, 1):
                pdf.set_fill_color(*ZEBRA_FILL) if fill else pdf.set_fill_color(255, 255, 255)
                pdf.cell(widths[0], 5, str(i), border=1, align='C', fill=True)
                pdf.cell(widths[1], 5, pdf.clean_text(str(d['lokasi_berangkat'])[:30]), border=1, fill=True)
                pdf.cell(widths[2], 5, str(d['pukul_berangkat'] or '-'), border=1, align='C', fill=True)
                pdf.cell(widths[3], 5, str(d['km_berangkat']), border=1, align='C', fill=True)
                pdf.cell(widths[4], 5, pdf.clean_text(str(d['lokasi_tujuan'])[:30]), border=1, fill=True)
                pdf.cell(widths[5], 5, str(d['pukul_tujuan'] or '-'), border=1, align='C', fill=True)
                pdf.cell(widths[6], 5, str(d['km_tujuan']), border=1, align='C', fill=True)
                pdf.ln()
                fill = not fill

            pdf_raw = pdf.output(dest='S')
            pdf_bytes = pdf_raw.encode('latin-1') if isinstance(pdf_raw, str) else bytes(pdf_raw)
            response = make_response(pdf_bytes)
            response.headers['Content-Type'] = 'application/pdf'
            response.headers['Content-Disposition'] = 'attachment; filename=BPF_Logsheet_' + str(master.get('display_id', master['id'])) + '_' + str(master['nopol']) + '_' + str(master['trip_date']) + '.pdf'
            return response
        except Exception as e:
            return f"Error: {str(e)}", 500

    @app.route('/ga/assignments')
    @role_required(['ga', 'finance', 'admin'])
    def ga_assignments():
        return redirect('/app/assignments')
