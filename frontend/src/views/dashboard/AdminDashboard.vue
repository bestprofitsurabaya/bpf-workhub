<script setup>
import { computed, nextTick, onMounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { api, notifyUnauthorized } from '../../api'
import { useAuthStore } from '../../stores/auth'
import StatCard from '../../components/StatCard.vue'
import PageHeader from '../../components/PageHeader.vue'
import Modal from '../../components/Modal.vue'
import ConfirmDialog from '../../components/ConfirmDialog.vue'
import { formatDateTime, formatNumber, formatRupiah, transactionStatusLabel } from '../../utils/format.js'
import LoadingState from '../../components/LoadingState.vue'
import EmptyState from '../../components/EmptyState.vue'
import ErrorState from '../../components/ErrorState.vue'
import { useStepupStore } from '../../stores/stepup'
import { markFirstAction } from '../../utils/usability.js'

const stepup = useStepupStore()
const router = useRouter()
const confirmRef = ref(null)
const ask = (message, opts) => confirmRef.value?.open(message, opts) ?? Promise.resolve(false)

const auth = useAuthStore()
const s = ref(null)
const loading = ref(true)
const err = ref('')

const fmt = formatRupiah
const num = formatNumber
const statusLabel = transactionStatusLabel
const fmtDateTime = (v) => formatDateTime(v, false)

onMounted(async () => {
  try { s.value = await api('/api/stats') }
  catch (e) { err.value = e.message }
  finally { loading.value = false }
  loadQueue()
  loadBranchStats()
  loadNavBadges()
})

async function refreshStats() {
  // Refresh diam-diam (tanpa mengubah state loading) agar dashboard tidak berkedip.
  try { s.value = await api('/api/stats') } catch { /* abaikan */ }
  loadNavBadges()
}

const cards = computed(() => {
  if (!s.value) return []
  const c = [
    { icon: '✅', label: 'Terverifikasi GA', value: s.value.verified_ga, color: '#0891b2', roles: ['ga', 'admin'], sub: 'Siap dicairkan Finance' },
    { icon: '📅', label: 'Transaksi Hari Ini', value: s.value.today_tx, color: '#2563eb', roles: ['ga', 'finance', 'admin'], sub: 'Klaim masuk hari ini' },
    { icon: '💵', label: 'Nominal Hari Ini', value: fmt(s.value.today_nominal), color: '#7c3aed', roles: ['finance', 'admin'], sub: 'Total nilai klaim hari ini' },
  ]
  return c.filter((x) => x.roles.includes(auth.role))
})

// ============================================================
// P2 UI/UX — "Perlu Tindakan Hari Ini"
// ============================================================
const navBadges = ref({})
async function loadNavBadges() {
  try {
    const d = await api('/api/nav/badges')
    navBadges.value = d?.badges || {}
  } catch { navBadges.value = {} }
}

const actionCards = computed(() => {
  if (!s.value) return []
  const b = navBadges.value
  const list = [
    { key: 'ga', icon: '🕐', label: 'Klaim menunggu verifikasi GA', hint: 'Antrean GA (pending)', count: Number(s.value.pending || 0), color: '#dc2626', roles: ['ga', 'admin'], kind: 'queue', tab: 'ga' },
    { key: 'finance', icon: '💰', label: 'Klaim siap dicairkan Finance', hint: 'Menunggu Finance (os_finance)', count: Number(s.value.os_finance || 0), color: '#d97706', roles: ['finance', 'admin'], kind: 'queue', tab: 'finance' },
    { key: 'water', icon: '🚰', label: 'Air minum menunggu verifikasi', hint: 'Pengajuan OB perlu dicek', count: Number(b.water_pending || 0), color: '#0891b2', roles: ['finance', 'admin'], kind: 'route', to: '/water' },
    { key: 'assignments', icon: '🚗', label: 'Penugasan belum dikonfirmasi', hint: 'Driver belum konfirmasi kendaraan', count: Number(b.assignments_pending || 0), color: '#7c3aed', roles: ['ga', 'admin'], kind: 'route', to: '/assignments' },
    { key: 'cash', icon: '💵', label: 'Kasbon / LPJ menunggu', hint: 'LPJ atau pencairan kasbon', count: Number(b.cash_pending || 0), color: '#059669', roles: ['ga', 'finance', 'admin'], kind: 'route', to: '/cash' },
  ]
  return list.filter((x) => x.roles.includes(auth.role))
})
const visibleActions = computed(() => actionCards.value.filter((a) => a.count > 0))
function runAction(a) {
  markFirstAction(`dashboard:${a.label}`)
  if (a.kind === 'queue') {
    queueTab.value = a.tab
    nextTick(() => document.getElementById('antrean-kerja')?.scrollIntoView({ behavior: 'smooth', block: 'start' }))
  } else if (a.to) {
    router.push(a.to)
  }
}

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
const isHoAdmin = computed(() => auth.isHoAdmin)

// Modal detail transaksi
const sel = ref(null)
const selData = ref(null)
const selCross = ref(null)
const selLoading = ref(false)
const selFinanceReview = ref(null) // finance review detail
const financeRemark = ref('') // remark form
const financeRemarkSaving = ref(false)
// v2.50.0 — verifikasi Subsidi Tepat (riwayat SPBU resmi akun perseroan)
const subsidy = ref(null)
const subsidyBusy = ref(false)

async function loadSubsidy(txId) {
  subsidy.value = null
  if (!['finance', 'admin'].includes(auth.role)) return
  try { subsidy.value = await api(`/api/subsidy/match/${txId}`) } catch { subsidy.value = null }
}

async function linkSubsidy(st) {
  if (!selData.value || !st || subsidyBusy.value) return
  const ok = await ask(`Tautkan klaim ini ke transaksi SPBU ${st.transaction_id} (${st.volume} L, ${st.spbu_id} ${st.witel || st.city}, ${st.transaction_date})?`, {
    title: 'Verifikasi Subsidi Tepat',
    confirmText: 'Tautkan',
  })
  if (!ok) return
  subsidyBusy.value = true
  try {
    const r = await api(`/api/subsidy/link/${selData.value.id}`, { method: 'POST', body: { subsidy_transaction_id: st.id } })
    queueMsg.value = '✅ ' + (r.msg || 'Tertaut')
    markFirstAction('subsidy_link')
    await loadSubsidy(selData.value.id)
  } catch (e) { queueMsg.value = '❌ ' + e.message }
  finally { subsidyBusy.value = false }
}

async function unlinkSubsidy() {
  if (!selData.value || subsidyBusy.value) return
  const ok = await ask('Lepas tautan verifikasi Subsidi Tepat klaim ini?', { title: 'Verifikasi Subsidi Tepat', confirmText: 'Lepas', danger: true })
  if (!ok) return
  subsidyBusy.value = true
  try {
    await api(`/api/subsidy/unlink/${selData.value.id}`, { method: 'POST' })
    queueMsg.value = '✅ Tautan dilepas'
    await loadSubsidy(selData.value.id)
  } catch (e) { queueMsg.value = '❌ ' + e.message }
  finally { subsidyBusy.value = false }
}

// v2.52.0 — restrukturisasi modal detail: tab klasifikasi + checklist
// verifikasi + zoom foto. Tujuan: Finance/GA tak lagi melihat tumpukan
// info tanpa urutan — keputusan berbasis checklist yang jelas.
const modalTab = ref('bukti')
const photoZoom = ref(null)
const modalTabs = computed(() => {
  const t = [{ key: 'bukti', label: '📋 Bukti & Data' }]
  if (canFinance.value) t.push({ key: 'subsidi', label: '⛽ Subsidi Tepat' })
  t.push({ key: 'analisis', label: '💰 Analisis Keuangan' })
  return t
})
const checklist = computed(() => {
  const d = selData.value
  const items = []
  items.push({
    label: 'Verifikasi GA',
    state: d?.ga_approved_by ? 'ok' : 'wait',
    detail: d?.ga_approved_by
      ? `${d.ga_approved_by}${d.ga_approved_at ? ' · ' + String(d.ga_approved_at).slice(0, 16) : ''}`
      : 'Menunggu ACC GA',
  })
  items.push({
    label: 'Anomali ML',
    state: !d?.ml_anomaly_flag ? 'none' : (d?.anomaly_cleared_by ? 'ok' : 'warn'),
    detail: !d?.ml_anomaly_flag ? 'Tidak ber-flag'
      : (d?.anomaly_cleared_by ? `Diperiksa ${d.anomaly_cleared_by}` : 'Belum diperiksa GA'),
  })
  items.push({
    label: 'Subsidi Tepat',
    state: subsidy.value?.linked ? 'ok' : (subsidy.value ? 'warn' : 'na'),
    detail: subsidy.value?.linked
      ? `${subsidy.value.linked.transaction_id} · ${subsidy.value.linked.volume} L`
      : (subsidy.value ? (subsidy.value.verdict || '—').toUpperCase() : '—'),
  })
  const hs = selCross.value?.health_score
  items.push({
    label: 'Health Score',
    state: hs == null ? 'na' : (hs >= 80 ? 'ok' : hs >= 60 ? 'warn' : 'bad'),
    detail: selCross.value
      ? `${hs ?? '—'}/100 · Budget ${selCross.value.budget_usage_percent ?? '—'}%` : '—',
  })
  return items
})

// v2.51.0 — Berita Acara Rekonsiliasi Subsidi Tepat (PDF untuk kantor pusat)
const attestOpen = ref(false)
const attestPeriod = ref(new Date().toISOString().slice(0, 7))
const attestBusy = ref(false)
const attestMsg = ref('')
const attestList = ref([])

async function openAttest() {
  attestOpen.value = true
  attestMsg.value = ''
  try { attestList.value = (await api('/api/subsidy/attest')).attestations || [] }
  catch { attestList.value = [] }
}

async function createAttest(row) {
  if (attestBusy.value) return
  if (row) {
    // unduh PDF BA tersimpan
    window.open(`/api/subsidy/attest/${row.id}/pdf`, '_blank')
    return
  }
  const ok = await ask(`Terbitkan Berita Acara periode ${attestPeriod.value}? Semua klaim yang DITAUT finance di periode itu dimasukkan dokumen (root hash terekam permanen).`, {
    title: 'Berita Acara Rekonsiliasi', confirmText: 'Terbitkan',
  })
  if (!ok) return
  attestBusy.value = true
  attestMsg.value = ''
  try {
    const r = await api('/api/subsidy/attest', { method: 'POST', body: { period: attestPeriod.value } })
    attestMsg.value = '✅ ' + (r.msg || 'Terbit')
    markFirstAction('subsidy_attest')
    await openAttest()
    window.open(`/api/subsidy/attest/${r.id}/pdf`, '_blank')
  } catch (e) { attestMsg.value = '❌ ' + e.message }
  finally { attestBusy.value = false }
}

async function loadQueue() {
  queueLoading.value = true; queueMsg.value = ''
  try { queue.value = (await api('/api/queue', { params: { tab: queueTab.value } })) || [] }
  catch (e) { queueMsg.value = '❌ ' + e.message }
  finally { queueLoading.value = false }
}

async function queueAction(path, label, needsStepup = false) {
  const ok = await ask(`Yakin ${label}?`, {
    title: 'Konfirmasi tindakan',
    confirmText: 'Ya, lanjutkan',
    danger: /hapus|tolak|menolak|PERMANEN/i.test(label),
  })
  if (!ok) return false
  qBusy.value = true; queueMsg.value = ''
  try {
    // Aksi uang (approve/payout) wajib step-up — PIN ulang bila perlu (ISO/IEC 27001 A.8.5)
    const run = () => api(path, { method: 'POST' })
    const r = needsStepup ? await stepup.require(run, label) : await run()
    queueMsg.value = '✅ ' + (r.msg || r.message || label)
    markFirstAction(`queue:${label}`)
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
  const reason = await ask(`Alasan menolak ${tx.display_id} (${tx.driver_name}):`, {
    title: 'Tolak klaim',
    confirmText: 'Tolak klaim',
    danger: true,
    input: true,
    required: true,
    placeholder: 'mis. foto bukti tidak terbaca / nominal tidak sesuai',
  })
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
  markFirstAction(`detail:${tx.display_id || tx.id}`)
  sel.value = tx
  selLoading.value = true
  selData.value = null; selCross.value = null; selFinanceReview.value = null; subsidy.value = null
  verifyMode.value = false; editMode.value = false
  financeRemark.value = ''
  modalTab.value = 'bukti'
  photoZoom.value = null
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
    // v2.50.0: kandidat verifikasi Subsidi Tepat (finance/admin)
    loadSubsidy(tx.id)
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
      if (r.status === 401) await notifyUnauthorized()
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
    <PageHeader :icon="auth.meta?.icon || ''" :title="`Selamat datang, ${auth.user?.full_name || auth.user?.user_name}`" :subtitle="`Dashboard ${auth.meta?.label} · data transaksi & klaim BBM terkini`">
      <span class="role-chip" :style="{ background: auth.meta?.color }">{{ auth.meta?.label }}</span>
    </PageHeader>

    <div v-if="loading" class="empty">⏳ Memuat data…</div>
    <div v-else-if="err" class="alert alert-error">{{ err }}</div>
    <template v-else>
      <!-- P2: yang perlu dikerjakan lebih dulu, bukan sekadar angka -->
      <section v-if="visibleActions.length" class="action-wrap">
        <div class="row" style="flex-wrap:wrap;gap:8px;align-items:baseline;">
          <h2 class="sec-title" style="margin:0;">⚡ Perlu Tindakan Hari Ini</h2>
          <span class="muted" style="font-size:11px;">Klik kartu untuk langsung ke antrean terkait.</span>
        </div>
        <div class="action-grid">
          <button v-for="a in visibleActions" :key="a.key" type="button" class="action-card"
                  :style="{ '--accent': a.color }" :aria-label="`${a.label}: ${a.count}`" @click="runAction(a)">
            <span class="action-ico" aria-hidden="true">{{ a.icon }}</span>
            <span class="action-count">{{ a.count }}</span>
            <span class="action-label">{{ a.label }}</span>
            <span class="action-hint">{{ a.hint }}</span>
          </button>
        </div>
      </section>
      <div v-else class="card card-pad action-clear">
        <b>✅ Tidak ada tindakan mendesak hari ini.</b>
        <span class="muted" style="font-size:12px;">Antrean sudah bersih — Anda bisa lanjut memantau laporan di bawah.</span>
      </div>

      <h2 class="sec-title">📊 Ringkasan Angka</h2>
      <div class="stat-grid">
        <StatCard v-for="c in cards" :key="c.label" :icon="c.icon" :label="c.label" :value="c.value" :color="c.color" :sub="c.sub" />
      </div>

      <!-- Ringkasan Cabang (Admin) -->
      <div v-if="isAdmin" class="card card-pad" style="margin-top:18px;">
        <div class="row" style="flex-wrap:wrap;gap:8px;align-items:center;">
          <h3 style="margin:0;">🏢 {{ isHoAdmin ? 'Ringkasan Cabang' : 'Ringkasan Cabang Anda' }}</h3>
          <span class="muted" style="font-size:11px;">{{ isHoAdmin ? 'Transaksi, kunjungan hari ini & user per cabang (multi-cabang)' : 'Transaksi, kunjungan hari ini & user cabang aktif' }}</span>
          <div class="spacer"></div>
          <button class="btn btn-sm" :title="isHoAdmin ? 'Unduh PDF ringkasan cabang' : 'Unduh PDF ringkasan cabang Anda'" @click="openBranchReportPdf">📄 PDF</button>
          <template v-if="isHoAdmin">
            <button class="btn btn-sm" title="Unduh laporan konsolidasi lintas cabang (semua DB) sebagai PDF" aria-label="Unduh PDF konsolidasi lintas cabang" @click="openConsolidatedPdf">🧮 PDF Konsolidasi</button>
            <button class="btn btn-sm" title="Unduh laporan konsolidasi lintas cabang sebagai Excel" aria-label="Unduh Excel konsolidasi lintas cabang" @click="openConsolidatedExcel">🧮 Excel Konsolidasi</button>
          </template>
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
      <div id="antrean-kerja" class="card card-pad" style="margin-top:18px;">
        <div class="row" style="flex-wrap:wrap;gap:8px;">
          <h3 style="margin:0;">🕐 Antrean Kerja</h3>
          <button v-for="t in queueTabs" :key="t.key" class="btn btn-sm" :class="queueTab === t.key ? 'btn-primary' : ''" @click="queueTab = t.key">{{ t.label }}</button>
          <button class="btn btn-sm" title="Unduh antrean tab aktif sebagai Excel" aria-label="Unduh antrean sebagai Excel" @click="exportQueueExcel">⬇️ Excel</button>
          <button v-if="canFinance" class="btn btn-sm" title="Berita Acara Rekonsiliasi Subsidi Tepat — dokumen resmi kantor pusat" @click="openAttest">🖨 Berita Acara SPBU</button>
          <span v-if="queueMsg" class="alert" :class="queueMsg.startsWith('✅') ? 'alert-success' : 'alert-error'" style="margin:0;">{{ queueMsg }}</span>
          <div class="spacer"></div>
        </div>
        <p class="muted" style="font-size:11px;margin:8px 0 0;">
          Tabel diringkas. Klik <b>Detail</b> untuk melihat BBM, liter, ODO, foto bukti, dan cross-check.
        </p>
        <div v-if="queueLoading"><LoadingState rows="3" label="Memuat antrean…" /></div>
        <div v-else-if="queueMsg && queueMsg.startsWith('❌')" ><ErrorState :message="queueMsg.slice(2)" @retry="loadQueue" /></div>
        <div class="table-wrap" v-else>
          <table class="tbl">
            <thead><tr><th>ID</th><th>Driver / Nopol</th><th>Nominal</th><th>Status</th><th>Waktu</th><th>Aksi</th></tr></thead>
            <tbody>
              <tr v-for="t in queue" :key="t.id">
                <td><b>{{ t.display_id }}</b></td>
                <td>
                  {{ t.driver_name }}
                  <div class="muted" style="font-size:10px;">{{ t.nopol }}</div>
                </td>
                <td>{{ fmt(t.nominal) }}</td>
                <td>
                  <span class="badge" :class="t.status === 'rejected' ? 'badge-red' : t.status === 'archived' ? 'badge-green' : t.status === 'os_finance' ? 'badge-amber' : 'badge-blue'">{{ statusLabel(t.status) }}</span>
                  <span v-if="t.ml_anomaly_flag" class="badge badge-red" style="margin-left:4px;">⚠️ Anomali</span>
                  <template v-else-if="getFlag(t.id)?.flags?.length">
                    <span v-for="(fl, fi) in getFlag(t.id).flags" :key="fi" class="badge" :class="fl.level === 'danger' ? 'badge-red' : 'badge-amber'" style="font-size:10px;margin-left:4px;">{{ fl.level === 'danger' ? '🔴' : '🟡' }} {{ fl.msg }}</span>
                  </template>
                </td>
                <td class="muted">{{ fmtDateTime(t.created_at) }}</td>
                <td>
                  <button class="btn btn-sm" :disabled="qBusy" title="Detail & verifikasi" @click="openDetail(t)">👁 Detail</button>
                  <template v-if="queueTab === 'ga' && canApprove">
                    <template v-if="t.ml_anomaly_flag">
                      <button class="btn btn-sm btn-primary" :disabled="qBusy" style="margin-left:6px;" title="Verifikasi anomali penuh (foto + konfirmasi) langsung di SPA" @click="openDetail(t, true)">🛡 Verifikasi</button>
                    </template>
                    <template v-else>
                      <button class="btn btn-sm btn-primary" :disabled="qBusy" style="margin-left:6px;" title="Setujui klaim" @click="doApprove(t)">✅ Setujui</button>
                      <button class="btn btn-sm btn-danger" :disabled="qBusy" style="margin-left:6px;" title="Tolak klaim" @click="doReject(t)">❌ Tolak</button>
                    </template>
                  </template>
                  <template v-else-if="queueTab === 'finance' && canFinance">
                    <button class="btn btn-sm btn-primary" :disabled="qBusy" style="margin-left:6px;" title="Cairkan dana" @click="doPayout(t)">💰 Cairkan</button>
                  </template>
                  <template v-else-if="queueTab === 'driver_confirm' && canFinance">
                    <button class="btn btn-sm btn-primary" :disabled="qBusy" style="margin-left:6px;" title="Arsipkan" @click="doArchive(t)">📦 Arsipkan</button>
                  </template>
                </td>
              </tr>
              <tr v-if="!queue.length"><td colspan="6" style="padding:0;"><EmptyState message="Antrean kosong. 🎉" icon="🎉" /></td></tr>
            </tbody>
          </table>
        </div>
      </div>

      <details class="card card-pad help-details">
        <summary>❓ Panduan verifikasi &amp; perbaikan data</summary>
        <p class="muted" style="font-size:12px;margin-top:8px;">
          Semua alur verifikasi tersedia langsung dari SPA — tanpa pindah ke antarmuka klasik:
        </p>
        <ul style="margin:8px 0 0;padding-left:18px;font-size:12px;">
          <li><b>👁 Detail</b> — foto bukti, cross-check (health score, flag, budget) &amp; riwayat pelaku.</li>
          <li><b>🛡 Verifikasi Anomali</b> — transaksi ber-flag ML diverifikasi penuh (konfirmasi wajib + foto MyPertamina opsional).</li>
          <li><b>✏️ Edit</b> — perbaikan data kendaraan/BBM/nominal/ODO/SPBU → status <i>modified</i> untuk review ulang.</li>
          <li><b>↩️ Unverify</b> / <b>🗑 Hapus</b> (admin) — koreksi status &amp; penghapusan permanen.</li>
        </ul>
      </details>
    </template>

    <!-- Modal Detail Transaksi -->
    <Modal v-if="sel" :title="'🔍 ' + (selData?.display_id || sel.display_id || 'Detail Transaksi')" @close="sel = null; selData = null; selCross = null">
      <div v-if="selLoading" class="empty" style="padding:16px;">⏳ Memuat detail…</div>
      <div v-else-if="selData">
        <div class="row" style="flex-wrap:wrap;gap:8px;margin-bottom:12px;">
          <span class="badge" :class="selData.ml_anomaly_flag ? 'badge-red' : 'badge-green'">{{ selData.ml_anomaly_flag ? '⚠️ Anomali ML' : 'Normal' }}</span>
          <span class="badge badge-blue">{{ statusLabel(selData.status) }}</span>
          <span class="badge" :class="selData.is_mypertamina_error ? 'badge-red' : 'badge-gray'">{{ selData.is_mypertamina_error ? '⚠️ Error MyPertamina' : 'MyPertamina OK' }}</span>
        </div>

        <!-- v2.52.0: Ringkasan Verifikasi — checklist keputusan di atas -->
        <div class="verify-checklist" data-testid="verify-checklist">
          <div v-for="it in checklist" :key="it.label" class="vc-item" :class="'vc-' + it.state">
            <div class="vc-head"><span class="vc-dot">{{ it.state === 'ok' ? '✅' : it.state === 'warn' ? '⚠️' : it.state === 'bad' ? '🔴' : it.state === 'none' ? '✅' : '⏳' }}</span><span class="vc-label">{{ it.label }}</span></div>
            <div class="vc-detail">{{ it.detail }}</div>
          </div>
        </div>

        <!-- v2.52.0: tab klasifikasi konten modal -->
        <div class="row" style="gap:6px;margin:12px 0 0;flex-wrap:wrap;">
          <button v-for="t in modalTabs" :key="t.key" class="btn btn-sm" :class="modalTab === t.key ? 'btn-primary' : ''" @click="modalTab = t.key">{{ t.label }}</button>
        </div>

        <template v-if="modalTab === 'bukti'">
        <div class="form-grid" style="margin-top:12px;">
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
        <div v-if="selData.photos?.length" style="display:flex;gap:10px;flex-wrap:wrap;">
          <button v-for="p in selData.photos" :key="p.url" title="Klik untuk perbesar" style="background:none;border:none;padding:0;cursor:zoom-in;text-align:center;" @click="photoZoom = p.url">
            <img :src="p.url" :alt="p.label" style="width:120px;height:120px;object-fit:cover;border-radius:8px;border:1px solid var(--border, #334155);" />
            <div class="muted" style="font-size:10px;">{{ p.label }}</div>
          </button>
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
        </template>

        <!-- 💰 Analisis Keuangan (tab) — bagian 1: volume & budget -->
        <template v-else-if="modalTab === 'analisis'">
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
        </template>

        <template v-else-if="modalTab === 'subsidi' && canFinance">
        <!-- v2.50.0: Verifikasi Subsidi Tepat (finance/admin) -->
        <template v-if="subsidy && canFinance">
          <h4 style="margin:14px 0 8px;">⛽ Verifikasi Subsidi Tepat</h4>
          <template v-if="subsidy.linked">
            <div style="border:1px solid #05966933;background:#05966914;border-radius:8px;padding:8px 10px;font-size:12px;">
              <b style="color:#059669;">✅ Tertaut ke SPBU resmi:</b>
              {{ subsidy.linked.transaction_id }} · {{ subsidy.linked.volume }} L · Rp {{ Number(subsidy.linked.amount).toLocaleString('id-ID') }}
              · {{ subsidy.linked.transaction_date }} · SPBU {{ subsidy.linked.spbu_id }} {{ subsidy.linked.witel || subsidy.linked.city }}
              <span class="muted">(oleh {{ subsidy.linked_by }})</span>
            </div>
            <button class="btn btn-sm" style="margin-top:6px;" :disabled="subsidyBusy" @click="unlinkSubsidy">🔓 Lepas Tautan</button>
          </template>
          <template v-else>
            <p style="margin:0 0 6px;font-size:12px;" class="muted">
              Bandingkan klaim ({{ subsidy.nopol_norm }} · {{ subsidy.liter }} L · Rp {{ Number(subsidy.nominal).toLocaleString('id-ID') }}) dengan riwayat akuisisi Subsidi Tepat (SPBU).
            </p>
            <div v-if="subsidy.verdict === 'no_record'"
                 style="border:1px solid #dc262633;background:#dc26260d;border-radius:8px;padding:8px 10px;font-size:12px;color:#b91c1c;">
              🔴 Tidak ada transaksi SPBU untuk nopol ini ±1 hari dari tanggal klaim.
              Pastikan data riwayat sudah diimpor (agen pull harian) sebelum memutuskan.
            </div>
            <div v-else-if="subsidy.verdict === 'no_match'"
                 style="border:1px solid #d9770633;background:#d977060d;border-radius:8px;padding:8px 10px;font-size:12px;color:#b45309;">
              🟡 Ada kandidat, tapi tidak sesuai volume/nominal — cek manual di bawah.
            </div>
            <div v-else-if="subsidy.verdict === 'close'"
                 style="border:1px solid #d9770633;background:#d977060d;border-radius:8px;padding:8px 10px;font-size:12px;color:#b45309;">
              🟡 Kandidat mendekati (selisih kecil) — periksa lalu tautkan yang benar.
            </div>
            <div v-else
                 style="border:1px solid #05966933;background:#05966914;border-radius:8px;padding:8px 10px;font-size:12px;color:#059669;">
              🟢 Ada kandidat yang cocok (liter &amp; nominal) — periksa dan tautkan.
            </div>
            <table class="table" style="margin-top:8px;font-size:12px;" v-if="(subsidy.candidates || []).length">
              <thead><tr><th>Waktu SPBU</th><th>Nopol</th><th>Volume</th><th>Nominal</th><th>SPBU</th><th>Verifikasi</th><th></th></tr></thead>
              <tbody>
                <tr v-for="c in subsidy.candidates" :key="c.id" :style="c.id === subsidy.linked?.id ? 'background:#05966914;' : ''">
                  <td>{{ c.transaction_date }}</td>
                  <td>{{ c.nopol_raw }}</td>
                  <td>{{ c.volume }} L <span v-if="c.dvol" class="muted">({{ c.dvol > 0 ? '+' : '' }}{{ c.dvol }})</span></td>
                  <td>Rp {{ Number(c.amount).toLocaleString('id-ID') }}</td>
                  <td>{{ c.spbu_id }} · {{ c.witel || c.city }}</td>
                  <td>{{ c.verification }}</td>
                  <td><button class="btn btn-sm btn-primary" :disabled="subsidyBusy" @click="linkSubsidy(c)">🔗 Tautkan</button></td>
                </tr>
              </tbody>
            </table>
            <p class="muted" style="font-size:11px;margin:6px 0 0;">Data riwayat diimpor dari portal Subsidi Tepat (agen host); sifatnya bantuan verifikasi — keputusan tetap Finance.</p>
          </template>
        </template>
        </template>

        <template v-else-if="modalTab === 'analisis'">
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
        </template>

        <!-- v2.52.0: Keputusan — selalu tampak, terpisah dari konten tab -->
        <div class="row" style="justify-content:flex-end;margin-top:14px;gap:6px;flex-wrap:wrap;">
          <template v-if="selData.status === 'pending' || selData.status === 'modified'">
            <button v-if="canApprove && !selData.ml_anomaly_flag" class="btn btn-sm btn-primary" :disabled="qBusy" @click="modalAction(`/api/queue/approve-ga/${selData.id}`, 'menyetujui klaim ini', true)">✅ Setujui</button>
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

    <!-- v2.51.0: Modal Berita Acara Rekonsiliasi Subsidi Tepat -->
    <Modal v-if="attestOpen" title="🖨 Berita Acara Rekonsiliasi Subsidi Tepat" @close="attestOpen = false">
      <p class="muted" style="font-size:12px;">
        Dokumen resmi untuk <b>Kantor Pusat</b>: semua klaim yang <b>diterbitkan/ditautkan Finance</b>
        di satu periode disandingkan dengan nomor transaksi resmi SPBU (MyPertamina), dilengkapi
        rantai hash SHA-256 + TTD bertingkat. Kantor pusat dapat mencerminkan setiap nomor transaksi
        langsung di portal subsiditepat.mypertamina.id → Riwayat.
      </p>
      <div class="row" style="gap:8px;margin-top:10px;flex-wrap:wrap;align-items:center;">
        <input class="input" type="month" v-model="attestPeriod" style="max-width:170px;" :disabled="attestBusy" />
        <button class="btn btn-sm btn-primary" :disabled="attestBusy" @click="createAttest(null)">🖨 Terbitkan BA</button>
      </div>
      <p v-if="attestMsg" class="alert" :class="attestMsg.startsWith('✅') ? 'alert-success' : 'alert-error'" style="margin:10px 0 0;font-size:12px;">{{ attestMsg }}</p>

      <h4 style="margin:16px 0 6px;">📚 BA tersimpan (arsip server)</h4>
      <div v-if="!attestList.length" class="muted" style="font-size:12px;">
        Belum ada Berita Acara yang diterbitkan.
      </div>
      <div v-else class="table-wrap">
        <table class="tbl">
          <thead><tr><th>BA</th><th>Periode</th><th>Klaim</th><th>Root Hash</th><th>Oleh</th><th>Waktu</th><th></th></tr></thead>
          <tbody>
            <tr v-for="a in attestList" :key="a.id">
              <td><b>#{{ a.id }}</b></td>
              <td>{{ a.period_start }} s/d {{ a.period_end }}</td>
              <td>{{ a.record_count }}</td>
              <td class="muted" style="font-size:10px;">{{ (a.root_hash || '').slice(0, 16) }}…</td>
              <td>{{ a.generated_by }}</td>
              <td class="muted" style="font-size:11px;">{{ a.generated_at?.slice(0, 19) }}</td>
              <td><button class="btn btn-sm" @click="createAttest(a)">📄 PDF</button></td>
            </tr>
          </tbody>
        </table>
      </div>
      <p class="muted" style="font-size:11px;margin-top:10px;">
        ⚠️ Root hash = sidik jari permanen isi dokumen. Bila data di sistem diubah setelah BA
        diterbitkan, hash tidak akan cocok dengan salinan cetak — perubahan apa pun terdeteksi.
      </p>
    </Modal>

    <!-- v2.52.0: overlay zoom foto bukti -->
    <div v-if="photoZoom" class="photo-zoom-overlay" @click="photoZoom = null">
      <img :src="photoZoom" alt="Foto bukti diperbesar" />
      <p class="muted" style="color:#e2e8f0;font-size:11px;margin-top:6px;">Klik di mana saja untuk menutup</p>
    </div>

    <ConfirmDialog ref="confirmRef" />
  </div>
</template>

<style scoped>
.action-wrap { margin-bottom: 18px; }
.sec-title { font-size: 13px; font-weight: 700; margin: 18px 0 10px; display: flex; align-items: center; gap: 8px; }
.action-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(170px, 1fr)); gap: 10px; margin-top: 10px; }
.action-card {
  --accent: var(--primary);
  display: grid; grid-template-columns: auto 1fr;
  grid-template-areas: "ico count" "label label" "hint hint";
  gap: 2px 10px; text-align: left;
  background: var(--surface); border: 1px solid var(--border);
  border-left: 4px solid var(--accent); border-radius: 12px;
  padding: 12px 14px; color: var(--text);
  box-shadow: var(--shadow); font-family: inherit;
  transition: transform .15s, border-color .15s;
}
.action-card:hover { transform: translateY(-2px); border-color: var(--accent); }
.action-ico { grid-area: ico; font-size: 20px; line-height: 1; }
.action-count { grid-area: count; justify-self: end; font-size: 24px; font-weight: 800; line-height: 1; color: var(--accent); }
.action-label { grid-area: label; font-weight: 700; font-size: 12.5px; }
.action-hint { grid-area: hint; font-size: 10.5px; color: var(--text-3); }
.action-clear { display: flex; flex-direction: column; gap: 3px; border-left: 4px solid var(--success); margin-bottom: 18px; }
.help-details { margin-top: 18px; }
.help-details summary { cursor: pointer; font-weight: 700; font-size: 13px; }

/* v2.52.0 — checklist verifikasi + zoom foto (modal detail) */
.verify-checklist {
  display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
  gap: 8px; margin-top: 2px;
}
.vc-item {
  border: 1px solid var(--border); border-radius: 10px; padding: 8px 10px;
  background: var(--surface);
}
.vc-head { display: flex; gap: 6px; align-items: center; font-weight: 700; font-size: 12px; }
.vc-dot { font-size: 13px; }
.vc-detail { font-size: 10.5px; color: var(--text-3); margin-top: 2px; word-break: break-all; }
.vc-ok { border-left: 3px solid var(--success, #059669); }
.vc-warn { border-left: 3px solid #d97706; }
.vc-bad { border-left: 3px solid #dc2626; }
.vc-wait { border-left: 3px solid var(--border); }
.vc-none { border-left: 3px solid var(--border); }
.vc-na { border-left: 3px solid var(--border); opacity: .7; }
.photo-zoom-overlay {
  position: fixed; inset: 0; z-index: 60;
  background: rgba(2, 6, 23, .82); display: flex; flex-direction: column;
  align-items: center; justify-content: center; cursor: zoom-out; padding: 24px;
}
.photo-zoom-overlay img {
  max-width: min(92vw, 900px); max-height: 82vh; border-radius: 12px;
  box-shadow: 0 20px 60px rgba(0,0,0,.5);
}
</style>
