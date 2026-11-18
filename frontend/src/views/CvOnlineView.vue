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
const isViewer = computed(() => auth.role === 'ga_hr')
const branchName = computed(() => auth.user?.branch_name || auth.user?.branch_code || '')

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
const userOptions = ref([])
const filters = reactive({ status: '', q: '', user_ef: '', branch: '', date_from: '', date_to: '' })

const detail = ref(null)
const showDetail = ref(false)
const reviewNote = ref('')
const confirmDelete = ref('')

const branchForms = ref([])
const showForms = ref(false)
// Admin Pusat tidak punya satu cabang sesi (scope_branch = null), jadi tautan
// mengikuti filter cabang yang sedang dipilih. Tanpa pilihan, tautan kosong —
// UI menampilkan petunjuk "pilih cabang", bukan pesan "muat ulang halaman".
const activeBranchCode = computed(() => scopeBranch.value || filters.branch || '')
const formLink = computed(() => {
  const code = activeBranchCode.value
  if (!code) return ''
  const entry = branchForms.value.find((b) => b.branch_code === code)
  return entry?.form_path ? window.location.origin + entry.form_path : ''
})

const subtitle = computed(() => {
  const scope = scopeBranch.value
    ? `Data pelamar — ${branchName.value || 'cabang ' + scopeBranch.value}`
    : (filters.branch
        ? `Data pelamar — cabang ${filters.branch}`
        : 'Data pelamar — semua cabang')
  return canVerify.value ? scope : `${scope} · hanya lihat`
})

const statusChips = computed(() => [
  { value: '', label: 'Semua', count: stats.value.total || 0 },
  { value: 'submitted', label: '🕒 Menunggu', count: stats.value.submitted || 0 },
  { value: 'verified', label: '✅ Terverifikasi', count: stats.value.verified || 0 },
  { value: 'rejected', label: '✕ Ditolak', count: stats.value.rejected || 0 },
])

const pages = computed(() => Math.max(1, Math.ceil(total.value / limit.value)))
const exportUrl = computed(() => {
  const query = new URLSearchParams()
  if (filters.status) query.set('status', filters.status)
  if (filters.q) query.set('q', filters.q)
  if (filters.user_ef) query.set('user_ef', filters.user_ef)
  if (filters.branch) query.set('branch', filters.branch)
  if (filters.date_from) query.set('date_from', filters.date_from)
  if (filters.date_to) query.set('date_to', filters.date_to)
  const suffix = query.toString()
  return '/api/cv-online/export' + (suffix ? '?' + suffix : '')
})

const EVENT_LABELS = {
  created: 'Form dikirim',
  consent: 'Persetujuan syarat & ketentuan',
  verify: 'Diverifikasi',
  reject: 'Ditolak',
  reopen: 'Verifikasi dibuka kembali',
}

function eventLabel(name) {
  return EVENT_LABELS[name] || name
}

function fmtDT(value) {
  if (!value) return '—'
  const text = String(value).replace('T', ' ')
  return text.slice(0, 16)
}

function waLink(hp) {
  const digits = String(hp || '').replace(/\D/g, '')
  if (!digits) return ''
  const intl = digits.startsWith('0') ? '62' + digits.slice(1) : digits
  return `https://wa.me/${intl}`
}

function pickStatus(value) {
  filters.status = value
  load(1)
}

async function load(target = 1) {
  loading.value = true
  err.value = ''
  try {
    const data = await api('/api/cv-online', {
      params: {
        page: target,
        limit: limit.value,
        status: filters.status,
        q: filters.q,
        user_ef: filters.user_ef,
        branch: filters.branch,
        date_from: filters.date_from,
        date_to: filters.date_to,
      },
    })
    rows.value = data.data || []
    stats.value = data.stats || {}
    total.value = data.total || 0
    page.value = data.page || target
    scopeBranch.value = data.scope_branch || null
  } catch (e) {
    err.value = e.message || 'Gagal memuat data registrasi CV.'
  } finally {
    loading.value = false
  }
}

function applyFilters() {
  load(1)
}

function resetFilters() {
  Object.assign(filters, { status: '', q: '', user_ef: '', branch: '', date_from: '', date_to: '' })
  load(1)
}

async function loadMeta() {
  try {
    const data = await api('/api/cv-online/meta')
    userOptions.value = data.options?.user || []
  } catch { /* filter opsional */ }
}

async function loadBranchForms() {
  try {
    const data = await api('/api/cv-online/branch-forms')
    branchForms.value = data.data || []
  } catch {
    branchForms.value = []
  }
}

async function copyLink(url, label = 'Link form publik') {
  if (!url) {
    err.value = activeBranchCode.value
      ? `Cabang ${activeBranchCode.value} belum punya tautan form ber-token.`
      : 'Pilih cabang dulu untuk menyalin tautan form.'
    return
  }
  try {
    await navigator.clipboard.writeText(url)
    msg.value = `${label} disalin: ${url}`
  } catch {
    msg.value = `${label}: ${url}`
  }
}

function branchUrl(entry) {
  return entry?.form_path ? window.location.origin + entry.form_path : ''
}

const qrModal = reactive({ show: false, label: '', url: '', dataUrl: '', file: '' })

async function showQr(url, label) {
  if (!url) { err.value = 'Link form belum tersedia — muat ulang halaman.'; return }
  Object.assign(qrModal, {
    show: true, label, url, dataUrl: '',
    file: 'qr-cv-online-' + label.toLowerCase().replace(/[^a-z0-9]+/g, '-') + '.png',
  })
  try {
    qrModal.dataUrl = await QRCode.toDataURL(url, { width: 420, margin: 2 })
  } catch (e) {
    err.value = 'Gagal membuat QR: ' + (e.message || e)
    qrModal.show = false
  }
}

function downloadQr() {
  if (!qrModal.dataUrl) return
  const link = document.createElement('a')
  link.href = qrModal.dataUrl
  link.download = qrModal.file
  link.click()
}

async function openDetail(row) {
  busy.value = true
  err.value = ''
  try {
    const data = await api(`/api/cv-online/${row.id}`)
    detail.value = data.data
    reviewNote.value = ''
    confirmDelete.value = ''
    showDetail.value = true
  } catch (e) {
    err.value = e.message || 'Gagal memuat detail.'
  } finally {
    busy.value = false
  }
}

function closeDetail() {
  showDetail.value = false
  detail.value = null
  reviewNote.value = ''
  confirmDelete.value = ''
}

async function doReview(action) {
  if (!detail.value) return
  if (action === 'reject' && reviewNote.value.trim().length < 3) {
    err.value = 'Catatan alasan penolakan wajib diisi.'
    return
  }
  busy.value = true
  err.value = ''
  try {
    await api(`/api/cv-online/${detail.value.id}/review`, {
      method: 'POST',
      body: { action, note: reviewNote.value.trim() },
    })
    msg.value = action === 'verify' ? 'Data diverifikasi.'
      : action === 'reject' ? 'Data ditolak.' : 'Verifikasi dibuka kembali.'
    await openDetail({ id: detail.value.id })
    await load(page.value)
  } catch (e) {
    err.value = e.message || 'Gagal memperbarui status.'
  } finally {
    busy.value = false
  }
}

async function doDelete() {
  if (!detail.value) return
  busy.value = true
  err.value = ''
  try {
    await api(`/api/cv-online/${detail.value.id}`, {
      method: 'DELETE',
      body: { confirm: confirmDelete.value.trim().toUpperCase() },
    })
    msg.value = 'Data dihapus.'
    closeDetail()
    await load(page.value)
  } catch (e) {
    err.value = e.message || 'Gagal menghapus data.'
  } finally {
    busy.value = false
  }
}

onMounted(() => {
  loadMeta()
  loadBranchForms()
  load(1)
})
</script>

<template>
  <div class="cv-view">
    <PageHeader icon="📄" title="Registrasi CV Online" :subtitle="subtitle">
      <a v-if="canVerify && formLink" class="btn" :href="formLink" target="_blank" rel="noopener">↗ Buka Form Publik</a>
      <button v-if="canVerify && formLink" class="btn" @click="copyLink(formLink)">🔗 Salin Link</button>
      <button v-if="canVerify && formLink" class="btn" @click="showQr(formLink, 'Form CV Online ' + activeBranchCode)">▦ QR</button>
      <span v-if="canVerify && !formLink" class="cv-hint">
        {{ activeBranchCode ? 'Cabang ' + activeBranchCode + ' belum punya token form.' : 'Pilih cabang untuk tautan form.' }}
      </span>
      <button class="btn" @click="showForms = !showForms">🔗 Link per Cabang</button>
      <a class="btn" :href="exportUrl" target="_blank" rel="noopener">⬇️ Ekspor CSV</a>
    </PageHeader>

    <div v-if="err" class="alert alert-error">{{ err }}</div>
    <div v-if="msg" class="alert alert-success">{{ msg }}</div>

    <div v-if="isViewer" class="cv-callout">
      Anda masuk sebagai GA/HR — data dapat dilihat dan diekspor. Verifikasi data
      dilakukan oleh Traineer atau Admin.
    </div>

    <div class="cv-stats">
      <div class="cv-stat"><span>Total</span><b>{{ stats.total || 0 }}</b></div>
      <div class="cv-stat cv-amber"><span>Menunggu</span><b>{{ stats.submitted || 0 }}</b></div>
      <div class="cv-stat cv-green"><span>Terverifikasi</span><b>{{ stats.verified || 0 }}</b></div>
      <div class="cv-stat cv-red"><span>Ditolak</span><b>{{ stats.rejected || 0 }}</b></div>
      <div class="cv-stat"><span>Hari Ini</span><b>{{ stats.today || 0 }}</b></div>
    </div>

    <div v-if="showForms" class="card card-pad">
      <h3 style="margin-top:0;">Link Form per Cabang</h3>
      <p class="cv-note" style="margin-top:0;">
        Setiap cabang punya tautan ber-token sendiri. Isian yang masuk lewat
        tautan cabang A tidak pernah tercatat atas nama cabang B.
      </p>
      <div class="cv-table-wrap">
        <table class="cv-table">
          <thead><tr><th>Cabang</th><th>Link</th><th></th></tr></thead>
          <tbody>
            <tr v-for="b in branchForms" :key="b.branch_code">
              <td><b>{{ b.branch_code }}</b><div class="cv-sub">{{ b.branch_name }}</div></td>
              <td class="cv-link-cell">
                <code v-if="b.form_path">{{ b.form_path }}</code>
                <span v-else class="cv-hint">Token belum tersedia — restart aplikasi.</span>
              </td>
              <td>
                <button class="btn btn-sm" :disabled="!b.form_path" @click="showQr(branchUrl(b), 'Form CV Online ' + b.branch_code)">▦ QR</button>
                <button class="btn btn-sm" :disabled="!b.form_path" @click="copyLink(branchUrl(b))">🔗 Salin</button>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

    <div class="card card-pad">
      <div class="cv-chips" role="tablist" aria-label="Filter status">
        <button v-for="c in statusChips" :key="c.value || 'all'" type="button" role="tab"
                class="cv-chip" :class="{ active: filters.status === c.value }"
                :aria-selected="filters.status === c.value"
                @click="pickStatus(c.value)">
          {{ c.label }} <b>{{ c.count }}</b>
        </button>
      </div>

      <form class="cv-filters" @submit.prevent="applyFilters">
        <input class="input" v-model="filters.q" placeholder="Cari nama, HP, pengundang, no. registrasi…" />
        <select class="select" v-model="filters.user_ef">
          <option value="">Semua user</option>
          <option v-for="u in userOptions" :key="u" :value="u">{{ u }}</option>
        </select>
        <select v-if="!scopeBranch" class="select" v-model="filters.branch" aria-label="Filter cabang">
          <option value="">Semua cabang</option>
          <option v-for="b in branchForms" :key="b.branch_code" :value="b.branch_code">{{ b.branch_code }} — {{ b.branch_name }}</option>
        </select>
        <input class="input" type="date" v-model="filters.date_from" aria-label="Dari tanggal" />
        <input class="input" type="date" v-model="filters.date_to" aria-label="Sampai tanggal" />
        <button class="btn btn-primary" type="submit">🔍 Terapkan</button>
        <button class="btn" type="button" @click="resetFilters">Reset</button>
      </form>

      <div v-if="loading" class="cv-empty">⏳ Memuat data…</div>
      <div v-else-if="!rows.length" class="cv-empty">
        <p style="margin:0 0 6px;">Belum ada registrasi CV untuk filter ini.</p>
        <a v-if="canVerify && formLink" class="btn btn-sm" :href="formLink" target="_blank" rel="noopener">↗ Buka form publik</a>
        <p v-else style="margin:0;">Data cabang Anda akan muncul di sini setelah pelamar mengisi form.</p>
      </div>
      <div v-else class="cv-table-wrap">
        <table class="cv-table">
          <thead>
            <tr>
              <th>Pelamar</th>
              <th>User</th>
              <th>Domisili</th>
              <th>No. HP</th>
              <th>Pendidikan</th>
              <th>Pengalaman</th>
              <th>Waktu Kirim</th>
              <th>Status</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="row in rows" :key="row.id">
              <td>
                <b>{{ row.nama }}</b>
                <div class="cv-sub">
                  <code>{{ row.registration_no }}</code>
                  <template v-if="row.tempat_lahir || row.tanggal_lahir">
                    · {{ row.tempat_lahir }}<template v-if="row.tanggal_lahir">, {{ row.tanggal_lahir }}</template>
                  </template>
                </div>
              </td>
              <td class="nowrap">{{ row.user_ef || '—' }}</td>
              <td>{{ row.domisili || '—' }}</td>
              <td class="nowrap">{{ row.no_hp_norm || row.no_hp || '—' }}</td>
              <td>{{ row.pendidikan_terakhir || '—' }}</td>
              <td>{{ row.pengalaman_status === 'sudah' ? (row.pengalaman_lama || 'Sudah') : (row.pengalaman_status === 'belum' ? 'Fresh graduate' : '—') }}</td>
              <td class="nowrap">{{ fmtDT(row.submitted_at) }}</td>
              <td><span class="cv-badge" :class="'st-' + row.status">{{ row.status === 'submitted' ? '🕒 Menunggu' : row.status === 'verified' ? '✅ Terverifikasi' : '✕ Ditolak' }}</span></td>
              <td><button class="btn btn-sm" @click="openDetail(row)">Detail</button></td>
            </tr>
          </tbody>
        </table>
      </div>

      <div v-if="pages > 1" class="cv-pager">
        <button class="btn btn-sm" :disabled="page <= 1" @click="load(page - 1)">‹ Sebelumnya</button>
        <span>Halaman {{ page }} / {{ pages }} · {{ total }} data</span>
        <button class="btn btn-sm" :disabled="page >= pages" @click="load(page + 1)">Berikutnya ›</button>
      </div>
    </div>

    <Modal v-if="showDetail && detail" :title="`Detail ${detail.registration_no}`" wide @close="closeDetail">
      <div class="cv-detail-grid">
        <div><span>Nama</span><b>{{ detail.nama }}</b></div>
        <div><span>Tempat / Tanggal Lahir</span><b>{{ detail.tempat_lahir || '—' }}<template v-if="detail.tanggal_lahir">, {{ detail.tanggal_lahir }}</template></b></div>
        <div><span>Jenis Kelamin</span><b>{{ detail.jenis_kelamin || '—' }}</b></div>
        <div><span>Domisili</span><b>{{ detail.domisili || '—' }}</b></div>
        <div><span>No. HP</span><b>{{ detail.no_hp || '—' }}</b>
          <a v-if="waLink(detail.no_hp)" :href="waLink(detail.no_hp)" target="_blank" rel="noopener" class="cv-wa">💬 WhatsApp</a>
        </div>
        <div><span>Status</span><b>{{ detail.status === 'submitted' ? '🕒 Menunggu' : detail.status === 'verified' ? '✅ Terverifikasi' : '✕ Ditolak' }}</b></div>
        <div class="cv-span"><span>Alamat</span><b>{{ detail.alamat || '—' }}</b></div>
        <div class="cv-span"><span>Sumber Informasi</span><b>{{ detail.sumber_informasi || '—' }}</b></div>
        <div><span>Diundang Oleh</span><b>{{ detail.diundang_oleh || '—' }}</b></div>
        <div><span>User</span><b>{{ detail.user_ef || '—' }}</b></div>
        <div class="cv-span"><span>Kontak Serumah</span><b class="cv-pre">{{ detail.kontak_serumah || '—' }}</b></div>
        <div class="cv-span"><span>Kontak Tidak Serumah</span><b class="cv-pre">{{ detail.kontak_tidak_serumah || '—' }}</b></div>
        <div><span>Pendidikan Terakhir</span><b>{{ detail.pendidikan_terakhir || '—' }}</b></div>
        <div><span>Sekolah Menengah</span><b>{{ detail.sekolah_menengah || '—' }}</b></div>
        <div><span>Perguruan Tinggi</span><b>{{ detail.perguruan_tinggi || '—' }}</b></div>
        <div><span>Pengalaman Bekerja</span><b>{{ detail.pengalaman_status === 'sudah' ? 'Sudah memiliki pengalaman' : detail.pengalaman_status === 'belum' ? 'Fresh graduate' : '—' }}</b></div>
        <div><span>Lama Pengalaman</span><b>{{ detail.pengalaman_lama || '—' }}</b></div>
        <div><span>Posisi Terakhir</span><b>{{ detail.posisi_terakhir || '—' }}</b></div>
        <div class="cv-span"><span>Pengalaman Kerja 1</span><b class="cv-pre">{{ detail.pengalaman_1 || '—' }}</b></div>
        <div class="cv-span"><span>Pengalaman Kerja 2</span><b class="cv-pre">{{ detail.pengalaman_2 || '—' }}</b></div>
        <div class="cv-span"><span>Catatan Verifikasi</span><b>{{ detail.review_note || '—' }}</b></div>
      </div>

      <template v-if="canVerify">
        <h4 class="cv-section">Verifikasi Data</h4>
        <textarea class="input" rows="2" v-model="reviewNote" maxlength="500"
                  placeholder="Catatan (wajib bila menolak)" />
        <div class="cv-actions">
          <button v-if="detail.status !== 'verified'" class="btn btn-primary" :disabled="busy"
                  @click="doReview('verify')">✅ Verifikasi</button>
          <button v-if="detail.status !== 'rejected'" class="btn" :disabled="busy"
                  @click="doReview('reject')">✕ Tolak</button>
          <button v-if="detail.status !== 'submitted'" class="btn" :disabled="busy"
                  @click="doReview('reopen')">↩️ Buka Ulang</button>
        </div>

        <div class="cv-danger">
          <b>Hapus data uji</b>
          <p>Ketik <code>HAPUS</code> untuk menghapus permanen. Data terverifikasi
            hanya dapat dihapus Admin Pusat.</p>
          <div class="cv-actions">
            <input class="input" v-model="confirmDelete" placeholder="HAPUS" style="max-width:140px;" />
            <button class="btn cv-btn-danger" :disabled="busy || confirmDelete.trim().toUpperCase() !== 'HAPUS'"
                    @click="doDelete">🗑️ Hapus</button>
          </div>
        </div>
      </template>

      <h4 class="cv-section">Riwayat</h4>
      <ul class="cv-events">
        <li v-for="(e, i) in detail.events" :key="i">
          <b>{{ eventLabel(e.event) }}</b>
          <span class="cv-sub">{{ fmtDT(e.created_at) }} · {{ e.actor || '—' }} {{ e.actor_role ? '(' + e.actor_role + ')' : '' }}</span>
          <div v-if="e.note" class="cv-note" style="text-align:left;">{{ e.note }}</div>
        </li>
        <li v-if="!detail.events || !detail.events.length" class="cv-sub">Belum ada riwayat.</li>
      </ul>
    </Modal>

    <Modal v-if="qrModal.show" :title="qrModal.label" @close="qrModal.show = false">
      <div class="cv-qr">
        <img v-if="qrModal.dataUrl" :src="qrModal.dataUrl" :alt="qrModal.label" />
        <code class="cv-qr-url">{{ qrModal.url }}</code>
        <div class="cv-actions" style="justify-content:center;">
          <button class="btn" :disabled="!qrModal.dataUrl" @click="downloadQr">⬇️ Unduh PNG</button>
          <button class="btn" @click="copyLink(qrModal.url)">🔗 Salin Link</button>
        </div>
      </div>
    </Modal>
  </div>
</template>

<style scoped>
.cv-view { display: grid; gap: 14px; }
.cv-callout {
  background: rgba(37, 99, 235, .07); border: 1px solid rgba(37, 99, 235, .3);
  border-radius: 10px; padding: 10px 12px; font-size: 12px; line-height: 1.5;
}
.cv-stats { display: grid; grid-template-columns: repeat(auto-fit, minmax(110px, 1fr)); gap: 8px; }
.cv-stat {
  background: var(--surface); border: 1px solid var(--border); border-radius: 12px;
  padding: 10px 12px;
}
.cv-stat span { display: block; font-size: 10px; color: var(--text-3); text-transform: uppercase; letter-spacing: .04em; }
.cv-stat b { font-size: 20px; }
.cv-amber b { color: #b45309; }
.cv-green b { color: #166534; }
.cv-red b { color: #b91c1c; }
.cv-chips { display: flex; flex-wrap: wrap; gap: 6px; margin-bottom: 12px; }
.cv-chip {
  border: 1px solid var(--border); background: var(--bg); border-radius: 99px;
  padding: 5px 10px; font-size: 11px; cursor: pointer; color: var(--text-2);
}
.cv-chip b { font-size: 10px; opacity: .8; }
.cv-chip.active { border-color: var(--primary, #7c3aed); color: var(--text); font-weight: 700; }
.cv-filters { display: flex; flex-wrap: wrap; gap: 8px; margin-bottom: 12px; }
.cv-filters .input, .cv-filters .select { flex: 1; min-width: 140px; }
.cv-table-wrap { overflow-x: auto; }
.cv-table { width: 100%; border-collapse: collapse; font-size: 12px; }
.cv-table th, .cv-table td { padding: 8px 10px; border-bottom: 1px solid var(--border); text-align: left; vertical-align: top; }
.cv-table th { font-size: 10px; text-transform: uppercase; letter-spacing: .04em; color: var(--text-3); }
.cv-table tbody tr:hover { background: var(--bg); }
.cv-sub { font-size: 10.5px; color: var(--text-3); margin-top: 2px; }
.cv-hint { font-size: 10.5px; color: var(--text-3); }
.cv-link-cell code { font-size: 10.5px; word-break: break-all; }
.nowrap { white-space: nowrap; }
.cv-badge {
  display: inline-block; padding: 2px 8px; border-radius: 99px; font-size: 10px;
  font-weight: 700; white-space: nowrap; border: 1px solid var(--border);
}
.cv-badge.st-submitted { background: rgba(245, 158, 11, .12); color: #92400e; border-color: rgba(245, 158, 11, .4); }
.cv-badge.st-verified { background: rgba(22, 163, 74, .12); color: #166534; border-color: rgba(22, 163, 74, .4); }
.cv-badge.st-rejected { background: rgba(220, 38, 38, .1); color: #b91c1c; border-color: rgba(220, 38, 38, .35); }
.cv-empty { text-align: center; padding: 22px 10px; font-size: 12px; color: var(--text-3); }
.cv-pager { display: flex; align-items: center; justify-content: space-between; gap: 8px; margin-top: 12px; font-size: 11px; color: var(--text-3); }
.cv-detail-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 10px 16px; margin-bottom: 12px; }
.cv-detail-grid span { display: block; font-size: 10px; color: var(--text-3); text-transform: uppercase; letter-spacing: .03em; }
.cv-detail-grid b { font-size: 12.5px; word-break: break-word; }
.cv-detail-grid .cv-span { grid-column: 1 / -1; }
.cv-pre { white-space: pre-wrap; font-weight: 500; }
.cv-wa { display: inline-block; margin-top: 2px; font-size: 11px; color: #166534; }
.cv-section {
  margin: 14px 0 8px; font-size: 11px; text-transform: uppercase;
  letter-spacing: .05em; color: var(--text-3); border-top: 1px solid var(--border); padding-top: 12px;
}
.cv-actions { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 8px; }
.cv-danger {
  margin-top: 14px; border: 1px solid rgba(220, 38, 38, .35); border-radius: 10px;
  padding: 10px 12px; background: rgba(220, 38, 38, .04);
}
.cv-danger b { font-size: 12px; }
.cv-danger p { margin: 4px 0 0; font-size: 11px; color: var(--text-3); line-height: 1.5; }
.cv-btn-danger { border-color: rgba(220, 38, 38, .5); color: #b91c1c; }
.cv-events { list-style: none; margin: 0; padding: 0; display: grid; gap: 8px; }
.cv-events li { border-left: 3px solid var(--border); padding-left: 10px; }
.cv-events b { font-size: 12px; }
.cv-note { font-size: 11px; color: var(--text-3); }
.cv-qr { display: grid; gap: 10px; justify-items: center; text-align: center; }
.cv-qr img { width: 260px; max-width: 100%; border: 1px solid var(--border); border-radius: 10px; }
.cv-qr-url { font-size: 10px; word-break: break-all; }
@media (max-width: 640px) {
  .cv-detail-grid { grid-template-columns: 1fr; }
}
</style>
