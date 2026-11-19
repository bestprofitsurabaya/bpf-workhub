/* Penanggalan Jawa — kalender Sultan Agung, kurup Asapon.
 *
 * Aturan (lihat id.wikipedia.org/wiki/Kalender_Jawa):
 *  - windu = 8 tahun: Alip, Ehe, Jimawal, Je, Dal, Be, Wawu, Jimakir
 *  - tahun kabisat (355 hari): Ehe, Dal, Jimakir; sisanya 354 hari
 *  - bulan: 30/29 bergantian, Besar 29 (30 saat kabisat)
 *
 * Jangkar: 1 Sura 1960 JA = 17 Juni 2026 (tahun Be).
 * Validasi terhadap sumber luar:
 *  - 1 Januari 2026  = 12 Rejeb 1959, Pon                (kalenderize.com)
 *  - 3 November 2026 = 22 Jumadilawal 1960, Selasa Wage, neptu 7
 *                                                        (detik, liputan6, ki-demang)
 *  - 4 November 2026 = 23 Jumadilawal 1960, Rabu Kliwon   (liputan6)
 *  - 1 Sura 1961     = 6 Juni 2027                       (KompasTV)
 */
(function () {
  'use strict';

  const HARI = ['Minggu', 'Senin', 'Selasa', 'Rabu', 'Kamis', 'Jumat', 'Sabtu'];
  const PASARAN = ['Legi', 'Pahing', 'Pon', 'Wage', 'Kliwon'];
  const BULAN = ['Sura', 'Sapar', 'Mulud', 'Bakda Mulud', 'Jumadilawal',
    'Jumadilakir', 'Rejeb', 'Ruwah', 'Pasa', 'Sawal', 'Sela', 'Besar'];
  const TAHUN = ['Alip', 'Ehe', 'Jimawal', 'Je', 'Dal', 'Be', 'Wawu', 'Jimakir'];
  const PANJANG = [30, 29, 30, 29, 30, 29, 30, 29, 30, 29, 30, 29];
  const KABISAT = ['Ehe', 'Dal', 'Jimakir'];

  const NEPTU_HARI = { Minggu: 5, Senin: 4, Selasa: 3, Rabu: 7, Kamis: 8, Jumat: 6, Sabtu: 9 };
  const NEPTU_PASARAN = { Legi: 5, Pahing: 9, Pon: 7, Wage: 4, Kliwon: 8 };

  const ANCHOR_TAHUN = 1960;
  const ANCHOR_DAY = Date.UTC(2026, 5, 17) / 86400000; // 17 Juni 2026
  const PASARAN_REF = Date.UTC(2026, 10, 3) / 86400000; // 3 Nov 2026 = Wage (index 3)
  const PASARAN_REF_IDX = 3;

  const dayNum = (s) => {
    const p = String(s).split('-').map(Number);
    return Date.UTC(p[0], p[1] - 1, p[2]) / 86400000;
  };

  function tahunNama(t) { return TAHUN[((t % 8) + 5) % 8]; }
  function tahunPanjang(t) { return KABISAT.indexOf(tahunNama(t)) >= 0 ? 355 : 354; }

  function bulanPanjang(t, i) {
    return PANJANG[i] + (i === 11 && KABISAT.indexOf(tahunNama(t)) >= 0 ? 1 : 0);
  }

  /* date = 'YYYY-MM-DD' */
  function parse(date) {
    if (!/^\d{4}-\d{2}-\d{2}$/.test(String(date))) return null;

    const today = dayNum(date);
    let diff = today - ANCHOR_DAY;
    let tahun = ANCHOR_TAHUN;

    while (diff >= tahunPanjang(tahun)) { diff -= tahunPanjang(tahun); tahun++; }
    while (diff < 0) { tahun--; diff += tahunPanjang(tahun); }

    let bulan = 0;
    while (diff >= bulanPanjang(tahun, bulan)) { diff -= bulanPanjang(tahun, bulan); bulan++; }
    const tanggal = diff + 1;

    const hari = HARI[new Date(date + 'T00:00:00Z').getUTCDay()];
    const delta = today - PASARAN_REF;
    const pIdx = (((PASARAN_REF_IDX + (delta % 5)) % 5) + 5) % 5;
    const pasaran = PASARAN[pIdx];

    return {
      hari,
      pasaran,
      neptu: NEPTU_HARI[hari] + NEPTU_PASARAN[pasaran],
      tanggal,
      bulan: BULAN[bulan],
      bulanKe: bulan + 1,
      tahun,
      tahunNama: tahunNama(tahun),
      label: `${hari} ${pasaran}, ${tanggal} ${BULAN[bulan]} ${tahun}`,
      labelSingkat: `${pasaran}, ${tanggal} ${BULAN[bulan]} ${tahun}`,
    };
  }

  window.BPF_JAWA = { parse, HARI, PASARAN, BULAN, TAHUN };
})();
