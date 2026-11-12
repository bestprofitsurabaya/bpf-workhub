<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import QRCode from 'qrcode'
import { api } from '../api'
import { useAuthStore } from '../stores/auth'
import PageHeader from '../components/PageHeader.vue'
import Modal from '../components/Modal.vue'

const auth = useAuthStore()
const isAdmin = computed(() => auth.role === 'admin')
const canVerify = computed(() => ['traineer', 'admin'].includes(auth.role))
const branchName = computed(() => auth.user?.branch_name || auth.user?.branch_code || '')

const tab = ref('data')
const loading = ref(true)
const busy = ref(false)
const err = ref('')
const msg = ref('')

const rows = ref([])
const stats = ref({})
const total = ref(0)
const page = ref(1)
const limit = ref(25)
const scopeBranch = ref(null)
const referrers = ref([])
const filters = reactive({ status: '', q: '', date_from: '', date_to: '', referrer_id: '' })

const detail = ref(null)
const events = ref([])
const showDetail = ref(false)
const verifyNote = ref('')
// v2.94.0: verifikasi/tolak massal untuk membereskan antrean migrasi.
const bulkIds = ref([])
const bulkNote = ref('')
const bulkBusy = ref(false)
const allPageSelected = computed(() => {
  const pending = rows.value.filter((r) => r.status === 'submitted')
  return pending.length > 0 && pending.every((r) => bulkIds.value.includes(r.id))
})
const editFields = reactive({ nama: '', nik: '', pendidikan: '', no_hp: '', referrer_id: '' })

// v2.83.0: ID Fingerprint & ID BPF — tampil di tabel, diedit traineer/admin,
// angka awal & pemetaan kolom counter sheet bisa diatur.
const idCfg = ref(null)
// v2.95.0: counter ID opsional per cabang (kosong = ikut counter global).
const branchCounters = ref([])
const idForm = reactive({
  fingerprint_series: 'B',
  bpf_series: 'C',
  start_fingerprint: '',
  start_bpf: '',
})

const adminRefs = ref([])
const adminUsers = ref([])
const newRef = reactive({ name: '', user_id: '' })
const syncInfo = ref(null)

// Form publik punya path sendiri (/first-work-form) supaya halaman ini tetap
// menampilkan data — bukan form — untuk semua role yang membukanya.
// v2.82.0: tiap cabang punya tautan ber-token sendiri; tautan cabang A tidak
// bisa dipakai mengirim isian atas nama cabang B.
const branchForms = ref([])
const formLink = computed(() => {
  const scope = scopeBranch.value
  const entry = branchForms.value.find((b) => b.branch_code === scope)
  // v2.86.2: tautan form WAJIB ber-token. Jangan pernah fallback ke tautan
  // tokenless — backend menolaknya (v2.84.0+) dan traineer akan membagikan
  // tautan mati. Kosong = tombol tautan/QR dinonaktifkan, bukan tautan salah.
  return entry?.form_path ? window.location.origin + entry.form_path : ''
})
const subtitle = computed(() => {
  const scope = scopeBranch.value
    ? `Pendaftar & verifikasi — ${branchName.value || 'cabang ' + scopeBranch.value}`
    : 'Pendaftar & verifikasi — semua cabang'
  return canVerify.value ? scope : `${scope} · hanya lihat`
})
// Chip status = cara tercepat traineer membuka antrean verifikasi.
const statusChips = computed(() => [
  { value: '', label: 'Semua', count: stats.value.total || 0 },
  { value: 'submitted', label: '🕒 Menunggu', count: stats.value.submitted || 0 },
  { value: 'verified', label: '✅ Terverifikasi', count: stats.value.verified || 0 },
  { value: 'rejected', label: '✕ Ditolak', count: stats.value.rejected || 0 },
])
function pickStatus(value) {
  filters.status = value
  load(1)
}
const pages = computed(() => Math.max(1, Math.ceil(total.value / limit.value)))
const exportUrl = computed(() => {
  const query = new URLSearchParams()
  if (filters.status) query.set('status', filters.status)
  if (filters.date_from) query.set('date_from', filters.date_from)
  if (filters.date_to) query.set('date_to', filters.date_to)
  const suffix = query.toString()
  return '/api/first-work/export' + (suffix ? '?' + suffix : '')
})

// v2.92.0: label event yang ramah dibaca (termasuk sinyal anti-fraud).
const EVENT_LABELS = {
  created: 'Form dikirim',
  consent: 'Persetujuan UU PDP',
  verified: 'Diverifikasi',
  rejected: 'Ditolak',
  ktp_purge: 'KTP dipurge (retensi)',
  phone_reuse: '⚠️ No. HP juga dipakai pendaftaran lain',
  ktp_reuse: '⚠️ File KTP identik dengan pendaftaran lain',
  bulk_verify: 'Diverifikasi massal',
  bulk_reject: 'Ditolak massal',
  ktp_link: 'Tautan unduh KTP dibuat',
  ktp_download: 'KTP diunduh via tautan',
  first_work_id_config: 'Pengaturan ID Fingerprint/BPF',
}
function eventLabel(name) {
  return EVENT_LABELS[name] || name
}

function fmtDT(value) {
  if (!value) return '-'
  const dt = new Date(String(value).replace(' ', 'T'))
  if (Number.isNaN(dt.getTime())) return String(value)
  return dt.toLocaleString('id-ID', {
    day: '2-digit', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit',
  })
}

function maskNik(nik) {
  const text = String(nik || '')
  if (text.length !== 16) return text || '—'
  return text.slice(0, 4) + '••••••••' + text.slice(-4)
}

async function load(target = 1) {
  loading.value = true
  err.value = ''
  try {
    const params = { page: target, limit: limit.value }
    Object.entries(filters).forEach(([key, value]) => { if (value) params[key] = value })
    const data = await api('/api/first-work', { params })
    rows.value = data.data || []
    stats.value = data.stats || {}
    total.value = data.total || 0
    page.value = data.page || target
    scopeBranch.value = data.scope_branch ?? null
    bulkIds.value = []
  } catch (e) {
    err.value = e.message || 'Gagal memuat data.'
  } finally {
    loading.value = false
  }
}

function toggleAllBulk(checked) {
  bulkIds.value = checked
    ? rows.value.filter((r) => r.status === 'submitted').map((r) => r.id)
    : []
}

async function runBulk(action) {
  if (!bulkIds.value.length) { err.value = 'Pilih data dulu.'; return }
  if (bulkNote.value.trim().length < 5) {
    err.value = 'Catatan minimal 5 karakter agar jejak audit jelas.'
    return
  }
  const label = action === 'verify' ? 'verifikasi' : 'tolak'
  if (!window.confirm(`Yakin ${label} ${bulkIds.value.length} pendaftar? Tiap baris tercatat di riwayat.`)) return
  bulkBusy.value = true
  err.value = ''
  try {
    const data = await api('/api/first-work/bulk-verify', {
      method: 'POST',
      body: { ids: bulkIds.value, action, note: bulkNote.value.trim() },
    })
    msg.value = `${data.updated} data diperbarui`
      + (data.skipped ? `, ${data.skipped} dilewati (bukan status menunggu).` : '.')
    bulkIds.value = []
    bulkNote.value = ''
    await load(page.value)
  } catch (e) {
    err.value = e.message || 'Gagal memproses massal.'
  } finally {
    bulkBusy.value = false
  }
}

async function loadMeta() {
  try {
    const data = await api('/api/first-work/meta')
    referrers.value = data.referrers || []
  } catch {
    referrers.value = []
  }
}

function applyFilters() {
  load(1)
}

function resetFilters() {
  Object.assign(filters, { status: '', q: '', date_from: '', date_to: '', referrer_id: '' })
  load(1)
}

async function openDetail(row) {
  err.value = ''
  try {
    const data = await api(`/api/first-work/${row.id}`)
    detail.value = data.data
    events.value = data.data.events || []
    verifyNote.value = ''
    Object.assign(editFields, {
      nama: data.data.nama || '',
      nik: data.data.nik || '',
      pendidikan: data.data.pendidikan_raw || '',
      no_hp: data.data.no_hp || '',
      referrer_id: data.data.referrer_id || '',
      fingerprint_no: data.data.fingerprint_no ?? '',
      bpf_no: data.data.bpf_no ?? '',
    })
    showDetail.value = true
  } catch (e) {
    err.value = e.message || 'Gagal memuat detail.'
  }
}

function closeDetail() {
  showDetail.value = false
  detail.value = null
  events.value = []
}

async function doVerify(action) {
  if (!detail.value) return
  if (action === 'reject' && !verifyNote.value.trim()) {
    err.value = 'Alasan penolakan wajib diisi.'
    return
  }
  busy.value = true
  err.value = ''
  try {
    await api(`/api/first-work/${detail.value.id}/verify`, {
      method: 'POST',
      body: { action, note: verifyNote.value.trim() },
    })
    msg.value = action === 'verify' ? 'Data diverifikasi.' : 'Data ditolak.'
    closeDetail()
    await load(page.value)
  } catch (e) {
    err.value = e.message || 'Gagal memperbarui status.'
  } finally {
    busy.value = false
  }
}

async function saveEdit() {
  if (!detail.value) return
  busy.value = true
  err.value = ''
  try {
    const body = {
      nama: editFields.nama,
      pendidikan: editFields.pendidikan,
      no_hp: editFields.no_hp,
      referrer_id: editFields.referrer_id || null,
    }
    if (/^\d{16}$/.test(String(editFields.nik || ''))) body.nik = editFields.nik
    await api(`/api/first-work/${detail.value.id}`, { method: 'PATCH', body })
    msg.value = 'Koreksi data disimpan.'
    await openDetail(detail.value)
    await load(page.value)
  } catch (e) {
    err.value = e.message || 'Gagal menyimpan koreksi.'
  } finally {
    busy.value = false
  }
}

// v2.83.0: muat konfigurasi ID (pemetaan seri + angka berikutnya).
async function loadIdConfig() {
  try {
    const data = await api('/api/first-work/id-config')
    idCfg.value = data
    branchCounters.value = data.branches || []
    idForm.fingerprint_series = data.fingerprint_series || 'B'
    idForm.bpf_series = data.bpf_series || 'C'
  } catch (e) {
    idCfg.value = null
    err.value = e.message || 'Gagal memuat pengaturan ID.'
  }
}

// v2.95.0: simpan counter khusus satu cabang (admin).
async function saveBranchCounter(branch) {
  const body = {}
  if (branch.start_fingerprint) body.start_fingerprint = branch.start_fingerprint
  if (branch.start_bpf) body.start_bpf = branch.start_bpf
  if (!Object.keys(body).length) {
    err.value = 'Isi minimal satu angka awal untuk cabang ini.'
    return
  }
  busy.value = true
  err.value = ''
  try {
    const data = await api(`/api/first-work/id-config/branch/${branch.branch_code}`, {
      method: 'PUT',
      body,
    })
    idCfg.value = data.data
    branchCounters.value = data.data.branches || []
    msg.value = data.msg || 'Counter cabang disimpan.'
  } catch (e) {
    err.value = e.message || 'Gagal menyimpan counter cabang.'
  } finally {
    busy.value = false
  }
}

// v2.83.0: simpan pemetaan + angka awal ID Fingerprint / ID BPF.
async function saveIdConfig() {
  if (idForm.fingerprint_series === idForm.bpf_series) {
    err.value = 'ID Fingerprint dan ID BPF tidak boleh memakai kolom counter yang sama.'
    return
  }
  busy.value = true
  err.value = ''
  try {
    const body = {
      fingerprint_series: idForm.fingerprint_series,
      bpf_series: idForm.bpf_series,
    }
    if (String(idForm.start_fingerprint).trim() !== '') {
      body.start_fingerprint = Number(String(idForm.start_fingerprint).trim())
    }
    if (String(idForm.start_bpf).trim() !== '') {
      body.start_bpf = Number(String(idForm.start_bpf).trim())
    }
    const data = await api('/api/first-work/id-config', { method: 'PUT', body })
    idCfg.value = data.data || idCfg.value
    idForm.start_fingerprint = ''
    idForm.start_bpf = ''
    msg.value = data.msg || 'Pengaturan ID disimpan.'
    await load(page.value)
  } catch (e) {
    err.value = e.message || 'Gagal menyimpan pengaturan ID.'
  } finally {
    busy.value = false
  }
}

// v2.83.0: koreksi ID satu baris dari modal detail.
async function saveIds() {
  if (!detail.value) return
  busy.value = true
  err.value = ''
  try {
    const body = {}
    if (String(editFields.fingerprint_no).trim() !== '') {
      body.fingerprint_no = Number(String(editFields.fingerprint_no).trim())
    } else {
      body.fingerprint_no = null
    }
    if (String(editFields.bpf_no).trim() !== '') {
      body.bpf_no = Number(String(editFields.bpf_no).trim())
    } else {
      body.bpf_no = null
    }
    await api(`/api/first-work/${detail.value.id}/ids`, { method: 'PATCH', body })
    msg.value = 'ID Fingerprint & ID BPF diperbarui.'
    await openDetail(detail.value)
    await load(page.value)
  } catch (e) {
    err.value = e.message || 'Gagal menyimpan ID.'
  } finally {
    busy.value = false
  }
}

async function openIdTab() {
  tab.value = 'ids'
  await loadIdConfig()
}

async function downloadKtp(row) {
  err.value = ''
  try {
    // v2.96.0: unduhan lewat tautan bertanda tangan berumur 5 menit.
    const data = await api(`/api/first-work/${row.id}/ktp-link`, { method: 'POST' })
    window.open(data.url, '_blank', 'noopener')
    msg.value = 'Tautan unduh dibuat (berlaku 5 menit) dan tercatat di riwayat.'
  } catch (e) {
    err.value = e.message || 'Gagal membuat tautan unduh KTP.'
  }
}

async function copyFormLink() {
  if (!formLink.value) {
    err.value = 'Tautan form ber-token belum termuat — muat ulang halaman.'
    return
  }
  await copyLink(formLink.value, 'Link form publik')
}

async function loadBranchForms() {
  try {
    const data = await api('/api/first-work/branch-forms')
    branchForms.value = data.branches || []
  } catch {
    branchForms.value = []
  }
}

async function copyLink(url, label = 'Link form cabang') {
  try {
    await navigator.clipboard.writeText(url)
    msg.value = `${label} disalin: ${url}`
  } catch {
    msg.value = `${label}: ${url}`
  }
}

// v2.84.0: QR statis per cabang. Token cabang bersifat permanen, jadi QR yang
// dicetak tetap sah sampai token dirotasi manual oleh admin. QR dibuat lokal
// di browser — URL berisi token rahasia, tidak boleh dikirim ke layanan QR
// pihak ketiga.
const qrModal = reactive({ show: false, label: '', url: '', dataUrl: '', file: '' })

function branchUrl(entry) {
  return entry?.form_path ? window.location.origin + entry.form_path : ''
}

async function showQr(url, label) {
  if (!url) { err.value = 'Link form belum tersedia — muat ulang halaman.'; return }
  Object.assign(qrModal, {
    show: true, label, url, dataUrl: '',
    file: 'qr-firstwork-' + (label.toLowerCase().replace(/[^a-z0-9]+/g, '-')) + '.png',
  })
  try {
    qrModal.dataUrl = await QRCode.toDataURL(url, { width: 420, margin: 2 })
  } catch (e) {
    err.value = 'Gagal membuat QR: ' + (e.message || e)
    qrModal.show = false
  }
}

function showBranchQr(entry) {
  showQr(branchUrl(entry), 'Form FirstWork ' + (entry?.branch_code || ''))
}

function printQr() {
  const win = window.open('', '_blank', 'width=520,height=680')
  if (!win) { err.value = 'Popup diblokir browser. Gunakan Unduh PNG.'; return }
  win.document.write(
    '<html><head><title>' + qrModal.label + '</title></head>' +
    '<body style="text-align:center;font-family:sans-serif;margin:24px">' +
    '<h3 style="margin:0 0 4px">' + qrModal.label + '</h3>' +
    '<p style="margin:0 0 12px;font-size:12px">Scan untuk mengisi Absensi FirstWork</p>' +
    '<img src="' + qrModal.dataUrl + '" style="width:360px" onload="window.focus();window.print()" />' +
    '<p style="font-size:10px;color:#555;word-break:break-all">' + qrModal.url + '</p>' +
    '</body></html>')
  win.document.close()
}

async function runSync(dryRun) {
  busy.value = true
  err.value = ''
  syncInfo.value = null
  try {
    const data = await api('/api/first-work/sync', {
      method: 'POST',
      body: { dry_run: dryRun, full: false },
    })
    syncInfo.value = data
    msg.value = dryRun ? 'Cek sync selesai (tanpa menulis).' : 'Sync Sheet selesai.'
    if (!dryRun) await load(1)
  } catch (e) {
    err.value = e.message || 'Sync gagal. Periksa URL Apps Script di system_config.'
  } finally {
    busy.value = false
  }
}

async function openAdmin() {
  tab.value = 'admin'
  if (isAdmin.value) loadBranchForms()
  if (adminRefs.value.length) return
  try {
    const data = await api('/api/first-work/referrers/manage')
    adminRefs.value = data.referrers || []
    adminUsers.value = data.users || []
  } catch (e) {
    err.value = e.message || 'Gagal memuat referrer.'
  }
}

async function addReferrer() {
  if (newRef.name.trim().length < 2) {
    err.value = 'Nama referrer minimal 2 karakter.'
    return
  }
  busy.value = true
  try {
    await api('/api/first-work/referrers', {
      method: 'POST',
      body: { name: newRef.name.trim(), user_id: newRef.user_id || null },
    })
    newRef.name = ''
    newRef.user_id = ''
    adminRefs.value = []
    await openAdmin()
    msg.value = 'Referrer ditambahkan.'
  } catch (e) {
    err.value = e.message || 'Gagal menambah referrer.'
  } finally {
    busy.value = false
  }
}

async function toggleReferrer(row) {
  busy.value = true
  try {
    await api(`/api/first-work/referrers/${row.id}`, { method: 'PATCH', body: { active: !row.active } })
    row.active = !row.active
    msg.value = row.active ? 'Referrer diaktifkan.' : 'Referrer dinonaktifkan.'
  } catch (e) {
    err.value = e.message || 'Gagal memperbarui referrer.'
  } finally {
    busy.value = false
  }
}

onMounted(() => {
  loadMeta()
  load(1)
  // v2.86.2: traineer juga butuh tautan ber-token (bukan hanya admin) —
  // sebelumnya fetch dilewati untuk traineer sehingga tautan jatuh ke
  // fallback tokenless yang lalu ditolak backend.
  if (canVerify.value) loadBranchForms()
})
</script>

<template>
  <div class="fw-view">
    <PageHeader icon="📝" title="Absensi FirstWork" :subtitle="subtitle">
      <a v-if="canVerify && formLink" class="btn" :href="formLink" target="_blank" rel="noopener">↗ Buka Form Publik</a>
      <button v-if="canVerify" class="btn" @click="copyFormLink">🔗 Salin Link</button>
      <button v-if="canVerify" class="btn" @click="showQr(formLink, 'Form FirstWork ' + (scopeBranch || 'SBY'))">▦ QR</button>
      <a class="btn" :href="exportUrl" target="_blank" rel="noopener">⬇️ Ekspor CSV</a>
      <button v-if="isAdmin" class="btn" :disabled="busy" @click="runSync(true)">🧪 Cek Sync</button>
      <button v-if="isAdmin" class="btn btn-primary" :disabled="busy" @click="runSync(false)">🔄 Sync Sheet</button>
    </PageHeader>

    <div v-if="err" class="alert alert-error">{{ err }}</div>
    <div v-if="msg" class="alert alert-success">{{ msg }}</div>

    <!-- v2.93.0: pendaftar yang menunggu terlalu lama -->
    <div v-if="(stats.pending_over_7d || 0) > 0" class="fw-callout fw-callout-warn">
      ⚠️ {{ stats.pending_over_7d }} pendaftar sudah menunggu lebih dari 7 hari.
      <button type="button" class="fw-link" @click="pickStatus('submitted')">Buka antrean</button>
    </div>

    <div class="fw-stats">
      <div class="fw-stat"><span>Total</span><b>{{ stats.total || 0 }}</b></div>
      <div class="fw-stat fw-amber"><span>Menunggu</span><b>{{ stats.submitted || 0 }}</b></div>
      <div class="fw-stat fw-green"><span>Terverifikasi</span><b>{{ stats.verified || 0 }}</b></div>
      <div class="fw-stat fw-red"><span>Ditolak</span><b>{{ stats.rejected || 0 }}</b></div>
      <div class="fw-stat"><span>Hari Ini</span><b>{{ stats.today || 0 }}</b></div>
      <div class="fw-stat fw-amber"><span>Antrean &gt;3 hari</span><b>{{ stats.pending_over_3d || 0 }}</b></div>
      <div class="fw-stat fw-red fw-stat-click" @click="pickStatus('submitted')">
        <span>Antrean &gt;7 hari</span><b>{{ stats.pending_over_7d || 0 }}</b>
      </div>
      <div class="fw-stat fw-amber"><span>Referensi Baru</span><b>{{ stats.needs_review || 0 }}</b></div>
    </div>

    <div class="fw-tabs">
      <button class="fw-tab" :class="{ active: tab === 'data' }" @click="tab = 'data'">Data Pengisian</button>
      <button v-if="canVerify" class="fw-tab" :class="{ active: tab === 'ids' }" @click="openIdTab">
        ID Fingerprint &amp; ID BPF
      </button>
      <button v-if="isAdmin" class="fw-tab" :class="{ active: tab === 'admin' }" @click="openAdmin">Referensi &amp; Sync</button>
    </div>

    <!-- ============ TAB ID (v2.83.0) ============ -->
    <div v-if="canVerify && tab === 'ids'" class="card card-pad">
      <h3 style="margin-top:0;">ID Fingerprint &amp; ID BPF</h3>
      <p class="fw-note" style="margin-top:0;">
        Setiap pengisian form otomatis mendapat ID Fingerprint dan ID BPF. Nomor
        mengalir dari counter yang diatur di sini. Data historis dari Google
        Spreadsheet sudah membawa nomornya masing-masing.
      </p>

      <div v-if="idCfg" class="fw-id-grid">
        <div class="fw-id-box">
          <b>ID Fingerprint</b>
          <div class="fw-id-meta">
            Terbit berikutnya: <b>{{ idCfg.next_fingerprint }}</b><br />
            Nomor terakhir terpakai: {{ idCfg.max_fingerprint ?? '—' }}<br />
            Belum ber-ID: {{ idCfg.missing_fingerprint }} dari {{ idCfg.total }}
          </div>
          <label class="fw-id-label">Sumber counter</label>
          <select class="select" v-model="idForm.fingerprint_series">
            <option v-for="(label, code) in idCfg.series_labels" :key="code" :value="code">
              Kolom {{ code }} — {{ label }}
            </option>
          </select>
          <label class="fw-id-label">Set angka awal (nomor berikutnya)</label>
          <input class="input" v-model="idForm.start_fingerprint" inputmode="numeric"
                 :placeholder="'Sekarang: ' + idCfg.next_fingerprint" />
        </div>
        <div class="fw-id-box">
          <b>ID BPF</b>
          <div class="fw-id-meta">
            Terbit berikutnya: <b>{{ idCfg.next_bpf }}</b><br />
            Nomor terakhir terpakai: {{ idCfg.max_bpf ?? '—' }}<br />
            Belum ber-ID: {{ idCfg.missing_bpf }} dari {{ idCfg.total }}
          </div>
          <label class="fw-id-label">Sumber counter</label>
          <select class="select" v-model="idForm.bpf_series">
            <option v-for="(label, code) in idCfg.series_labels" :key="code" :value="code">
              Kolom {{ code }} — {{ label }}
            </option>
          </select>
          <label class="fw-id-label">Set angka awal (nomor berikutnya)</label>
          <input class="input" v-model="idForm.start_bpf" inputmode="numeric"
                 :placeholder="'Sekarang: ' + idCfg.next_bpf" />
        </div>
      </div>
      <p v-else class="fw-empty">⏳ Memuat pengaturan ID…</p>

      <div v-if="idCfg && branchCounters.length" class="fw-branch-counters">
        <h4>Counter ID per cabang</h4>
        <p class="fw-note">
          “Ikut global” berarti cabang memakai counter bersama. Setelah diatur,
          cabang memakai counter sendiri — nomor yang sudah terpakai tetap
          dilewati, jadi tidak ada ID ganda antar cabang. Angka awal tidak boleh
          mundur atau menabrak nomor yang sudah dipakai cabang itu.
        </p>
        <div class="fw-table-wrap">
          <table class="fw-table">
            <thead>
              <tr><th>Cabang</th><th>FP berikutnya</th><th>BPF berikutnya</th><th>Set angka awal</th><th></th></tr>
            </thead>
            <tbody>
              <tr v-for="b in branchCounters" :key="b.branch_code">
                <td>
                  <b>{{ b.branch_code }}</b>
                  <div class="fw-sub">{{ b.branch_name }}</div>
                  <small v-if="!b.has_counter" class="fw-hint">ikut global</small>
                </td>
                <td class="nowrap">{{ b.next_fingerprint }}</td>
                <td class="nowrap">{{ b.next_bpf }}</td>
                <td>
                  <div class="fw-id-inputs">
                    <input class="input" v-model="b.start_fingerprint" inputmode="numeric"
                           :placeholder="'FP: ' + b.next_fingerprint" />
                    <input class="input" v-model="b.start_bpf" inputmode="numeric"
                           :placeholder="'BPF: ' + b.next_bpf" />
                  </div>
                </td>
                <td>
                  <button class="btn btn-sm btn-primary" :disabled="busy"
                          @click="saveBranchCounter(b)">Simpan</button>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>

      <div class="fw-actions">
        <button class="btn btn-primary" :disabled="busy" @click="saveIdConfig">💾 Simpan Pengaturan ID</button>
        <button class="btn" :disabled="busy" @click="loadIdConfig">↩️ Muat Ulang</button>
      </div>
      <p class="fw-note">
        Angka awal = nomor yang akan terbit untuk pengisian berikutnya. Kolom
        angka awal boleh dibiarkan kosong bila hanya pemetaan counter yang
        ingin diubah. Nomor yang sudah terpakai tidak akan diterbitkan dua kali.
      </p>
    </div>

    <!-- ============ TAB DATA ============ -->
    <div v-show="tab === 'data'" class="card card-pad">
      <div class="fw-chips" role="tablist" aria-label="Filter status">
        <button v-for="c in statusChips" :key="c.value || 'all'" type="button" role="tab"
                class="fw-chip" :class="{ active: filters.status === c.value }"
                :aria-selected="filters.status === c.value"
                @click="pickStatus(c.value)">
          {{ c.label }} <b>{{ c.count }}</b>
        </button>
      </div>

      <form class="fw-filters" @submit.prevent="applyFilters">
        <input class="input" v-model="filters.q" placeholder="Cari nama, NIK, HP, no. registrasi…" />
        <select class="select" v-model="filters.referrer_id">
          <option value="">Semua referensi</option>
          <option v-for="ref in referrers" :key="ref.id" :value="String(ref.id)">{{ ref.name }}</option>
        </select>
        <input class="input" type="date" v-model="filters.date_from" />
        <input class="input" type="date" v-model="filters.date_to" />
        <button class="btn btn-primary" type="submit">🔍 Terapkan</button>
        <button class="btn" type="button" @click="resetFilters">Reset</button>
      </form>

      <div v-if="canVerify && rows.length" class="fw-bulk">
        <label class="fw-bulk-all">
          <input type="checkbox" :checked="allPageSelected" @change="toggleAllBulk($event.target.checked)" />
          Pilih semua di halaman
        </label>
        <span class="fw-bulk-count">{{ bulkIds.length }} dipilih</span>
        <input class="input fw-bulk-note" v-model="bulkNote" maxlength="500"
               placeholder="Catatan bersama (wajib) — cth: verifikasi data migrasi sheet" />
        <button class="btn btn-primary btn-sm" :disabled="!bulkIds.length || bulkBusy"
                @click="runBulk('verify')">✅ Verifikasi terpilih</button>
        <button class="btn btn-sm" :disabled="!bulkIds.length || bulkBusy"
                @click="runBulk('reject')">✕ Tolak terpilih</button>
      </div>

      <div v-if="loading" class="fw-empty">⏳ Memuat data…</div>
      <div v-else-if="!rows.length" class="fw-empty">
        <p style="margin:0 0 6px;">Tidak ada pengisian untuk filter ini.</p>
        <a v-if="canVerify && formLink" class="btn btn-sm" :href="formLink" target="_blank" rel="noopener">↗ Buka form publik</a>
        <p v-else style="margin:0;">Data cabang Anda akan muncul di sini setelah pendaftar mengisi form.</p>
      </div>
      <div v-else class="fw-table-wrap">
        <table class="fw-table">
          <thead>
            <tr>
              <th v-if="canVerify" class="fw-check"></th>
              <th>Pendaftar</th>
              <th>ID Fingerprint</th>
              <th>ID BPF</th>
              <th>Pendidikan</th>
              <th>Referensi</th>
              <th>Waktu Kirim</th>
              <th>Status</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="row in rows" :key="row.id">
              <td v-if="canVerify" class="fw-check">
                <input type="checkbox" :value="row.id" v-model="bulkIds"
                       :disabled="row.status !== 'submitted'" />
              </td>
              <td>
                <b>{{ row.nama }}</b>
                <div class="fw-sub">
                  <code>{{ row.registration_no }}</code> · NIK {{ maskNik(row.nik) }} · {{ row.no_hp || '—' }}
                </div>
              </td>
              <td class="nowrap">{{ row.fingerprint_no ?? '—' }}</td>
              <td class="nowrap">{{ row.bpf_no ?? '—' }}</td>
              <td>{{ row.pendidikan_norm || row.pendidikan_raw || '—' }}</td>
              <td>
                {{ row.referrer_name || row.referensi_raw || '—' }}
                <span v-if="row.referrer_needs_review" class="fw-flag" title="Perlu pemetaan referrer">⚠️</span>
              </td>
              <td class="nowrap">{{ fmtDT(row.submitted_at) }}</td>
              <td><span class="fw-badge" :class="'st-' + row.status">{{ row.status_label }}</span></td>
              <td><button class="btn btn-sm" @click="openDetail(row)">Detail</button></td>
            </tr>
          </tbody>
        </table>
      </div>

      <div v-if="pages > 1" class="fw-pager">
        <button class="btn btn-sm" :disabled="page <= 1" @click="load(page - 1)">‹ Sebelumnya</button>
        <span>Halaman {{ page }} / {{ pages }} · {{ total }} data</span>
        <button class="btn btn-sm" :disabled="page >= pages" @click="load(page + 1)">Berikutnya ›</button>
      </div>
    </div>

    <!-- ============ TAB ADMIN ============ -->
    <div v-if="isAdmin && tab === 'admin'" class="card card-pad">
      <div v-if="syncInfo" class="fw-sync">
        <b>Hasil sync</b>
        <div class="fw-sync-grid">
          <span v-for="(value, key) in syncInfo.stats" :key="key">{{ key }}: <b>{{ value }}</b></span>
        </div>
        <div v-if="syncInfo.samples && syncInfo.samples.length" class="fw-samples">
          <div v-for="s in syncInfo.samples" :key="s.sheet_row">
            baris {{ s.sheet_row }} · {{ s.nama }} · {{ s.referensi }} →
            {{ s.referrer_id ? 'referrer #' + s.referrer_id : 'perlu review' }}
          </div>
        </div>
      </div>

      <h3 style="margin-top:0;">Link Form per Cabang</h3>
      <p class="fw-note" style="margin-top:0;">
        Setiap cabang punya tautan ber-token sendiri. Isian yang masuk lewat
        tautan cabang A tidak pernah tercatat atas nama cabang B.
      </p>
      <div class="fw-table-wrap">
        <table class="fw-table">
          <thead><tr><th>Cabang</th><th>Link</th><th></th></tr></thead>
          <tbody>
            <tr v-for="b in branchForms" :key="b.branch_code">
              <td><b>{{ b.branch_code }}</b><div class="fw-sub">{{ b.branch_name }}</div></td>
              <td class="fw-link-cell">
                <code v-if="b.form_path">{{ b.form_path }}</code>
                <span v-else class="fw-hint">Token belum tersedia — restart aplikasi.</span>
              </td>
              <td>
                <button class="btn btn-sm" :disabled="!b.form_path"
                        @click="showBranchQr(b)">▦ QR</button>
                <button class="btn btn-sm" :disabled="!b.form_path"
                        @click="copyLink(branchUrl(b))">🔗 Salin</button>
              </td>
            </tr>
          </tbody>
        </table>
      </div>

      <h3>Master Referensi</h3>
      <div class="fw-filters">
        <input class="input" v-model="newRef.name" placeholder="Nama referrer baru (cth: IFAH)" />
        <select class="select" v-model="newRef.user_id">
          <option value="">Tanpa akun user</option>
          <option v-for="u in adminUsers" :key="u.id" :value="String(u.id)">
            {{ u.full_name }} ({{ u.role }})
          </option>
        </select>
        <button class="btn btn-primary" :disabled="busy" @click="addReferrer">➕ Tambah</button>
      </div>

      <div class="fw-table-wrap">
        <table class="fw-table">
          <thead>
            <tr><th>Nama</th><th>Terkait Akun</th><th>Pengisian</th><th>Status</th><th></th></tr>
          </thead>
          <tbody>
            <tr v-for="ref in adminRefs" :key="ref.id">
              <td>{{ ref.name }}</td>
              <td>{{ ref.user_id ? '#' + ref.user_id : '—' }}</td>
              <td>{{ ref.submission_count }}</td>
              <td>
                <span class="fw-badge" :class="ref.active ? 'st-verified' : 'st-rejected'">
                  {{ ref.active ? 'Aktif' : 'Nonaktif' }}
                </span>
              </td>
              <td>
                <button class="btn btn-sm" :disabled="busy" @click="toggleReferrer(ref)">
                  {{ ref.active ? 'Nonaktifkan' : 'Aktifkan' }}
                </button>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
      <p class="fw-note">
        Referensi dipakai untuk memetakan nama pengundang ke akun user (opsional).
        Referensi yang belum dipetakan tetap tersimpan dan ditandai ⚠️.
      </p>
    </div>

    <!-- ============ DETAIL ============ -->
    <Modal v-if="showDetail && detail" :title="`Detail ${detail.registration_no}`" wide @close="closeDetail">
      <div class="fw-detail-grid">
        <div><span>Nama</span><b>{{ detail.nama }}</b></div>
        <div><span>NIK</span><b>{{ detail.nik || detail.nik_raw || '—' }}</b>
          <small v-if="!detail.nik_valid">NIK tidak valid 16 digit</small></div>
        <div><span>Pendidikan</span><b>{{ detail.pendidikan_raw || detail.pendidikan_norm || '—' }}</b></div>
        <div><span>Referensi</span><b>{{ detail.referrer_name || detail.referensi_raw || '—' }}</b>
          <small v-if="detail.referrer_needs_review">Belum dipetakan ke master</small></div>
        <div><span>No. HP</span><b>{{ detail.no_hp || '—' }}</b></div>
        <div><span>ID Fingerprint</span><b>{{ detail.fingerprint_no ?? '—' }}</b></div>
        <div><span>ID BPF</span><b>{{ detail.bpf_no ?? '—' }}</b></div>
        <div><span>Waktu Kirim</span><b>{{ fmtDT(detail.submitted_at) }}</b></div>
        <div><span>Status</span><b>{{ detail.status_label }}</b></div>
        <div><span>Sumber</span><b>{{ detail.source === 'sheet' ? 'Migrasi Sheet' : 'Form publik' }}</b></div>
        <div v-if="detail.verified_by"><span>Diverifikasi Oleh</span><b>{{ detail.verified_by }}</b></div>
        <div v-if="detail.verification_note"><span>Catatan</span><b>{{ detail.verification_note }}</b></div>
      </div>

      <div class="fw-actions">
        <button v-if="canVerify" class="btn" :disabled="busy" @click="downloadKtp(detail)">🪪 Unduh KTP</button>
        <a v-if="detail.merged_doc_url" class="btn" :href="detail.merged_doc_url" target="_blank" rel="noopener">📄 Dokumen Gabungan</a>
      </div>

      <div v-if="canVerify" class="fw-verify">
        <label>Catatan verifikasi (wajib untuk penolakan)</label>
        <input class="input" v-model="verifyNote" maxlength="500" placeholder="cth: data sesuai KTP" />
        <div class="fw-actions">
          <button class="btn btn-primary" :disabled="busy" @click="doVerify('verify')">✅ Verifikasi</button>
          <button class="btn" :disabled="busy" @click="doVerify('reject')">✕ Tolak</button>
        </div>
      </div>

      <div v-if="canVerify" class="fw-edit">
        <h4>ID Fingerprint &amp; ID BPF (traineer/admin)</h4>
        <div class="fw-edit-grid">
          <input class="input" v-model="editFields.fingerprint_no" inputmode="numeric"
                 placeholder="ID Fingerprint (angka)" />
          <input class="input" v-model="editFields.bpf_no" inputmode="numeric"
                 placeholder="ID BPF (angka)" />
        </div>
        <button class="btn btn-primary" :disabled="busy" @click="saveIds">💾 Simpan ID</button>
      </div>

      <div v-if="isAdmin" class="fw-edit">
        <h4>Koreksi data (admin)</h4>
        <div class="fw-edit-grid">
          <input class="input" v-model="editFields.nama" placeholder="Nama" />
          <input class="input" v-model="editFields.nik" inputmode="numeric" maxlength="16" placeholder="NIK 16 digit" />
          <input class="input" v-model="editFields.pendidikan" placeholder="Pendidikan" />
          <input class="input" v-model="editFields.no_hp" placeholder="No. HP" />
          <select class="select" v-model="editFields.referrer_id">
            <option value="">— Referensi belum dipetakan —</option>
            <option v-for="ref in referrers" :key="ref.id" :value="String(ref.id)">{{ ref.name }}</option>
          </select>
        </div>
        <button class="btn btn-primary" :disabled="busy" @click="saveEdit">💾 Simpan Koreksi</button>
      </div>

      <div v-if="events.length" class="fw-events">
        <h4>Riwayat</h4>
        <div v-for="(e, index) in events" :key="index" class="fw-event"
             :class="{ 'fw-event-warn': String(e.event).includes('reuse') }">
          <b>{{ eventLabel(e.event) }}</b> · {{ e.status_to || '-' }} · {{ e.actor || 'sistem' }}
          <span>{{ fmtDT(e.created_at) }}</span>
          <div v-if="e.note" class="fw-hint">{{ e.note }}</div>
        </div>
      </div>
    </Modal>

    <!-- ============ QR STATIS (v2.84.0) ============ -->
    <Modal v-if="qrModal.show" :title="qrModal.label" @close="qrModal.show = false">
      <div class="fw-qr">
        <img v-if="qrModal.dataUrl" :src="qrModal.dataUrl" alt="QR form pengisian" />
        <p v-else class="fw-empty">⏳ Menyiapkan QR…</p>
        <code class="fw-qr-url">{{ qrModal.url }}</code>
        <p class="fw-note">
          QR ini statis — bisa dicetak &amp; ditempel di lokasi pendaftaran.
          Di dalamnya ada token cabang, jadi jangan dibagikan ke cabang lain.
        </p>
        <div class="fw-actions" style="justify-content:center;">
          <a v-if="qrModal.dataUrl" class="btn btn-primary" :href="qrModal.dataUrl"
             :download="qrModal.file">⬇️ Unduh PNG</a>
          <button v-if="qrModal.dataUrl" class="btn" @click="printQr">🖨️ Cetak</button>
        </div>
      </div>
    </Modal>
  </div>
</template>

<style scoped>
.fw-view { display: grid; gap: 14px; }
.fw-chips { display: flex; flex-wrap: wrap; gap: 8px; margin-bottom: 12px; }
.fw-chip {
  display: inline-flex; align-items: center; gap: 6px;
  border: 1px solid var(--border); background: var(--surface); color: var(--text-2);
  border-radius: 999px; padding: 6px 12px; font-size: 12px; font-weight: 600; cursor: pointer;
}
.fw-chip b { font-size: 11px; color: var(--text-3); }
.fw-chip:hover { border-color: var(--primary, #7c3aed); color: var(--text); }
.fw-chip.active { border-color: var(--primary, #7c3aed); color: var(--primary, #7c3aed); background: var(--surface-2, #f5f3ff); }
.fw-chip.active b { color: inherit; }
.fw-sub { font-size: 11px; color: var(--text-3); margin-top: 2px; }
.fw-stats { display: grid; gap: 10px; grid-template-columns: repeat(auto-fit, minmax(120px, 1fr)); }
.fw-stat {
  background: var(--surface); border: 1px solid var(--border); border-radius: 12px;
  padding: 12px 14px; display: flex; flex-direction: column; gap: 4px;
}
.fw-stat span { font-size: 11px; color: var(--text-3); }
.fw-stat b { font-size: 20px; }
.fw-amber b { color: #b45309; }
.fw-green b { color: var(--success, #16a34a); }
.fw-red b { color: var(--danger, #dc2626); }
.fw-tabs { display: flex; gap: 8px; flex-wrap: wrap; }
.fw-tab {
  border: 1px solid var(--border); background: var(--surface); color: var(--text-2);
  border-radius: 10px; padding: 7px 14px; font-size: 12px; font-weight: 600; cursor: pointer;
}
.fw-tab.active { border-color: var(--primary, #7c3aed); color: var(--primary, #7c3aed); }
.fw-filters { display: flex; flex-wrap: wrap; gap: 8px; margin-bottom: 12px; }
.fw-filters .input, .fw-filters .select { flex: 1 1 150px; min-width: 130px; }
.fw-table-wrap { overflow-x: auto; }
.fw-table { width: 100%; border-collapse: collapse; font-size: 12px; }
.fw-table th {
  text-align: left; font-size: 11px; color: var(--text-3); font-weight: 600;
  padding: 8px 10px; border-bottom: 1px solid var(--border); white-space: nowrap;
}
.fw-table td { padding: 9px 10px; border-bottom: 1px solid var(--border); vertical-align: top; }
.fw-table tr:hover td { background: var(--bg); }
.nowrap { white-space: nowrap; }
.fw-badge {
  display: inline-block; padding: 2px 9px; border-radius: 999px; font-size: 10px;
  font-weight: 700; white-space: nowrap;
}
.st-submitted { background: #fef3c7; color: #92400e; }
.st-verified { background: #dcfce7; color: #166534; }
.st-rejected { background: #fee2e2; color: #991b1b; }
.fw-flag { font-size: 10px; }
.fw-empty { padding: 26px; text-align: center; color: var(--text-3); font-size: 12px; }
.fw-pager { display: flex; align-items: center; justify-content: space-between; gap: 8px; margin-top: 12px; font-size: 11px; color: var(--text-3); }
.fw-detail-grid { display: grid; gap: 10px; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); }
.fw-detail-grid span { display: block; font-size: 10px; color: var(--text-3); text-transform: uppercase; letter-spacing: .03em; }
.fw-detail-grid b { font-size: 13px; word-break: break-word; }
.fw-detail-grid small { display: block; font-size: 10px; color: #b45309; }
.fw-actions { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 12px; }
.fw-verify, .fw-edit, .fw-events { margin-top: 14px; padding-top: 12px; border-top: 1px solid var(--border); }
.fw-verify label { display: block; font-size: 11px; color: var(--text-3); margin-bottom: 5px; }
.fw-edit-grid { display: grid; gap: 8px; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); margin: 8px 0; }
.fw-event { font-size: 11px; padding: 6px 0; border-bottom: 1px dashed var(--border); }
.fw-event-warn b { color: #b45309; }
/* v2.94.0: verifikasi massal */
.fw-bulk { display: flex; flex-wrap: wrap; gap: 8px; align-items: center;
  padding: 10px; margin-bottom: 10px; border: 1px solid var(--border); border-radius: 8px; }
.fw-bulk-all { display: flex; align-items: center; gap: 6px; font-size: 12px; }
.fw-bulk-count { font-size: 12px; font-weight: 600; color: var(--text-2); }
.fw-bulk-note { flex: 1 1 240px; min-width: 200px; }
.fw-check { width: 28px; }
/* v2.95.0: counter per cabang */
.fw-branch-counters { margin-top: 18px; }
.fw-id-inputs { display: flex; gap: 6px; }
.fw-id-inputs .input { width: 110px; }
/* v2.93.0: peringatan antrean menua */
.fw-callout-warn { border-color: #f59e0b; background: rgba(245, 158, 11, .1); color: #92400e; }
.fw-stat-click { cursor: pointer; }
.fw-stat-click:hover { border-color: #dc2626; }
.fw-event span { color: var(--text-3); margin-left: 6px; }
.fw-hint { font-size: 10px; color: var(--text-3); }
.fw-sync { background: var(--bg); border: 1px solid var(--border); border-radius: 10px; padding: 12px; margin-bottom: 14px; font-size: 12px; }
.fw-sync-grid { display: flex; flex-wrap: wrap; gap: 10px; margin-top: 6px; font-size: 11px; color: var(--text-2); }
.fw-samples { margin-top: 8px; font-size: 11px; color: var(--text-3); display: grid; gap: 2px; }
.fw-note { margin-top: 10px; font-size: 11px; color: var(--text-3); }
.fw-link-cell { max-width: 420px; overflow-wrap: anywhere; }
.fw-link-cell code { font-size: 10px; }
/* v2.83.0: panel ID Fingerprint & ID BPF */
.fw-id-grid { display: grid; gap: 12px; grid-template-columns: repeat(auto-fit, minmax(260px, 1fr)); margin: 12px 0; }
.fw-id-box {
  border: 1px solid var(--border); border-radius: 12px; padding: 14px;
  display: grid; gap: 8px; align-content: start;
}
.fw-id-box b { font-size: 13px; }
.fw-id-meta { font-size: 11px; color: var(--text-2); display: grid; gap: 2px; }
.fw-id-label { display: block; font-size: 10px; color: var(--text-3); text-transform: uppercase; letter-spacing: .03em; margin-top: 4px; }
/* v2.84.0: QR statis */
.fw-qr { display: grid; justify-items: center; gap: 10px; }
.fw-qr img { width: 300px; max-width: 80vw; border: 1px solid var(--border); border-radius: 10px; padding: 8px; background: #fff; }
.fw-qr-url { font-size: 10px; overflow-wrap: anywhere; text-align: center; color: var(--text-2); }
</style>
