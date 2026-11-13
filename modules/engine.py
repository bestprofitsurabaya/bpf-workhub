"""Core Business Logic: ML, Insights, Rekap Engine"""
import numpy as np
from sklearn.ensemble import IsolationForest
from sklearn.preprocessing import StandardScaler
from modules.config import get_db_connection

def generate_human_insight(performa, avg_kpl, limit_good, appt, total_tx):
    """Generate human-readable coaching insight"""
    if total_tx == 0:
        return "Sistem belum mendeteksi data transaksi yang cukup untuk menyusun analisis berkendara."
    base_msg = f"Rata-rata konsumsi BBM Anda: {avg_kpl:.2f} KM/Liter. "
    appt_ratio = appt / total_tx if total_tx > 0 else 0

    if performa in ["SANGAT BAIK", "BAIK"]:
        return base_msg + "Performa sangat efisien. Pertahankan eco-driving dan cek tekanan ban."
    elif performa == "CUKUP":
        msg = base_msg + "Efisiensi di zona aman, masih bisa dioptimalkan. "
        return msg + ("Tingginya appointment memengaruhi rute. Kelompokkan area pertemuan." if appt_ratio > 3 else "Terapkan akselerasi halus, hindari pengereman mendadak.")
    else:
        msg = base_msg + f"Konsumsi di bawah standar ({limit_good} KM/L). "
        return msg + ("Tingginya mobilitas rute pendek + idling menyebabkan pemborosan. Matikan mesin jika berhenti >2 menit." if appt_ratio > 4 else "Periksa tekanan ban, filter udara, dan hindari akselerasi agresif.")


class PerformanceAnalyzer:
    """ML-based anomaly detection for fuel efficiency"""

    @staticmethod
    def analyze_performance(nopol, current_efficiency, conn, vehicle_type, bbm_type):
        cursor = None
        try:
            cursor = conn.cursor(dictionary=True)
            cursor.execute("""
                SELECT warning_km_per_liter, good_km_per_liter FROM vehicle_bbm_allowed 
                WHERE vehicle_type = %s AND bbm_type = %s
            """, (vehicle_type, bbm_type))
            limit = cursor.fetchone()
            cursor.close()
            cursor = None

            warning = float(limit['warning_km_per_liter']) if limit else 10.5
            good = float(limit['good_km_per_liter']) if limit else 12.5

            cursor = conn.cursor(dictionary=True)
            cursor.execute("""
                SELECT km_per_liter FROM transactions 
                WHERE nopol = %s AND km_per_liter > 0 AND status IN ('verified_ga','os_finance','archived') 
                ORDER BY created_at DESC LIMIT 15
            """, (nopol,))
            history = cursor.fetchall()
            cursor.close()
            cursor = None

            if current_efficiency <= 0:
                return {'is_anomaly': False, 'status': 'PERLU DATA', 'category': 'info', 'message': 'Menunggu data'}

            is_anomaly, status, category = False, 'BAIK', 'success'
            message = f'Performa {vehicle_type} - {bbm_type} normal'

            if current_efficiency < warning:
                status, category = 'PERLU PEMERIKSAAN (Boros)', 'danger'
                message = f'{current_efficiency:.1f} KM/L < standar {warning} KM/L'
                is_anomaly = True
            elif current_efficiency < good:
                status, category = 'CUKUP', 'warning'
                message = f'{current_efficiency:.1f} KM/L, perlu pemantauan'

            # ML check
            if len(history) >= 5:
                data = [r['km_per_liter'] for r in history] + [current_efficiency]
                if len(data) >= 6:
                    try:
                        X = np.array(data).reshape(-1, 1)
                        X_scaled = StandardScaler().fit_transform(X)
                        preds = IsolationForest(contamination=0.15, random_state=42, n_estimators=50).fit_predict(X_scaled)
                        if preds[-1] == -1:
                            is_anomaly, status, category = True, 'ANOMALI ML', 'danger'
                            message = 'ML mendeteksi anomali'
                    except Exception as e:
                        print(f"ML Error: {e}")

            return {'is_anomaly': is_anomaly, 'status': status, 'category': category, 'message': message,
                    'vehicle_type': vehicle_type, 'bbm_type': bbm_type, 'current_efficiency': current_efficiency}
        except Exception as e:
            return {'is_anomaly': False, 'status': 'ERROR', 'category': 'error', 'message': str(e)}
        finally:
            if cursor:
                try: cursor.close()
                except Exception: pass


def get_rekap_data(start_date=None, end_date=None, nopol=None, driver=None, tx_type=None):
    """Fetch & calculate rekap with multifill detection"""
    try:
        conn = get_db_connection()
        if not conn:
            return []
        cursor = conn.cursor(dictionary=True)

        # v2.101.0: definisi Rekap disamakan — klaim yang sudah dibayar/arsip
        # + LPJ sah, tanpa `rejected`/`pending` (modules/bbm_scope.py).
        from modules import bbm_scope
        query = f"""
            SELECT t.*, d.vehicle_type as master_vehicle, d.bbm_type as master_bbm
            FROM transactions t LEFT JOIN drivers d ON t.driver_name = d.name
            WHERE {bbm_scope.rekap_scope_sql('t')}
              AND (t.is_dummy = 0 OR t.is_dummy IS NULL)
        """
        params = []
        if start_date:
            query += " AND DATE(t.created_at) >= %s"; params.append(start_date)
        if end_date:
            query += " AND DATE(t.created_at) <= %s"; params.append(end_date)
        if nopol:
            query += " AND t.nopol LIKE %s"; params.append(f"%{nopol}%")
        if driver:
            query += " AND t.driver_name LIKE %s"; params.append(f"%{driver}%")
        # v2.72.0: filter tx_type benar-benar diterapkan — sebelumnya parameter
        # ini diterima tapi tidak pernah dipakai (dead code yang diam-diam
        # mengabaikan ?type=...). Semantik mengikuti /api/transactions/archive:
        # CLAIM vs CASH_LPJ.
        # v2.107.0: voucher bukan jenis transaksi baru — baris CLAIM berlabel
        # rekanan. Filter VOUCHER memilih baris ber-voucher_value.
        if tx_type in ('CLAIM', 'CASH_LPJ'):
            query += " AND t.transaction_type = %s"; params.append(tx_type)
        elif tx_type == 'VOUCHER':
            query += (" AND t.transaction_type = 'CLAIM'"
                      " AND COALESCE(t.voucher_value, 0) > 0")
        query += " ORDER BY t.created_at ASC"

        cursor.execute(query, params)
        all_tx = cursor.fetchall()
        cursor.close()
        conn.close()

        # Fetch threshold
        try:
            c2 = get_db_connection()
            cur2 = c2.cursor(dictionary=True)
            cur2.execute("SELECT config_value FROM system_config WHERE config_key = 'multifill_km_threshold'")
            row = cur2.fetchone()
            threshold = float(row['config_value']) if row else 40.0
            cur2.close(); c2.close()
        except Exception:
            threshold = 40.0

        # Group & calculate
        groups = {}
        for tx in all_tx:
            groups.setdefault(tx['nopol'], []).append(tx)

        result = []
        for nopol_key, tx_list in groups.items():
            last_odo = None
            accumulated = 0.0
            for i, tx in enumerate(tx_list):
                curr = tx['odo_km']
                if last_odo is None:
                    tx['km_awal'] = tx['km_akhir'] = curr
                    tx['total_km'] = 0; tx['rata_rata'] = 0.0
                    last_odo = curr
                else:
                    dist = curr - last_odo if curr >= last_odo else 0
                    if dist < threshold:
                        tx['is_multifill'] = True
                        tx['rata_rata'] = 0.0
                        tx['km_awal'] = last_odo; tx['km_akhir'] = curr; tx['total_km'] = dist
                        accumulated += float(tx['liter'] or 0)
                    else:
                        tx['is_multifill'] = False
                        total_fuel = float(tx['liter'] or 0) + accumulated
                        tx['km_awal'] = last_odo; tx['km_akhir'] = curr; tx['total_km'] = dist
                        tx['rata_rata'] = (dist / total_fuel) if total_fuel > 0 else 0
                        last_odo = curr; accumulated = 0.0
                result.append(tx)

        result.sort(key=lambda x: x['created_at'], reverse=True)
        return result
    except Exception as e:
        print(f"Rekap error: {e}")
        return []
