<script setup>
/**
 * KPI meja kerja BBM (v2.104.0 — Fase 3, poin "angka → baris").
 *
 * Empat angka yang selama ini hanya informatif kini bisa diklik: setiap kartu
 * membuka daftar baris yang terfilter di tab operasional. Angkanya datang
 * dari `/api/bbm/workspace/summary` — definisi tunggal yang sama dengan
 * Rekap/Realisasi/Analisis (modules/bbm_scope.py), bukan angka terpisah.
 *
 * Kartu TIDAK menjalankan aksi uang; hanya memindahkan pengguna ke daftar
 * baris sumber. Aksi uang tetap lewat endpoint + step-up yang sudah ada.
 */
import { computed, onMounted, ref, watch } from 'vue'
import { api } from '../api'

const props = defineProps({
  scope: { type: Object, default: null },
})
const emit = defineEmits(['open'])

const data = ref(null)
const loading = ref(true)
const err = ref('')

const fmt = (n) => 'Rp ' + Number(n || 0).toLocaleString('id-ID')

const CARDS = [
  {
    key: 'klaim_dibayar',
    label: 'Klaim dibayar',
    icon: '💰',
    tone: 'blue',
    tab: 'bbm',
    filters: { bbmTab: 'history', bbmType: 'CLAIM' },
    pick: (d) => d?.claims?.dibayar,
    hint: 'Klaim BBM sudah dibayar / diarsipkan',
  },
  {
    key: 'lpj_sah',
    label: 'LPJ sah',
    icon: '📋',
    tone: 'green',
    tab: 'bbm',
    filters: { bbmTab: 'history', bbmType: 'CASH_LPJ' },
    pick: (d) => d?.claims?.lpj_sah,
    hint: 'LPJ kasbon yang sah (verified_ga/archived)',
  },
  {
    key: 'voucher_sah',
    label: 'Voucher rekanan',
    icon: '🎟️',
    tone: 'teal',
    tab: 'voucher',
    filters: {},
    pick: (d) => d?.claims?.voucher_sah,
    hint: 'Voucher terverifikasi GA (dihitung sekali)',
  },
  {
    key: 'kasbon_cair',
    label: 'Kasbon cair',
    icon: '💵',
    tone: 'purple',
    tab: 'kasbon',
    filters: { kasbon: 'cair' },
    pick: (d) => d?.kasbon?.cair,
    hint: 'Dana sudah diserahkan ke driver',
  },
  {
    key: 'outstanding',
    label: 'Dana di driver',
    icon: '🚗',
    tone: 'amber',
    tab: 'kasbon',
    filters: { kasbon: 'outstanding' },
    pick: (d) => d?.kasbon?.outstanding,
    hint: 'Kasbon belum ada LPJ — perlu ditagih',
  },
]

const cards = computed(() =>
  CARDS.map((c) => {
    const m = c.pick(data.value) || {}
    return { ...c, amount: m.amount ?? 0, count: m.count ?? 0 }
  })
)

const periodLabel = computed(() => {
  const s = data.value?.period?.start
  const e = data.value?.period?.end
  return s && e ? `${s} s/d ${e}` : ''
})

// Cakupan KPI = cabang sesi (server mengembalikan meta.branch). Angka ini
// ditampilkan bersama label cabang supaya tidak pernah tertukar dengan
// laporan lintas-cabang (Realisasi bisa "Semua Cabang" untuk HO/Admin Pusat).
const branchLabel = computed(() => {
  const b = data.value?.meta?.branch
  return b ? String(b).toUpperCase() : '-'
})

async function load() {
  loading.value = true
  err.value = ''
  try {
    const p = { start_date: props.scope?.start, end_date: props.scope?.end }
    data.value = await api('/api/bbm/workspace/summary', { params: p })
  } catch (e) {
    data.value = null
    err.value = e?.data?.error || e?.message || 'Gagal memuat ringkasan'
  } finally {
    loading.value = false
  }
}

function openCard(card) {
  emit('open', { tab: card.tab, filters: card.filters, label: card.label })
}

watch(() => props.scope, load)
onMounted(load)
</script>

<template>
  <div class="card card-pad bbm-kpi" data-testid="bbm-kpi">
    <div class="row" style="gap:10px;flex-wrap:wrap;align-items:center;margin-bottom:10px;">
      <b>📌 KPI Periode Ini</b>
      <span v-if="periodLabel" class="muted" style="font-size:11px;">{{ periodLabel }}</span>
      <span class="badge badge-gray" data-testid="kpi-branch">Cabang: {{ branchLabel }}</span>
      <div class="spacer"></div>
      <span class="muted" style="font-size:11px;">Klik angka → daftar baris sumber</span>
    </div>

    <div v-if="loading" class="muted" style="font-size:12px;">⏳ Memuat ringkasan…</div>
    <div v-else-if="err" class="muted" style="font-size:12px;color:var(--danger);">⚠️ {{ err }}</div>
    <div v-else class="row" style="gap:10px;flex-wrap:wrap;">
      <button v-for="c in cards" :key="c.key" type="button"
              class="card card-pad kpi-item" :class="'tone-' + c.tone"
              :data-testid="'kpi-' + c.key"
              :aria-label="c.label + ' — buka daftar baris'"
              @click="openCard(c)">
        <div class="muted" style="font-size:12px;">{{ c.icon }} {{ c.label }}</div>
        <b style="font-size:20px;display:block;margin-top:2px;">{{ fmt(c.amount) }}</b>
        <div class="muted" style="font-size:10px;">{{ c.count }} baris · {{ c.hint }}</div>
      </button>
    </div>
  </div>
</template>

<style scoped>
.bbm-kpi { margin-bottom: 14px; }
.kpi-item {
  flex: 1 1 190px; min-width: 190px; text-align: left; cursor: pointer;
  font-size: inherit; color: inherit;
  background: var(--surface, #fff); transition: border-color .15s ease, transform .15s ease;
}
.kpi-item:hover { transform: translateY(-1px); border-color: var(--primary, #2563eb); }
.kpi-item:focus-visible { outline: 2px solid var(--primary, #2563eb); outline-offset: 2px; }
.tone-blue { border-left: 3px solid #2563eb; }
.tone-green { border-left: 3px solid #059669; }
.tone-purple { border-left: 3px solid #7c3aed; }
.tone-amber { border-left: 3px solid #d97706; }
.tone-teal { border-left: 3px solid #0d9488; }
</style>
