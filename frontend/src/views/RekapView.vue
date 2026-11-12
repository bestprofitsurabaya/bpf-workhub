<script setup>
import { computed, onMounted, ref } from 'vue'
import { api } from '../api'
import LoadingState from '../components/LoadingState.vue'
import EmptyState from '../components/EmptyState.vue'
import ErrorState from '../components/ErrorState.vue'
import PageHeader from '../components/PageHeader.vue'
import ReportMeta from '../components/ReportMeta.vue'
import { formatDateTime, formatRupiah, transactionStatusLabel } from '../utils/format.js'

function localISO(d) {
  const mm = String(d.getMonth() + 1).padStart(2, '0')
  const dd = String(d.getDate()).padStart(2, '0')
  return `${d.getFullYear()}-${mm}-${dd}`
}

const today = localISO(new Date())
const start = ref(localISO(new Date(Date.now() - 29 * 864e5)))
const end = ref(today)
const driver = ref('')
const nopol = ref('')
const txType = ref('')
const rows = ref([])
const summary = ref(null)
const total = ref(0)
const totalPages = ref(1)
const page = ref(1)
const PER_PAGE = 50
const loading = ref(true)
const err = ref('')
const notice = ref('')
const generatedAt = ref('')

const fmt = formatRupiah
const num = (n) => Number(n || 0).toLocaleString('id-ID')
const typeLabel = (t) => (t === 'CASH_LPJ' ? 'LPJ Kasbon' : 'Klaim BBM')

async function load(resetPage = true) {
  loading.value = true; err.value = ''; notice.value = ''
  if (resetPage) page.value = 1
  try {
    const d = await api('/api/transactions/archive', {
      params: {
        start_date: start.value, end_date: end.value,
        driver: driver.value, nopol: nopol.value, type: txType.value,
        limit: PER_PAGE, page: page.value,
      },
    })
    rows.value = d.data || []
    summary.value = d.summary
    total.value = d.total || 0
    totalPages.value = d.total_pages || 1
    generatedAt.value = new Date().toLocaleString('id-ID')
  } catch (e) { err.value = e.message }
  finally { loading.value = false }
}

function preset(key) {
  const now = new Date()
  if (key === '7') start.value = localISO(new Date(Date.now() - 6 * 864e5))
  else if (key === '30') start.value = localISO(new Date(Date.now() - 29 * 864e5))
  else if (key === 'month') start.value = localISO(new Date(now.getFullYear(), now.getMonth(), 1))
  else if (key === 'year') start.value = `${now.getFullYear()}-01-01`
  end.value = today
  load(true)
}

function prevPage() { if (page.value > 1) { page.value--; load(false) } }
function nextPage() { if (page.value < totalPages.value) { page.value++; load(false) } }

const statusBadge = (s) =>
  ({ pending: ['⏳', 'badge-amber'], verified_ga: ['✅', 'badge-blue'], os_finance: ['💰', 'badge-purple'], archived: ['📦', 'badge-green'], rejected: ['❌', 'badge-red'], modified: ['✏️', 'badge-gray'] })[s] || ['—', 'badge-gray']

function pdfParams() {
  const p = new URLSearchParams({
    start_date: start.value, end_date: end.value,
    driver: driver.value, nopol: nopol.value, type: txType.value,
  })
  return p.toString()
}

function openPdf(dl) {
  if (!total.value) { notice.value = 'Tidak ada data pada filter ini — PDF tidak dibuat.'; return }
  window.open('/admin/rekap/pdf?' + pdfParams() + (dl ? '&dl=1' : ''), dl ? '_self' : '_blank')
}

function csvCell(v) {
  const s = String(v ?? '')
  return /[",\n;]/.test(s) ? '"' + s.replace(/"/g, '""') + '"' : s
}

async function exportCsv() {
  notice.value = ''
  try {
    const d = await api('/api/transactions/archive', {
      params: {
        start_date: start.value, end_date: end.value,
        driver: driver.value, nopol: nopol.value, type: txType.value,
        limit: 5000, page: 1,
      },
    })
    const data = d.data || []
    if (!data.length) { notice.value = 'Tidak ada data pada filter ini — CSV tidak dibuat.'; return }
    const header = ['ID', 'Driver', 'Nopol', 'BBM', 'Jenis', 'Nominal', 'Liter', 'km/L', 'Tanggal', 'Status']
    const lines = [header.join(',')]
    for (const t of data) {
      lines.push([
        t.display_id, t.driver_name, t.nopol, t.bbm_type, typeLabel(t.transaction_type),
        Number(t.nominal || 0), Number(t.liter || 0).toFixed(2),
        Number(t.km_per_liter || 0).toFixed(2), t.created_at, transactionStatusLabel(t.status),
      ].map(csvCell).join(','))
    }
    const blob = new Blob(['\ufeff' + lines.join('\n')], { type: 'text/csv;charset=utf-8;' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `rekap_klaim_bbm_${start.value}_${end.value}.csv`
    a.click()
    URL.revokeObjectURL(url)
    if ((d.total || 0) > data.length) {
      notice.value = `CSV berisi ${data.length} dari ${d.total} baris (batas ekspor 5.000). Persempit periode untuk data lengkap.`
    }
  } catch (e) { notice.value = e.message || 'Gagal mengekspor CSV.' }
}

const kpi = computed(() => ({
  rows: total.value,
  nominal: summary.value?.total_nominal ?? 0,
  liter: summary.value?.total_liter ?? 0,
  kml: summary.value?.avg_kml ?? 0,
}))

onMounted(load)
</script>

<template>
  <div>
    <PageHeader icon="📄" title="Rekap Klaim BBM" subtitle="Klaim BBM terarsip: nilai, liter, dan efisiensi per periode" />

    <ReportMeta
      title="Rekap Klaim BBM"
      question="Berapa klaim BBM yang sudah diarsipkan Finance pada periode ini, berapa nilainya, dan seberapa efisien pemakaiannya?"
      :period="`${start} s/d ${end}`"
      scope="Cabang aktif sesuai sesi login"
      source="Tabel transactions (klaim BBM & LPJ kasbon)"
      basis="Hanya status archived; data demo dikecualikan"
      exclusions="Klaim pending, verified_ga, os_finance, dan rejected tidak dihitung"
      :generated-at="generatedAt"
      :rows="total"
    />

    <div class="card card-pad" style="margin-bottom:16px;">
      <div class="row" style="flex-wrap:wrap;gap:8px;">
        <div class="field" style="margin:0;"><label>Dari</label><input class="input" type="date" v-model="start" /></div>
        <div class="field" style="margin:0;"><label>Sampai</label><input class="input" type="date" v-model="end" /></div>
        <div class="field" style="margin:0;min-width:140px;"><label>Driver</label><input class="input" v-model="driver" placeholder="Semua driver" @keyup.enter="load(true)" /></div>
        <div class="field" style="margin:0;min-width:140px;"><label>Nopol</label><input class="input" v-model="nopol" placeholder="Semua nopol" @keyup.enter="load(true)" /></div>
        <div class="field" style="margin:0;min-width:140px;"><label>Jenis</label>
          <select class="select" v-model="txType">
            <option value="">Semua</option>
            <option value="CLAIM">Klaim BBM</option>
            <option value="CASH_LPJ">LPJ Kasbon</option>
          </select>
        </div>
        <button class="btn btn-primary" @click="load(true)" style="margin-top:18px;">🔍 Tampilkan</button>
      </div>
      <div class="row" style="gap:6px;margin-top:10px;flex-wrap:wrap;">
        <span class="muted" style="font-size:11px;align-self:center;">Cepat:</span>
        <button class="btn btn-sm" @click="preset('7')">7 hari</button>
        <button class="btn btn-sm" @click="preset('30')">30 hari</button>
        <button class="btn btn-sm" @click="preset('month')">Bulan ini</button>
        <button class="btn btn-sm" @click="preset('year')">Tahun ini</button>
        <div class="spacer"></div>
        <button class="btn" @click="exportCsv">⬇️ CSV</button>
        <button class="btn" @click="openPdf(false)">📄 Preview PDF</button>
        <button class="btn btn-primary" @click="openPdf(true)">⬇️ Download PDF</button>
      </div>
    </div>

    <div v-if="notice" class="alert" style="margin-bottom:12px;">ℹ️ {{ notice }}</div>

    <div v-if="loading"><LoadingState rows="4" label="Memuat rekap…" /></div>
    <div v-else-if="err"><ErrorState :message="err" @retry="load" /></div>
    <template v-else>
      <div class="stat-grid" style="margin-bottom:16px;">
        <div class="stat-card"><div class="s-icon" style="background:#2563eb1a;">📄</div><div class="s-value" style="color:#2563eb;">{{ num(kpi.rows) }}</div><div class="s-label">Klaim Terarsip</div><div class="s-bar" style="background:#2563eb;"></div></div>
        <div class="stat-card"><div class="s-icon" style="background:#0596691a;">💵</div><div class="s-value" style="color:#059669;">{{ fmt(kpi.nominal) }}</div><div class="s-label">Total Nominal</div><div class="s-bar" style="background:#059669;"></div></div>
        <div class="stat-card"><div class="s-icon" style="background:#d977061a;">⛽</div><div class="s-value" style="color:#d97706;">{{ num(kpi.liter) }} L</div><div class="s-label">Total Liter</div><div class="s-bar" style="background:#d97706;"></div></div>
        <div class="stat-card"><div class="s-icon" style="background:#8b5cf61a;">🎯</div><div class="s-value" style="color:#8b5cf6;">{{ kpi.kml }}</div><div class="s-label">Rata-rata km/L</div><div class="s-bar" style="background:#8b5cf6;"></div></div>
      </div>

      <div class="card">
        <div class="table-wrap">
          <table class="tbl">
            <thead><tr><th>ID</th><th>Driver</th><th>Nopol</th><th>BBM</th><th>Jenis</th><th>Nominal</th><th>Liter</th><th>Tanggal</th><th>Status</th></tr></thead>
            <tbody>
              <tr v-for="t in rows" :key="t.id">
                <td><b>{{ t.display_id }}</b></td>
                <td>{{ t.driver_name }}</td>
                <td>{{ t.nopol }}</td>
                <td>{{ t.bbm_type }}</td>
                <td><span class="badge badge-gray">{{ typeLabel(t.transaction_type) }}</span></td>
                <td>{{ fmt(t.nominal) }}</td>
                <td>{{ Number(t.liter || 0).toFixed(2) }}</td>
                <td class="muted">{{ formatDateTime(t.created_at) }}</td>
                <td><span class="badge" :class="statusBadge(t.status)[1]">{{ statusBadge(t.status)[0] }} {{ transactionStatusLabel(t.status) }}</span></td>
              </tr>
              <tr v-if="!rows.length"><td colspan="9" style="padding:0;"><EmptyState message="Tidak ada data pada filter ini. Coba longgarkan periode atau kosongkan driver/nopol." icon="🗓️" /></td></tr>
            </tbody>
          </table>
        </div>
        <div v-if="totalPages > 1" class="pager" style="display:flex;align-items:center;gap:10px;justify-content:center;padding:12px;">
          <button class="btn btn-sm" :disabled="page <= 1" @click="prevPage">← Sebelumnya</button>
          <span class="muted" style="font-size:12px;">Halaman {{ page }} / {{ totalPages }} · {{ total }} entri</span>
          <button class="btn btn-sm" :disabled="page >= totalPages" @click="nextPage">Berikutnya →</button>
        </div>
      </div>
    </template>
  </div>
</template>
