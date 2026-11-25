<script setup>
/**
 * Bank soal TKD — panel staff.
 *
 * Kunci jawaban sengaja ditampilkan di sini (panel staff), tetapi hanya di
 * dalam modal preview/form yang tidak dipakai pelamar. Panel pelamar berada
 * di components/RecruitmentTkdPanel.vue dan tidak pernah menerima `answer`.
 */
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { api } from '../api'
import Modal from '../components/Modal.vue'

const CATEGORIES = ['REGULASI', 'PERUSAHAAN', 'PRODUK', 'HITUNG', 'PROFIL']
const TYPES = ['MCQ', 'NUMERIC', 'SHORT_TEXT', 'PROFILE_TEXT']
const OPTION_IDS = ['a', 'b', 'c', 'd', 'e']
const TIERS = ['30k', '50k', '100k']
const TYPE_LABELS = {
  MCQ: 'Pilihan ganda',
  NUMERIC: 'Angka',
  SHORT_TEXT: 'Teks pendek',
  PROFILE_TEXT: 'Teks profil',
}

const filters = reactive({ category: '', active: '', q: '' })
const applied = reactive({ category: '', active: '', q: '' })
const rows = ref([])
const loading = ref(true)
const busy = ref(false)
const saving = ref(false)
const importing = ref(false)
const err = ref('')
const msg = ref('')
const formOpen = ref(false)
const formErrors = ref([])
const previewRow = ref(null)
const csvFile = ref(null)
const updateDrafts = ref(false)
const importResult = ref(null)

function emptyForm() {
  return {
    id: null, code: '', category: 'REGULASI', type: 'MCQ', prompt: '',
    options: { a: '', b: '', c: '', d: '', e: '' },
    answer_option: '', numeric_value: '', numeric_tolerance: '0.5',
    aliases: '', points: 1, modal_tier: '', active: false, sort_order: 0,
  }
}
const form = reactive(emptyForm())

// PROFILE_TEXT selalu 0 poin; tier modal hanya relevan pada kategori HITUNG.
watch(() => [form.type, form.category], () => {
  if (form.type === 'PROFILE_TEXT') form.points = 0
  if (form.category !== 'HITUNG') form.modal_tier = ''
})

function messageOf(e, fallback) {
  const text = e?.message || e?.msg || e?.data?.msg || e?.data?.error
  return typeof text === 'string' && text ? text : fallback
}

function typeLabel(type) {
  return TYPE_LABELS[type] || type || '—'
}

function excerpt(text, max = 90) {
  const value = String(text || '').trim()
  return value.length > max ? `${value.slice(0, max)}…` : (value || '—')
}

function isNumber(value) {
  return value !== '' && value !== null && value !== undefined
    && Number.isFinite(Number(value))
}

async function load() {
  loading.value = true
  err.value = ''
  try {
    const params = {}
    if (applied.category) params.category = applied.category
    if (applied.active) params.active = applied.active
    if (applied.q.trim()) params.q = applied.q.trim()
    const data = await api('/api/recruitment/tkd/questions', { params })
    rows.value = Array.isArray(data?.data) ? data.data : []
  } catch (e) {
    err.value = messageOf(e, 'Gagal memuat bank soal.')
  } finally {
    loading.value = false
  }
}

function applyFilters() {
  if (busy.value) return
  Object.assign(applied, filters)
  load()
}

function resetFilters() {
  if (busy.value) return
  Object.assign(filters, { category: '', active: '', q: '' })
  Object.assign(applied, { category: '', active: '', q: '' })
  importResult.value = null
  load()
}

function openForm(row = null) {
  if (busy.value || saving.value) return
  formErrors.value = []
  Object.assign(form, emptyForm())
  if (row) {
    form.id = row.id
    form.code = row.code || ''
    form.category = row.category || 'REGULASI'
    form.type = row.type || 'MCQ'
    form.prompt = row.prompt || ''
    ;(row.options || []).forEach((option) => {
      if (option && OPTION_IDS.includes(option.id)) {
        form.options[option.id] = option.text || ''
      }
    })
    const answer = row.answer || {}
    form.answer_option = answer.option || ''
    form.numeric_value = answer.value === null || answer.value === undefined
      ? '' : String(answer.value)
    // Backend memakai 0.5 bila toleransi tidak tersimpan; pakai nilai yang sama
    // supaya edit soal lama tidak gagal validasi klien.
    form.numeric_tolerance = answer.tolerance === null || answer.tolerance === undefined
      ? '0.5' : String(answer.tolerance)
    form.aliases = Array.isArray(answer.aliases) ? answer.aliases.join('|') : ''
    form.points = row.points ?? 1
    form.modal_tier = row.modal_tier || ''
    form.active = row.active === true || Number(row.active) === 1
    form.sort_order = row.sort_order || 0
  }
  formOpen.value = true
}

function closeForm() {
  if (!saving.value) formOpen.value = false
}

function builtOptions() {
  return OPTION_IDS
    .filter((id) => String(form.options[id] || '').trim())
    .map((id) => ({ id, text: String(form.options[id]).trim() }))
}

function builtAliases() {
  return String(form.aliases || '').split('|').map((s) => s.trim()).filter(Boolean)
}

function buildBody() {
  let answer = null
  if (form.type === 'MCQ') {
    answer = { option: String(form.answer_option || '').trim().toLowerCase() }
  } else if (form.type === 'NUMERIC') {
    answer = {
      value: Number(form.numeric_value),
      tolerance: form.numeric_tolerance === '' ? 0 : Number(form.numeric_tolerance),
    }
  } else if (form.type === 'SHORT_TEXT') {
    answer = { aliases: builtAliases() }
  }
  return {
    code: String(form.code || '').trim().toUpperCase(),
    category: form.category,
    type: form.type,
    prompt: String(form.prompt || '').trim(),
    options: form.type === 'MCQ' ? builtOptions() : [],
    answer,
    points: form.type === 'PROFILE_TEXT' ? 0 : Number(form.points),
    modal_tier: form.category === 'HITUNG' ? String(form.modal_tier || '') : '',
    active: form.active ? 1 : 0,
    sort_order: Number(form.sort_order) || 0,
  }
}

function validateForm() {
  const errors = []
  const code = String(form.code || '').trim().toUpperCase()
  if (!code) errors.push('Kode soal wajib diisi.')
  else if (!/^[A-Z0-9][A-Z0-9_-]{2,39}$/.test(code)) {
    errors.push('Kode soal harus 3–40 karakter A-Z/0-9/_/-.')
  }
  const prompt = String(form.prompt || '').trim()
  if (!prompt) errors.push('Pertanyaan wajib diisi.')
  else if (prompt.length > 2000) errors.push('Pertanyaan maksimal 2000 karakter.')

  if (form.type === 'MCQ') {
    const options = builtOptions()
    if (options.length < 2) errors.push('MCQ minimal 2 opsi jawaban.')
    if (!String(form.answer_option || '').trim()) {
      errors.push('Kunci jawaban wajib dipilih')
    } else if (!options.some((o) => o.id === String(form.answer_option).trim().toLowerCase())) {
      errors.push('Kunci jawaban harus salah satu opsi yang diisi.')
    }
    if (!(Number(form.points) > 0)) errors.push('Poin harus lebih dari 0.')
  } else if (form.type === 'NUMERIC') {
    if (!isNumber(form.numeric_value)) errors.push('Kunci jawaban NUMERIC harus angka.')
    if (!isNumber(form.numeric_tolerance) || Number(form.numeric_tolerance) < 0) {
      errors.push('Toleransi harus angka non-negatif.')
    }
    if (!(Number(form.points) > 0)) errors.push('Poin harus lebih dari 0.')
  } else if (form.type === 'SHORT_TEXT') {
    const aliases = builtAliases()
    if (!aliases.length) errors.push('SHORT_TEXT minimal 1 alias jawaban.')
    else if (aliases.length > 10) errors.push('SHORT_TEXT maksimal 10 alias.')
    if (!(Number(form.points) > 0)) errors.push('Poin harus lebih dari 0.')
  } else if (form.type === 'PROFILE_TEXT') {
    if (form.category !== 'PROFIL') errors.push('PROFILE_TEXT hanya boleh untuk kategori PROFIL.')
    if (Number(form.points) !== 0) errors.push('PROFILE_TEXT harus 0 poin.')
  }

  if (form.category === 'HITUNG' && form.modal_tier && !TIERS.includes(form.modal_tier)) {
    errors.push('Tier modal tidak dikenal.')
  }
  return errors
}

async function save() {
  if (saving.value) return
  formErrors.value = validateForm()
  if (formErrors.value.length) return

  const body = buildBody()
  const isEdit = Boolean(form.id)
  saving.value = true
  err.value = ''
  msg.value = ''
  try {
    if (isEdit) {
      await api(`/api/recruitment/tkd/questions/${form.id}`, { method: 'PUT', body })
    } else {
      await api('/api/recruitment/tkd/questions', { method: 'POST', body })
    }
    formOpen.value = false
    msg.value = isEdit ? 'Soal berhasil diperbarui.' : 'Soal berhasil ditambahkan.'
    await load()
  } catch (e) {
    err.value = messageOf(e, 'Gagal menyimpan soal.')
  } finally {
    saving.value = false
  }
}

async function toggle(row) {
  if (busy.value) return
  busy.value = true
  err.value = ''
  msg.value = ''
  try {
    await api(`/api/recruitment/tkd/questions/${row.id}/toggle`, { method: 'POST' })
    msg.value = row.active ? 'Soal dinonaktifkan.' : 'Soal diaktifkan.'
    await load()
  } catch (e) {
    err.value = messageOf(e, 'Gagal mengubah status soal.')
  } finally {
    busy.value = false
  }
}

function answerText(row) {
  const answer = row?.answer || {}
  if (row?.type === 'MCQ') {
    const option = (row.options || []).find((o) => o?.id === answer.option)
    return option?.text
      ? `${String(answer.option || '').toUpperCase()} — ${option.text}`
      : String(answer.option || '—')
  }
  if (row?.type === 'NUMERIC') {
    return `${answer.value ?? '—'} ± ${answer.tolerance ?? 0}`
  }
  if (row?.type === 'SHORT_TEXT') {
    return (answer.aliases || []).join(' | ') || '—'
  }
  return 'Tanpa kunci (jawaban esai)'
}

function onFileChange(event) {
  csvFile.value = event.target.files?.[0] || null
  importResult.value = null
}

async function importCsv() {
  if (importing.value || busy.value) return
  if (!csvFile.value) {
    err.value = 'Pilih berkas CSV terlebih dahulu.'
    return
  }
  importing.value = true
  err.value = ''
  msg.value = ''
  importResult.value = null
  try {
    const csv = await csvFile.value.text()
    const data = await api('/api/recruitment/tkd/questions/import', {
      method: 'POST',
      body: { csv, update_drafts: updateDrafts.value },
    })
    const result = data?.data || data || {}
    importResult.value = {
      inserted: Number(result.inserted) || 0,
      updated: Number(result.updated) || 0,
      skipped: Number(result.skipped) || 0,
      errors: Array.isArray(result.errors) ? result.errors : [],
    }
    msg.value = 'Impor CSV selesai.'
    await load()
  } catch (e) {
    err.value = messageOf(e, 'Gagal mengimpor CSV.')
  } finally {
    importing.value = false
  }
}

onMounted(load)
</script>

<template>
  <div class="tkb-panel">
    <div v-if="err" class="alert alert-error" data-alert="error">{{ err }}</div>
    <div v-if="msg" class="alert alert-success" data-alert="success">{{ msg }}</div>

    <div class="card card-pad">
      <div class="tkb-head">
        <div>
          <h3>📚 Bank Soal TKD</h3>
          <div class="muted tkb-sub">Kelola soal, kunci jawaban, dan status penerbitan.</div>
        </div>
        <div class="tkb-tools">
          <a class="btn btn-sm" href="/api/recruitment/tkd/questions/export.csv" download>
            ⬇️ Ekspor CSV
          </a>
          <button class="btn btn-sm btn-primary" type="button" data-action="new"
                  :disabled="busy || saving" @click="openForm()">＋ Tambah soal</button>
        </div>
      </div>

      <form class="tkb-filters" @submit.prevent="applyFilters">
        <select class="select" data-filter="category" v-model="filters.category"
                aria-label="Filter kategori" :disabled="busy">
          <option value="">Semua kategori</option>
          <option v-for="category in CATEGORIES" :key="category" :value="category">{{ category }}</option>
        </select>
        <select class="select" data-filter="active" v-model="filters.active"
                aria-label="Filter status" :disabled="busy">
          <option value="">Semua status</option>
          <option value="1">Aktif</option>
          <option value="0">Draft</option>
        </select>
        <input class="input" data-filter="q" v-model="filters.q" aria-label="Cari kode atau pertanyaan"
               placeholder="Cari kode atau pertanyaan…" :disabled="busy" />
        <button class="btn btn-sm btn-primary" type="button" data-action="apply"
                :disabled="busy" @click="applyFilters">🔍 Terapkan</button>
        <button class="btn btn-sm" type="button" data-action="reset"
                :disabled="busy" @click="resetFilters">Reset</button>
      </form>

      <div v-if="loading" class="tkb-empty">⏳ Memuat soal…</div>
      <div v-else-if="!rows.length" class="tkb-empty">Belum ada soal untuk filter ini.</div>
      <div v-else class="tkb-table-wrap">
        <table class="tkb-table">
          <thead>
            <tr>
              <th>Kode</th><th>Kategori</th><th>Tipe</th><th>Pertanyaan</th>
              <th>Tier</th><th>Poin</th><th>Status</th><th>Aksi</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="row in rows" :key="row.id">
              <td><code>{{ row.code }}</code></td>
              <td>{{ row.category }}</td>
              <td>{{ typeLabel(row.type) }}</td>
              <td class="tkb-prompt">{{ excerpt(row.prompt) }}</td>
              <td>{{ row.modal_tier || '—' }}</td>
              <td>{{ row.points }}</td>
              <td>
                <span class="fw-badge" :class="row.active ? 'st-verified' : 'st-submitted'">
                  {{ row.active ? 'Aktif' : 'Draft' }}
                </span>
              </td>
              <td>
                <div class="tkb-actions">
                  <button class="btn btn-sm" type="button" :data-preview="row.id"
                          :disabled="busy" @click="previewRow = row">Preview</button>
                  <button class="btn btn-sm" type="button" :data-edit="row.id"
                          :disabled="busy || saving" @click="openForm(row)">Edit</button>
                  <button class="btn btn-sm" type="button" :data-toggle="row.id"
                          :disabled="busy" @click="toggle(row)">
                    {{ row.active ? 'Nonaktifkan' : 'Aktifkan' }}
                  </button>
                </div>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

    <div class="card card-pad tkb-import">
      <h3>📥 Impor CSV</h3>
      <p class="muted tkb-sub">Baris valid masuk sebagai draft; soal aktif tidak ditimpa.</p>
      <div class="tkb-import-row">
        <input type="file" class="input" accept=".csv,text/csv" data-import-file
               @change="onFileChange" />
        <label class="tkb-check">
          <input type="checkbox" data-import-update v-model="updateDrafts" />
          Perbarui draft yang sudah ada
        </label>
        <button class="btn btn-sm btn-primary" type="button" data-action="import"
                :disabled="importing || busy" @click="importCsv">
          {{ importing ? 'Mengimpor…' : 'Impor' }}
        </button>
      </div>
      <div v-if="importResult" class="alert alert-info tkb-import-result" data-import-result>
        Impor selesai: {{ importResult.inserted }} ditambahkan,
        {{ importResult.updated }} diperbarui, {{ importResult.skipped }} dilewati.
        <ul v-if="importResult.errors.length">
          <li v-for="(error, i) in importResult.errors" :key="i">{{ error }}</li>
        </ul>
      </div>
    </div>

    <Modal v-if="formOpen" :title="form.id ? 'Edit soal TKD' : 'Tambah soal TKD'" wide
           @close="closeForm">
      <form class="tkb-form" @submit.prevent="save">
        <div v-if="formErrors.length" class="alert alert-error" data-form-errors>
          <div v-for="error in formErrors" :key="error">• {{ error }}</div>
        </div>
        <div class="tkb-grid">
          <label class="tkb-field">Kode soal
            <input class="input" data-field="code" v-model="form.code" placeholder="REG-01" />
          </label>
          <label class="tkb-field">Kategori
            <select class="select" data-field="category" v-model="form.category">
              <option v-for="category in CATEGORIES" :key="category" :value="category">{{ category }}</option>
            </select>
          </label>
          <label class="tkb-field">Tipe soal
            <select class="select" data-field="type" v-model="form.type">
              <option v-for="type in TYPES" :key="type" :value="type">{{ typeLabel(type) }}</option>
            </select>
          </label>
          <label class="tkb-field">Poin
            <input class="input" type="number" step="any" min="0" data-field="points"
                   v-model="form.points" :disabled="form.type === 'PROFILE_TEXT'" />
          </label>
          <label class="tkb-field">Urutan
            <input class="input" type="number" step="1" data-field="sort_order"
                   v-model="form.sort_order" />
          </label>
          <label v-if="form.category === 'HITUNG'" class="tkb-field">Tier modal
            <select class="select" data-field="modal_tier" v-model="form.modal_tier">
              <option value="">Umum (tanpa tier)</option>
              <option v-for="tier in TIERS" :key="tier" :value="tier">{{ tier }}</option>
            </select>
          </label>
          <label class="tkb-check tkb-span">
            <input type="checkbox" data-field="active" v-model="form.active" />
            Aktifkan soal (tanpa centang = draft)
          </label>
        </div>

        <label class="tkb-field">Pertanyaan
          <textarea class="textarea" data-field="prompt" rows="3" v-model="form.prompt"
                    placeholder="Tuliskan pertanyaan…"></textarea>
        </label>

        <fieldset v-if="form.type === 'MCQ'" class="tkb-fieldset">
          <legend>Opsi jawaban</legend>
          <div class="tkb-grid">
            <label v-for="id in OPTION_IDS" :key="id" class="tkb-field">
              Opsi {{ id.toUpperCase() }}
              <input class="input" :data-field="`option_${id}`" v-model="form.options[id]" />
            </label>
          </div>
        </fieldset>

        <fieldset class="tkb-fieldset">
          <legend>Kunci jawaban (khusus staff)</legend>
          <label v-if="form.type === 'MCQ'" class="tkb-field">Jawaban benar
            <select class="select" data-field="answer_option" v-model="form.answer_option">
              <option value="">Pilih kunci…</option>
              <option v-for="id in OPTION_IDS" :key="id" :value="id"
                      :disabled="!String(form.options[id] || '').trim()">
                {{ id.toUpperCase() }} — {{ form.options[id] || '(kosong)' }}
              </option>
            </select>
          </label>
          <div v-else-if="form.type === 'NUMERIC'" class="tkb-grid">
            <label class="tkb-field">Nilai benar
              <input class="input" type="number" step="any" data-field="answer_value"
                     v-model="form.numeric_value" />
            </label>
            <label class="tkb-field">Toleransi
              <input class="input" type="number" step="any" min="0" data-field="answer_tolerance"
                     v-model="form.numeric_tolerance" />
            </label>
          </div>
          <label v-else-if="form.type === 'SHORT_TEXT'" class="tkb-field">
            Alias jawaban (pisahkan dengan |)
            <input class="input" data-field="answer_aliases" v-model="form.aliases"
                   placeholder="jakarta|ibukota|dkj" />
          </label>
          <p v-else class="muted tkb-sub">PROFILE_TEXT tidak memiliki kunci dan harus 0 poin.</p>
        </fieldset>

        <div class="tkb-form-actions">
          <button class="btn" type="button" :disabled="saving" @click="closeForm">Batal</button>
          <button class="btn btn-primary" type="button" data-action="save"
                  :disabled="saving" @click="save">
            {{ saving ? 'Menyimpan…' : 'Simpan soal' }}
          </button>
        </div>
      </form>
    </Modal>

    <Modal v-if="previewRow" title="Preview soal (staff)" @close="previewRow = null">
      <div class="tkb-preview">
        <div class="muted tkb-sub">{{ previewRow.code }} · {{ previewRow.category }} ·
          {{ typeLabel(previewRow.type) }}</div>
        <p class="tkb-preview-prompt">{{ previewRow.prompt }}</p>
        <ol v-if="(previewRow.options || []).length" class="tkb-preview-options">
          <li v-for="option in previewRow.options" :key="option.id">
            {{ String(option.id || '').toUpperCase() }}. {{ option.text }}
          </li>
        </ol>
        <p v-else class="muted tkb-sub">Tidak ada opsi pilihan pada tipe soal ini.</p>
        <div class="tkb-staff-key">
          <b>Kunci (khusus staff)</b>
          <div data-preview-answer>{{ answerText(previewRow) }}</div>
          <div class="muted tkb-sub">Poin: {{ previewRow.points }}</div>
        </div>
      </div>
    </Modal>
  </div>
</template>

<style scoped>
.tkb-head { display: flex; flex-wrap: wrap; gap: 10px; justify-content: space-between; align-items: flex-start; }
.tkb-head h3 { margin: 0; }
.tkb-sub { font-size: 12px; margin-top: 4px; }
.tkb-tools { display: flex; flex-wrap: wrap; gap: 6px; }
.tkb-tools .btn { text-decoration: none; }
.tkb-filters { display: flex; flex-wrap: wrap; gap: 8px; margin: 14px 0 12px; }
.tkb-filters .input, .tkb-filters .select { flex: 1 1 150px; min-width: 130px; }
.tkb-empty { padding: 26px; text-align: center; color: var(--text-3); font-size: 12px; }
.tkb-table-wrap { overflow-x: auto; }
.tkb-table { width: 100%; border-collapse: collapse; font-size: 12px; }
.tkb-table th {
  text-align: left; padding: 8px 10px; border-bottom: 1px solid var(--border);
  color: var(--text-2); white-space: nowrap; font-weight: 600;
}
.tkb-table td { padding: 9px 10px; border-bottom: 1px solid var(--border); vertical-align: top; }
.tkb-table tr:hover td { background: var(--bg); }
.tkb-prompt { max-width: 260px; }
.tkb-actions { display: flex; flex-wrap: wrap; gap: 4px; }
.fw-badge {
  display: inline-block; font-size: 10px; font-weight: 700; padding: 2px 8px;
  border-radius: 999px; background: var(--surface-2, #f1f5f9);
  color: var(--text-2, #475569); white-space: nowrap;
}
.fw-badge.st-verified { background: #d1fae5; color: #065f46; }
.fw-badge.st-submitted { background: #fef3c7; color: #92400e; }
.tkb-import { margin-top: 12px; }
.tkb-import h3 { margin: 0; }
.tkb-import-row { display: flex; flex-wrap: wrap; gap: 10px; align-items: center; margin-top: 10px; }
.tkb-import-row input[type="file"] { flex: 1 1 220px; }
.tkb-check { display: inline-flex; align-items: center; gap: 6px; font-size: 12px; }
.tkb-import-result { margin: 12px 0 0; }
.tkb-import-result ul { margin: 6px 0 0; padding-left: 18px; }
.tkb-form { display: grid; gap: 12px; }
.tkb-grid { display: grid; gap: 10px; grid-template-columns: repeat(auto-fit, minmax(170px, 1fr)); }
.tkb-field { display: grid; gap: 4px; font-size: 12px; color: var(--text-2); }
.tkb-span { grid-column: 1 / -1; }
.tkb-fieldset { border: 1px solid var(--border); border-radius: 10px; padding: 12px; display: grid; gap: 10px; }
.tkb-fieldset legend { font-size: 12px; font-weight: 700; padding: 0 6px; }
.tkb-form-actions { display: flex; justify-content: flex-end; gap: 8px; }
.tkb-preview-prompt { font-size: 13px; font-weight: 600; }
.tkb-preview-options { margin: 8px 0; padding-left: 20px; font-size: 12px; }
.tkb-staff-key {
  margin-top: 12px; padding: 10px 12px; border: 1px solid var(--border);
  border-left: 3px solid var(--primary); border-radius: 8px; font-size: 12px;
}
</style>
