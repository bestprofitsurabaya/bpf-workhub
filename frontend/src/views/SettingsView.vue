<script setup>
import { computed, onMounted, ref } from 'vue'
import { api } from '../api'
import Modal from '../components/Modal.vue'
import ConfirmDialog from '../components/ConfirmDialog.vue'
import LoadingState from '../components/LoadingState.vue'
import ErrorState from '../components/ErrorState.vue'
import PageHeader from '../components/PageHeader.vue'
import { identity } from '../stores/identity'
import { useAuthStore } from '../stores/auth'

const auth = useAuthStore()
const confirmRef = ref(null)
const ask = (message, opts) => confirmRef.value?.open(message, opts) ?? Promise.resolve(false)

const drivers = ref([])
const vehicles = ref([])
const bbms = ref([])
const loading = ref(true)
const err = ref('')
const msg = ref('')
const busy = ref(false)

// Buat akun sekaligus (v2.19): semua driver + semua user di dropdown marketing
const bulkBusy = ref(false)
const bulkMsg = ref('')
const bulkResult = ref(null) // { scope, created: [], skipped: [] }
const showBulk = ref(false)

async function bulkCreate(scope) {
  const label = scope === 'driver' ? 'SEMUA driver aktif' : scope === 'marketing' ? 'SEMUA user di dropdown marketing' : 'semua akun'
  if (!(await ask(`Buat akun login (PIN acak aman) untuk ${label} yang belum punya akun?`, { confirmText: 'Ya, lanjutkan' }))) return
  bulkBusy.value = true; bulkMsg.value = ''; bulkResult.value = null
  try {
    const r = await api('/api/users/bulk-create', { method: 'POST', body: { scope } })
    bulkMsg.value = '✅ ' + (r.msg || 'Akun dibuat')
    bulkResult.value = r
    showBulk.value = true
  } catch (e) { bulkMsg.value = '❌ ' + e.message }
  finally { bulkBusy.value = false }
}

const showVehicleForm = ref(false)
const vehicleForm = ref({ nopol: '', vehicle_type: 'AVANZA', brand: 'Toyota', bbm_default: 'PERTALITE' })

// Identitas perusahaan / cabang (v2.19.2) — multi-cabang
const identityForm = ref({ company_name: '', company_subtitle: '', system_name: '', system_version: '', company_address: '', company_phone: '' })
const identityMsg = ref('')
const identityBusy = ref(false)

async function loadIdentityForm() {
  try {
    const d = await api('/api/system-config/identity')
    if (d && !d.error) {
      identityForm.value = {
        company_name: d.company_name || '',
        company_subtitle: d.company_subtitle || '',
        system_name: d.system_name || '',
        system_version: d.system_version || '',
        company_address: d.company_address || '',
        company_phone: d.company_phone || '',
      }
    }
  } catch { /* noop */ }
}

async function saveIdentity() {
  identityBusy.value = true; identityMsg.value = ''
  try {
    const r = await api('/api/system-config/identity', { method: 'PUT', body: { ...identityForm.value } })
    identityMsg.value = '✅ ' + (r.msg || 'Identitas perusahaan disimpan')
    Object.assign(identity, r.identity || identityForm.value)
    document.title = identity.system_name
  } catch (e) { identityMsg.value = '❌ ' + e.message }
  finally { identityBusy.value = false }
}

// Status deploy (v2.98.1) — versi image berjalan vs versi repo (CHANGELOG).
const deployStatus = ref(null)
const deployErr = ref('')
const deployBusy = ref(false)

async function loadDeployStatus() {
  deployBusy.value = true; deployErr.value = ''
  try { deployStatus.value = await api('/api/admin/deploy-status') }
  catch (e) { deployStatus.value = null; deployErr.value = e.message || 'Gagal memuat status deploy' }
  finally { deployBusy.value = false }
}

const deployBadge = computed(() => {
  if (!deployStatus.value) return { label: 'Tidak diketahui', cls: 'badge-gray' }
  if (deployStatus.value.stale) return { label: '⚠️ Tertinggal', cls: 'badge-red' }
  if (deployStatus.value.state === 'ok') return { label: '✅ Sinkron', cls: 'badge-green' }
  return { label: '❔ Tidak diketahui', cls: 'badge-gray' }
})

// Cabang (v2.19.2) — multi-cabang: satu instalasi, banyak cabang (DB terpisah)
const branches = ref([])
const currentBranch = ref(null)
const branchBusy = ref(false)
const branchMsg = ref('')
const showBranchForm = ref(false)
const branchForm = ref({ id: null, code: '', name: '', db_name: '', city: '', address: '', phone: '', company_name: '', company_subtitle: '', system_name: '', system_version: '', is_active: true, ensure_db: true })

async function loadBranches() {
  try {
    const d = await api('/api/branches/current')
    currentBranch.value = d.current || null
    branches.value = Array.isArray(d.branches) ? d.branches : []
  } catch { /* noop */ }
  // v2.37.7: daftar dari /current tidak memuat field identitas (id, address,
  // phone, dst.) — lengkapi dari /api/branches agar tombol ✏️ Edit mengisi
  // form dengan nilai yang benar (bukan form Tambah kosong).
  try {
    const full = await api('/api/branches')
    if (Array.isArray(full.branches) && full.branches.length) {
      const byCode = Object.fromEntries(full.branches.map((b) => [b.code, b]))
      branches.value = branches.value.map((b) => ({ ...b, ...(byCode[b.code] || {}) }))
    }
  } catch { /* tetap pakai daftar /current */ }
}

function openBranchForm(b) {
  if (b && b.id) {
    branchForm.value = {
      id: b.id, code: b.code, name: b.name, db_name: b.db_name, city: b.city || '',
      address: b.address || '', phone: b.phone || '', company_name: b.company_name || '',
      company_subtitle: b.company_subtitle || '', system_name: b.system_name || '',
      system_version: b.system_version || '', is_active: !!b.is_active, ensure_db: false,
    }
  } else {
    branchForm.value = { id: null, code: '', name: '', db_name: '', city: '', address: '', phone: '', company_name: '', company_subtitle: '', system_name: '', system_version: '', is_active: true, ensure_db: true }
  }
  showBranchForm.value = true
}

async function saveBranch() {
  branchBusy.value = true; branchMsg.value = ''
  try {
    const body = { ...branchForm.value }
    body.code = (body.code || '').trim().toUpperCase()
    if (!body.code || !body.name || !body.db_name) { branchMsg.value = '❌ code, nama, dan db_name wajib'; return }
    const r = await api('/api/branches/save', { method: 'POST', body })
    branchMsg.value = '✅ ' + (r.msg || 'Cabang disimpan')
    showBranchForm.value = false
    loadBranches()
  } catch (e) { branchMsg.value = '❌ ' + e.message }
  finally { branchBusy.value = false }
}

async function toggleBranch(code, active) {
  branchBusy.value = true; branchMsg.value = ''
  try {
    const r = await api(`/api/branches/${encodeURIComponent(code)}/${active ? 'activate' : 'deactivate'}`, { method: 'POST' })
    branchMsg.value = '✅ ' + (r.msg || 'Status cabang diperbarui')
    loadBranches()
  } catch (e) { branchMsg.value = '❌ ' + e.message }
  finally { branchBusy.value = false }
}

async function ensureDb(code) {
  branchBusy.value = true; branchMsg.value = ''
  try {
    const r = await api(`/api/branches/${encodeURIComponent(code)}/ensure-db`, { method: 'POST' })
    branchMsg.value = '✅ ' + (r.msg || 'Database cabang siap')
  } catch (e) { branchMsg.value = '❌ ' + e.message }
  finally { branchBusy.value = false }
}

async function seedDemoBranch(code) {
  if (!(await ask(`Tanam data demo (rute + transaksi dummy) ke cabang ${code}? Idempoten — data asli aman.`, { confirmText: 'Ya, lanjutkan' }))) return
  branchBusy.value = true; branchMsg.value = ''
  try {
    const r = await api(`/api/branches/${encodeURIComponent(code)}/seed-demo`, { method: 'POST' })
    branchMsg.value = '✅ ' + (r.msg || 'Data demo ditanam')
  } catch (e) { branchMsg.value = '❌ ' + e.message }
  finally { branchBusy.value = false }
}

async function switchBranch(code) {
  if (!code || code === currentBranch.value?.code) return
  branchBusy.value = true; branchMsg.value = ''
  try {
    const r = await api('/api/branches/switch', { method: 'POST', body: { code } })
    branchMsg.value = '✅ ' + (r.msg || 'Cabang diganti')
    setTimeout(() => window.location.reload(), 600)
  } catch (e) { branchMsg.value = '❌ ' + e.message }
  finally { branchBusy.value = false }
}

// Nomor dokumen (v2.29.11) — lihat & reset counter doc_sequences per cabang
const docseqs = ref([])
const docseqLoading = ref(false)
const docseqMsg = ref('')
const docseqFilter = ref('')

function fmtSeqDate(d) {
  if (!d || d.length !== 8) return d || '—'
  return `${d.slice(0, 4)}-${d.slice(4, 6)}-${d.slice(6, 8)}`
}

const docseqRows = computed(() => {
  const rows = []
  for (const b of docseqs.value) {
    for (const s of b.sequences || []) {
      rows.push({ ...s, branchName: b.name })
    }
  }
  if (docseqFilter.value) return rows.filter((r) => r.branch === docseqFilter.value)
  return rows
})

async function loadDocSequences() {
  docseqLoading.value = true
  try {
    const d = await api('/api/admin/doc-sequences')
    docseqs.value = Array.isArray(d?.branches) ? d.branches : []
  } catch { docseqs.value = [] }
  finally { docseqLoading.value = false }
}

async function resetSeq(row) {
  const scope = row.date ? `tanggal ${fmtSeqDate(row.date)}` : 'SEMUA tanggal'
  if (!(await ask(`Reset counter ${row.prefix} cabang ${row.branch} (${scope})?\n\nNomor berikutnya akan mulai dari 0001. HANYA lakukan bila belum ada dokumen dgn nomor tsb yang masih dipakai hari ini.`, { confirmText: 'Ya, lanjutkan', danger: true }))) return
  docseqMsg.value = ''
  try {
    const r = await api('/api/admin/doc-sequences/reset', {
      method: 'POST',
      body: { branch_code: row.branch, prefix: row.prefix, date: row.date || '' },
    })
    docseqMsg.value = '✅ ' + (r.msg || 'Counter direset')
    loadDocSequences()
  } catch (e) { docseqMsg.value = '❌ ' + e.message }
}

// Data demo (v2.19.2) — dibuat & dibersihkan Admin
const demoStatus = ref(null)
const demoBusy = ref(false)
const demoMsg = ref('')

async function loadDemoStatus() {
  try { demoStatus.value = await api('/api/demo/status') } catch { demoStatus.value = null }
}

async function demoSeed() {
  if (!(await ask('Buat data demo (rute appointment + transaksi dummy)? Aman — idempoten, tidak mengubah data asli.', { confirmText: 'Ya, lanjutkan' }))) return
  demoBusy.value = true; demoMsg.value = ''
  try {
    const r = await api('/api/demo/seed', { method: 'POST', body: { scope: 'all' } })
    demoMsg.value = '✅ ' + (r.msg || 'Data demo dibuat') + (r.summary ? ` (rute baru ${r.summary.routes}, transaksi ${r.summary.transactions})` : '')
    loadDemoStatus()
  } catch (e) { demoMsg.value = '❌ ' + e.message }
  finally { demoBusy.value = false }
}

async function demoClean() {
  if (!(await ask('BERSIHKAN semua data demo (rute appointment DEMO-* + transaksi dummy)? Data asli TIDAK terpengaruh.', { confirmText: 'Ya, lanjutkan', danger: true }))) return
  demoBusy.value = true; demoMsg.value = ''
  try {
    const r = await api('/api/demo/clean', { method: 'POST', body: { scope: 'all' } })
    demoMsg.value = '✅ ' + (r.msg || 'Data demo dibersihkan') + (r.summary ? ` (rute ${r.summary.routes}, transaksi ${r.summary.transactions})` : '')
    loadDemoStatus()
  } catch (e) { demoMsg.value = '❌ ' + e.message }
  finally { demoBusy.value = false }
}

// Tanda tangan tanda terima air minum (v2.6): Finance = penyerah, GA = penerima
const waterNames = ref({ ga: '', finance: '', head: '' })
const waterMsg = ref('')

// v2.107.0 — voucher rekanan: nilai per cabang + nama SPBU mitra default.
const voucherCfg = ref({ value: 130000, partner: '' })
const voucherMsg = ref('')
async function loadVoucherCfg() {
  try {
    const d = await api('/api/voucher/config')
    voucherCfg.value = { value: Number(d?.value) || 130000, partner: d?.partner || '' }
  } catch { /* biarkan default */ }
}
async function saveVoucherCfg() {
  voucherMsg.value = ''
  try {
    const r = await api('/api/voucher/config', {
      method: 'POST',
      body: { value: Number(voucherCfg.value.value) || 0, partner: voucherCfg.value.partner },
    })
    voucherMsg.value = '✅ ' + (r?.msg || 'Pengaturan voucher disimpan')
  } catch (e) { voucherMsg.value = '❌ ' + (e?.data?.msg || e.message) }
}

// Fitur edit/hapus transaksi air minum (v2.37.0) — toggle Admin per cabang
const waterEditEnabled = ref(false)
const waterEditBusy = ref(false)
const waterEditMsg = ref('')

async function loadEditEnabled() {
  try {
    const d = await api('/api/water/edit-enabled')
    waterEditEnabled.value = !!d?.enabled
  } catch { waterEditEnabled.value = false }
}

async function toggleWaterEdit(e) {
  const enabled = e.target.checked
  const verb = enabled ? 'AKTIFKAN' : 'NONAKTIFKAN'
  if (!(await ask(`${verb} fitur edit/hapus transaksi air minum untuk cabang ini?\n\nBila aktif: Finance bisa mengedit & menghapus pengajuan (wajib PIN, tercatat di audit log).`, { confirmText: 'Ya, lanjutkan' }))) {
    e.target.checked = !enabled
    return
  }
  waterEditBusy.value = true; waterEditMsg.value = ''
  try {
    const r = await api('/api/water/edit-enabled', { method: 'PUT', body: { enabled } })
    waterEditEnabled.value = !!r.enabled
    waterEditMsg.value = '✅ ' + (r.msg || 'Status fitur diperbarui')
  } catch (err) {
    waterEditMsg.value = '❌ ' + err.message
    e.target.checked = !enabled
  } finally { waterEditBusy.value = false }
}

async function loadWaterNames() {
  try {
    const [ga, finance, head] = await Promise.all([
      api('/api/system-config/water_ga_name').catch(() => ({ value: '' })),
      api('/api/system-config/water_finance_name').catch(() => ({ value: '' })),
      api('/api/system-config/water_head_name').catch(() => ({ value: '' })),
    ])
    waterNames.value = { ga: ga.value || '', finance: finance.value || '', head: head.value || '' }
  } catch { /* noop */ }
}

// ---- URL sumber sheet Receptionist (v2.41.2) ----
const sheetUrls = ref({ applicants: '', inout: '' })
const sheetSyncMeta = ref({ applicants: '', inout: '' })
const sheetMsg = ref('')
const sheetBusy = ref(false)
const sheetTest = ref(null)
const sheetTestBusy = ref('')

async function loadSheetUrls() {
  try {
    const d = await api('/api/receptionist/sheet-urls')
    sheetUrls.value = { applicants: d.data?.applicants || '', inout: d.data?.inout || '' }
    sheetSyncMeta.value = {
      applicants: d.data?.last_sync?.applicants || '',
      inout: d.data?.last_sync?.inout || '',
    }
  } catch { /* noop */ }
}

async function saveSheetUrls() {
  sheetBusy.value = true; sheetMsg.value = ''
  try {
    const r = await api('/api/receptionist/sheet-urls', { method: 'POST', body: sheetUrls.value })
    sheetMsg.value = '✅ ' + (r.msg || 'URL disimpan')
    loadSheetUrls()
  } catch (e) { sheetMsg.value = '❌ ' + e.message }
  finally { sheetBusy.value = false }
}

async function testSheetUrl(modul) {
  const url = (sheetUrls.value[modul] || '').trim()
  if (!url) { sheetMsg.value = '⚠️ Isi URL dulu sebelum diuji.'; return }
  sheetTestBusy.value = modul; sheetMsg.value = ''; sheetTest.value = null
  try {
    const r = await api('/api/receptionist/test-url', { method: 'POST', body: { modul, url } })
    sheetTest.value = { modul, ...r }
  } catch (e) {
    sheetTest.value = { modul, status: 'error', detail: e.message }
  } finally { sheetTestBusy.value = '' }
}

// ---- Mode In-Out + Webhook realtime (v2.42) ----
const inoutMode = ref('hybrid')
const inoutModeMsg = ref('')
const webhook = ref({ secret: '', revealed: false, url_hint: '', header: 'X-BPF-Token' })
const webhookMsg = ref('')
const webhookBusy = ref(false)

async function loadInOutMode() {
  try {
    const d = await api('/api/receptionist/inout-mode')
    inoutMode.value = d.mode || 'hybrid'
  } catch { /* noop */ }
}

async function saveInOutMode() {
  inoutModeMsg.value = ''
  try {
    const r = await api('/api/receptionist/inout-mode', { method: 'POST', body: { mode: inoutMode.value } })
    inoutModeMsg.value = '✅ ' + (r.msg || 'Mode disimpan')
  } catch (e) { inoutModeMsg.value = '❌ ' + e.message }
}

async function loadWebhook() {
  try {
    const d = await api('/api/receptionist/webhook-config')
    webhook.value = { ...webhook.value, secret: d.secret || '', url_hint: d.url_hint || '', header: d.header || 'X-BPF-Token' }
  } catch { /* noop */ }
}

async function rotateWebhook() {
  if (!(await ask('Buat secret webhook baru? Token lama di Apps Script langsung tidak berlaku.', { confirmText: 'Ya, lanjutkan' }))) return
  webhookBusy.value = true; webhookMsg.value = ''
  try {
    const r = await api('/api/receptionist/webhook-config', { method: 'POST' })
    webhook.value.secret = r.secret || ''
    webhook.value.revealed = true
    webhookMsg.value = '✅ ' + (r.msg || 'Secret baru dibuat')
  } catch (e) { webhookMsg.value = '❌ ' + e.message }
  finally { webhookBusy.value = false }
}

function copyWebhook() {
  const text = `${webhook.value.url_hint}\nHeader: ${webhook.value.header}\nSecret: ${webhook.value.secret}`
  navigator.clipboard?.writeText(text).then(
    () => { webhookMsg.value = '✅ URL + secret disalin ke clipboard' },
    () => { webhookMsg.value = '⚠️ Gagal menyalin — salin manual' },
  )
}

async function saveWaterNames() {
  busy.value = true; waterMsg.value = ''
  try {
    await api('/api/system-config/water_ga_name', { method: 'PUT', body: { value: waterNames.value.ga } })
    await api('/api/system-config/water_finance_name', { method: 'PUT', body: { value: waterNames.value.finance } })
    await api('/api/system-config/water_head_name', { method: 'PUT', body: { value: waterNames.value.head } })
    waterMsg.value = '✅ Nama penandatangan air minum disimpan'
  } catch (e) { waterMsg.value = '❌ ' + e.message }
  finally { busy.value = false }
}

const vehicleTypes = computed(() => ['AVANZA', ...[...new Set(vehicles.value.map((v) => (v.vehicle_type || '').trim()).filter(Boolean))].sort()].filter((v, i, a) => a.indexOf(v) === i).slice(0, 12))
const bbmNames = computed(() => bbms.value.map((b) => b.name).filter(Boolean))

async function load() {
  loading.value = true; err.value = ''
  try {
    const [d, v, b] = await Promise.all([
      api('/api/drivers').catch(() => []),
      api('/api/vehicles').catch(() => []),
      api('/api/bbm_types').catch(() => []),
    ])
    drivers.value = Array.isArray(d) ? d : []
    vehicles.value = Array.isArray(v) ? v : []
    bbms.value = Array.isArray(b) ? b : []
  } catch (e) { err.value = e.message }
  finally { loading.value = false }
}

/** Reset PIN massal seluruh akun driver ke PIN acak aman (bukan 123456). */
async function resetDriverPinMassal() {
  if (!(await ask('Reset PIN SEMUA akun driver ke PIN acak aman? PIN hasil reset akan ditampilkan sekali — salin dan distribusikan.', { confirmText: 'Ya, lanjutkan', danger: true }))) return
  busy.value = true; msg.value = ''
  try {
    const r = await api('/api/drivers/pin-reset', { method: 'POST', body: {} })
    msg.value = '✅ ' + (r.msg || 'PIN semua driver direset') + (r.pin ? ` PIN: ${r.pin}` : '')
  } catch (e) { msg.value = '❌ ' + e.message }
  finally { busy.value = false }
}

async function addVehicle() {
  busy.value = true; msg.value = ''
  try {
    const body = { ...vehicleForm.value }
    body.nopol = body.nopol.trim().toUpperCase()
    if (!body.nopol) { msg.value = '❌ No. Polisi wajib diisi'; return }
    await api('/api/vehicles/add', { method: 'POST', body })
    msg.value = '✅ Kendaraan tersimpan'
    showVehicleForm.value = false
    vehicleForm.value = { nopol: '', vehicle_type: 'AVANZA', brand: 'Toyota', bbm_default: 'PERTALITE' }
    load()
  } catch (e) { msg.value = '❌ ' + e.message }
  finally { busy.value = false }
}

// Retensi & arsip dokumen (v2.34.0, Tahap 5/6 ISO) — kebijakan per kelas + arsip audit trail
const retention = ref(null)
const retentionBusy = ref(false)
const retentionMsg = ref('')
const archiveDays = ref(1825)

const retentionRows = computed(() => (retention.value?.classes || []).map((c) => {
  const perDb = c.per_db || []
  const expired = perDb.reduce((s, d) => s + (d.expired || 0), 0)
  const olds = perDb.filter((d) => d.oldest).map((d) => d.oldest).sort()
  const news = perDb.filter((d) => d.newest).map((d) => d.newest).sort()
  return { ...c, total: c.total || 0, expired, oldest: olds[0] || '', newest: news[news.length - 1] || '' }
}))

function fmtDays(d) { return d == null ? '♾ Permanen' : `${Number(d).toLocaleString('id-ID')} hari` }

async function loadRetention() {
  retentionBusy.value = true
  try { retention.value = await api('/api/admin/retention/overview') } catch { retention.value = null }
  finally { retentionBusy.value = false }
}

async function archiveAuditLogs() {
  const n = Number(archiveDays.value)
  if (!n || n < 30) { retentionMsg.value = '❌ Minimal 30 hari (anti salah-klik).'; return }
  if (!(await ask(`Arsipkan SEMUA jejak audit lebih tua dari ${n} hari di seluruh database (master + cabang)?\n\nBaris dipindah ke tabel arsip activity_logs_archive (tetap utuh & bisa dibuka), lalu dihapus dari tabel aktif. Tindakan ini dicatat di register retensi + audit log.`, { confirmText: 'Ya, lanjutkan', danger: true }))) return
  retentionBusy.value = true; retentionMsg.value = ''
  try {
    const r = await api('/api/admin/retention/archive-audit', { method: 'POST', body: { days: n } })
    retentionMsg.value = '✅ ' + (r.msg || 'Audit trail diarsipkan')
    loadRetention()
  } catch (e) { retentionMsg.value = '❌ ' + e.message }
  finally { retentionBusy.value = false }
}

// Verifikasi & registri dokumen (v2.35.0, Tahap 6/6 ISO) — integritas PDF via hash SHA-256
const docs = ref([])
const docFile = ref(null)
const docVerifyBusy = ref(false)
const docVerifyResult = ref(null)

async function loadDocs() {
  try {
    const d = await api('/api/admin/documents?limit=50')
    docs.value = Array.isArray(d?.documents) ? d.documents : []
  } catch { docs.value = [] }
}

function onDocFile(e) { docFile.value = e.target.files?.[0] || null; docVerifyResult.value = null }

async function verifyDoc() {
  if (!docFile.value) { docVerifyResult.value = { error: 'Pilih file PDF dulu.' }; return }
  docVerifyBusy.value = true; docVerifyResult.value = null
  try {
    const fd = new FormData()
    fd.append('file', docFile.value)
    const csrf = localStorage.getItem('bpf_csrf') || sessionStorage.getItem('bpf_csrf')
    const headers = { Accept: 'application/json' }
    if (csrf) headers['X-CSRF-Token'] = csrf
    const r = await fetch('/api/documents/verify', { method: 'POST', headers, body: fd })
    const d = await r.json().catch(() => null)
    if (!r.ok) throw new Error((d && (d.msg || d.error)) || `HTTP ${r.status}`)
    docVerifyResult.value = d
    loadDocs()
  } catch (e) { docVerifyResult.value = { error: e.message } }
  finally { docVerifyBusy.value = false }
}

function shortSha(s) { return s ? String(s).slice(0, 12) + '…' : '—' }
function fmtDT(s) {
  if (!s) return '—'
  const t = s.includes('T') ? s : s.replace(' ', 'T')
  return new Date(t).toLocaleString('id-ID', { dateStyle: 'medium', timeStyle: 'short' })
}

// ---- Navigasi seksi (v2.37.0) — halaman panjang jadi terstruktur ----
const SECTIONS = [
  { id: 'sec-master', label: '🚗 Data Master' },
  { id: 'sec-air', label: '🚰 Air Minum' },
  { id: 'sec-voucher', label: '🎟️ Voucher Rekanan' },
  { id: 'sec-sheetsync', label: '🔗 Sumber Sheet' },
  { id: 'sec-receptionist-realtime', label: '⚡ Realtime Sheet' },
  { id: 'sec-cabang', label: '🏢 Cabang & Nomor' },
  { id: 'sec-kepatuhan', label: '🗄️ Kepatuhan (ISO)' },
  { id: 'sec-deploy', label: '🚀 Deploy' },
  { id: 'sec-branding', label: '🎨 Identitas' },
  { id: 'sec-lainnya', label: '🧪 Lainnya' },
]
const activeSection = ref('sec-master')
const secNavEl = ref(null)

function scrollToSection(id) {
  activeSection.value = id
  const el = document.getElementById(id)
  if (el) {
    const y = el.getBoundingClientRect().top + window.scrollY - 70
    window.scrollTo({ top: y, behavior: 'smooth' })
  }
}

let _secObserver = null
onMounted(() => { load(); loadWaterNames(); loadVoucherCfg(); loadEditEnabled(); loadIdentityForm(); loadDemoStatus(); loadDeployStatus(); loadBranches(); loadDocSequences(); loadRetention(); loadDocs(); loadSheetUrls(); loadInOutMode(); loadWebhook() })
onMounted(() => {
  // Highlight seksi aktif saat scroll (IntersectionObserver — ringan).
  _secObserver = new IntersectionObserver((entries) => {
    for (const en of entries) {
      if (en.isIntersecting) activeSection.value = en.target.id
    }
  }, { rootMargin: '-70px 0px -60% 0px' })
  for (const s of SECTIONS) {
    const el = document.getElementById(s.id)
    if (el) _secObserver.observe(el)
  }
})
</script>

<template>
  <div>
    <PageHeader icon="⚙️" title="Pengaturan" subtitle="Konfigurasi aplikasi — data master, integrasi & keamanan" />
    <div v-if="msg" class="alert" :class="msg.startsWith('✅') ? 'alert-success' : 'alert-error'">{{ msg }}</div>
    <div v-if="loading"><LoadingState :rows="4" label="Memuat pengaturan…" /></div>
    <div v-else-if="err"><ErrorState :message="err" @retry="load" /></div>
    <template v-else>
      <!-- Peta seksi: lompat cepat tanpa scroll panjang -->
      <nav ref="secNavEl" class="settings-nav card" aria-label="Peta pengaturan">
        <button v-for="s in SECTIONS" :key="s.id" class="settings-nav-btn"
                :class="{ active: activeSection === s.id }" @click="scrollToSection(s.id)">{{ s.label }}</button>
      </nav>

      <div id="sec-master" class="card card-pad" style="margin-bottom:16px;display:flex;align-items:center;">
        <div class="grow">
          <h3 style="margin:0;">🚗 Data Master</h3>
          <p class="muted" style="font-size:11px;">Kendaraan &amp; tipe BBM · data driver dikelola di <b>Manajemen User</b> (satu akun = satu driver)</p>
        </div>
        <router-link class="btn btn-primary btn-sm" to="/users">👥 User &amp; Driver</router-link>
        <button class="btn btn-sm" style="margin-left:8px;" @click="showVehicleForm = true">🚙 Tambah Kendaraan</button>
        <button class="btn btn-sm" style="margin-left:8px;" :disabled="busy" @click="resetDriverPinMassal" title="Reset PIN semua akun driver ke PIN acak aman">🔑 Reset PIN Driver (acak)</button>
      </div>

      <div class="card card-pad" style="margin-bottom:16px;">
        <h3 style="margin:0;">👥 Buat Akun Sekaligus</h3>
        <p class="muted" style="font-size:11px;">
          Buat akun login (role driver / marketing, <b>PIN acak aman</b> yang ditampilkan setelah dibuat) untuk semua driver aktif dan
          semua user di dropdown marketing yang belum punya akun. Akun yang sudah ada dilewati — idempoten.
        </p>
        <div class="row" style="margin-top:10px;gap:8px;">
          <button class="btn btn-primary btn-sm" :disabled="bulkBusy" @click="bulkCreate('driver')">🚗 Buat Akun Semua Driver</button>
          <button class="btn btn-sm" :disabled="bulkBusy" @click="bulkCreate('marketing')">📣 Buat Akun User Marketing</button>
          <span v-if="bulkMsg" class="alert" :class="bulkMsg.startsWith('✅') ? 'alert-success' : 'alert-error'" style="margin:0;padding:6px 10px;">{{ bulkMsg }}</span>
        </div>
      </div>

      <div id="sec-air" class="card card-pad" style="margin-bottom:16px;">
        <h3 style="margin:0;">🚰 Tanda Terima Air Minum</h3>
        <p class="muted" style="font-size:11px;">Nama penandatangan dokumen PDF pembelian air minum — Finance selaku <b>Menyerahkan</b> &amp; GA selaku <b>Menerima</b></p>
        <div class="form-grid" style="margin-top:12px;">
          <div class="field"><label>Nama Finance (Menyerahkan)</label><input class="input" v-model="waterNames.finance" placeholder="mis. Rina Wijaya" /></div>
          <div class="field"><label>Nama GA (Menerima)</label><input class="input" v-model="waterNames.ga" placeholder="mis. Andi Prasetyo" /></div>
          <div class="field"><label>Nama Kepala Cabang (Mengetahui — export rekap)</label><input class="input" v-model="waterNames.head" placeholder="mis. Budi Santoso" /></div>
        </div>
        <div class="row" style="justify-content:flex-end;gap:8px;margin-top:8px;">
          <span class="muted" style="font-size:12px;">{{ waterMsg }}</span>
          <button class="btn btn-primary btn-sm" :disabled="busy" @click="saveWaterNames">💾 Simpan Nama TTD</button>
        </div>
        <div class="water-toggle" style="margin-top:14px;padding-top:12px;border-top:1px solid var(--border);">
          <div class="row" style="align-items:flex-start;gap:10px;flex-wrap:wrap;">
            <div class="grow">
              <b style="font-size:13px;">✏️✖️ Edit &amp; Hapus Transaksi oleh Finance</b>
              <p class="muted" style="font-size:11px;margin:4px 0 0;">
                Bila <b>AKTIF</b>: Finance boleh mengedit (tanggal/item/remark) pengajuan berstatus Menunggu &amp;
                Terverifikasi, dan menghapus pengajuan secara permanen. Setiap perubahan wajib verifikasi PIN (step-up)
                dan tercatat lengkap di Audit Log (data lama tersimpan sebagai snapshot). Status <b>Ditolak</b> tidak bisa diedit.
              </p>
            </div>
            <label class="switch" style="flex-shrink:0;">
              <input type="checkbox" :checked="waterEditEnabled" :disabled="waterEditBusy" @change="toggleWaterEdit($event)" />
              <span class="slider"><span class="slider-label">{{ waterEditEnabled ? 'AKTIF' : 'NONAKTIF' }}</span></span>
            </label>
          </div>
          <span v-if="waterEditMsg" class="muted" style="font-size:12px;">{{ waterEditMsg }}</span>
        </div>
      </div>

      <div id="sec-voucher" class="card card-pad" style="margin-bottom:16px;">
        <h3 style="margin:0;">🎟️ Voucher BBM Rekanan</h3>
        <p class="muted" style="font-size:11px;">
          SPBU mitra memberi voucher + blanko ke driver; kantor membayar mitra per periode.
          Nilai voucher berlaku untuk cabang ini dan disimpan per transaksi saat dipakai,
          sehingga perubahan harga tidak mengubah histori.
        </p>
        <div class="form-grid" style="margin-top:12px;">
          <div class="field"><label>Nilai Voucher (Rp)</label>
            <input class="input" type="number" min="1" v-model.number="voucherCfg.value" data-testid="voucher-cfg-value" />
          </div>
          <div class="field"><label>Nama SPBU Mitra (default)</label>
            <input class="input" v-model="voucherCfg.partner" placeholder="mis. SPBU 54.601.01" data-testid="voucher-cfg-partner" />
          </div>
        </div>
        <div class="alert" style="padding:6px 10px;font-size:12px;margin-top:8px;">
          Nominal yang ditagihkan ke mitra = <b>nilai voucher + kode harian</b> cabang.
          Contoh: Rp {{ Number(voucherCfg.value || 0).toLocaleString('id-ID') }} + kode 700
          = Rp {{ (Number(voucherCfg.value || 0) + 700).toLocaleString('id-ID') }}.
        </div>
        <div class="row" style="justify-content:flex-end;gap:8px;margin-top:8px;">
          <span class="muted" style="font-size:12px;">{{ voucherMsg }}</span>
          <button class="btn btn-primary btn-sm" :disabled="busy" @click="saveVoucherCfg">💾 Simpan Pengaturan Voucher</button>
        </div>
      </div>

      <div id="sec-sheetsync" class="card card-pad" style="margin-bottom:16px;">
        <h3 style="margin:0;">🔗 Sumber Sheet Receptionist <span class="badge badge-blue" style="font-size:10px;vertical-align:middle;">v2.41</span></h3>
        <p class="muted" style="font-size:11px;">
          URL Google Sheet sumber data <b>Pelamar</b> &amp; <b>In-Out Karyawan</b> (auto-sync tiap 30 menit).
          Bila sheet dibuat <i>privat</i>, deploy Google Apps Script Web App (JSON <code>{"rows": [...]}</code>)
          dengan akun yang punya akses, lalu tempel URL <code>/exec</code> di sini — tanpa ubah kode.
        </p>
        <div class="form-grid" style="margin-top:12px;">
          <div class="field" style="grid-column:1/-1;">
            <label>Sheet Pelamar (kolom: Tanggal Interview, Jam, Nama, …)</label>
            <div class="row" style="gap:6px;">
              <input class="input" v-model="sheetUrls.applicants" placeholder="https://docs.google.com/…/gviz/tq?tqx=out:csv atau …/exec" style="flex:1;" />
              <button class="btn btn-sm" :disabled="sheetTestBusy === 'applicants'" @click="testSheetUrl('applicants')">{{ sheetTestBusy === 'applicants' ? '⏳…' : '🧪 Uji' }}</button>
            </div>
            <div v-if="sheetSyncMeta.applicants" class="muted" style="font-size:11px;margin-top:4px;">Sinkron terakhir: {{ sheetSyncMeta.applicants }}</div>
          </div>
          <div class="field" style="grid-column:1/-1;">
            <label>Sheet In-Out Karyawan (kolom: Nama, Jabatan, Pergi, …)</label>
            <div class="row" style="gap:6px;">
              <input class="input" v-model="sheetUrls.inout" placeholder="https://docs.google.com/…/gviz/tq?tqx=out:csv atau …/exec" style="flex:1;" />
              <button class="btn btn-sm" :disabled="sheetTestBusy === 'inout'" @click="testSheetUrl('inout')">{{ sheetTestBusy === 'inout' ? '⏳…' : '🧪 Uji' }}</button>
            </div>
            <div v-if="sheetSyncMeta.inout" class="muted" style="font-size:11px;margin-top:4px;">Sinkron terakhir: {{ sheetSyncMeta.inout }}</div>
          </div>
        </div>
        <div v-if="sheetTest" class="alert" :class="sheetTest.status === 'success' && sheetTest.header_ok ? 'alert-success' : sheetTest.status === 'success' ? 'alert-warning' : 'alert-error'" style="margin-top:10px;font-size:12px;">
          <template v-if="sheetTest.status === 'success'">
            {{ sheetTest.header_ok ? '✅' : '⚠️' }} {{ sheetTest.rows }} baris terbaca.
            Header dikenali: {{ sheetTest.header_ok ? 'YA' : 'TIDAK' }}.
            <span v-if="sheetTest.sample_header">Contoh: {{ sheetTest.sample_header }}</span>
            <template v-if="!sheetTest.header_ok"> Periksa kembali pemetaan kolom / modul yang dipilih.</template>
          </template>
          <template v-else>❌ Gagal mengambil: {{ sheetTest.detail }}</template>
        </div>
        <div class="row" style="justify-content:flex-end;gap:8px;margin-top:8px;">
          <span class="muted" style="font-size:12px;">{{ sheetMsg }}</span>
          <button class="btn btn-primary btn-sm" :disabled="sheetBusy" @click="saveSheetUrls">💾 Simpan URL</button>
        </div>
      </div>

      <!-- Webhook realtime + mode in-out (v2.42) -->
      <div id="sec-receptionist-realtime" class="card card-pad" style="margin-bottom:16px;">
        <h3 style="margin:0;">⚡ Realtime Sheet Receptionist <span class="badge badge-blue" style="font-size:10px;vertical-align:middle;">v2.42</span></h3>
        <p class="muted" style="font-size:11px;">
          Data <b>Pelamar</b> &amp; <b>In-Out Karyawan</b> bisa ter-update <b>realtime</b>: Google Apps Script
          (trigger <code>onEdit</code>) mendorong setiap edit langsung ke aplikasi lewat webhook di bawah —
          seperti pengalaman overtime di GA HR, tanpa menunggu sync 30 menit. Template:
          <code>scripts/gas_bridge_receptionist_v2.gs</code>.
        </p>
        <div class="form-grid" style="margin-top:12px;">
          <div class="field">
            <label>Mode pencatatan In-Out Karyawan</label>
            <div class="row" style="gap:6px;">
              <select class="select" v-model="inoutMode" style="flex:1;">
                <option value="hybrid">Hybrid — resepsionis catat dari aplikasi + sheet (disarankan)</option>
                <option value="sheet">Sheet saja — aplikasi read-only</option>
              </select>
              <button class="btn btn-sm btn-primary" @click="saveInOutMode">💾</button>
            </div>
            <div v-if="inoutModeMsg" class="muted" style="font-size:11px;margin-top:4px;">{{ inoutModeMsg }}</div>
          </div>
          <div class="field">
            <label>Webhook URL (dipakai Apps Script)</label>
            <input class="input" :value="webhook.url_hint" readonly />
          </div>
          <div class="field" style="grid-column:1/-1;">
            <label>Secret {{ webhook.header }} ({{ webhook.revealed ? 'terlihat' : 'disembunyikan' }})</label>
            <div class="row" style="gap:6px;">
              <input class="input" :type="webhook.revealed ? 'text' : 'password'" :value="webhook.secret" readonly style="flex:1;" />
              <button class="btn btn-sm" @click="webhook.revealed = !webhook.revealed">{{ webhook.revealed ? '🙈 Sembunyikan' : '👁️ Lihat' }}</button>
              <button class="btn btn-sm" @click="copyWebhook">📋 Salin</button>
              <button class="btn btn-sm btn-danger" :disabled="webhookBusy" @click="rotateWebhook">🔄 Rotasi</button>
            </div>
            <div class="muted" style="font-size:11px;margin-top:4px;">⚠️ Ganti secret (rotasi) bila dicurigai bocor — token lama langsung mati; perbarui di Apps Script (REC_v2_setSecret).</div>
            <div v-if="webhookMsg" class="muted" style="font-size:11px;margin-top:4px;">{{ webhookMsg }}</div>
          </div>
        </div>
      </div>

      <div id="sec-cabang" class="card card-pad" style="margin-bottom:16px;">
        <h3 style="margin:0;">{{ auth.isHoAdmin ? '🏢 Cabang (Multi-Cabang)' : '🏢 Cabang Anda' }}</h3>
        <p class="muted" style="font-size:11px;">
          <template v-if="auth.isHoAdmin">
            Satu instalasi melayani banyak cabang — setiap cabang punya <b>database sendiri</b> (isolasi data penuh).
            Alamat &amp; telepon tiap cabang dipakai sebagai <b>kop dokumen resmi</b> (PDF/Excel export) —
            perbarui di sini bila kantor pindah. Cabang aktif: <b>{{ currentBranch?.name || '—' }}</b>
          </template>
          <template v-else>
            Anda login sebagai <b>Admin Cabang</b> — data dan operasional dibatasi ke cabang aktif.
            Perubahan identitas cabang, database, dan status aktif hanya dapat dilakukan Admin Pusat.
            Cabang aktif: <b>{{ currentBranch?.name || '—' }}</b>
          </template>
        </p>
        <div class="row" style="margin-top:10px;gap:8px;align-items:center;flex-wrap:wrap;">
          <button v-if="auth.isHoAdmin" class="btn btn-primary btn-sm" @click="openBranchForm(null)">➕ Tambah Cabang</button>
          <template v-if="auth.isHoAdmin">
            <label class="muted" style="font-size:12px;">Ganti cabang (Admin Pusat):</label>
            <select class="select" style="width:auto;" :value="currentBranch?.code" :disabled="branchBusy" @change="switchBranch($event.target.value)">
              <option v-for="b in branches" :key="b.code" :value="b.code">{{ b.name }} ({{ b.code }})</option>
            </select>
          </template>
          <span v-else class="badge badge-gray">🔒 Admin cabang — operasional cabang ini saja</span>
          <span v-if="branchMsg" class="alert" :class="branchMsg.startsWith('✅') ? 'alert-success' : 'alert-error'" style="margin:0;padding:6px 10px;">{{ branchMsg }}</span>
        </div>
        <div class="table-wrap" style="margin-top:10px;">
          <table class="tbl">
            <thead><tr><th>Kode</th><th>Nama Cabang</th><th>Database</th><th>Kota</th><th>Status</th><th></th></tr></thead>
            <tbody>
              <tr v-for="b in branches" :key="b.code">
                <td><b>{{ b.code }}</b></td>
                <td>{{ b.name }}</td>
                <td>{{ b.db_name }}</td>
                <td>{{ b.city || '—' }}</td>
                <td><span class="badge" :class="b.is_active ? 'badge-green' : 'badge-red'">{{ b.is_active ? 'Aktif' : 'Nonaktif' }}</span></td>
                <td>
                  <template v-if="auth.isHoAdmin">
                    <button class="btn btn-sm" @click="openBranchForm(b)" title="Edit identitas cabang (nama, kota, alamat kop dokumen, telepon)">✏️ Edit</button>
                    <button class="btn btn-sm" @click="ensureDb(b.code)" title="Buat/sinkronkan database cabang">🗄️ DB</button>
                    <button class="btn btn-sm" @click="seedDemoBranch(b.code)" title="Tanam data demo (rute + transaksi dummy) ke cabang ini">🧪 Demo</button>
                    <button class="btn btn-sm" @click="toggleBranch(b.code, !b.is_active)" :disabled="branchBusy">{{ b.is_active ? '🔴 Nonaktifkan' : '🟢 Aktifkan' }}</button>
                  </template>
                  <span v-else class="muted" style="font-size:11px;">Read-only</span>
                </td>
              </tr>
              <tr v-if="!branches.length"><td colspan="6" class="empty">Belum ada cabang.</td></tr>
            </tbody>
          </table>
        </div>
      </div>

      <div class="card card-pad" style="margin-bottom:16px;">
        <h3 style="margin:0;">🔢 Nomor Dokumen (Penomoran)</h3>
        <p class="muted" style="font-size:11px;">
          Nomor urut harian per cabang &amp; jenis dokumen — format <code>PREFIX-CABANG-TANGGAL-0001</code>
          (mis. <code>WTR-SBY-20260905-0001</code>). Daftar ini hanya menampilkan counter yang sudah terpakai.
          <b>Reset</b> dipakai untuk memulai dari 0001 lagi (mis. selesai uji coba / awal hari) —
          hati-hati: jangan reset bila masih ada dokumen dengan nomor tersebut hari ini.
        </p>
        <div class="row" style="margin-top:10px;gap:8px;align-items:center;flex-wrap:wrap;">
          <label class="muted" style="font-size:12px;">Filter cabang:</label>
          <select class="select" style="width:auto;" v-model="docseqFilter">
            <option value="">Semua cabang</option>
            <option v-for="b in docseqs" :key="b.code" :value="b.code">{{ b.name }} ({{ b.code }})</option>
          </select>
          <button class="btn btn-sm" :disabled="docseqLoading" @click="loadDocSequences">🔄 Muat Ulang</button>
          <span v-if="docseqMsg" class="alert" :class="docseqMsg.startsWith('✅') ? 'alert-success' : 'alert-error'" style="margin:0;padding:6px 10px;">{{ docseqMsg }}</span>
        </div>
        <div class="table-wrap" style="margin-top:10px;">
          <table class="tbl">
            <thead><tr><th>Cabang</th><th>Jenis Dokumen</th><th>Prefix</th><th>Tanggal</th><th>Nomor Terakhir</th><th></th></tr></thead>
            <tbody>
              <tr v-for="(r, i) in docseqRows" :key="r.seq_key + i">
                <td><b>{{ r.branch }}</b><br><span class="muted" style="font-size:11px;">{{ r.branchName }}</span></td>
                <td>{{ r.prefix_label }}</td>
                <td><code>{{ r.prefix }}</code></td>
                <td>{{ fmtSeqDate(r.date) }}</td>
                <td><b>{{ String(r.seq).padStart(4, '0') }}</b></td>
                <td><button class="btn btn-sm" @click="resetSeq(r)">🔄 Reset</button></td>
              </tr>
              <tr v-if="docseqLoading"><td colspan="6" class="empty">Memuat…</td></tr>
              <tr v-if="!docseqLoading && !docseqRows.length"><td colspan="6" class="empty">Belum ada nomor dokumen — semua counter bersih.</td></tr>
            </tbody>
          </table>
        </div>
      </div>

      <div id="sec-kepatuhan" class="card card-pad" style="margin-bottom:16px;">
        <h3 style="margin:0;">🗄️ Retensi &amp; Arsip Dokumen <span class="badge" style="font-size:10px;vertical-align:middle;">Tahap 5/6 ISO · A.8.2 · ISO 15489</span></h3>
        <p class="muted" style="font-size:11px;">
          Kebijakan retensi per kelas dokumen (detail: <code>RETENTION_POLICY.md</code>).
          Baris yang lewat masa retensi dihitung dari tanggal kolom masing-masing (tanggal transaksi / dibuat).
          <b>TIDAK ada penghapusan otomatis</b> — penghancuran data bisnis butuh persetujuan manajemen &amp; dieksekusi manual.
          Satu-satunya tindakan di sini: <b>arsipkan audit trail</b> yang sudah lewat masa aktif (dipindah ke tabel arsip, bukan dihapus).
        </p>
        <div class="row" style="margin-top:10px;gap:8px;align-items:center;flex-wrap:wrap;">
          <button class="btn btn-sm" :disabled="retentionBusy" @click="loadRetention">🔄 Muat Inventaris</button>
          <label class="muted" style="font-size:12px;">Arsipkan audit log &gt; <input type="number" min="30" v-model="archiveDays" style="width:90px;padding:3px 6px;" /> hari:</label>
          <button class="btn btn-sm" :disabled="retentionBusy" @click="archiveAuditLogs">🗜 Arsipkan Audit Trail</button>
          <span v-if="retentionMsg" class="alert" :class="retentionMsg.startsWith('✅') ? 'alert-success' : 'alert-error'" style="margin:0;padding:6px 10px;">{{ retentionMsg }}</span>
        </div>
        <div class="table-wrap" style="margin-top:10px;">
          <table class="tbl">
            <thead><tr><th>Kelas Dokumen</th><th>Masa Retensi</th><th>Total Baris</th><th>Estimasi &gt; Retensi</th><th>Rentang Data</th></tr></thead>
            <tbody>
              <tr v-for="c in retentionRows" :key="c.key">
                <td><b>{{ c.label }}</b><br><span class="muted" style="font-size:11px;">{{ c.note }}</span></td>
                <td>{{ fmtDays(c.retention_days) }}</td>
                <td>{{ Number(c.total || 0).toLocaleString('id-ID') }}</td>
                <td>
                  <span v-if="c.expired"><b style="color:#b45309;">{{ Number(c.expired).toLocaleString('id-ID') }}</b></span>
                  <span v-else class="muted">0</span>
                </td>
                <td class="muted" style="font-size:11px;">{{ c.oldest ? c.oldest.slice(0, 10) : '—' }} s/d {{ c.newest ? c.newest.slice(0, 10) : '—' }}</td>
              </tr>
              <tr v-if="retentionBusy && !retentionRows.length"><td colspan="5" class="empty">Memuat…</td></tr>
              <tr v-if="!retentionBusy && !retentionRows.length"><td colspan="5" class="empty">Klik “Muat Inventaris” untuk melihat status retensi.</td></tr>
            </tbody>
          </table>
        </div>
        <details v-if="retention?.actions?.length" style="margin-top:8px;">
          <summary class="muted" style="font-size:12px;cursor:pointer;">Riwayat tindakan retensi ({{ retention.actions.length }})</summary>
          <div class="table-wrap" style="margin-top:6px;">
            <table class="tbl">
              <thead><tr><th>Waktu</th><th>Kelas</th><th>Aksi</th><th>DB</th><th>Baris</th><th>Oleh</th></tr></thead>
              <tbody>
                <tr v-for="a in retention.actions" :key="a.id">
                  <td style="font-size:11px;">{{ fmtDT(a.created_at) }}</td>
                  <td>{{ a.class_key }}</td>
                  <td>{{ a.action }}</td>
                  <td class="muted" style="font-size:11px;">{{ a.db_name }}</td>
                  <td>{{ a.rows_affected }}</td>
                  <td>{{ a.actor }}</td>
                </tr>
              </tbody>
            </table>
          </div>
        </details>
      </div>

      <div class="card card-pad" style="margin-bottom:16px;">
        <h3 style="margin:0;">🔏 Verifikasi &amp; Registri Dokumen <span class="badge" style="font-size:10px;vertical-align:middle;">Tahap 6/6 ISO · A.8.2</span></h3>
        <p class="muted" style="font-size:11px;">
          Setiap PDF resmi (Tanda Terima Air Minum, Form Permohonan Overtime, dll.) dicatat hash SHA-256-nya
          + penandatangan + waktu terbit di registri. Unggah PDF untuk membuktikan dokumen <b>utuh</b>
          (tidak diubah sejak diterbitkan) dan melihat siapa yang menerbitkannya.
        </p>
        <div class="row" style="margin-top:10px;gap:8px;align-items:center;flex-wrap:wrap;">
          <input type="file" accept=".pdf,application/pdf" @change="onDocFile" style="font-size:12px;" />
          <button class="btn btn-primary btn-sm" :disabled="docVerifyBusy || !docFile" @click="verifyDoc">🔍 Verifikasi Dokumen</button>
          <button class="btn btn-sm" @click="loadDocs">🔄 Registri</button>
        </div>
        <div v-if="docVerifyResult" class="alert" style="margin-top:10px;"
             :class="docVerifyResult.error ? 'alert-error' : (docVerifyResult.found ? 'alert-success' : 'alert-error')">
          <template v-if="docVerifyResult.error">❌ {{ docVerifyResult.error }}</template>
          <template v-else-if="docVerifyResult.found">
            ✅ <b>{{ docVerifyResult.document.doc_type }} {{ docVerifyResult.document.doc_no }}</b>
            — diterbitkan {{ fmtDT(docVerifyResult.document.created_at) }} oleh
            <b>{{ docVerifyResult.document.signer_name || '—' }}</b> ({{ docVerifyResult.document.signer_role || '—' }}) ·
            cabang {{ docVerifyResult.document.branch_code || '—' }} ·
            SHA-256 <code>{{ shortSha(docVerifyResult.document.sha256) }}</code>
          </template>
          <template v-else>{{ docVerifyResult.msg }}</template>
        </div>
        <div class="table-wrap" style="margin-top:10px;">
          <table class="tbl">
            <thead><tr><th>Waktu Terbit</th><th>Jenis</th><th>No. Dokumen</th><th>Cabang</th><th>Penandatangan</th><th>Hash (SHA-256)</th></tr></thead>
            <tbody>
              <tr v-for="doc in docs" :key="doc.id">
                <td style="font-size:11px;">{{ fmtDT(doc.created_at) }}</td>
                <td>{{ doc.doc_type }}</td>
                <td><code>{{ doc.doc_no }}</code></td>
                <td>{{ doc.branch_code || '—' }}</td>
                <td>{{ doc.signer_name || '—' }} <span class="muted" style="font-size:11px;">({{ doc.signer_role || '—' }})</span></td>
                <td><code style="font-size:11px;">{{ shortSha(doc.sha256) }}</code></td>
              </tr>
              <tr v-if="!docs.length"><td colspan="6" class="empty">Belum ada dokumen terdaftar — PDF resmi otomatis tercatat saat diunduh.</td></tr>
            </tbody>
          </table>
        </div>
      </div>

      <div id="sec-deploy" class="card card-pad" style="margin-bottom:16px;">
        <h3 style="margin:0;">🚀 Status Deploy <span class="badge" :class="deployBadge.cls" style="font-size:10px;vertical-align:middle;">{{ deployBadge.label }}</span></h3>
        <p class="muted" style="font-size:11px;">
          Guard deploy membandingkan versi image yang berjalan dengan versi repo
          (<code>CHANGELOG.md</code>). Bila repo lebih baru, server menolak request
          non-health dengan 503 sampai image di-rebuild — mencegah perilaku lama
          tetap melayani pengguna.
        </p>
        <div v-if="deployStatus" class="form-grid" style="margin-top:12px;">
          <div class="field"><label>Versi berjalan (image)</label><input class="input" :value="deployStatus.running_version || '—'" readonly /></div>
          <div class="field"><label>Versi repo (CHANGELOG)</label><input class="input" :value="deployStatus.repo_version || '—'" readonly /></div>
          <div class="field"><label>Mode guard</label><input class="input" :value="deployStatus.mode || '—'" readonly /></div>
        </div>
        <p v-if="deployStatus?.stale" class="alert alert-error" style="margin-top:10px;">
          ⚠️ Image tertinggal dari repo. Jalankan <code>docker compose up -d --build web</code>.
        </p>
        <p v-else-if="deployStatus" class="alert alert-success" style="margin-top:10px;">
          ✅ Versi image dan repo sudah sinkron.
        </p>
        <p v-else-if="deployErr" class="alert alert-error" style="margin-top:10px;">{{ deployErr }}</p>
        <div class="row" style="justify-content:flex-end;margin-top:8px;">
          <button class="btn btn-sm" :disabled="deployBusy" @click="loadDeployStatus">↩️ Muat Ulang</button>
        </div>
      </div>

      <div id="sec-branding" class="card card-pad" style="margin-bottom:16px;">
        <h3 style="margin:0;">🏢 Identitas Perusahaan / Cabang</h3>
        <p class="muted" style="font-size:11px;">
          Variabel branding dipakai di PDF (kop surat &amp; footer), halaman login, sidebar &amp; watermark foto —
          bisa diubah Admin saat aplikasi dipakai cabang lain (siap multi-cabang).
        </p>
        <div class="form-grid" style="margin-top:12px;">
          <div class="field"><label>Nama Perusahaan</label><input class="input" v-model="identityForm.company_name" placeholder="PT BESTPROFIT FUTURES" /></div>
          <div class="field"><label>Nama Sistem / Aplikasi</label><input class="input" v-model="identityForm.system_name" placeholder="BPF WorkHub" /></div>
          <div class="field"><label>Subjudul (kantor | kota)</label><input class="input" v-model="identityForm.company_subtitle" placeholder="Kantor Pusat | Jakarta" /></div>
          <div class="field"><label>Versi</label><input class="input" v-model="identityForm.system_version" placeholder="v2.20.1" /></div>
          <div class="field"><label>Alamat Kantor</label><input class="input" v-model="identityForm.company_address" placeholder="Jl. Darmo 45, Surabaya" /></div>
          <div class="field"><label>Telepon</label><input class="input" v-model="identityForm.company_phone" placeholder="031-1234567" /></div>
        </div>
        <div class="row" style="justify-content:flex-end;gap:8px;margin-top:8px;">
          <span class="muted" style="font-size:12px;">{{ identityMsg }}</span>
          <button class="btn btn-primary btn-sm" :disabled="identityBusy" @click="saveIdentity">💾 Simpan Identitas</button>
        </div>
      </div>

      <div id="sec-lainnya" class="card card-pad" style="margin-bottom:16px;">
        <h3 style="margin:0;">🧪 Data Demo</h3>
        <p class="muted" style="font-size:11px;">
          Buat atau bersihkan data demo (rute appointment <code>DEMO-*</code> &amp; transaksi dummy) — data asli tidak terpengaruh.
          Memudahkan gladi resik / pelatihan user baru.
        </p>
        <div class="row" style="margin-top:10px;gap:8px;align-items:center;flex-wrap:wrap;">
          <button class="btn btn-primary btn-sm" :disabled="demoBusy" @click="demoSeed">✨ Buat Data Demo</button>
          <button class="btn btn-sm btn-danger" :disabled="demoBusy" @click="demoClean">🧹 Bersihkan Data Demo</button>
          <span v-if="demoStatus" class="muted" style="font-size:12px;">Rute demo: <b>{{ demoStatus.demo_appointments }}</b> · Transaksi demo: <b>{{ demoStatus.demo_transactions }}</b></span>
          <span v-if="demoMsg" class="alert" :class="demoMsg.startsWith('✅') ? 'alert-success' : 'alert-error'" style="margin:0;padding:6px 10px;">{{ demoMsg }}</span>
        </div>
      </div>

      <div class="card" style="margin-bottom:16px;">
        <div class="row" style="padding:14px 18px 0;align-items:baseline;gap:8px;">
          <h3 style="margin:0;">👤 Driver</h3>
          <span class="muted" style="font-size:11px;">Sumber data: akun user ber-role driver</span>
          <div class="spacer"></div>
          <router-link class="btn btn-sm" to="/users">✏️ Kelola di Manajemen User</router-link>
        </div>
        <div class="table-wrap">
          <table class="tbl">
            <thead><tr><th>Nama Driver</th><th>Nopol</th><th>Tipe</th><th>BBM</th><th>Akun</th><th>Status</th></tr></thead>
            <tbody>
              <tr v-for="d in drivers" :key="d.name">
                <td><b>{{ d.display_name || d.name }}</b><div class="muted" style="font-size:11px;">{{ d.name }}</div></td>
                <td>{{ d.nopol || '—' }}</td><td>{{ d.vehicle_type }}</td>
                <td>{{ d.bbm_type }}</td>
                <td><span class="badge" :class="d.has_account ? 'badge-green' : 'badge-red'">{{ d.has_account ? '🔗 Terhubung' : 'Tanpa akun' }}</span></td>
                <td><span class="badge" :class="d.is_active ? 'badge-green' : 'badge-red'">{{ d.is_active ? 'Aktif' : 'Nonaktif' }}</span></td>
              </tr>
              <tr v-if="!drivers.length"><td colspan="6" class="empty">Belum ada driver.</td></tr>
            </tbody>
          </table>
        </div>
      </div>

      <div class="stat-grid">
        <div class="card card-pad">
          <h3>🚙 Kendaraan</h3>
          <div class="table-wrap">
            <table class="tbl">
              <thead><tr><th>Tipe</th><th>Merk</th><th>Kapasitas</th><th>Status</th></tr></thead>
              <tbody>
                <tr v-for="v in vehicles" :key="v.id || v.vehicle_type">
                  <td><b>{{ v.vehicle_type }}</b></td><td>{{ v.brand }}</td><td>{{ v.fuel_capacity }}</td>
                  <td><span class="badge" :class="v.is_active ? 'badge-green' : 'badge-red'">{{ v.is_active ? 'Aktif' : 'Nonaktif' }}</span></td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>
        <div class="card card-pad">
          <h3>⛽ Tipe BBM</h3>
          <div class="table-wrap">
            <table class="tbl">
              <thead><tr><th>Nama</th><th>Harga/L</th><th>Status</th></tr></thead>
              <tbody>
                <tr v-for="b in bbms" :key="b.id || b.name">
                  <td><b>{{ b.name }}</b></td><td>{{ 'Rp ' + Number(b.price_per_liter || 0).toLocaleString('id-ID') }}</td>
                  <td><span class="badge" :class="b.is_active ? 'badge-green' : 'badge-red'">{{ b.is_active ? 'Aktif' : 'Nonaktif' }}</span></td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </template>

    <Modal v-if="showBulk && bulkResult" title="✅ Hasil Buat Akun Sekaligus" @close="showBulk = false">
      <p class="alert alert-info" style="font-size:12px;">{{ bulkResult.msg }}</p>
      <p v-if="bulkResult.pin" class="alert alert-warning" style="font-size:12px;">
        PIN akun baru: <b>{{ bulkResult.pin }}</b> — salin sekarang, PIN tidak ditampilkan lagi.
      </p>
      <h4 style="margin:10px 0 6px;">🆕 Akun dibuat ({{ bulkResult.created.length }})</h4>
      <div v-if="bulkResult.created.length" class="table-wrap">
        <table class="tbl">
          <thead><tr><th>Username</th><th>Role</th><th>Tim</th></tr></thead>
          <tbody>
            <tr v-for="c in bulkResult.created" :key="c.username">
              <td><b>{{ c.username }}</b></td><td>{{ c.role }}</td><td>{{ c.team || '—' }}</td>
            </tr>
          </tbody>
        </table>
      </div>
      <p v-else class="muted" style="font-size:12px;">Tidak ada akun baru (semua sudah ada / tidak ada data).</p>
      <h4 style="margin:12px 0 6px;">⏭ Dilewati ({{ bulkResult.skipped.length }})</h4>
      <ul v-if="bulkResult.skipped.length" style="font-size:11px;margin:0;padding-left:18px;">
        <li v-for="(s, i) in bulkResult.skipped" :key="i">{{ s.name }} — {{ s.reason }}</li>
      </ul>
      <p v-else class="muted" style="font-size:12px;">—</p>
      <div class="row" style="justify-content:flex-end;margin-top:12px;">
        <button class="btn btn-primary" @click="showBulk = false">Tutup</button>
      </div>
    </Modal>

    <Modal v-if="showBranchForm" :title="branchForm.id ? `✏️ Edit Cabang ${branchForm.code}` : '➕ Tambah Cabang'" @close="showBranchForm = false">
      <div class="form-grid">
        <div class="field"><label>Kode Cabang *</label><input class="input" v-model="branchForm.code" placeholder="mis. MLG" :disabled="!!branchForm.id" /></div>
        <div class="field"><label>Nama Cabang *</label><input class="input" v-model="branchForm.name" placeholder="mis. Cabang Malang" /></div>
        <div class="field"><label>Nama Database *</label><input class="input" v-model="branchForm.db_name" placeholder="mis. bpf_branch_malang" :disabled="!!branchForm.id" /></div>
        <div class="field"><label>Kota</label><input class="input" v-model="branchForm.city" placeholder="Malang" /></div>
        <div class="field"><label>Alamat</label><input class="input" v-model="branchForm.address" /></div>
        <div class="field"><label>Telepon</label><input class="input" v-model="branchForm.phone" /></div>
        <div class="field"><label>Nama Perusahaan</label><input class="input" v-model="branchForm.company_name" placeholder="PT BESTPROFIT FUTURES" /></div>
        <div class="field"><label>Subjudul (kantor | kota)</label><input class="input" v-model="branchForm.company_subtitle" placeholder="Sistem Operasional | Malang" /></div>
        <div class="field"><label>Nama Sistem</label><input class="input" v-model="branchForm.system_name" placeholder="BPF WorkHub" /></div>
        <div class="field"><label>Versi</label><input class="input" v-model="branchForm.system_version" placeholder="v2.20.1" /></div>
      </div>
      <label class="muted" style="font-size:12px;display:flex;align-items:center;gap:6px;margin-top:8px;">
        <input type="checkbox" v-model="branchForm.ensure_db" /> Buat database cabang langsung (salinan skema)
      </label>
      <div class="row" style="justify-content:flex-end;margin-top:12px;">
        <button class="btn" @click="showBranchForm = false">Batal</button>
        <button class="btn btn-primary" :disabled="branchBusy" @click="saveBranch">💾 Simpan Cabang</button>
      </div>
    </Modal>

    <Modal v-if="showVehicleForm" title="🚙 Tambah Kendaraan" @close="showVehicleForm = false">
      <div class="form-grid">
        <div class="field"><label>No. Polisi *</label><input class="input" v-model="vehicleForm.nopol" placeholder="mis. L 1234 AB" /></div>
        <div class="field"><label>Tipe Kendaraan</label>
          <select class="select" v-model="vehicleForm.vehicle_type"><option v-for="t in vehicleTypes" :key="t" :value="t">{{ t }}</option></select>
        </div>
        <div class="field"><label>Merk</label><input class="input" v-model="vehicleForm.brand" /></div>
        <div class="field"><label>BBM Default</label>
          <select class="select" v-model="vehicleForm.bbm_default"><option v-for="b in bbmNames" :key="b" :value="b">{{ b }}</option></select>
        </div>
      </div>
      <div class="row" style="justify-content:flex-end;margin-top:12px;">
        <button class="btn" @click="showVehicleForm = false">Batal</button>
        <button class="btn btn-primary" :disabled="busy" @click="addVehicle">💾 Simpan</button>
      </div>
    </Modal>

    <ConfirmDialog ref="confirmRef" />
  </div>
</template>

<style scoped>
/* Peta seksi — sticky saat halaman di-scroll */
.settings-nav {
  position: sticky;
  top: 60px;
  z-index: 20;
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  padding: 10px 12px;
  margin-bottom: 16px;
}
.settings-nav-btn {
  border: 1px solid var(--border);
  background: var(--bg, #fff);
  color: var(--text, inherit);
  border-radius: 999px;
  padding: 5px 12px;
  font-size: 12px;
  cursor: pointer;
  transition: background .15s, color .15s;
}
.settings-nav-btn:hover { background: var(--accent-soft, #eef2ff); }
.settings-nav-btn.active { background: var(--accent, #2563eb); color: #fff; border-color: var(--accent, #2563eb); }

/* Toggle switch standar (dipakai fitur edit/hapus air minum) */
.switch { position: relative; display: inline-flex; align-items: center; cursor: pointer; }
.switch input { position: absolute; opacity: 0; width: 0; height: 0; }
.switch .slider {
  display: inline-flex;
  align-items: center;
  width: 96px;
  height: 28px;
  border-radius: 999px;
  background: #9ca3af;
  transition: background .2s;
  padding: 0 10px;
  justify-content: flex-end;
}
.switch .slider-label { color: #fff; font-size: 10px; font-weight: 700; letter-spacing: .4px; }
.switch input:checked + .slider { background: #16a34a; justify-content: flex-start; }
.switch input:disabled + .slider { opacity: .6; cursor: wait; }
.switch .slider::before {
  content: '';
  position: absolute;
  top: 4px;
  left: 4px;
  width: 20px;
  height: 20px;
  border-radius: 50%;
  background: #fff;
  transition: transform .2s;
}
.switch input:checked + .slider::before { transform: translateX(28px); }
</style>
