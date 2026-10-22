<script setup>
import { onMounted, ref } from 'vue'
import { api } from '../api'
import LoadingState from '../components/LoadingState.vue'
import EmptyState from '../components/EmptyState.vue'
import ErrorState from '../components/ErrorState.vue'
import { formatDateTime, formatRupiah, transactionStatusLabel } from '../utils/format.js'

const today = new Date().toISOString().slice(0, 10)
const start = ref(new Date(Date.now() - 7 * 864e5).toISOString().slice(0, 10))
const end = ref(today)
const rows = ref([])
const summary = ref(null)
const total = ref(0)
const totalPages = ref(1)
const page = ref(1)
const PER_PAGE = 50
const loading = ref(true)
const err = ref('')

const fmt = formatRupiah

async function load(resetPage = true) {
  loading.value = true; err.value = ''
  if (resetPage) page.value = 1
  try {
    const d = await api('/api/transactions/archive', { params: { start_date: start.value, end_date: end.value, limit: PER_PAGE, page: page.value } })
    rows.value = d.data || []
    summary.value = d.summary
    total.value = d.total || 0
    totalPages.value = d.total_pages || 1
  } catch (e) { err.value = e.message }
  finally { loading.value = false }
}

function prevPage() { if (page.value > 1) { page.value--; load(false) } }
function nextPage() { if (page.value < totalPages.value) { page.value++; load(false) } }

const statusBadge = (s) =>
  ({ pending: ['⏳', 'badge-amber'], verified_ga: ['✅', 'badge-blue'], os_finance: ['💰', 'badge-purple'], archived: ['📦', 'badge-green'], rejected: ['❌', 'badge-red'], modified: ['✏️', 'badge-gray'] })[s] || ['—', 'badge-gray']

function openPdf(dl) {
  const p = new URLSearchParams({ start_date: start.value, end_date: end.value })
  window.open('/admin/rekap/pdf?' + p.toString() + (dl ? '&dl=1' : ''), dl ? '_self' : '_blank')
}

onMounted(load)
</script>

<template>
  <div>
    <div class="card card-pad" style="margin-bottom:16px;">
      <div class="row">
        <div class="field" style="margin:0;"><label>Dari</label><input class="input" type="date" v-model="start" /></div>
        <div class="field" style="margin:0;"><label>Sampai</label><input class="input" type="date" v-model="end" /></div>
        <button class="btn btn-primary" @click="load(true)" style="margin-top:18px;">🔍 Tampilkan</button>
        <div class="spacer"></div>
        <button class="btn" @click="openPdf(false)">📄 Preview PDF</button>
        <button class="btn btn-primary" @click="openPdf(true)">⬇️ Download PDF</button>
      </div>
    </div>

    <div v-if="loading"><LoadingState rows="4" label="Memuat rekap…" /></div>
    <div v-else-if="err"><ErrorState :message="err" @retry="load" /></div>
    <template v-else>
      <div class="stat-grid" style="margin-bottom:16px;">
        <div class="stat-card"><div class="s-icon" style="background:#2563eb1a;">📄</div><div class="s-value" style="color:#2563eb;">{{ total }}</div><div class="s-label">Transaksi Terarsip</div><div class="s-bar" style="background:#2563eb;"></div></div>
        <div class="stat-card"><div class="s-icon" style="background:#0596691a;">💵</div><div class="s-value" style="color:#059669;">{{ fmt(summary?.total_nominal) }}</div><div class="s-label">Total Nominal</div><div class="s-bar" style="background:#059669;"></div></div>
      </div>

      <div class="card">
        <div class="table-wrap">
          <table class="tbl">
            <thead><tr><th>ID</th><th>Driver</th><th>Nopol</th><th>BBM</th><th>Nominal</th><th>Liter</th><th>Tanggal</th><th>Status</th></tr></thead>
            <tbody>
              <tr v-for="t in rows" :key="t.id">
                <td><b>{{ t.display_id }}</b></td>
                <td>{{ t.driver_name }}</td>
                <td>{{ t.nopol }}</td>
                <td>{{ t.bbm_type }}</td>
                <td>{{ fmt(t.nominal) }}</td>
                <td>{{ Number(t.liter || 0).toFixed(2) }}</td>
                <td class="muted">{{ formatDateTime(t.created_at) }}</td>
                <td><span class="badge" :class="statusBadge(t.status)[1]">{{ statusBadge(t.status)[0] }} {{ transactionStatusLabel(t.status) }}</span></td>
              </tr>
              <tr v-if="!rows.length"><td colspan="8" style="padding:0;"><EmptyState message="Tidak ada data pada rentang tanggal ini." icon="🗓️" /></td></tr>
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
