<script setup>
import { computed, onMounted, ref } from 'vue'
import { api } from '../api'
import LoadingState from '../components/LoadingState.vue'
import EmptyState from '../components/EmptyState.vue'
import ErrorState from '../components/ErrorState.vue'
import Modal from '../components/Modal.vue'

const logs = ref([])
const loading = ref(true)
const err = ref('')
const fAction = ref('all')
const fRole = ref('all')
const branches = ref([])
const fBranch = ref('current')
const branchLoading = ref(false)
const page = ref(1)
const PER_PAGE = 25

async function loadBranches() {
  try {
    const d = await api('/api/branches/current')
    branches.value = (d && d.branches) || []
  } catch { branches.value = [] }
}

async function loadLogs() {
  loading.value = true; err.value = ''
  try {
    logs.value = await api('/api/audit-logs', {
      params: fBranch.value === 'current' ? {} : { branch: fBranch.value },
    }) || []
  } catch (e) { err.value = e.message }
  finally { loading.value = false }
}

const actions = computed(() => ['all', ...[...new Set(logs.value.map((l) => l.action).filter(Boolean))].sort()])
const roles = computed(() => ['all', ...[...new Set(logs.value.map((l) => l.user_type).filter(Boolean))].sort()])
const filtered = computed(() =>
  logs.value.filter((l) =>
    (fAction.value === 'all' || l.action === fAction.value) &&
    (fRole.value === 'all' || l.user_type === fRole.value)))
const pageCount = computed(() => Math.max(1, Math.ceil(filtered.value.length / PER_PAGE)))
const paged = computed(() => filtered.value.slice((page.value - 1) * PER_PAGE, page.value * PER_PAGE))
const todayCount = computed(() =>
  logs.value.filter((l) => new Date(l.created_at).toDateString() === new Date().toDateString()).length)

const actionLabel = (a) => (a || '—').replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase())

// ---- Detail snapshot (v2.37.3): klik baris → old_data/new_data ----
const detail = ref(null)
const detailLoading = ref(false)
const detailErr = ref('')

async function openDetail(l) {
  detailErr.value = ''; detail.value = null; detailLoading.value = true
  try {
    const q = fBranch.value !== 'current' ? `?branch=${encodeURIComponent(fBranch.value)}` : ''
    detail.value = await api(`/api/audit-logs/${l.id}${q}`)
  } catch (e) { detailErr.value = e.message }
  finally { detailLoading.value = false }
}

const snapshotKeys = (snap) => Object.keys(snap || {}).sort()
const fmtVal = (v) => (v === null || v === undefined || v === '') ? '—'
  : (typeof v === 'object' ? JSON.stringify(v) : String(v))

function prevPage() { page.value = Math.max(1, page.value - 1) }
function nextPage() { page.value = Math.min(pageCount.value, page.value + 1) }
function applyFilters() { page.value = 1 }

onMounted(async () => {
  loadBranches()
  loadLogs()
})
</script>

<template>
  <div>
    <div class="card card-pad" style="margin-bottom:16px;display:flex;align-items:center;gap:12px;flex-wrap:wrap;">
      <div class="grow">
        <h3 style="margin:0;">📝 Audit Log</h3>
        <p class="muted" style="font-size:11px;">Jejak digital seluruh aktivitas (ISO/IEC 27001 · A.8.15 logging &amp; monitoring) · Khusus Admin</p>
      </div>
      <span class="badge badge-blue">📅 Hari ini: {{ todayCount }}</span>
      <span class="badge badge-gray">Total: {{ filtered.length }} / {{ logs.length }}</span>
    </div>

    <div v-if="loading"><LoadingState rows="4" label="Memuat audit log…" /></div>
    <div v-else-if="err"><ErrorState :message="err" @retry="loadLogs" /></div>
    <template v-else>
      <div class="card card-pad" style="margin-bottom:16px;">
        <div class="row">
          <div class="field" style="margin:0;flex:1;">
            <label>Filter Cabang</label>
            <select class="select" v-model="fBranch" @change="applyFilters; loadLogs()">
              <option value="current">Cabang aktif</option>
              <option v-for="b in branches" :key="b.code" :value="b.code">{{ b.name }} ({{ b.code }})</option>
            </select>
          </div>
          <div class="field" style="margin:0;flex:1;">
            <label>Filter Aksi</label>
            <select class="select" v-model="fAction" @change="applyFilters">
              <option v-for="a in actions" :key="a" :value="a">{{ a === 'all' ? 'Semua Aksi' : actionLabel(a) }}</option>
            </select>
          </div>
          <div class="field" style="margin:0;flex:1;">
            <label>Filter Peran</label>
            <select class="select" v-model="fRole" @change="applyFilters">
              <option v-for="r in roles" :key="r" :value="r">{{ r === 'all' ? 'Semua Peran' : r.toUpperCase() }}</option>
            </select>
          </div>
        </div>
      </div>

      <div class="card">
        <div class="table-wrap">
          <table class="tbl">
            <thead><tr><th>Waktu</th><th>User</th><th>Tipe</th><th>Aksi</th><th>Ref</th><th>Cabang</th><th>IP</th><th></th></tr></thead>
            <tbody>
              <tr v-for="l in paged" :key="l.id">
                <td class="muted">{{ l.created_at }}</td>
                <td><b>{{ l.user_name }}</b></td>
                <td><span class="badge badge-gray">{{ l.user_type }}</span></td>
                <td>{{ actionLabel(l.action) }}</td>
                <td>{{ l.transaction_id || '—' }}</td>
                <td><span v-if="l.branch_code" class="branch-chip">🏢 {{ l.branch_code }}</span><span v-else class="muted">—</span></td>
                <td class="muted">{{ l.ip_address || '—' }}</td>
                <td style="text-align:center;"><button class="btn btn-sm" style="padding:1px 8px;font-size:11px;" title="Lihat detail snapshot" @click="openDetail(l)">🔍</button></td>
              </tr>
              <tr v-if="!filtered.length"><td colspan="8" style="padding:0;"><EmptyState message="Tidak ada data dengan filter ini." icon="🔍" /></td></tr>
            </tbody>
          </table>
        </div>
      </div>

      <div v-if="pageCount > 1" class="pager" style="display:flex;align-items:center;gap:10px;justify-content:center;padding:12px;">
        <button class="btn btn-sm" :disabled="page <= 1" @click="prevPage">← Sebelumnya</button>
        <span class="muted" style="font-size:12px;">Halaman {{ page }} / {{ pageCount }} · {{ filtered.length }} entri</span>
        <button class="btn btn-sm" :disabled="page >= pageCount" @click="nextPage">Berikutnya →</button>
      </div>
    </template>

    <!-- Modal detail snapshot (v2.37.3) -->
    <Modal v-if="detail || detailLoading || detailErr" :title="'🔍 Detail Log #' + (detail ? detail.id : '…')" @close="detail = null; detailErr = ''">
      <div v-if="detailLoading" class="muted" style="padding:20px;text-align:center;">⏳ Memuat detail…</div>
      <div v-else-if="detailErr" class="alert alert-error">{{ detailErr }}</div>
      <template v-else-if="detail">
        <div class="row" style="gap:8px;align-items:center;flex-wrap:wrap;">
          <span class="badge badge-gray">{{ detail.user_type }}</span>
          <b>{{ detail.user_name || '—' }}</b>
          <span class="badge badge-blue">{{ actionLabel(detail.action) }}</span>
          <span v-if="detail.branch_code" class="branch-chip">🏢 {{ detail.branch_code }}</span>
        </div>
        <p class="muted" style="font-size:12px;margin-top:6px;">
          🕐 {{ detail.created_at }} · 🌐 {{ detail.ip_address || '—' }} · Ref: {{ detail.transaction_id || '—' }}
        </p>
        <p v-if="detail.user_agent" class="muted" style="font-size:11px;word-break:break-all;">🖥️ {{ detail.user_agent }}</p>
        <div v-if="detail.old_data" style="margin-top:12px;">
          <b style="font-size:12px;color:#b45309;">📥 Data Lama (sebelum aksi)</b>
          <div class="card card-pad" style="margin-top:6px;background:var(--bg-alt,#fffbeb);">
            <table class="tbl">
              <tbody>
                <tr v-for="k in snapshotKeys(detail.old_data)" :key="'o'+k">
                  <td class="muted" style="width:30%;">{{ k }}</td>
                  <td style="word-break:break-word;">{{ fmtVal(detail.old_data[k]) }}</td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>
        <div v-if="detail.new_data" style="margin-top:12px;">
          <b style="font-size:12px;color:#15803d;">📤 Data Baru (setelah aksi)</b>
          <div class="card card-pad" style="margin-top:6px;background:var(--bg-alt,#f0fdf4);">
            <table class="tbl">
              <tbody>
                <tr v-for="k in snapshotKeys(detail.new_data)" :key="'n'+k">
                  <td class="muted" style="width:30%;">{{ k }}</td>
                  <td style="word-break:break-word;">{{ fmtVal(detail.new_data[k]) }}</td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>
        <div v-if="!detail.old_data && !detail.new_data" class="muted" style="margin-top:12px;font-size:12px;">
          Entri ini tidak menyimpan snapshot data.
        </div>
        <div class="row" style="justify-content:flex-end;margin-top:12px;">
          <button class="btn" @click="detail = null">Tutup</button>
        </div>
      </template>
    </Modal>
  </div>
</template>
