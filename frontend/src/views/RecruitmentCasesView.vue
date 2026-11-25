<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { api } from '../api'
import { useAuthStore } from '../stores/auth'
import PageHeader from '../components/PageHeader.vue'

// Saat dipakai sebagai tab hub, header induk disembunyikan (prop embedded).
defineProps({ embedded: { type: Boolean, default: false } })

// Rilis A (Task 6): dashboard kasus rekrutmen untuk staff. Satu kasus per NIK,
// empat langkah (CV/TRAINING/TKD/FIRSTWORK) dan riwayat perpindahan cabang.
// NIK tidak pernah dikirim/diterima dalam bentuk penuh — API hanya mengirim
// nik_masked, dan kolom teks dipakai untuk mencari nama/NIK bila diperlukan.
const auth = useAuthStore()
const STAFF_ROLES = ['traineer', 'ga_hr', 'admin']
const STEP_TYPES = ['CV', 'TRAINING', 'TKD', 'FIRSTWORK']
const EXCEPTION_ALLOWED = ['BELUM', 'PENDING']
// Rilis B (Task 6): bukti manual hanya untuk langkah yang datanya tidak
// berasal dari modul nyata. CV/FIRSTWORK diisi submit CV Online/FirstWork.
const EVIDENCE_STEP_TYPES = ['TRAINING', 'TKD']
const EMPTY_EVIDENCE = {
  open: false, date: '', note: '', file_url: '', score: '', saving: false,
}

const isStaff = computed(() => STAFF_ROLES.includes(auth.role))
const subtitle = computed(() => isStaff.value
  ? 'Daftar kasus, langkah, dan riwayat cabang'
  : 'Daftar kasus, langkah, dan riwayat cabang · hanya lihat')

const loading = ref(true)
const busy = ref(false)
const err = ref('')
const msg = ref('')
const rows = ref([])
const expanded = ref('')
const filters = reactive({ q: '', branch_code: '', status: '' })
// Form bukti per langkah: kunci `s<id>` untuk langkah ada, `m<caseId>|<type>`
// untuk langkah yang belum ada (dibuat malas saat POST pertama).
const evidenceForms = reactive({})
function evidenceKey(caseId, step) {
  return step.id ? `s${step.id}` : `m${caseId}|${step.step_type}`
}
function formFor(key) {
  return evidenceForms[key] || EMPTY_EVIDENCE
}
function toggleEvidence(key) {
  if (!evidenceForms[key]) evidenceForms[key] = { ...EMPTY_EVIDENCE }
  evidenceForms[key].open = !evidenceForms[key].open
}

const branchOptions = computed(() => {
  const codes = new Set()
  rows.value.forEach((row) => {
    if (row.first_branch) codes.add(row.first_branch)
    ;(row.branches || []).forEach((b) => { if (b.branch_code) codes.add(b.branch_code) })
  })
  if (auth.user?.branch_code) codes.add(auth.user.branch_code)
  return [...codes].sort()
})

const statusOptions = computed(() => {
  const values = new Set(['AKTIF', 'NONAKTIF'])
  rows.value.forEach((row) => { if (row.status) values.add(row.status) })
  return [...values].sort()
})

// NIK penuh (16 digit) dicari di server; teks lain (nama / 4 digit terakhir)
// difilter lokal dari hasil API yang sudah termasker.
const nikQuery = computed(() => filters.q.replace(/[\s-]/g, ''))
const visibleRows = computed(() => {
  const q = filters.q.trim()
  if (!q || /^\d{16}$/.test(nikQuery.value)) return rows.value
  const needle = q.toLowerCase()
  return rows.value.filter((row) =>
    String(row.nama || '').toLowerCase().includes(needle)
    || String(row.nik_masked || '').includes(q))
})

function fmtDT(value) {
  if (!value) return '-'
  const dt = new Date(String(value).replace(' ', 'T'))
  if (Number.isNaN(dt.getTime())) return String(value)
  return dt.toLocaleString('id-ID', {
    day: '2-digit', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit',
  })
}

function statusBadge(status) {
  const s = String(status || '').toUpperCase()
  if (['SELESAI', 'AKTIF', 'VERIFIED'].includes(s)) return 'st-verified'
  if (['DIKECUALIKAN', 'NONAKTIF', 'REJECTED'].includes(s)) return 'st-rejected'
  return 'st-submitted'
}

function stepsFor(row, type) {
  return (row.steps || []).filter((s) => s.step_type === type)
}

// Langkah TRAINING/TKD yang belum ada tetap dapat diisi bukti: tampilkan
// kartu "Bukti baru" dengan step_id=0 (dibuat malas oleh backend saat POST).
function evidenceTargets(row, type) {
  const steps = stepsFor(row, type)
  if (steps.length) return steps
  if (!EVIDENCE_STEP_TYPES.includes(type)) return []
  return [{ id: 0, step_type: type, status: 'BELUM', branch_code: '',
            exception_reason: null, completed_at: null }]
}

// Riwayat cabang diurutkan API dari terbaru; tetap hitung sendiri agar aman
// bila urutan berubah. "Asal" = first_branch, "Saat ini" = kunjungan terakhir.
function currentBranch(row) {
  const branches = row.branches || []
  if (!branches.length) return row.first_branch || '—'
  const latest = branches.reduce((best, b) => {
    const time = (b) => b.last_seen_at || b.first_seen_at || ''
    return time(b) > time(best) ? b : best
  }, branches[0])
  return latest.branch_code || row.first_branch || '—'
}

function toggleDetail(caseId) {
  expanded.value = expanded.value === caseId ? '' : caseId
}

function canException(step) {
  return isStaff.value && EXCEPTION_ALLOWED.includes(step.status)
}

function canEvidence(step) {
  return isStaff.value && EVIDENCE_STEP_TYPES.includes(step.step_type)
    && step.status !== 'DIKECUALIKAN'
}

async function load() {
  loading.value = true
  err.value = ''
  try {
    const params = {}
    if (filters.branch_code) params.branch_code = filters.branch_code
    if (filters.status) params.status = filters.status
    if (/^\d{16}$/.test(nikQuery.value)) params.nik = filters.q.trim()
    const data = await api('/api/recruitment/cases', { params })
    rows.value = data?.data || []
    if (expanded.value && !rows.value.some((r) => r.case_id === expanded.value)) {
      expanded.value = ''
    }
  } catch (e) {
    err.value = e.message || 'Gagal memuat kasus.'
  } finally {
    loading.value = false
  }
}

function applyFilters() {
  load()
}

function resetFilters() {
  Object.assign(filters, { q: '', branch_code: '', status: '' })
  load()
}

async function markException(step) {
  if (!canException(step) || busy.value) return
  const answer = window.prompt(
    `Alasan pengecualian langkah ${step.step_type} (wajib, maks. 500 karakter):`)
  if (answer === null) return
  const reason = String(answer).trim()
  if (!reason) { err.value = 'Alasan wajib diisi.'; return }
  if (reason.length > 500) { err.value = 'Alasan maksimal 500 karakter.'; return }
  if (!step.id) { err.value = 'Langkah tidak punya ID. Muat ulang halaman.'; return }

  busy.value = true
  err.value = ''
  msg.value = ''
  try {
    await api(`/api/recruitment/steps/${step.id}/exception`, {
      method: 'POST',
      body: { reason },
    })
    msg.value = 'Langkah dikecualikan.'
    await load()
  } catch (e) {
    err.value = e.message || 'Gagal mengecualikan langkah.'
  } finally {
    busy.value = false
  }
}

async function submitEvidence(row, step) {
  const key = evidenceKey(row.case_id, step)
  const form = evidenceForms[key]
  if (!form || form.saving || !canEvidence(step)) return

  const date = String(form.date || '').trim()
  const note = String(form.note || '').trim()
  if (!date) { err.value = 'Tanggal bukti wajib diisi.'; return }
  if (!note) { err.value = 'Catatan bukti wajib diisi.'; return }

  const body = { date, note }
  const fileUrl = String(form.file_url || '').trim()
  const score = String(form.score || '').trim()
  if (fileUrl) body.file_url = fileUrl
  if (score) body.score = score
  // Langkah belum ada: kirim step_id=0 agar backend membuatnya lebih dulu.
  if (!step.id) {
    body.case_id = row.case_id
    body.step_type = step.step_type
  }

  form.saving = true
  err.value = ''
  msg.value = ''
  try {
    await api(`/api/recruitment/steps/${step.id || 0}/evidence`, {
      method: 'POST',
      body,
    })
    msg.value = 'Bukti berhasil disimpan.'
    form.open = false
    await load()
  } catch (e) {
    err.value = e.message || 'Gagal menyimpan bukti.'
  } finally {
    form.saving = false
  }
}

onMounted(load)
</script>

<template>
  <div class="fw-view">
    <PageHeader v-if="!embedded" icon="🗂️" title="Dashboard Kasus Rekrutmen" :subtitle="subtitle" />

    <div v-if="err" class="alert alert-error">{{ err }}</div>
    <div v-if="msg" class="alert alert-success">{{ msg }}</div>

    <div class="card card-pad">
      <form class="fw-filters" @submit.prevent="applyFilters">
        <input class="input" v-model="filters.q" aria-label="Cari NIK atau nama"
               placeholder="Cari nama, NIK, atau 4 digit terakhir…" />
        <select class="select" v-model="filters.branch_code" aria-label="Filter cabang">
          <option value="">Semua cabang</option>
          <option v-for="code in branchOptions" :key="code" :value="code">{{ code }}</option>
        </select>
        <select class="select" v-model="filters.status" aria-label="Filter status">
          <option value="">Semua status</option>
          <option v-for="status in statusOptions" :key="status" :value="status">{{ status }}</option>
        </select>
        <button class="btn btn-primary" type="submit">🔍 Terapkan</button>
        <button class="btn" type="button" @click="resetFilters">Reset</button>
      </form>

      <div v-if="loading" class="fw-empty">⏳ Memuat kasus…</div>
      <div v-else-if="!visibleRows.length" class="fw-empty">
        Tidak ada kasus untuk filter ini.
      </div>
      <div v-else class="fw-table-wrap">
        <table class="fw-table">
          <thead>
            <tr>
              <th>Case ID</th>
              <th>NIK</th>
              <th>Nama</th>
              <th>Cabang Asal</th>
              <th>Status</th>
              <th></th>
            </tr>
          </thead>
          <tbody v-for="row in visibleRows" :key="row.case_id">
            <tr>
              <td><code>{{ row.case_id }}</code></td>
              <td class="nowrap">{{ row.nik_masked }}</td>
              <td><b>{{ row.nama }}</b></td>
              <td class="nowrap">{{ row.first_branch || '—' }}</td>
              <td><span class="fw-badge" :class="statusBadge(row.status)">{{ row.status }}</span></td>
              <td>
                <button class="btn btn-sm" :aria-expanded="expanded === row.case_id"
                        @click="toggleDetail(row.case_id)">
                  {{ expanded === row.case_id ? 'Tutup detail' : 'Detail' }}
                </button>
              </td>
            </tr>
            <tr v-if="expanded === row.case_id" class="rc-detail-row">
              <td colspan="6">
                <div class="rc-detail">
                  <div class="rc-branch-summary">
                    Cabang asal: <b>{{ row.first_branch || '—' }}</b>
                    <span class="rc-sep">·</span>
                    Cabang saat ini: <b>{{ currentBranch(row) }}</b>
                  </div>

                  <div class="rc-step-grid">
                    <div v-for="type in STEP_TYPES" :key="type" class="rc-step-col"
                         :data-step-type="type">
                      <h4>{{ type }}</h4>
                      <p v-if="!stepsFor(row, type).length" class="fw-hint">Belum ada data</p>
                      <div v-for="step in evidenceTargets(row, type)"
                           :key="evidenceKey(row.case_id, step)" class="rc-step">
                        <template v-if="step.id">
                          <span class="fw-badge" :class="statusBadge(step.status)">{{ step.status }}</span>
                          <div class="fw-sub">Cabang: {{ step.branch_code || '—' }}</div>
                          <div class="fw-sub">Selesai: {{ fmtDT(step.completed_at) }}</div>
                          <div v-if="step.exception_reason" class="rc-reason">
                            Alasan: {{ step.exception_reason }}
                          </div>
                          <button v-if="canException(step)" class="btn btn-sm"
                                  :data-step-type="type" :disabled="busy"
                                  @click="markException(step)">Kecualikan</button>
                        </template>
                        <div v-else class="fw-sub">Bukti baru · cabang diambil otomatis</div>
                        <button v-if="canEvidence(step)" class="btn btn-sm"
                                :data-evidence-step="evidenceKey(row.case_id, step)"
                                :disabled="formFor(evidenceKey(row.case_id, step)).saving"
                                @click="toggleEvidence(evidenceKey(row.case_id, step))">
                          {{ formFor(evidenceKey(row.case_id, step)).open ? 'Tutup bukti' : 'Isi bukti' }}
                        </button>
                        <div v-if="canEvidence(step) && formFor(evidenceKey(row.case_id, step)).open"
                             class="rc-evidence-form"
                             :data-evidence-form="evidenceKey(row.case_id, step)">
                          <label class="rc-field">Tanggal
                            <input class="input" type="date"
                                   v-model="formFor(evidenceKey(row.case_id, step)).date" />
                          </label>
                          <label class="rc-field">Catatan
                            <textarea class="input" rows="2"
                                      v-model="formFor(evidenceKey(row.case_id, step)).note"></textarea>
                          </label>
                          <label class="rc-field">URL berkas (opsional)
                            <input class="input" data-field="file_url"
                                   v-model="formFor(evidenceKey(row.case_id, step)).file_url" />
                          </label>
                          <label class="rc-field">Nilai (opsional)
                            <input class="input" data-field="score"
                                   v-model="formFor(evidenceKey(row.case_id, step)).score" />
                          </label>
                          <button class="btn btn-sm btn-primary" data-save-evidence
                                  :disabled="formFor(evidenceKey(row.case_id, step)).saving"
                                  @click="submitEvidence(row, step)">Simpan bukti</button>
                        </div>
                      </div>
                    </div>
                  </div>

                  <div class="rc-history">
                    <h4>Riwayat cabang</h4>
                    <p v-if="!(row.branches || []).length" class="fw-hint">Belum ada riwayat.</p>
                    <div v-for="b in row.branches || []" :key="b.branch_code + '-' + b.first_seen_at"
                         class="rc-history-item">
                      <b>{{ b.branch_code }}</b>
                      <span v-if="b.branch_code === row.first_branch" class="rc-tag">Asal</span>
                      <span v-if="b.branch_code === currentBranch(row)" class="rc-tag rc-tag-current">Saat ini</span>
                      <span class="fw-sub">
                        {{ fmtDT(b.first_seen_at) }} → {{ fmtDT(b.last_seen_at) }}
                      </span>
                    </div>
                  </div>
                </div>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  </div>
</template>

<style scoped>
.rc-detail-row > td { background: var(--bg); }
.rc-detail { display: grid; gap: 14px; padding: 4px 0 8px; }
.rc-branch-summary { font-size: 12px; color: var(--text-2); }
.rc-sep { margin: 0 6px; color: var(--text-3); }
.rc-step-grid {
  display: grid; gap: 10px;
  grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
}
.rc-step-col {
  border: 1px solid var(--border); border-radius: 10px; padding: 10px;
  background: var(--surface);
}
.rc-step-col h4, .rc-history h4 {
  margin: 0 0 8px; font-size: 11px; letter-spacing: .04em; color: var(--text-2);
}
.rc-step { padding: 6px 0; border-top: 1px dashed var(--border); }
.rc-step .btn { margin-top: 8px; }
.rc-reason { margin-top: 4px; font-size: 10px; color: #b45309; }
.rc-evidence-form {
  display: grid; gap: 6px; margin-top: 8px; padding: 8px;
  border: 1px solid var(--border); border-radius: 8px; background: var(--bg);
}
.rc-field { display: grid; gap: 3px; font-size: 10px; color: var(--text-2); }
.rc-field .input { width: 100%; font-size: 11px; padding: 4px 6px; }
.rc-evidence-form .btn { margin-top: 0; }
.rc-history-item {
  display: flex; flex-wrap: wrap; align-items: center; gap: 6px;
  padding: 5px 0; border-bottom: 1px dashed var(--border); font-size: 12px;
}
.rc-history-item .fw-sub { margin: 0; }
.rc-tag {
  font-size: 9px; font-weight: 700; padding: 1px 6px; border-radius: 999px;
  background: var(--surface-2, #f5f3ff); color: var(--primary, #7c3aed);
}
.rc-tag-current { background: #dcfce7; color: #166534; }
</style>
