<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
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
const editFields = reactive({ nama: '', nik: '', pendidikan: '', no_hp: '', referrer_id: '' })

const adminRefs = ref([])
const adminUsers = ref([])
const newRef = reactive({ name: '', user_id: '' })
const syncInfo = ref(null)

// Form publik punya path sendiri (/first-work-form) supaya halaman ini tetap
// menampilkan data — bukan form — untuk semua role yang membukanya.
const formLink = `${window.location.origin}/app/first-work-form`
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
  } catch (e) {
    err.value = e.message || 'Gagal memuat data.'
  } finally {
    loading.value = false
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

async function downloadKtp(row) {
  err.value = ''
  try {
    const response = await fetch(`/api/first-work/${row.id}/ktp`)
    if (!response.ok) {
      const data = await response.json().catch(() => ({}))
      throw new Error(data.error || 'File KTP tidak tersedia')
    }
    const blob = await response.blob()
    const url = URL.createObjectURL(blob)
    const anchor = document.createElement('a')
    anchor.href = url
    anchor.download = `KTP_${row.registration_no}`
    anchor.click()
    URL.revokeObjectURL(url)
  } catch (e) {
    err.value = e.message
  }
}

async function copyFormLink() {
  try {
    await navigator.clipboard.writeText(formLink)
    msg.value = 'Link form publik disalin: ' + formLink
  } catch {
    msg.value = 'Link form publik: ' + formLink
  }
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
})
</script>

<template>
  <div class="fw-view">
    <PageHeader icon="📝" title="Absensi FirstWork" :subtitle="subtitle">
      <a v-if="canVerify" class="btn" :href="formLink" target="_blank" rel="noopener">↗ Buka Form Publik</a>
      <button v-if="canVerify" class="btn" @click="copyFormLink">🔗 Salin Link</button>
      <a class="btn" :href="exportUrl" target="_blank" rel="noopener">⬇️ Ekspor CSV</a>
      <button v-if="isAdmin" class="btn" :disabled="busy" @click="runSync(true)">🧪 Cek Sync</button>
      <button v-if="isAdmin" class="btn btn-primary" :disabled="busy" @click="runSync(false)">🔄 Sync Sheet</button>
    </PageHeader>

    <div v-if="err" class="alert alert-error">{{ err }}</div>
    <div v-if="msg" class="alert alert-success">{{ msg }}</div>

    <div class="fw-stats">
      <div class="fw-stat"><span>Total</span><b>{{ stats.total || 0 }}</b></div>
      <div class="fw-stat fw-amber"><span>Menunggu</span><b>{{ stats.submitted || 0 }}</b></div>
      <div class="fw-stat fw-green"><span>Terverifikasi</span><b>{{ stats.verified || 0 }}</b></div>
      <div class="fw-stat fw-red"><span>Ditolak</span><b>{{ stats.rejected || 0 }}</b></div>
      <div class="fw-stat"><span>Hari Ini</span><b>{{ stats.today || 0 }}</b></div>
      <div class="fw-stat fw-amber"><span>Referensi Baru</span><b>{{ stats.needs_review || 0 }}</b></div>
    </div>

    <div class="fw-tabs">
      <button class="fw-tab" :class="{ active: tab === 'data' }" @click="tab = 'data'">Data Pengisian</button>
      <button v-if="isAdmin" class="fw-tab" :class="{ active: tab === 'admin' }" @click="openAdmin">Referensi &amp; Sync</button>
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

      <div v-if="loading" class="fw-empty">⏳ Memuat data…</div>
      <div v-else-if="!rows.length" class="fw-empty">
        <p style="margin:0 0 6px;">Tidak ada pengisian untuk filter ini.</p>
        <a v-if="canVerify" class="btn btn-sm" :href="formLink" target="_blank" rel="noopener">↗ Buka form publik</a>
        <p v-else style="margin:0;">Data cabang Anda akan muncul di sini setelah pendaftar mengisi form.</p>
      </div>
      <div v-else class="fw-table-wrap">
        <table class="fw-table">
          <thead>
            <tr>
              <th>Pendaftar</th>
              <th>Pendidikan</th>
              <th>Referensi</th>
              <th>Waktu Kirim</th>
              <th>Status</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="row in rows" :key="row.id">
              <td>
                <b>{{ row.nama }}</b>
                <div class="fw-sub">
                  <code>{{ row.registration_no }}</code> · NIK {{ maskNik(row.nik) }} · {{ row.no_hp || '—' }}
                </div>
              </td>
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

      <h3 style="margin-top:0;">Master Referensi</h3>
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
        <div v-for="(e, index) in events" :key="index" class="fw-event">
          <b>{{ e.event }}</b> · {{ e.status_to || '-' }} · {{ e.actor || 'sistem' }}
          <span>{{ fmtDT(e.created_at) }}</span>
          <div v-if="e.note" class="fw-hint">{{ e.note }}</div>
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
.fw-event span { color: var(--text-3); margin-left: 6px; }
.fw-hint { font-size: 10px; color: var(--text-3); }
.fw-sync { background: var(--bg); border: 1px solid var(--border); border-radius: 10px; padding: 12px; margin-bottom: 14px; font-size: 12px; }
.fw-sync-grid { display: flex; flex-wrap: wrap; gap: 10px; margin-top: 6px; font-size: 11px; color: var(--text-2); }
.fw-samples { margin-top: 8px; font-size: 11px; color: var(--text-3); display: grid; gap: 2px; }
.fw-note { margin-top: 10px; font-size: 11px; color: var(--text-3); }
</style>
