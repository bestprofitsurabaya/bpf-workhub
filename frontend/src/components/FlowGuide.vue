<script setup>
/**
 * Panduan alur BBM (v2.108.0).
 *
 * Lima istilah yang sering tertukar: BBM, Voucher Rekanan, Kasbon & LPJ,
 * Subsidi Tepat, dan Laporan. Komponen ini menjelaskan "intinya", "kapan
 * dipakai", dan "di mana tombolnya" — tanpa memaksa user membuka buku panduan.
 */
import { computed } from 'vue'

const props = defineProps({
  audience: { type: String, default: 'staff' }, // 'staff' | 'driver'
  open: { type: Boolean, default: false },
})

const STAFF_ITEMS = [
  {
    icon: '⛽', title: 'BBM', badge: 'Klaim tunai',
    what: 'Driver membayar BBM sendiri di SPBU, lalu meminta ganti ke kantor.',
    when: 'Setiap pembelian BBM tunai. Bukti: foto ODO sebelum, nota + ODO sesudah, dan struk.',
    where: 'Tab BBM — verifikasi GA, pencairan Finance, arsip.',
  },
  {
    icon: '🎟️', title: 'Voucher Rekanan', badge: 'Tanpa uang driver',
    what: 'SPBU mitra memberi voucher + blanko. Driver tidak membayar; kantor membayar SPBU per periode.',
    when: 'Hanya di SPBU mitra yang menerima voucher. Wajib nomor nota dan liter dari nota.',
    where: 'Tab Voucher Rekanan — verifikasi GA, tagihan periode, pembayaran ke mitra.',
  },
  {
    icon: '🧾', title: 'Kasbon & LPJ', badge: 'Uang muka',
    what: 'Kasbon adalah uang muka perjalanan, bukan penggantian biaya. LPJ adalah bukti pemakaiannya.',
    when: 'Driver butuh dana sebelum jalan. Setelah dana diterima, LPJ wajib diisi; kasbon belum selesai sebelum LPJ disetujui.',
    where: 'Tab Kasbon & LPJ — persetujuan GA/Finance, serah dana, verifikasi LPJ.',
  },
  {
    icon: '🛡️', title: 'Subsidi Tepat', badge: 'Data SPBU',
    what: 'Data transaksi SPBU Subsidi Tepat (termasuk akses OTP) untuk rekonsiliasi BBM bersubsidi.',
    when: 'Dipakai Finance/Admin untuk mencocokkan pembelian di SPBU Subsidi Tepat. Driver tidak mengisi di sini.',
    where: 'Tab Subsidi Tepat — khusus Finance/Admin.',
  },
  {
    icon: '📈', title: 'Laporan', badge: 'Hanya melihat',
    what: 'Rekap klaim, realisasi pengeluaran, dan analisis efisiensi BBM/armada.',
    when: 'Untuk memeriksa hasil dan membuat keputusan — bukan tempat mengajukan atau membayar.',
    where: 'Tab Laporan — Rekap, Realisasi, Analisis.',
  },
]

const DRIVER_ITEMS = [
  {
    icon: '⛽', title: 'BBM', badge: 'Paling sering',
    what: 'Laporan pemakaian BBM: Anda bayar dulu di SPBU, lalu minta ganti ke kantor.',
    when: 'Setiap isi BBM tunai. Siapkan foto ODO sebelum, nota + ODO sesudah, dan struk.',
    where: 'Tab BBM → mode Klaim BBM.',
  },
  {
    icon: '🎟️', title: 'Voucher Rekanan', badge: 'Tidak bayar',
    what: 'SPBU mitra memberi voucher + blanko. Anda tidak membayar; kantor membayar SPBU mitra.',
    when: 'Hanya di SPBU mitra. Isi nama SPBU, nomor nota, liter, dan foto bukti yang sama.',
    where: 'Tab BBM → mode Voucher Rekanan.',
  },
  {
    icon: '🧾', title: 'Kasbon & LPJ', badge: 'Uang muka',
    what: 'Kasbon adalah uang muka perjalanan — bukan penggantian biaya BBM.',
    when: 'Butuh dana sebelum jalan. Setelah dana diterima, isi LPJ dengan bukti pemakaian.',
    where: 'Ajukan di tab Kasbon; isi LPJ lewat form BBM (tab BBM).',
  },
  {
    icon: '📊', title: 'Rapor', badge: 'Hanya melihat',
    what: 'Ringkasan performa BBM kendaraan Anda (rata-rata km/liter).',
    when: 'Untuk melihat apakah konsumsi BBM wajar. Tidak perlu mengisi apa pun.',
    where: 'Tab Rapor.',
  },
]

const items = computed(() => (props.audience === 'driver' ? DRIVER_ITEMS : STAFF_ITEMS))
</script>

<template>
  <details class="flow-guide" data-testid="flow-guide" :open="open">
    <summary>
      <span class="fg-title">🧭 Bingung bedanya? Panduan singkat 5 menit</span>
      <span class="fg-sub">BBM · Voucher Rekanan · Kasbon &amp; LPJ · Subsidi Tepat · Laporan</span>
    </summary>

    <div class="fg-grid">
      <article v-for="item in items" :key="item.title" class="fg-card">
        <header>
          <span class="fg-icon" aria-hidden="true">{{ item.icon }}</span>
          <b>{{ item.title }}</b>
          <span class="fg-badge">{{ item.badge }}</span>
        </header>
        <p><span class="fg-label">Intinya</span> {{ item.what }}</p>
        <p><span class="fg-label">Kapan</span> {{ item.when }}</p>
        <p class="fg-where"><span class="fg-label">Di mana</span> {{ item.where }}</p>
      </article>
    </div>

    <p class="fg-note">
      <b>Aturan cepat:</b> BBM = uang Anda yang diganti. Voucher = kantor yang bayar SPBU mitra.
      Kasbon = uang muka yang wajib di-LPJ. Subsidi Tepat = data SPBU untuk Finance.
      Laporan = melihat hasil, bukan mengajukan.
    </p>
    <p v-if="audience === 'driver'" class="fg-note fg-note-driver">
      Subsidi Tepat dan Laporan staf bukan pekerjaan driver. Ringkasan performa Anda ada di tab <b>Rapor</b>.
    </p>
  </details>
</template>

<style scoped>
.flow-guide {
  margin: 0 0 12px;
  border: 1px solid var(--border);
  border-radius: 12px;
  background: var(--surface);
  overflow: hidden;
}
.flow-guide summary {
  display: flex;
  flex-direction: column;
  gap: 2px;
  padding: 10px 12px;
  cursor: pointer;
  list-style: none;
}
.flow-guide summary::-webkit-details-marker { display: none; }
.flow-guide summary::after {
  content: '▾';
  position: absolute;
  right: 14px;
  opacity: .6;
}
.flow-guide summary { position: relative; padding-right: 32px; }
.fg-title { font-size: 12px; font-weight: 700; }
.fg-sub { font-size: 10px; opacity: .7; }
.fg-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
  gap: 8px;
  padding: 0 10px 10px;
}
.fg-card {
  border: 1px solid var(--border);
  border-radius: 10px;
  padding: 8px 10px;
  background: var(--bg-2, #f8fafc);
  font-size: 11px;
  line-height: 1.45;
}
.fg-card header {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-bottom: 4px;
  flex-wrap: wrap;
}
.fg-card header b { font-size: 12px; }
.fg-icon { font-size: 15px; }
.fg-badge {
  margin-left: auto;
  font-size: 9px;
  font-weight: 700;
  padding: 2px 6px;
  border-radius: 999px;
  background: var(--primary-soft, #dbeafe);
  color: var(--primary, #1d4ed8);
  white-space: nowrap;
}
.fg-card p { margin: 2px 0; }
.fg-label {
  display: inline-block;
  min-width: 52px;
  font-size: 9px;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: .03em;
  opacity: .55;
}
.fg-where { opacity: .85; }
.fg-note {
  margin: 0;
  padding: 8px 12px;
  border-top: 1px dashed var(--border);
  font-size: 10px;
  line-height: 1.5;
  background: var(--bg-2, #f8fafc);
}
.fg-note-driver { border-top: none; padding-top: 0; }
@media (max-width: 480px) {
  .fg-grid { grid-template-columns: 1fr; }
}
</style>
