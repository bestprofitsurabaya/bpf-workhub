<script setup>
/**
 * Hasil & koreksi skor TKD — panel staff.
 *
 * Kunci jawaban sengaja ditampilkan hanya di modal detail staff. Komponen
 * pelamar (components/RecruitmentTkdPanel.vue) tidak pernah menerima kunci.
 * NIK penuh tidak pernah dirender: daftar/review memakai `nik_masked`, dan
 * input NIK dipakai untuk query lalu langsung dikosongkan.
 */
import { computed, onMounted, reactive, ref } from 'vue'
import { api } from '../api'
import { useAuthStore } from '../stores/auth'
import Modal from '../components/Modal.vue'

const STATUSES = ['BERLANGSUNG', 'SELESAI', 'KEDALUWARSA']
const FULL_NIK_RE = /\d{16}/g

const auth = useAuthStore()
const isAdmin = computed(() => auth?.role === 'admin')
const ownBranch = String(auth?.user?.branch_code || '').toUpperCase()

function defaultFilters() {
  return { branch: ownBranch, status: '', from: '', to: '', q: '' }
}

const filters = reactive(defaultFilters())
const applied = reactive(defaultFilters())
const rows = ref([])
const loading = ref(true)
const err = ref('')
const msg = ref('')

const detailOpen = ref(false)
const detail = ref(null)
const detailLoading = ref(false)
const detailErr = ref('')

const scoreOpen = ref(false)
const scoreCaseId = ref('')
const scoreNama = ref('')
const scoreForm = reactive({ score: '', reason: '' })
const scoreErrors = ref([])
const scoreErr = ref('')
const savingScore = ref(false)

const manualOpen = ref(false)
const nikQuery = ref('')
const searching = ref(false)
const searchErr = ref('')
const searchDone = ref(false)
const searchResults = ref([])

const detailAttempt = computed(() => detail.value?.attempt || {})
const detailCase = computed(() => detail.value?.case || {})
const detailItems = computed(() =>
  Array.isArray(detail.value?.items) ? detail.value.items : [])
const detailTier = computed(() =>
  detail.value?.modal_tier || detailAttempt.value.modal_tier || '—')
const profileAnswer = computed(() => detail.value?.profile_text_answer)

const summary = computed(() => {
  const scores = rows.value
    .map((row) => Number(row.score))
    .filter((score) => Number.isFinite(score))
  const sameCase = rows.value.length > 0
    && rows.value.every((row) => row.case_id === rows.value[0].case_id)
  const official = sameCase ? rows.value[0]?.official_score : null
  return {
    attempts: rows.value.length,
    best: scores.length ? Math.max(...scores) : null,
    official: official === null || official === undefined ? null : official,
  }
})

function messageOf(e, fallback) {
  const text = e?.message || e?.msg || e?.data?.msg || e?.data?.error
  return typeof text === 'string' && text ? text : fallback
}

/** Mask pertahanan: 16 digit beruntun dari respons apa pun tidak boleh tampil. */
function safeText(value) {
  if (value === null || value === undefined) return '—'
  let text
  if (typeof value === 'object') {
    try { text = JSON.stringify(value) } catch { text = String(value) }
  } else {
    text = String(value)
  }
  return text.replace(FULL_NIK_RE, (digits) => `****${digits.slice(-4)}`)
}

function optionList(options) {
  if (Array.isArray(options)) return options
  if (options && typeof options === 'object') {
    return Object.entries(options).map(([id, value]) => ({
      id,
      text: value && typeof value === 'object' ? value.text : value,
    }))
  }
  return []
}

function displayValue(value, type = '', options = []) {
  if (value === null || value === undefined || value === '') return '—'
  if (Array.isArray(value)) return value.map((v) => displayValue(v, type, options)).join(', ')
  if (typeof value === 'object') {
    if (value.option !== undefined) {
      const opt = optionList(options).find(
        (o) => String(o?.id || '') === String(value.option))
      return opt?.text
        ? `${String(value.option).toUpperCase()} — ${safeText(opt.text)}`
        : safeText(value.option)
    }
    if (value.value !== undefined) {
      const tolerance = value.tolerance !== undefined
        ? ` ± ${safeText(value.tolerance)}` : ''
      return `${safeText(value.value)}${tolerance}`
    }
    if (value.text !== undefined) return safeText(value.text)
    if (value.aliases !== undefined) return displayValue(value.aliases, type, options)
    return safeText(value)
  }
  return safeText(value)
}

function passedLabel(value) {
  return value === true || value === 1 || value === '1' ? 'Lulus' : 'Tidak lulus'
}

function buildParams(source) {
  const params = {}
  const branch = String(source.branch || '').trim()
  const status = String(source.status || '').trim()
  const from = String(source.from || '').trim()
  const to = String(source.to || '').trim()
  const q = String(source.q || '').trim()
  if (branch) params.branch_code = branch.toUpperCase()
  if (status) params.status = status.toUpperCase()
  if (from) params.from = from
  if (to) params.to = to
  if (q) params.q = q
  return params
}

async function load() {
  loading.value = true
  err.value = ''
  msg.value = ''
  try {
    const data = await api('/api/recruitment/tkd/attempts', { params: buildParams(applied) })
    rows.value = Array.isArray(data?.data) ? data.data : []
  } catch (e) {
    rows.value = []
    err.value = safeText(messageOf(e, 'Gagal memuat hasil TKD.'))
  } finally {
    loading.value = false
  }
}

function applyFilters() {
  if (loading.value) return
  Object.assign(applied, filters)
  load()
}

function resetFilters() {
  if (loading.value) return
  Object.assign(filters, defaultFilters())
  Object.assign(applied, defaultFilters())
  load()
}

async function openDetail(id) {
  if (!id) return
  msg.value = ''
  scoreOpen.value = false
  manualOpen.value = false
  detailOpen.value = true
  detail.value = null
  detailErr.value = ''
  detailLoading.value = true
  try {
    const resp = await api(`/api/recruitment/tkd/review/${encodeURIComponent(id)}`)
    detail.value = resp?.data || null
    if (!detail.value) detailErr.value = 'Detail tidak ditemukan.'
  } catch (e) {
    detailErr.value = safeText(messageOf(e, 'Gagal memuat detail hasil.'))
  } finally {
    detailLoading.value = false
  }
}

function closeDetail() {
  if (!detailLoading.value) detailOpen.value = false
}

function openScore(caseId, nama = '') {
  msg.value = ''
  detailOpen.value = false
  manualOpen.value = false
  scoreCaseId.value = String(caseId || '').trim()
  scoreNama.value = String(nama || '')
  scoreForm.score = ''
  scoreForm.reason = ''
  scoreErrors.value = []
  scoreErr.value = ''
  scoreOpen.value = true
}

function closeScore() {
  if (!savingScore.value) scoreOpen.value = false
}

/** Terima "75.5" dan "75,5" seperti parse_numeric() di backend. */
function parseScore(value) {
  const text = String(value ?? '').trim()
  if (!text) return null
  let normalized = text
  if (text.includes(',') && text.includes('.')) {
    normalized = text.replace(/\./g, '').replace(',', '.')
  } else if (text.includes(',')) {
    normalized = text.replace(',', '.')
  }
  if (!/^\d+(?:\.\d+)?$/.test(normalized)) return null
  const score = Number(normalized)
  return Number.isFinite(score) ? score : null
}

function validateScore() {
  const errors = []
  const raw = String(scoreForm.score ?? '').trim()
  if (!raw) {
    errors.push('Skor wajib diisi.')
  } else {
    const score = parseScore(raw)
    if (score === null || score < 0 || score > 100) {
      errors.push('Skor harus antara 0 dan 100.')
    }
  }
  const reason = String(scoreForm.reason ?? '').trim()
  if (!reason) errors.push('Alasan wajib')
  else if (reason.length > 500) errors.push('Alasan maksimal 500 karakter.')
  return errors
}

async function saveScore() {
  if (savingScore.value) return
  scoreErrors.value = validateScore()
  if (scoreErrors.value.length) return

  const caseId = String(scoreCaseId.value || '').trim()
  if (!caseId) {
    scoreErr.value = 'Kasus tidak dipilih.'
    return
  }
  const body = {
    case_id: caseId,
    score: parseScore(scoreForm.score),
    reason: String(scoreForm.reason).trim(),
  }
  savingScore.value = true
  scoreErr.value = ''
  try {
    await api('/api/recruitment/tkd/score', { method: 'POST', body })
    scoreOpen.value = false
    manualOpen.value = false
    searchResults.value = []
    searchDone.value = false
    nikQuery.value = ''
    await load()
    msg.value = 'Skor berhasil dikoreksi.'
  } catch (e) {
    scoreErr.value = safeText(messageOf(e, 'Gagal menyimpan koreksi skor.'))
  } finally {
    savingScore.value = false
  }
}

function openManual() {
  msg.value = ''
  detailOpen.value = false
  scoreOpen.value = false
  nikQuery.value = ''
  searchResults.value = []
  searchDone.value = false
  searchErr.value = ''
  manualOpen.value = true
}

function closeManual() {
  if (!searching.value) manualOpen.value = false
}

async function doSearch() {
  if (searching.value) return
  const nik = String(nikQuery.value || '').trim()
  // NIK hanya dipakai sebagai query — jangan biarkan tersimpan di layar/state.
  nikQuery.value = ''
  searchResults.value = []
  searchDone.value = false
  searchErr.value = ''
  if (!nik) {
    searchErr.value = 'NIK wajib diisi.'
    return
  }
  searching.value = true
  try {
    const resp = await api('/api/recruitment/cases', { params: { nik } })
    searchResults.value = Array.isArray(resp?.data) ? resp.data : []
    searchDone.value = true
    if (!searchResults.value.length) searchErr.value = 'Kasus tidak ditemukan.'
  } catch (e) {
    searchErr.value = safeText(messageOf(e, 'Gagal mencari kasus.'))
  } finally {
    searching.value = false
  }
}

onMounted(load)
</script>

<template>
  <div class="tk-results-panel">
    <div v-if="err" class="alert alert-error" data-alert="error">{{ err }}</div>
    <div v-if="msg" class="alert alert-success" data-alert="success">{{ msg }}</div>

    <div class="card card-pad">
      <div class="tk-results-head">
        <div>
          <h3>📊 Hasil TKD</h3>
          <div class="muted tk-results-sub">Lihat hasil ujian dan koreksi skor pelamar.</div>
        </div>
        <button class="btn btn-sm" type="button" data-action="manual-search"
                @click="openManual">Koreksi tanpa attempt</button>
      </div>

      <form class="tk-results-filters" @submit.prevent="applyFilters">
        <label class="tk-results-field">Cabang
          <input class="input" data-filter="branch" v-model="filters.branch"
                 :readonly="!isAdmin" placeholder="Kode cabang"
                 aria-label="Filter cabang" :disabled="loading" />
        </label>
        <label class="tk-results-field">Status
          <select class="select" data-filter="status" v-model="filters.status"
                  aria-label="Filter status" :disabled="loading">
            <option value="">Semua status</option>
            <option v-for="status in STATUSES" :key="status" :value="status">{{ status }}</option>
          </select>
        </label>
        <label class="tk-results-field">Dari
          <input class="input" type="date" data-filter="from" v-model="filters.from"
                 aria-label="Filter tanggal mulai" :disabled="loading" />
        </label>
        <label class="tk-results-field">Sampai
          <input class="input" type="date" data-filter="to" v-model="filters.to"
                 aria-label="Filter tanggal akhir" :disabled="loading" />
        </label>
        <label class="tk-results-field">Cari
          <input class="input" data-filter="q" v-model="filters.q"
                 aria-label="Cari nama atau NIK" placeholder="Nama atau NIK…"
                 :disabled="loading" />
        </label>
        <button class="btn btn-sm btn-primary" type="button" data-action="apply"
                :disabled="loading" @click="applyFilters">🔍 Terapkan</button>
        <button class="btn btn-sm" type="button" data-action="reset"
                :disabled="loading" @click="resetFilters">Reset</button>
      </form>

      <div v-if="loading" class="tk-results-empty">⏳ Memuat hasil…</div>
      <div v-else-if="!rows.length" class="tk-results-empty">
        Belum ada hasil untuk filter ini.
      </div>
      <div v-if="!loading && rows.length" class="tk-results-summary" data-summary>
        <span>Percobaan: <b>{{ summary.attempts }}</b></span>
        <span>Skor terbaik: <b>{{ summary.best ?? '—' }}</b></span>
        <span>Skor resmi: <b>{{ summary.official ?? '—' }}</b></span>
      </div>
      <div v-if="!loading && rows.length" class="tk-results-table-wrap">
        <table class="tk-results-table">
          <thead>
            <tr>
              <th>Nama</th><th>NIK</th><th>Cabang</th><th>Attempt</th>
              <th>Status</th><th>Skor</th><th>Lulus</th><th>Mulai</th>
              <th>Selesai</th><th>Sumber</th><th>Aksi</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="row in rows" :key="row.id">
              <td>{{ safeText(row.nama) }}</td>
              <td><code>{{ safeText(row.nik_masked) }}</code></td>
              <td>{{ safeText(row.branch_code) }}</td>
              <td>{{ row.attempt_no ?? '—' }}</td>
              <td><span class="fw-badge">{{ safeText(row.status) }}</span></td>
              <td><b>{{ row.score ?? '—' }}</b></td>
              <td>{{ passedLabel(row.passed) }}</td>
              <td>{{ safeText(row.started_at) }}</td>
              <td>{{ safeText(row.submitted_at) }}</td>
              <td>{{ safeText(row.score_source) }}</td>
              <td>
                <div class="tk-results-actions">
                  <button class="btn btn-sm" type="button" :data-review="row.id"
                          @click="openDetail(row.id)">Detail</button>
                  <button class="btn btn-sm" type="button" :data-score="row.case_id"
                          @click="openScore(row.case_id, row.nama)">Koreksi</button>
                </div>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

    <Modal v-if="detailOpen" title="Detail hasil TKD (staff)" wide @close="closeDetail">
      <div v-if="detailLoading" class="tk-results-empty">⏳ Memuat detail…</div>
      <template v-else-if="detailErr">
        <div class="alert alert-error">{{ detailErr }}</div>
        <div class="tk-results-form-actions">
          <button class="btn" type="button" data-action="close-detail"
                  @click="closeDetail">Tutup</button>
        </div>
      </template>
      <div v-else-if="detail" class="tk-results-detail">
        <div class="tk-results-detail-meta">
          <span><b>Nama:</b> {{ safeText(detailCase.nama) }}</span>
          <span><b>Kasus:</b> {{ safeText(detailCase.case_id || detailAttempt.case_id) }}</span>
          <span><b>Attempt:</b> {{ detailAttempt.attempt_no ?? '—' }}</span>
          <span><b>Status:</b> {{ safeText(detailAttempt.status) }}</span>
          <span><b>Skor percobaan:</b> {{ detail.score ?? '—' }}</span>
          <span><b>Skor resmi:</b> {{ detailCase.tkd_score ?? '—' }}</span>
          <span><b>Sumber skor resmi:</b> {{ safeText(detailCase.tkd_score_source) }}</span>
          <span><b>Tier modal:</b> {{ safeText(detailTier) }}</span>
        </div>
        <p v-if="detailAttempt.pass_score_snapshot !== undefined"
           class="muted tk-results-sub">
          Nilai lulus saat ujian: {{ detailAttempt.pass_score_snapshot }}
        </p>

        <table class="tk-results-table tk-results-detail-table">
          <thead>
            <tr>
              <th>No</th><th>Pertanyaan</th><th>Jawaban pelamar</th>
              <th>Kunci</th><th>Benar/Salah</th><th>Poin</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="item in detailItems" :key="item.position">
              <td>{{ item.position }}</td>
              <td>{{ displayValue(item.snapshot?.prompt) }}</td>
              <td>{{ displayValue(item.answer, item.snapshot?.type, item.snapshot?.options) }}</td>
              <td>{{ displayValue(item.snapshot?.answer, item.snapshot?.type, item.snapshot?.options) }}</td>
              <td>{{ item.is_correct === 1 || item.is_correct === true ? 'Benar' : 'Salah' }}</td>
              <td>{{ item.points_awarded ?? '—' }}</td>
            </tr>
          </tbody>
        </table>
        <p v-if="!detailItems.length" class="muted tk-results-sub">Tidak ada butir jawaban.</p>

        <div class="tk-results-staff-key">
          <b>Jawaban PROFILE_TEXT</b>
          <div data-profile-answer>{{ displayValue(profileAnswer, 'PROFILE_TEXT') }}</div>
          <div class="muted tk-results-sub">Kunci dan poin hanya tersedia di panel staff.</div>
        </div>
        <div class="tk-results-form-actions">
          <button class="btn" type="button" data-action="close-detail"
                  @click="closeDetail">Tutup</button>
        </div>
      </div>
    </Modal>

    <Modal v-if="scoreOpen" title="Koreksi skor TKD" @close="closeScore">
      <form class="tk-results-form" @submit.prevent="saveScore">
        <div v-if="scoreErrors.length" class="alert alert-error" data-score-errors>
          <div v-for="error in scoreErrors" :key="error">• {{ error }}</div>
        </div>
        <div v-if="scoreErr" class="alert alert-error" data-score-error>{{ scoreErr }}</div>
        <p class="muted tk-results-sub">
          Kasus: <b>{{ safeText(scoreNama || scoreCaseId) }}</b> ({{ safeText(scoreCaseId) }})
        </p>
        <label class="tk-results-field">Skor (0–100)
          <input class="input" type="text" inputmode="decimal"
                 data-field="score" v-model="scoreForm.score" placeholder="0–100" />
        </label>
        <label class="tk-results-field">Alasan koreksi
          <textarea class="textarea" rows="3" data-field="reason"
                    v-model="scoreForm.reason" placeholder="Tuliskan alasan koreksi…"></textarea>
        </label>
        <div class="tk-results-form-actions">
          <button class="btn" type="button" :disabled="savingScore"
                  @click="closeScore">Batal</button>
          <button class="btn btn-primary" type="button" data-action="save-score"
                  :disabled="savingScore" @click="saveScore">
            {{ savingScore ? 'Menyimpan…' : 'Simpan skor' }}
          </button>
        </div>
      </form>
    </Modal>

    <Modal v-if="manualOpen" title="Cari kasus untuk koreksi manual" @close="closeManual">
      <form class="tk-results-form" @submit.prevent="doSearch">
        <p class="muted tk-results-sub">Masukkan NIK 16 digit untuk mencari kasus.</p>
        <label class="tk-results-field">NIK
          <input class="input" data-field="nik" v-model="nikQuery"
                 inputmode="numeric" autocomplete="off" placeholder="NIK 16 digit" />
        </label>
        <button class="btn btn-sm btn-primary" type="button" data-action="do-search"
                :disabled="searching" @click="doSearch">
          {{ searching ? 'Mencari…' : '🔍 Cari kasus' }}
        </button>
      </form>
      <div v-if="searchErr" class="alert alert-error">{{ searchErr }}</div>
      <ul v-if="searchResults.length" class="tk-results-cases" data-search-results>
        <li v-for="candidate in searchResults" :key="candidate.case_id">
          <span><b>{{ safeText(candidate.nama) }}</b>
            <span class="muted">· {{ safeText(candidate.nik_masked) }} ·
              {{ safeText(candidate.case_id) }}</span></span>
          <button class="btn btn-sm" type="button" :data-pick-case="candidate.case_id"
                  @click="openScore(candidate.case_id, candidate.nama)">Koreksi</button>
        </li>
      </ul>
    </Modal>
  </div>
</template>

<style scoped>
.tk-results-head { display: flex; flex-wrap: wrap; gap: 10px; justify-content: space-between; align-items: flex-start; }
.tk-results-head h3 { margin: 0; }
.tk-results-sub { font-size: 12px; margin-top: 4px; }
.tk-results-filters { display: flex; flex-wrap: wrap; gap: 8px; margin: 14px 0 12px; }
.tk-results-field { display: grid; gap: 4px; font-size: 12px; color: var(--text-2); }
.tk-results-filters .input, .tk-results-filters .select { flex: 1 1 140px; min-width: 120px; }
.tk-results-empty { padding: 26px; text-align: center; color: var(--text-3); font-size: 12px; }
.tk-results-summary {
  display: flex; flex-wrap: wrap; gap: 8px 18px; margin: 0 0 12px;
  padding: 10px 12px; border: 1px solid var(--border); border-radius: 8px;
  background: var(--bg); font-size: 12px;
}
.tk-results-table-wrap { overflow-x: auto; }
.tk-results-table { width: 100%; border-collapse: collapse; font-size: 12px; }
.tk-results-table th {
  text-align: left; padding: 8px 10px; border-bottom: 1px solid var(--border);
  color: var(--text-2); white-space: nowrap; font-weight: 600;
}
.tk-results-table td { padding: 9px 10px; border-bottom: 1px solid var(--border); vertical-align: top; }
.tk-results-table tr:hover td { background: var(--bg); }
.tk-results-actions, .tk-results-form-actions { display: flex; flex-wrap: wrap; gap: 6px; justify-content: flex-end; }
.tk-results-detail { display: grid; gap: 12px; }
.tk-results-detail-meta { display: flex; flex-wrap: wrap; gap: 8px 18px; font-size: 12px; }
.tk-results-detail-table th, .tk-results-detail-table td { white-space: normal; min-width: 90px; }
.tk-results-staff-key {
  padding: 10px 12px; border: 1px solid var(--border);
  border-left: 3px solid var(--primary); border-radius: 8px; font-size: 12px;
}
.tk-results-form { display: grid; gap: 10px; }
.tk-results-cases { list-style: none; margin: 12px 0 0; padding: 0; display: grid; gap: 6px; }
.tk-results-cases li {
  display: flex; flex-wrap: wrap; gap: 8px; align-items: center; justify-content: space-between;
  border: 1px solid var(--border); border-radius: 8px; padding: 8px 10px; font-size: 12px;
}
.fw-badge {
  display: inline-block; font-size: 10px; font-weight: 700; padding: 2px 8px;
  border-radius: 999px; background: var(--surface-2, #f1f5f9);
  color: var(--text-2, #475569); white-space: nowrap;
}
</style>
