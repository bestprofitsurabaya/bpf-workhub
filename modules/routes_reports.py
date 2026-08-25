"""Report, Rekap, Analytics & Settings Routes"""
from flask import (request, redirect, url_for, flash, make_response)
from modules.config import get_db_connection
from modules.helpers import log_activity_async, role_required
from modules.engine import get_rekap_data
from modules.pdf_generator import PDFReportCompact, BBMReportPDF
from datetime import datetime
import zipfile, io, os, subprocess
from io import BytesIO

def register_report_routes(app):

    @app.route('/admin/report/<int:tx_id>')
    @role_required(['ga', 'finance', 'admin'])
    def generate_report(tx_id):
        try:
            conn = get_db_connection()
            cursor = conn.cursor(dictionary=True)
            cursor.execute("SELECT * FROM transactions WHERE id=%s", (tx_id,))
            tx = cursor.fetchone()
            if not tx:
                cursor.close(); conn.close()
                return "Data tidak ditemukan", 404
            # Generate PDF FIRST, then mark as reported (prevent marking on failure).
            pdf = PDFReportCompact()
            pdf.add_page()
            pdf.generate_compact_report(tx, app.config['UPLOAD_FOLDER'])
            pdf_raw = pdf.output(dest='S')
            pdf_bytes = pdf_raw.encode('latin-1') if isinstance(pdf_raw, str) else bytes(pdf_raw)
            # Only mark reported AFTER successful PDF generation.
            cursor.execute("UPDATE transactions SET is_reported=TRUE WHERE id=%s", (tx_id,))
            conn.commit()
            cursor.close(); conn.close()
            response = make_response(pdf_bytes)
            response.headers['Content-Type'] = 'application/pdf'
            response.headers['Content-Disposition'] = f'attachment; filename=BPF_Report_{tx.get("display_id", tx["id"])}_{tx["nopol"]}_{tx.get("created_at", datetime.now()).strftime("%Y%m%d")}.pdf'
            return response
        except Exception as e:
            print(f'[reports] generate_report error: {e}')
            return 'Terjadi kesalahan server', 500

    @app.route('/admin/rekap')
    @role_required(['ga', 'finance', 'admin'])
    def admin_rekap():
        # v2.5: halaman klasik dipensiunkan — rekap memakai SPA /app/rekap
        # (API pengganti: /api/transactions/archive, /admin/rekap/pdf tetap di sini).
        return redirect('/app/rekap')

    @app.route('/admin/rekap/pdf')
    @role_required(['ga', 'finance', 'admin'])
    def rekap_pdf():
        try:
            filters = {'start_date': request.args.get('start_date','').strip(), 'end_date': request.args.get('end_date','').strip(),
                       'nopol': request.args.get('nopol','').strip(), 'driver': request.args.get('driver','').strip()}
            data = get_rekap_data(start_date=filters['start_date'] if filters['start_date'] else None,
                                  end_date=filters['end_date'] if filters['end_date'] else None,
                                  nopol=filters['nopol'] if filters['nopol'] else None, tx_type=filters['type'] if filters.get('type') else None,
                                  driver=filters['driver'] if filters['driver'] else None)
            if not data:
                flash('Tidak ada data', 'warning')
                return redirect(url_for('admin_rekap'))
            ts = []
            ts.append(f"DRIVER: {filters['driver'].upper()}" if filters['driver'] else "DRIVER: ALL")
            ts.append(f"NOPOL: {filters['nopol'].upper()}" if filters['nopol'] else "NOPOL: ALL")
            if filters['start_date'] or filters['end_date']:
                s, e = filters['start_date'] or 'ALL', filters['end_date'] or 'ALL'
                ts.append(f"PERIODE: {s} S/D {e}")
            title = "REKAP DANA BBM - " + " | ".join(ts)
            pdf = BBMReportPDF(title=title)
            pdf.add_page()
            pdf.generate_table(data)
            pdf_raw = pdf.output(dest='S')
            pdf_bytes = pdf_raw.encode('latin-1') if isinstance(pdf_raw, str) else bytes(pdf_raw)
            response = make_response(pdf_bytes)
            response.headers['Content-Type'] = 'application/pdf'
            disposition = 'attachment' if request.args.get('dl') else 'inline'
            response.headers['Content-Disposition'] = f'{disposition}; filename=BPF_Rekap_BBM_{datetime.now().strftime("%Y%m%d")}.pdf'
            return response
        except Exception as e:
            return f"Error: {str(e)}", 500

    @app.route('/admin/analytics')
    @role_required(['ga', 'finance', 'admin'])
    def admin_analytics():
        # v2.5: halaman klasik dipensiunkan — analytics memakai SPA /app/analytics
        # (API pengganti: /api/analytics di routes_api_transactions).
        return redirect('/app/analytics')

    @app.route('/admin/logs')
    @role_required(['ga', 'finance', 'admin'])
    def admin_logs_view():
        # v2.5: halaman klasik dipensiunkan — logs memakai SPA /app/logs
        # (API pengganti: /api/logs di routes_api_transactions).
        return redirect('/app/logs')

    @app.route('/admin/riwayat')
    @role_required(['ga', 'finance', 'admin'])
    def admin_riwayat():
        return redirect(url_for('admin_rekap'))

    @app.route('/finance/download-archive/<int:tx_id>')
    @role_required(['finance', 'admin'])
    def download_archive(tx_id):
        try:
            conn = get_db_connection()
            cursor = conn.cursor(dictionary=True)
            cursor.execute("SELECT * FROM transactions WHERE id=%s", (tx_id,))
            tx = cursor.fetchone()
            cursor.close(); conn.close()
            if not tx: return "Not found", 404
            memory_file = BytesIO()
            with zipfile.ZipFile(memory_file, 'w', zipfile.ZIP_DEFLATED) as zf:
                for field, label in [('foto_odo_sebelum','01_ODO'),('foto_nota_odo_sesudah','02_Nota'),('foto_struk','03_Struk'),('foto_struk_dispenser','04_Dispenser')]:
                    fn = tx.get(field)
                    if fn:
                        fp = os.path.join(app.config['UPLOAD_FOLDER'], fn)
                        if os.path.exists(fp):
                            zf.write(fp, f"{label}_{tx['nopol']}{os.path.splitext(fn)[1]}")
            memory_file.seek(0)
            response = make_response(memory_file.read())
            response.headers['Content-Type'] = 'application/zip'
            response.headers['Content-Disposition'] = f'attachment; filename=BPF_Archive_{tx.get("display_id", tx["id"])}_{tx["nopol"]}_{datetime.now().strftime("%Y%m%d")}.zip'
            return response
        except Exception as e:
            return f"Error: {str(e)}", 500

    @app.route('/admin/backup')
    @role_required(['admin'])
    def backup_database():
        try:
            filename = f'backup_bpf_bbm_{datetime.now().strftime("%Y%m%d_%H%M%S")}.sql'
            log_activity_async(0, 'backup_download', 'admin', 'Admin', new_data={'filename': filename})
            # Use env vars for DB credentials (never hardcode passwords).
            db_host = os.getenv('DB_HOST', 'db')
            db_user = os.getenv('DB_USER', 'bpf_user')
            db_pass = os.getenv('DB_PASS', 'bpf_pass')
            db_name = os.getenv('DB_NAME', 'bpf_asset_system')
            cmd = ['mysqldump', '--ssl=0', '-h', db_host, '-u', db_user, f'-p{db_pass}', db_name]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
            if result.returncode != 0:
                return make_response("Backup unavailable", 500)
            response = make_response(result.stdout)
            response.headers['Content-Type'] = 'application/sql'
            response.headers['Content-Disposition'] = f'attachment; filename={filename}'
            return response
        except Exception as e:
            print(f'[reports] backup error: {e}')
            return 'Terjadi kesalahan server', 500

    @app.route('/admin/templates/import-bbm')
    @role_required(['ga', 'finance', 'admin'])
    def download_import_template():
        from openpyxl import Workbook
        wb = Workbook(); ws = wb.active; ws.title = "Template Import BBM"
        ws.append(["Tanggal (DD/MM/YYYY HH:MM)", "Nama Driver", "No Polisi", "Tipe Kendaraan", "Jenis BBM", "Nominal (Rp)", "Harga Per Liter", "Odometer (KM)", "Jumlah Appointment", "Alamat GPS"])
        ws.append(["02/07/2026 14:00", "AKHAD", "L 1413 CBI", "AVANZA", "PERTALITE", 200000, 10000, 12936, 3, "Jl. Raya Darmo 45, Surabaya"])
        out = io.BytesIO(); wb.save(out); out.seek(0)
        log_activity_async(0, 'template_download', 'admin', 'Admin', ip=request.remote_addr)
        response = make_response(out.read())
        response.headers['Content-Type'] = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        response.headers['Content-Disposition'] = 'attachment; filename=Template_Import_BBM.xlsx'
        return response

    @app.route('/admin/settings/import-xlsx', methods=['POST'])
    @role_required(['ga', 'finance', 'admin'])
    def import_xlsx_data():
        from openpyxl import load_workbook
        from modules.helpers import ensure_all_master_data
        if 'excel_file' not in request.files:
            flash('Tidak ada file!', 'error')
            return redirect(url_for('admin_settings'))
        file = request.files['excel_file']
        if file.filename == '':
            flash('Nama file kosong!', 'error')
            return redirect(url_for('admin_settings'))
        try:
            wb = load_workbook(file, data_only=True); ws = wb.active
            conn = get_db_connection(); cursor = conn.cursor()
            success = 0
            for row in ws.iter_rows(min_row=2, values_only=True):
                if not row[1] or not row[2]: continue
                try:
                    created_at = row[0] if isinstance(row[0], datetime) else datetime.strptime(str(row[0]), "%d/%m/%Y %H:%M")
                except Exception:
                    created_at = datetime.now()
                driver_name = str(row[1]).strip().upper()
                nopol = str(row[2]).strip().upper()
                vehicle_type = str(row[3]).strip().upper() if row[3] else "AVANZA"
                bbm_type = str(row[4]).strip().upper() if row[4] else "PERTALITE"
                nominal = float(row[5] or 0)
                price_per_liter = float(row[6] or 10000)
                liter = nominal/price_per_liter if price_per_liter>0 else 0
                odo_km = int(row[7] or 0)
                jumlah_appt = int(row[8] or 0)
                gps_address = str(row[9]) if row[9] else "Import Data Historis"
                ensure_all_master_data(driver_name, nopol, vehicle_type, bbm_type, price_per_liter)
                cursor.execute("INSERT INTO transactions (driver_name, nopol, vehicle_type, bbm_type, nominal, liter, price_per_liter, odo_km, spbu_type, status, ml_anomaly_flag, km_per_liter, gps_address, jumlah_appointment, created_at) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,'rekanan','archived',0,0,%s,%s,%s)",
                    (driver_name, nopol, vehicle_type, bbm_type, nominal, liter, price_per_liter, odo_km, gps_address, jumlah_appt, created_at))
                success += 1
            conn.commit(); cursor.close(); conn.close()
            log_activity_async(0, 'import_excel', 'admin', 'Admin', new_data={'total_rows': success}, ip=request.remote_addr)
            flash(f'✅ {success} data berhasil diimpor!', 'success')
        except Exception as e:
            flash(f'Error: {str(e)}', 'error')
        return redirect(url_for('admin_settings'))
