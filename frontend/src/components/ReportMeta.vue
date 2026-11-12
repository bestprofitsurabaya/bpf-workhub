<script setup>
/**
 * Identitas laporan — menjawab "ini laporan apa, datanya dari mana, dihitung
 * bagaimana". Dipakai di Rekap, Rekap Pengeluaran, dan Analisis agar pengguna
 * tidak menebak-nebak arti angka.
 */
defineProps({
  title: { type: String, required: true },
  question: { type: String, default: '' },
  period: { type: String, default: '' },
  scope: { type: String, default: '' },
  source: { type: String, default: '' },
  basis: { type: String, default: '' },
  exclusions: { type: String, default: '' },
  generatedAt: { type: String, default: '' },
  rows: { type: [Number, String], default: '' },
})
</script>

<template>
  <section class="report-meta card card-pad">
    <div class="rm-head">
      <div>
        <div class="rm-title">📋 {{ title }}</div>
        <p v-if="question" class="rm-question">{{ question }}</p>
      </div>
      <span v-if="generatedAt" class="rm-generated">Dibuat {{ generatedAt }}</span>
    </div>
    <div class="rm-grid">
      <div v-if="period"><span>Periode</span><b>{{ period }}</b></div>
      <div v-if="scope"><span>Cakupan</span><b>{{ scope }}</b></div>
      <div v-if="source"><span>Sumber data</span><b>{{ source }}</b></div>
      <div v-if="basis"><span>Dasar hitung</span><b>{{ basis }}</b></div>
      <div v-if="rows !== ''"><span>Jumlah baris</span><b>{{ rows }}</b></div>
    </div>
    <p v-if="exclusions" class="rm-excl">Tidak termasuk: {{ exclusions }}</p>
  </section>
</template>

<style scoped>
.report-meta { margin-bottom: 14px; border-left: 4px solid var(--primary, #2563eb); }
.rm-head { display: flex; gap: 10px; align-items: flex-start; justify-content: space-between; flex-wrap: wrap; }
.rm-title { font-weight: 800; font-size: 14px; }
.rm-question { margin: 4px 0 0; font-size: 12px; color: var(--text-3, #64748b); max-width: 780px; }
.rm-generated { font-size: 11px; color: var(--text-3, #64748b); white-space: nowrap; }
.rm-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(170px, 1fr)); gap: 8px 14px; margin-top: 10px; }
.rm-grid span { display: block; font-size: 10px; text-transform: uppercase; letter-spacing: .03em; color: var(--text-3, #64748b); }
.rm-grid b { font-size: 12px; font-weight: 600; }
.rm-excl { margin: 10px 0 0; font-size: 11px; color: var(--warning, #b45309); }
</style>
