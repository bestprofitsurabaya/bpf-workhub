"""Perhitungan km/L BBM (v2.130.0).

Modul murni tanpa dependensi DB/ML supaya algoritma "top up" bisa diuji
terpisah dari `modules.engine`.
"""


def compute_km_metrics(tx_list, threshold=40.0):
    """Hitung km/L per baris BBM untuk SATU kendaraan (urut kronologis).

    v2.130.0 — "top up": liter dari pengisian beruntun (jarak < threshold)
    diakumulasi ke pengisian penuh berikutnya. Baris tanpa ODO (odo_km=0)
    TIDAK memutus interval: liternya ikut diakumulasi, bukan dianggap jarak
    0 km. Dipisah dari get_rekap_data agar bisa diuji tanpa DB.
    """
    result = []
    last_odo = None
    accumulated = 0.0
    for i, tx in enumerate(tx_list):
        curr = float(tx['odo_km'] or 0)
        liter = float(tx['liter'] or 0)

        # v2.130.0 — ODO kosong bukan berarti 0 km. Baris tanpa ODO
        # tidak boleh memutus interval: liternya diakumulasi ke
        # pengisian berikutnya yang punya ODO (top up).
        if curr <= 0:
            tx['is_multifill'] = True
            tx['is_topup'] = True
            tx['rata_rata'] = 0.0
            tx['km_awal'] = 0
            tx['km_akhir'] = 0
            tx['total_km'] = 0
            if last_odo is not None:
                accumulated += liter
            result.append(tx)
            continue

        if last_odo is None:
            # ODO pertama = patokan. Liter sebelum patokan tidak
            # punya jarak acuan, jadi tidak dipakai menghitung km/L.
            last_odo = curr
            tx['km_awal'] = tx['km_akhir'] = curr
            tx['total_km'] = 0
            tx['rata_rata'] = 0.0
            tx['is_multifill'] = False
            tx['is_topup'] = False
            accumulated = 0.0
            result.append(tx)
            continue

        dist = curr - last_odo
        if dist <= 0:
            # ODO mundur/tidak berubah: tandai, jangan reset patokan.
            tx['is_multifill'] = False
            tx['is_topup'] = False
            tx['rata_rata'] = 0.0
            tx['km_awal'] = last_odo
            tx['km_akhir'] = curr
            tx['total_km'] = dist
            result.append(tx)
            continue

        total_fuel = liter + accumulated
        tx['km_awal'] = last_odo
        tx['km_akhir'] = curr
        tx['total_km'] = dist
        if dist < threshold and total_fuel > 0:
            # Pengisian beruntun (top up): jarak terlalu pendek untuk
            # km/L yang stabil. Liter dibawa ke pengisian penuh berikut.
            tx['is_multifill'] = True
            tx['is_topup'] = True
            tx['rata_rata'] = 0.0
            accumulated = total_fuel
        else:
            tx['is_multifill'] = False
            tx['is_topup'] = False
            tx['rata_rata'] = (dist / total_fuel) if total_fuel > 0 else 0.0
            last_odo = curr
            accumulated = 0.0
        result.append(tx)
    return result

