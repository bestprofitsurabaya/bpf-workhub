/**
 * Dasar hitung tiga laporan BBM — satu sumber teks (v2.113.2).
 *
 * Angka Rekap, Realisasi, dan Analisis memakai definisi tunggal di
 * `modules/bbm_scope.py` (`BASIS_VERSION`). Teks di bawah ini dipakai baik oleh
 * kartu meta di layar maupun baris header CSV, supaya file ekspor tidak
 * menjelaskan dasar hitung yang berbeda dari layarnya.
 *
 * Penting: JANGAN menulis ulang kalimat ini di masing-masing view.
 */
export const BASIS_VERSION = 'bbm-scope-3'

export const REPORT_BASIS = {
  rekap:
    'Klaim cash CLAIM os_finance/archived + LPJ CASH_LPJ verified_ga/archived '
    + '+ voucher rekanan verified_ga/archived; data demo dikecualikan',
  realisasi:
    'Kasbon cair: handover_at terisi · LPJ sah: CASH_LPJ verified_ga/archived · '
    + 'Voucher: CLAIM berlabel rekanan, verified_ga/archived (sekali saat pemakaian) · '
    + 'Klaim tunai: CLAIM os_finance/archived dengan voucher_value=0 · '
    + 'Total = LPJ + voucher + klaim (tiga kanal, tanpa hitung ganda)',
  analisis:
    'Klaim dibayar os_finance/archived + LPJ sah verified_ga/archived; '
    + 'kasbon cair = handover_at terisi; armada mengikuti periode',
}
