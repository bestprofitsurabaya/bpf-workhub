<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { api } from '../../api'
import { useAuthStore } from '../../stores/auth'
import StatCard from '../../components/StatCard.vue'
import Modal from '../../components/Modal.vue'
import LoadingState from '../../components/LoadingState.vue'
import EmptyState from '../../components/EmptyState.vue'
import ErrorState from '../../components/ErrorState.vue'
import { useStepupStore } from '../../stores/stepup'

const stepup = useStepupStore()

const auth = useAuthStore()
const s = ref(null)
const loading = ref(true)
const err = ref('')

const fmt = (n) => 'Rp ' + Number(n || 0).toLocaleString('id-ID')
const num = (n) => Number(n || 0).toLocaleString('id-ID')

onMounted(async () => {
  try { s.value = await api('/api/stats') }
  catch (e) { err.value = e.message }
  finally { loading.value = false }
  loadQueue()
  loadBranchStats()
})

async function refreshStats() {
  // Refresh diam-diam (tanpa mengubah state loading) agar dashboard tidak berkedip.
  try { s.value = await api('/api/stats') } catch { /* abaikan */ }
}

const cards = computed(() => {
  if (!s.value) return []
  const c = [
    { icon: '🕐', label: 'Antrean GA (pending)', value: s.value.pending, color: '#dc2626', roles: ['ga', 'admin'] },
    { icon: '✅', label: 'Verified GA', value: s.value.verified_ga, color: '#0891b2', roles: ['ga', 'admin'] },
    { icon: '💰', label: 'Menunggu Finance (os_finance)', value: s.value.os_finance, color: '#d97706', roles: ['finance', 'admin'] },
    { icon: '📦', label: 'Terarsip', value: s.value.archived, color: '#059669', roles: ['ga', 'finance', 'admin'] },
    { icon: '📅', label: 'Transaksi Hari Ini', value: s.value.today_tx, color: '#2563eb', roles: ['ga', 'finance', 'admin'] },
    { icon: '💵', label: 'Nominal Hari Ini', value: fmt(s.value.today_nominal), color: '#7c3aed', roles: ['finance', 'admin'] },
  ]
  return c.filter((x) => x.roles.includes(auth.role))
})

// ============================================================
// Ringkasan Cabang (v2.20.0) — statistik per cabang (Admin)
// ============================================================
const branchStats = ref([])
const branchStatsLoading = ref(false)

async function loadBranchStats() {
  if (auth.role !== 'admin') return
  branchStatsLoading.value = true
  try {
    const d = await api('/api/branches/stats')
    branchStats.value = (d && d.branches) || []
  } catch { branchStats.value = [] }
  finally { branchStatsLoading.value = false }
}

function openBranchReportPdf() {
  window.open('/api/branches/report-pdf', '_blank')
}

function openConsolidatedPdf() {
  window.open('/api/branches/consolidated-pdf', '_blank')
}

function openConsolidatedExcel() {
  window.open('/api/branches/consolidated-excel', '_blank')
}

function exportQueueExcel() {
  // Sesi cookie dibawa otomatis; buka lewat fetch lalu unduh blob (agar
  // error 401/403 bisa ditangani, bukan halaman kosong).
  api(`/api/queue/export-excel?tab=${queueTab.value}`, { raw: true })
    .then((blob) => {
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `antrean_${queueTab.value}_${new Date().toISOString().slice(0, 10)}.xlsx`
      a.click()
      URL.revokeObjectURL(url)
    })
    .catch((e) => { queueMsg.value = '❌ Gagal export Excel: ' + e.message })
}

const quick = computed(() => {
  const m = [
    { icon: '🗺️', label: 'Log Perjalanan', path: '/trips', roles: ['ga', 'finance', 'admin'] },
    { icon: '🚗', label: 'Assignments', path: '/assignments', roles: ['ga', 'admin'] },
    { icon: '📋', label: 'Rekap', path: '/rekap', roles: ['finance', 'admin'] },
    { icon: '📈', label: 'Analytics', path: '/analytics', roles: ['ga', 'finance', 'admin'] },
    { icon: '👥', label: 'Manajemen User', path: '/users', roles: ['admin'] },
    { icon: '📝', label: 'Audit Log', path: '/logs', roles: ['admin'] },
    { icon: '⚙️', label: 'Pengaturan', path: '/settings', roles: ['admin'] },
  ]
  return m.filter((x) => x.roles.includes(auth.role))
})

// ============================================================
// Antrean Kerja — approve GA / payout / archive / reject / detail
// ============================================================
const QUEUE_TABS = [
  { key: 'ga', label: '🕐 Antrean GA', roles: ['ga', 'admin'] },
  { key: 'finance', label: '💰 Finance', roles: ['finance', 'admin'] },
  { key: 'driver_confirm', label: '🤝 Konfirmasi Driver', roles: ['finance', 'admin'] },
]
const queueTab = ref('ga')
const queue = ref([])
const queueLoading = ref(false)
const queueMsg = ref('')
const qBusy = ref(false)

const queueTabs = computed(() => QUEUE_TABS.filter((t) => t.roles.includes(auth.role)))
const canApprove = computed(() => ['ga', 'admin'].includes(auth.role))
const canFinance = computed(() => ['finance', 'admin'].includes(auth.role))
const isAdmin = computed(() => auth.role === 'admin')

// Modal detail transaksi
const sel = ref(null)
const selData = ref(null)
const selCross = ref(null)
const selLoading = ref(false)
const selFinanceReview = ref(null) // finance review detail
const financeRemark = ref('') // remark form
const financeRemarkSaving = ref(false)

async function loadQueue() {
  queueLoading.value = true; queueMsg.value = ''
  try { queue.value = (await api('/api/queue', { params: { tab: queueTab.value } })) || [] }
  catch (e) { queueMsg.value = '❌ ' + e.message }
  finally { queueLoading.value = false }
}

async function queueAction(path, label, needsStepup = false) {
  if (!confirm(`Yakin ${label}?`)) return false
  qBusy.value = true; queueMsg.value = ''
  try {
    // Aksi uang (approve/payout) wajib step-up — PIN ulang bila perlu (ISO/IEC 27001 A.8.5)
    const run = () => api(path, { method: 'POST' })
    const r = needsStepup ? await stepup.require(run, label) : await run()
    queueMsg.value = '✅ ' + (r.msg || r.message || label)
    loadQueue(); refreshStats()
    return true
  } catch (e) { queueMsg.value = '❌ ' + e.message; return false }
  finally { qBusy.value = false }
}

async function modalAction(path, label) {
  const ok = await queueAction(path, label)
  if (ok) { sel.value = null; selData.value = null; selCross.value = null }
  return ok
}

function doApprove(tx) {
  if (tx.ml_anomaly_flag) {
    queueMsg.value = '⚠️ Transaksi ber-flag anomali ML — buka 👁 Detail lalu pilih 🛡 Verifikasi Anomali untuk verifikasi penuh.'
    return
  }
  return queueAction(`/api/queue/approve-ga/${tx.id}`, 'menyetujui klaim ini', true)
}
const doPayout = (tx) => queueAction(`/api/queue/payout/${tx.id}`, 'mencairkan dana klaim ini', true)
const doArchive = (tx) => queueAction(`/api/queue/archive/${tx.id}`, 'mengarsipkan klaim ini')

async function doReject(tx) {
  const reason = prompt(`Alasan menolak ${tx.display_id} (${tx.driver_name}):`, '')
  if (reason === null) return
  qBusy.value = true; queueMsg.value = ''
  try {
    const r = await api(`/api/queue/reject/${tx.id}`, { method: 'POST', body: { reason } })
    queueMsg.value = '✅ ' + (r.msg || 'Klaim ditolak')
    loadQueue(); refreshStats()
    if (sel.value) { sel.value = null; selData.value = null; selCross.value = null }
  } catch (e) { queueMsg.value = '❌ ' + e.message }
  finally { qBusy.value = false }
}

async function openDetail(tx, verify = false) {
  sel.value = tx
  selLoading.value = true
  selData.value = null; selCross.value = null; selFinanceReview.value = null
  verifyMode.value = false; editMode.value = false
  financeRemark.value = ''
  try {
    const promises = [
      api(`/api/transactions/detail/${tx.id}`),
      api(`/api/cross-check/${tx.id}`).catch(() => null),
    ]
    // Finance review: prev ODO, monthly stats, budget — untuk role finance
    if (canFinance) promises.push(api(`/api/finance-review/${tx.id}`).catch(() => null))
    const [d, c, fr] = await Promise.all(promises)
    selData.value = d
    selCross.value = c
    selFinanceReview.value = fr || null
    // Tombol 🛡 di baris antrean membuka modal langsung ke form verifikasi anomali
    if (verify && d?.ml_anomaly_flag) openVerify(tx)
  } catch (e) { queueMsg.value = '❌ ' + e.message }
  finally { selLoading.value = false }
}

async function doFinanceRemark() {
  if (!selData.value || !financeRemark.value.trim()) return
  financeRemarkSaving.value = true
  try {
    await api('/api/finance-remark', { method: 'POST', body: { tx_id: selData.value.id, remark: financeRemark.value.trim(), username: auth.user?.full_name || auth.user?.user_name || 'Finance' } })
    queueMsg.value = '✅ Remark tersimpan'
    financeRemark.value = ''
    // Reload detail
    const d = await api(`/api/transactions/detail/${sel.value.id}`)
    selData.value = d
  } catch (e) { queueMsg.value = '❌ ' + e.message }
  finally { financeRemarkSaving.value = false }
}

// ============================================================
// Verifikasi mendalam (termasuk anomali ML) & perbaikan data — dari SPA
// ============================================================
const verifyMode = ref(false)
const verifyForm = ref({ confirm_anomaly: false, mypertamina_error: false, file: null })
const editMode = ref(false)
const editForm = ref({ vehicle_type: '', bbm_type: '', nominal: 0, odo_km: 0, spbu_type: 'rekanan' })

function openVerify(tx) {
  verifyForm.value = { confirm_anomaly: false, mypertamina_error: false, file: null }
  verifyMode.value = true; editMode.value = false
}

function openEdit(tx) {
  editForm.value = {
    vehicle_type: tx.vehicle_type || '',
    bbm_type: tx.bbm_type || '',
    nominal: tx.nominal || 0,
    odo_km: tx.odo_km || 0,
    spbu_type: tx.spbu_type || 'rekanan',
  }
  editMode.value = true; verifyMode.value = false
}

async function doVerify(tx) {
  if (tx.ml_anomaly_flag && !verifyForm.value.confirm_anomaly) {
    queueMsg.value = '⚠️ Centang konfirmasi setelah memeriksa foto bukti.'
    return
  }
  qBusy.value = true; queueMsg.value = ''
  try {
    // Step-up (ISO/IEC 27001 A.8.5): verifikasi & persetujuan = menyetujui
    // klaim (uang). Seluruh request (termasuk foto) dijalankan ulang setelah
    // PIN ulang berhasil — jangan pecah menjadi dua request yang berbeda.
    const run = async () => {
      const fd = new FormData()
      fd.append('confirm_anomaly', verifyForm.value.confirm_anomaly ? '1' : '0')
      fd.append('mypertamina_error', verifyForm.value.mypertamina_error ? '1' : '0')
      if (verifyForm.value.file) fd.append('foto_mypertamina', verifyForm.value.file)
      const csrf = localStorage.getItem('bpf_csrf') || sessionStorage.getItem('bpf_csrf')
      const r = await fetch(`/api/queue/verify/${tx.id}`, {
        method: 'POST',
        headers: csrf ? { 'X-CSRF-Token': csrf } : {},
        body: fd,
      })
      const d = await r.json().catch(() => null)
      if (r.status === 401) window.dispatchEvent(new CustomEvent('bpf:unauthorized'))
      if (!r.ok) {
        const err = new Error((d && (d.msg || d.error)) || `HTTP ${r.status}`)
        err.status = r.status
        err.data = d
        throw err
      }
      return d
    }
    const d = await stepup.require(run, `verifikasi & menyetujui klaim ${tx.display_id || tx.id}`)
    queueMsg.value = '✅ ' + (d?.msg || 'Klaim diverifikasi')
    loadQueue(); refreshStats()
    sel.value = null; selData.value = null; selCross.value = null
  } catch (e) { queueMsg.value = '❌ ' + e.message }
  finally { qBusy.value = false }
}

async function doModify(tx) {
  qBusy.value = true; queueMsg.value = ''
  try {
    const r = await api(`/api/queue/modify/${tx.id}`, { method: 'POST', body: { ...editForm.value } })
    queueMsg.value = '✅ ' + (r.msg || 'Data diperbaiki')
    loadQueue(); refreshStats()
    sel.value = null; selData.value = null; selCross.value = null
  } catch (e) { queueMsg.value = '❌ ' + e.message }
  finally { qBusy.value = false }
}

// ============================================================
// Transaction Flags (anomali ODO) — load saat tab GA aktif
// ============================================================
const txFlags = ref({})

async function loadTxFlags() {
  try { txFlags.value = await api('/api/transaction-flags') } catch { txFlags.value = {} }
}

function getFlag(id) {
  return txFlags.value[String(id)] || null
}

watch(queueTab, (tab) => {
  loadQueue()
  if (tab === 'ga') loadTxFlags()
})
</script>

<template>
  <div>
    <div class="card card-pad" style="margin-bottom:16px;display:flex;align-items:center;gap:14px;flex-wrap:wrap;">
      <div style="font-size:26px;">{{ auth.meta?.icon }}</div>
      <div class="grow">
        <div style="font-weight:800;font-size:16px;">Selamat datang, {{ auth.user?.full_name || auth.user?.user_name }}</div>
        <div class="muted" style="font-size:12px;">
          Dashboard {{ auth.meta?.label }} · data transaksi &amp; klaim BBM terkini
        </div>
      </div>
      <span class="role-chip" :style="{ background: auth.meta?.color }">{{ auth.meta?.label }}</span>
    </div>

    <div v-if="loading" class="empty">⏳ Memuat data…</div>
    <div v-else-if="err" class="alert alert-error">{{ err }}</div>
    <template v-else>
      <div class="stat-grid">
        <StatCard v-for="c in cards" :key="c.label" :icon="c.icon" :label="c.label" :value="c.value" :color="c.color" />
      </div>

      <!-- Ringkasan Cabang (Admin) -->
      <div v-if="isAdmin" class="card card-pad" style="margin-top:18px;">
        <div class="row" style="flex-wrap:wrap;gap:8px;align-items:center;">
          <h3 style="margin:0;">🏢 Ringkasan Cabang</h3>
          <span class="muted" style="font-size:11px;">Transaksi, kunjungan hari ini &amp; user per cabang (multi-cabang)</span>
          <div class="spacer"></div>
          <button class="btn btn-sm" title="Unduh PDF ringkasan cabang" @click="openBranchReportPdf">📄 PDF</button>
          <button class="btn btn-sm" title="Unduh laporan konsolidasi lintas cabang (semua DB) sebagai PDF" aria-label="Unduh PDF konsolidasi lintas cabang" @click="openConsolidatedPdf">🧮 PDF Konsolidasi</button>
          <button class="btn btn-sm" title="Unduh laporan konsolidasi lintas cabang sebagai Excel" aria-label="Unduh Excel konsolidasi lintas cabang" @click="openConsolidatedExcel">🧮 Excel Konsolidasi</button>
          <button class="btn btn-sm" :disabled="branchStatsLoading" @click="loadBranchStats">🔄</button>
        </div>
        <div v-if="branchStatsLoading" class="empty" style="padding:14px;">⏳ Memuat…</div>
        <div class="table-wrap" v-else style="margin-top:10px;">
          <table class="tbl">
            <thead><tr><th>Kode</th><th>Nama Cabang</th><th>Database</th><th>Transaksi</th><th>Kunjungan Hari Ini</th><th>User</th><th>Status</th></tr></thead>
            <tbody>
              <tr v-for="b in branchStats" :key="b.code">
                <td><b>{{ b.code }}</b></td>
                <td>{{ b.name }}</td>
                <td class="muted">{{ b.db_name }}</td>
                <td>{{ Number(b.transactions || 0).toLocaleString('id-ID') }}</td>
                <td>{{ b.appointments_today }}</td>
                <td>{{ b.users }}</td>
                <td><span class="badge" :class="b.is_active ? 'badge-green' : 'badge-red'">{{ b.is_active ? 'Aktif' : 'Nonaktif' }}</span></td>
              </tr>
              <tr v-if="!branchStats.length"><td colspan="7" class="empty">Belum ada cabang terdaftar.</td></tr>
            </tbody>
          </table>
        </div>
      </div>

      <!-- Antrean Kerja -->
      <div class="card card-pad" style="margin-top:18px;">
        <div class="row" style="flex-wrap:wrap;gap:8px;">
          <h3 style="margin:0;">🕐 Antrean Kerja</h3>
          <button v-for="t in queueTabs" :key="t.key" class="btn btn-sm" :class="queueTab === t.key ? 'btn-primary' : ''" @click="queueTab = t.key">{{ t.label }}</button>
          <button class="btn btn-sm" title="Unduh antrean tab aktif sebagai Excel" aria-label="Unduh antrean sebagai Excel" @click="exportQueueExcel">⬇️ Excel</button>
          <span v-if="queueMsg" class="alert" :class="queueMsg.startsWith('✅') ? 'alert-success' : 'alert-error'" style="margin:0;">{{ queueMsg }}</span>
          <div class="spacer"></div>
        </div>
        <div v-if="queueLoading"><LoadingState rows="3" label="Memuat antrean…" /></div>
        <div v-else-if="queueMsg && queueMsg.startsWith('❌')" ><ErrorState :message="queueMsg.slice(2)" @retry="loadQueue" /></div>
        <div class="table-wrap" v-else>
          <table class="tbl">
            <thead><tr><th>ID</th><th>Driver</th><th>Nopol</th><th>BBM</th><th>Nominal</th><th>Liter</th><th>ODO</th><th>Anomali</th><th>Waktu</th><th></th></tr></thead>
            <tbody>
              <tr v-for="t in queue" :key="t.id">
                <td><b>{{ t.display_id }}</b></td>
                <td>{{ t.driver_name }}</td>
                <td>{{ t.nopol }}</td>
                <td>{{ t.bbm_type }}</td>
                <td>{{ fmt(t.nominal) }}</td>
                <td>{{ Number(t.liter || 0).toFixed(2) }}</td>
                <td>{{ t.odo_km ?? '—' }}</td>
                <td>
                  <span v-if="t.ml_anomaly_flag" class="badge badge-red">⚠️ Anomali</span>
                  <template v-else-if="getFlag(t.id)?.flags?.length">
                    <span v-for="(fl, fi) in getFlag(t.id).flags" :key="fi" class="badge" :class="fl.level === 'danger' ? 'badge-red' : 'badge-amber'" style="font-size:10px;">{{ fl.level === 'danger' ? '🔴' : '🟡' }} {{ fl.msg }}</span>
                  </template>
                  <span v-else class="muted">—</span>
                </td>
                <td class="muted">{{ t.created_at }}</td>
                <td>
                  <button class="btn btn-sm" :disabled="qBusy" title="Detail & verifikasi" @click="openDetail(t)">👁 Detail</button>
                  <template v-if="queueTab === 'ga' && canApprove">
                    <template v-if="t.ml_anomaly_flag">
                      <button class="btn btn-sm btn-primary" :disabled="qBusy" style="margin-left:6px;" title="Verifikasi anomali penuh (foto + konfirmasi) langsung di SPA" @click="openDetail(t, true)">🛡 Verifikasi</button>
                    </template>
                    <template v-else>
                      <button class="btn btn-sm btn-primary" :disabled="qBusy" style="margin-left:6px;" @click="doApprove(t)">✅</button>
                      <button class="btn btn-sm btn-danger" :disabled="qBusy" style="margin-left:6px;" @click="doReject(t)">❌</button>
                    </template>
                  </template>
                  <template v-else-if="queueTab === 'finance' && canFinance">
                    <button class="btn btn-sm btn-primary" :disabled="qBusy" style="margin-left:6px;" @click="doPayout(t)">💰</button>
                  </template>
                  <template v-else-if="queueTab === 'driver_confirm' && canFinance">
                    <button class="btn btn-sm btn-primary" :disabled="qBusy" style="margin-left:6px;" @click="doArchive(t)">📦</button>
                  </template>
                </td>
              </tr>
              <tr v-if="!queue.length"><td colspan="10" style="padding:0;"><EmptyState message="Antrean kosong. 🎉" icon="🎉" /></td></tr>
            </tbody>
          </table>
        </div>
      </div>

      <div class="card card-pad" style="margin-top:18px;">
        <h3>⚡ Aksi Cepat</h3>
        <div class="stat-grid">
          <router-link v-for="q in quick" :key="q.path" :to="q.path" style="text-decoration:none;">
            <div class="stat-card" style="display:flex;align-items:center;gap:12px;">
              <span style="font-size:22px;">{{ q.icon }}</span>
              <span style="font-weight:600;font-size:13px;">{{ q.label }}</span>
            </div>
          </router-link>
        </div>
      </div>

      <div class="card card-pad" style="margin-top:18px;">
        <h3>🔎 Verifikasi Mendalam</h3>
        <p class="muted" style="font-size:12px;">
          Semua alur verifikasi kini tersedia langsung dari SPA — tanpa pindah ke antarmuka klasik:
        </p>
        <ul style="margin:8px 0 0;padding-left:18px;font-size:12px;">
          <li><b>👁 Detail</b> — foto bukti, cross-check (health score, flag, budget) &amp; riwayat pelaku.</li>
          <li><b>🛡 Verifikasi Anomali</b> — transaksi ber-flag ML diverifikasi penuh (konfirmasi wajib + foto MyPertamina opsional).</li>
          <li><b>✏️ Edit</b> — perbaikan data kendaraan/BBM/nominal/ODO/SPBU → status <i>modified</i> untuk review ulang.</li>
          <li><b>↩️ Unverify</b> / <b>🗑 Hapus</b> (admin) — koreksi status &amp; penghapusan permanen.</li>
        </ul>
      </div>
    </template>

    <!-- Modal Detail Transaksi -->
    <Modal v-if="sel" :title="'🔍 ' + (selData?.display_id || sel.display_id || 'Detail Transaksi')" @close="sel = null; selData = null; selCross = null">
      <div v-if="selLoading" class="empty" style="padding:16px;">⏳ Memuat detail…</div>
      <div v-else-if="selData">
        <div class="row" style="flex-wrap:wrap;gap:8px;margin-bottom:12px;">
          <span class="badge" :class="selData.ml_anomaly_flag ? 'badge-red' : 'badge-green'">{{ selData.ml_anomaly_flag ? '⚠️ Anomali ML' : 'Normal' }}</span>
          <span class="badge badge-blue">{{ selData.status }}</span>
          <span class="badge" :class="selData.is_mypertamina_error ? 'badge-red' : 'badge-gray'">{{ selData.is_mypertamina_error ? '⚠️ Error MyPertamina' : 'MyPertamina OK' }}</span>
        </div>

        <div class="form-grid">
          <div class="field"><label>Driver</label><input class="input" :value="selData.driver_name" disabled /></div>
          <div class="field"><label>Nopol / Kendaraan</label><input class="input" :value="selData.nopol + ' · ' + (selData.vehicle_type || '')" disabled /></div>
          <div class="field"><label>BBM / SPBU</label><input class="input" :value="selData.bbm_type + ' · ' + (selData.spbu_type || '')" disabled /></div>
          <div class="field"><label>Nominal / Liter</label><input class="input" :value="fmt(selData.nominal) + ' · ' + Number(selData.liter || 0).toFixed(2) + ' L'" disabled /></div>
          <div class="field"><label>ODO / Km per Liter</label><input class="input" :value="selData.odo_km + ' km · ' + Number(selData.km_per_liter || 0).toFixed(1) + ' km/L'" disabled /></div>
          <div class="field"><label>Waktu</label><input class="input" :value="selData.created_at" disabled /></div>
        </div>
        <p v-if="selData.gps_address" class="muted" style="font-size:11px;">📍 {{ selData.gps_address }}</p>
        <p v-if="selData.rejection_reason" class="alert alert-error" style="margin:6px 0;">❌ Alasan tolak: {{ selData.rejection_reason }}</p>

        <h4 style="margin:12px 0 8px;">📷 Foto Bukti</h4>
        <div v-if="selData.photos?.length" style="display:flex;gap:8px;flex-wrap:wrap;">
          <a v-for="p in selData.photos" :key="p.url" :href="p.url" target="_blank" style="text-align:center;text-decoration:none;">
            <img :src="p.url" :alt="p.label" style="width:84px;height:84px;object-fit:cover;border-radius:8px;border:1px solid var(--border, #334155);" />
            <div class="muted" style="font-size:10px;">{{ p.label }}</div>
          </a>
        </div>
        <div v-else class="muted" style="font-size:12px;">Tidak ada foto bukti.</div>

        <!-- Form Verifikasi Anomali ML -->
        <div v-if="verifyMode && canApprove" class="alert alert-info" style="margin-top:12px;">
          <b>🛡 Verifikasi Mendalam (Anomali ML)</b>
          <p style="font-size:12px;margin:6px 0;">Transaksi ini ber-flag anomali — periksa foto bukti &amp; cross-check di atas sebelum menyetujui.</p>
          <label style="display:flex;gap:8px;align-items:center;font-size:13px;margin:6px 0;">
            <input type="checkbox" v-model="verifyForm.confirm_anomaly" /> Saya sudah memeriksa bukti &amp; menyetujui
          </label>
          <label style="display:flex;gap:8px;align-items:center;font-size:13px;margin:6px 0;">
            <input type="checkbox" v-model="verifyForm.mypertamina_error" /> Tandai error MyPertamina
          </label>
          <div style="margin:8px 0;">
            <label style="font-size:12px;">Foto MyPertamina (opsional):</label>
            <input type="file" accept="image/*" @change="e => verifyForm.file = e.target.files[0] || null" style="display:block;margin-top:4px;font-size:12px;" />
          </div>
          <button class="btn btn-sm btn-primary" :disabled="qBusy" @click="doVerify(selData)">✅ Simpan Verifikasi</button>
          <button class="btn btn-sm" :disabled="qBusy" @click="verifyMode = false">Batal</button>
        </div>

        <!-- Form Perbaikan Data -->
        <div v-if="editMode && canApprove" class="alert alert-info" style="margin-top:12px;">
          <b>✏️ Perbaiki Data Transaksi</b>
          <div class="form-grid" style="margin-top:8px;">
            <div class="field"><label>Kendaraan</label><input class="input" v-model="editForm.vehicle_type" /></div>
            <div class="field"><label>BBM</label><input class="input" v-model="editForm.bbm_type" /></div>
            <div class="field"><label>Nominal (Rp)</label><input class="input" type="number" v-model="editForm.nominal" /></div>
            <div class="field"><label>ODO (km)</label><input class="input" type="number" v-model="editForm.odo_km" /></div>
            <div class="field"><label>SPBU</label>
              <select class="input" v-model="editForm.spbu_type">
                <option value="rekanan">Rekanan</option>
                <option value="non_rekanan">Non-Rekanan</option>
              </select>
            </div>
          </div>
          <p class="muted" style="font-size:11px;margin:6px 0;">Perubahan menandai status <b>modified</b> untuk review ulang GA.</p>
          <button class="btn btn-sm btn-primary" :disabled="qBusy" @click="doModify(selData)">💾 Simpan Perubahan</button>
          <button class="btn btn-sm" :disabled="qBusy" @click="editMode = false">Batal</button>
        </div>

        <!-- Finance Review (prev ODO, monthly, budget) -->
        <template v-if="selFinanceReview && canFinance">
          <h4 style="margin:14px 0 8px;">💰 Finance Review</h4>
          <div class="row" style="gap:10px;flex-wrap:wrap;">
            <div class="stat-card" style="flex:1;min-width:120px;">
              <div class="s-icon" style="background:#d977061a;">📍</div>
              <div class="s-value" style="color:#d97706;font-size:16px;">{{ selFinanceReview.previous_odo?.odo_km ?? '—' }}</div>
              <div class="s-label">ODO Sebelumnya</div>
              <div class="s-bar" style="background:#d97706;"></div>
            </div>
            <div class="stat-card" style="flex:1;min-width:120px;">
              <div class="s-icon" style="background:#2563eb1a;">📅</div>
              <div class="s-value" style="color:#2563eb;">{{ num(selFinanceReview.monthly?.total_tx || 0) }}</div>
              <div class="s-label">Transaksi Bulan Ini</div>
              <div class="s-bar" style="background:#2563eb;"></div>
            </div>
            <div class="stat-card" style="flex:1;min-width:120px;">
              <div class="s-icon" style="background:#0596691a;">💵</div>
              <div class="s-value" style="color:#059669;">{{ fmt(selFinanceReview.monthly?.total_nominal || 0) }}</div>
              <div class="s-label">Nominal Bulan Ini</div>
              <div class="s-bar" style="background:#059669;"></div>
            </div>
          </div>
          <!-- Finance Remark -->
          <div style="margin-top:10px;">
            <div class="field"><label>Catatan Finance</label>
              <div class="row" style="gap:6px;">
                <input class="input" v-model="financeRemark" placeholder="Tambahkan catatan..." style="flex:1;" @keyup.enter="doFinanceRemark" />
                <button class="btn btn-sm btn-primary" :disabled="financeRemarkSaving || !financeRemark.trim()" @click="doFinanceRemark">💬 Simpan</button>
              </div>
            </div>
          </div>
        </template>

        <template v-if="selCross">
          <h4 style="margin:14px 0 8px;">🩺 Cross-Check</h4>
          <div class="row" style="gap:10px;flex-wrap:wrap;">
            <div class="stat-card" style="flex:1;min-width:120px;">
              <div class="s-icon" style="background:#2563eb1a;">🩺</div>
              <div class="s-value" style="color:#2563eb;font-size:20px;">{{ selCross.health_score || 0 }}/100</div>
              <div class="s-label">Health Score</div>
            </div>
            <div class="stat-card" style="flex:1;min-width:120px;">
              <div class="s-icon" style="background:#d977061a;">📊</div>
              <div class="s-value" style="color:#d97706;font-size:20px;">{{ selCross.budget_usage_percent || 0 }}%</div>
              <div class="s-label">Budget Bulanan</div>
            </div>
            <div class="stat-card" style="flex:1;min-width:120px;">
              <div class="s-icon" style="background:#0596691a;">🧮</div>
              <div class="s-value" style="color:#059669;font-size:20px;">{{ Number(selCross.odo_diff || 0).toLocaleString('id-ID') }}</div>
              <div class="s-label">Selisih ODO</div>
            </div>
          </div>
          <ul style="margin:10px 0 0;padding-left:18px;font-size:12px;">
            <li v-for="(f, i) in selCross.flags || []" :key="i" :class="f.level === 'danger' ? 'alert-error' : f.level === 'warning' ? 'alert-info' : 'alert-success'" style="padding:4px 8px;border-radius:6px;margin-bottom:4px;list-style:none;">
              {{ f.level === 'danger' ? '🔴' : f.level === 'warning' ? '🟡' : '🟢' }} {{ f.msg }}
            </li>
            <li v-if="!(selCross.flags || []).length" class="muted" style="list-style:none;">Tidak ada flag — transaksi bersih ✅</li>
          </ul>
          <p class="muted" style="font-size:11px;margin:8px 0 0;">
            Rekomendasi: <b>{{ selCross.recommendation }}</b> · Rata-rata 3 bulan: {{ selCross.avg_3months?.avg_kml || '—' }} km/L ({{ selCross.avg_3months?.tx_count || 0 }} tx)
          </p>
        </template>

        <div class="row" style="justify-content:flex-end;margin-top:14px;gap:6px;flex-wrap:wrap;">
          <template v-if="selData.status === 'pending' || selData.status === 'modified'">
            <button v-if="canApprove && !selData.ml_anomaly_flag" class="btn btn-sm btn-primary" :disabled="qBusy" @click="modalAction(`/api/queue/approve-ga/${selData.id}`, 'menyetujui klaim ini', true)">✅ Approve</button>
            <button v-if="canApprove && selData.ml_anomaly_flag" class="btn btn-sm btn-primary" :disabled="qBusy" @click="openVerify(selData)">🛡 Verifikasi Anomali</button>
            <button v-if="canApprove" class="btn btn-sm" :disabled="qBusy" @click="openEdit(selData)">✏️ Edit</button>
            <button v-if="canApprove" class="btn btn-sm btn-danger" :disabled="qBusy" @click="doReject(selData)">❌ Tolak</button>
          </template>
          <button v-if="selData.status === 'verified_ga' && canFinance" class="btn btn-sm btn-primary" :disabled="qBusy" @click="modalAction(`/api/queue/payout/${selData.id}`, 'mencairkan dana klaim ini', true)">💰 Cairkan</button>
          <button v-if="selData.status === 'os_finance' && canFinance" class="btn btn-sm btn-primary" :disabled="qBusy" @click="modalAction(`/api/queue/archive/${selData.id}`, 'mengarsipkan klaim ini')">📦 Arsipkan</button>
          <button v-if="selData.status === 'verified_ga' && canApprove" class="btn btn-sm" :disabled="qBusy" @click="modalAction(`/api/queue/unverify/${selData.id}`, 'mengembalikan klaim ke antrean GA')">↩️ Unverify</button>
          <button v-if="isAdmin" class="btn btn-sm btn-danger" :disabled="qBusy" @click="modalAction(`/api/queue/delete/${selData.id}`, 'menghapus PERMANEN transaksi ini')">🗑 Hapus</button>
        </div>
      </div>
    </Modal>
  </div>
</template>
