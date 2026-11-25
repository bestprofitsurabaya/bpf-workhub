<script setup>
/**
 * TKD (Tes Kemampuan Dasar) untuk pelamar.
 *
 * Panel ini hanya menerima identitas yang sudah diketik di portal. Semua
 * keputusan (status, kesempatan, waktu, dan penilaian) berasal dari server.
 * Kunci jawaban/poin tidak pernah dikirim maupun dirender di sini.
 */
import { computed, onBeforeUnmount, onMounted, reactive, ref } from 'vue'
import { api } from '../api'

const props = defineProps({
  token: { type: String, default: '' },
  nik: { type: String, default: '' },
  dob: { type: String, default: '' },
})
const emit = defineEmits(['close'])

// Mesin tampilan: loading | error | intro | exam | result.
const mode = ref('loading')
const status = ref(null)
const msg = ref('')
const tier = ref('30k')
const attempt = ref(null)
const questions = ref([])
const index = ref(0)
const answers = reactive({})
const saveStatus = ref('')
const starting = ref(false)
const resuming = ref(false)
const submitting = ref(false)
const result = ref(null)
const now = ref(Date.now())
const expiresMs = ref(0)

const TIERS = [
  { value: '30k', label: '$30.000' },
  { value: '50k', label: '$50.000' },
  { value: '100k', label: '$100.000' },
]

let ticker = null
let saveTimer = null
let pendingSave = null

const rules = computed(() => {
  const s = status.value || {}
  return {
    question_count: s.question_count ?? 20,
    duration_minutes: s.duration_minutes ?? 25,
    pass_score: s.pass_score ?? 70,
    max_attempts: s.max_attempts ?? 2,
  }
})

const question = computed(() => questions.value[index.value] || null)
const remainingSeconds = computed(() =>
  expiresMs.value ? Math.max(0, Math.ceil((expiresMs.value - now.value) / 1000)) : 0)
const timerText = computed(() => {
  const s = remainingSeconds.value
  return `${String(Math.floor(s / 60)).padStart(2, '0')}:${String(s % 60).padStart(2, '0')}`
})
const progress = computed(() =>
  questions.value.length ? ((index.value + 1) / questions.value.length) * 100 : 0)
const canStart = computed(() =>
  Boolean(status.value?.can_start) && status.value?.bank_ready !== false)
const canRetry = computed(() => Boolean(status.value?.can_start))
const remainingAttempts = computed(() => {
  const used = result.value?.attempts_used ?? status.value?.attempts_used
  const max = result.value?.max_attempts ?? status.value?.max_attempts
  if (used === undefined || used === null || max === undefined || max === null) return null
  return Math.max(0, Number(max) - Number(used))
})
const stateLabel = computed(() => ({
  BELUM: 'Belum pernah tes',
  BISA_COBA: 'Bisa mencoba lagi',
  BERLANGSUNG: 'Ujian berlangsung',
  LULUS: 'Lulus',
  HABIS: 'Kesempatan habis',
  DIKECUALIKAN: 'Dikecualikan',
  SKOR_BELUM_TERCATAT: 'Skor belum tercatat — hubungi Traineer',
  SEGERA: 'TKD segera tersedia',
}[status.value?.state] || ''))

function fmt(value) {
  if (value === null || value === undefined || value === '') return '—'
  const n = Number(value)
  return Number.isFinite(n)
    ? n.toLocaleString('id-ID', { maximumFractionDigits: 2 })
    : String(value)
}

function messageOf(e, fallback) {
  const text = e?.message || e?.msg || e?.data?.msg || e?.data?.error
  return typeof text === 'string' && text ? text : fallback
}

function identity() {
  return { nik: props.nik, dob: props.dob, token: props.token }
}

function stopTicker() {
  if (ticker !== null) {
    clearInterval(ticker)
    ticker = null
  }
}

function startTicker() {
  stopTicker()
  now.value = Date.now()
  ticker = setInterval(() => {
    now.value = Date.now()
    if (remainingSeconds.value <= 0 && mode.value === 'exam' && !submitting.value) {
      void submit()
    }
  }, 1000)
}

function clearSave() {
  if (saveTimer !== null) {
    clearTimeout(saveTimer)
    saveTimer = null
  }
  pendingSave = null
}

async function loadStatus({ quiet = false } = {}) {
  try {
    const resp = await api('/api/recruitment/tkd/status', {
      method: 'POST', body: identity(),
    })
    // Respons kosong hanya terjadi pada mock; jangan merusak state yang ada.
    if (resp === undefined || resp === null) return null
    if (resp.status && resp.status !== 'success') {
      throw Object.assign(new Error(resp.msg || 'Gagal memuat status TKD.'),
        { status: resp.status })
    }
    status.value = resp.data || null
    return status.value
  } catch (e) {
    if (!quiet) {
      mode.value = 'error'
      msg.value = messageOf(e, 'Gagal memuat status TKD. Coba lagi.')
    }
    return null
  }
}

async function refreshStatus() {
  const previous = status.value
  const next = await loadStatus({ quiet: true })
  status.value = next || previous
}

function enterExam(data) {
  attempt.value = data
  questions.value = Array.isArray(data?.questions) ? data.questions : []
  for (const key of Object.keys(answers)) delete answers[key]
  const saved = data?.answers || {}
  for (const q of questions.value) {
    const value = saved[String(q.position)] ?? saved[q.position]
    if (value !== undefined && value !== null) answers[q.position] = value
  }
  index.value = 0
  result.value = null
  saveStatus.value = ''
  msg.value = ''
  mode.value = 'exam'

  const rawExpiry = String(data?.expires_at || '').replace(' ', 'T')
  const parsed = Date.parse(rawExpiry)
  expiresMs.value = Number.isFinite(parsed)
    ? parsed
    : Date.now() + Number(data?.remaining_seconds || 0) * 1000
  startTicker()
  if (remainingSeconds.value <= 0) void submit()
}

function showResult(data) {
  result.value = data || null
  clearSave()
  stopTicker()
  mode.value = 'result'
  void refreshStatus()
}

async function start() {
  if (starting.value || submitting.value) return
  starting.value = true
  msg.value = ''
  try {
    const resp = await api('/api/recruitment/tkd/start', {
      method: 'POST', body: { ...identity(), modal_tier: tier.value },
    })
    if (resp && resp.status && resp.status !== 'success') {
      throw Object.assign(new Error(resp.msg || 'Ujian belum bisa dimulai.'),
        { status: resp.status })
    }
    if (!resp?.data) throw new Error('Ujian belum bisa dimulai.')
    enterExam(resp.data)
  } catch (e) {
    const text = messageOf(e, 'Ujian belum bisa dimulai.')
    await loadStatus({ quiet: true })
    if (mode.value !== 'error') mode.value = 'intro'
    msg.value = text
  } finally {
    starting.value = false
  }
}

async function resume() {
  const id = status.value?.active_attempt?.id
  if (!id || resuming.value) return
  resuming.value = true
  msg.value = ''
  try {
    const resp = await api(`/api/recruitment/tkd/attempts/${encodeURIComponent(id)}`,
      { method: 'GET' })
    if (resp && resp.status && resp.status !== 'success') {
      throw Object.assign(new Error(resp.msg || 'Gagal melanjutkan ujian.'),
        { status: resp.status })
    }
    if (!resp?.data) throw new Error('Gagal melanjutkan ujian.')
    if (resp.data.finished) showResult(resp.data.result)
    else enterExam(resp.data)
  } catch (e) {
    msg.value = messageOf(e, 'Gagal melanjutkan ujian.')
  } finally {
    resuming.value = false
  }
}

async function persistAnswer() {
  if (saveTimer !== null) {
    clearTimeout(saveTimer)
    saveTimer = null
  }
  const pending = pendingSave
  pendingSave = null
  if (!pending || !attempt.value?.attempt_id) return
  try {
    const resp = await api(
      `/api/recruitment/tkd/attempts/${encodeURIComponent(attempt.value.attempt_id)}/answers/${pending.position}`,
      { method: 'PUT', body: pending.body })
    if (resp && resp.status && resp.status !== 'success') {
      throw Object.assign(new Error(resp.msg || 'Jawaban gagal disimpan.'),
        { status: resp.status, data: resp })
    }
    if (resp?.data?.result) {
      showResult(resp.data.result)
      return
    }
    if (!pendingSave) saveStatus.value = 'Tersimpan'
  } catch (e) {
    if (e?.status === 409 && (e?.data?.data || e?.data?.result)) {
      showResult(e.data.data || e.data.result)
      return
    }
    saveStatus.value = 'Gagal menyimpan'
    msg.value = messageOf(e, 'Jawaban gagal disimpan.')
  }
}

function answerOf(q) {
  const value = answers[q.position]
  if (!value || typeof value !== 'object') return ''
  if (q.type === 'MCQ') return value.option ?? ''
  if (q.type === 'NUMERIC') return value.value ?? ''
  return value.text ?? ''
}

function setAnswer(q, value) {
  let body
  if (q.type === 'MCQ') {
    body = { answer: { option: value } }
  } else if (q.type === 'NUMERIC') {
    body = { answer: { value } }
  } else {
    body = { answer: { text: value } }
  }
  answers[q.position] = body.answer
  if (saveTimer !== null) clearTimeout(saveTimer)
  pendingSave = { position: q.position, body }
  saveStatus.value = 'Menyimpan…'
  saveTimer = setTimeout(() => { void persistAnswer() }, 500)
}

async function flushSave() {
  if (saveTimer !== null) {
    clearTimeout(saveTimer)
    saveTimer = null
  }
  if (pendingSave) await persistAnswer()
}

async function submit() {
  // Guard submit ganda: tombol cepat dua kali / timer + tombol tidak boleh
  // mengirim dua permintaan finalize.
  if (submitting.value || mode.value !== 'exam' || !attempt.value?.attempt_id) return
  submitting.value = true
  stopTicker()
  await flushSave()
  if (mode.value !== 'exam') {
    submitting.value = false
    return
  }
  try {
    const resp = await api(
      `/api/recruitment/tkd/attempts/${encodeURIComponent(attempt.value.attempt_id)}/submit`,
      { method: 'POST' })
    if (resp && resp.status && resp.status !== 'success') {
      throw Object.assign(new Error(resp.msg || 'Ujian gagal dikumpulkan.'),
        { status: resp.status, data: resp })
    }
    showResult(resp?.data)
  } catch (e) {
    if (e?.status === 409 && e?.data?.data) {
      showResult(e.data.data)
    } else if (e?.status === 409 && e?.data?.result) {
      showResult(e.data.result)
    } else {
      msg.value = messageOf(e, 'Ujian gagal dikumpulkan. Coba lagi.')
      submitting.value = false
      if (mode.value === 'exam') startTicker()
      return
    }
  }
  submitting.value = false
}

async function retry() {
  result.value = null
  mode.value = 'intro'
  await loadStatus()
}

function close() {
  emit('close')
}

onMounted(async () => {
  await loadStatus()
  if (mode.value === 'loading') mode.value = 'intro'
})

onBeforeUnmount(() => {
  stopTicker()
  clearSave()
})
</script>

<template>
  <section class="tkd-panel" role="dialog" aria-modal="true" aria-label="Tes Kemampuan Dasar">
    <header class="tkd-head">
      <h2>Tes Kemampuan Dasar</h2>
      <button type="button" class="tkd-close" data-action="close" aria-label="Tutup" @click="close">
        Tutup ✕
      </button>
    </header>

    <div v-if="mode === 'loading'" class="tkd-state">Memuat status TKD…</div>

    <div v-else-if="mode === 'error'" class="tkd-state" role="alert">
      <p>{{ msg || 'Gagal memuat status TKD. Coba lagi.' }}</p>
      <button type="button" data-action="reload" @click="retry">Coba lagi</button>
    </div>

    <div v-else-if="mode === 'intro'">
      <p v-if="msg" class="tkd-msg" role="alert">{{ msg }}</p>
      <ul class="tkd-rules">
        <li>{{ fmt(rules.question_count) }} soal</li>
        <li>{{ fmt(rules.duration_minutes) }} menit</li>
        <li>lulus {{ fmt(rules.pass_score) }}</li>
        <li>{{ fmt(rules.max_attempts) }} kesempatan</li>
        <li>Tidak ada kunci atau pembahasan.</li>
      </ul>

      <p v-if="stateLabel" class="tkd-badge">{{ stateLabel }}</p>
      <p v-if="status && status.official_score !== null && status.official_score !== undefined">
        Skor resmi: {{ fmt(status.official_score) }}
      </p>
      <p v-if="status?.state === 'BERLANGSUNG'">
        Sisa waktu: <span data-timer>{{ timerText }}</span>
      </p>

      <div v-if="canStart" class="tkd-start">
        <label class="tkd-label" for="tkd-tier">Rencana modal</label>
        <select id="tkd-tier" v-model="tier" data-tier>
          <option v-for="item in TIERS" :key="item.value" :value="item.value">{{ item.label }}</option>
        </select>
        <button type="button" data-action="start" :disabled="starting" @click="start">
          {{ starting ? 'Menyiapkan…' : 'Mulai tes' }}
        </button>
      </div>
      <button v-else-if="status?.state === 'BERLANGSUNG'" type="button" data-action="resume"
        :disabled="resuming" @click="resume">
        {{ resuming ? 'Membuka…' : 'Lanjutkan' }}
      </button>
      <p v-else-if="status?.state === 'HABIS'">Hubungi Traineer cabang.</p>
      <p v-else-if="status?.state === 'DIKECUALIKAN'">Dikecualikan staff; hubungi Traineer.</p>
    </div>

    <div v-else-if="mode === 'exam' && question" class="tkd-exam">
      <div class="tkd-exam-head">
        <span data-question-count>Soal {{ index + 1 }} dari {{ questions.length }}</span>
        <span data-timer>{{ timerText }}</span>
      </div>
      <div class="tkd-progress" role="presentation">
        <span :style="{ width: progress + '%' }"></span>
      </div>
      <p v-if="question.category" class="tkd-category">{{ question.category }}</p>
      <p class="tkd-prompt">{{ question.prompt }}</p>

      <div v-if="question.type === 'MCQ'" class="tkd-options">
        <label v-for="opt in (question.options || [])" :key="opt.id" class="tkd-option">
          <input type="radio" :name="`tkd-soal-${question.position}`" :value="opt.id"
            :checked="answerOf(question) === opt.id" @change="setAnswer(question, opt.id)" />
          <span>{{ opt.text }}</span>
        </label>
      </div>
      <input v-else-if="question.type === 'NUMERIC'" class="tkd-input" type="number" step="any"
        :value="answerOf(question)" @input="setAnswer(question, $event.target.value)" />
      <input v-else-if="question.type === 'SHORT_TEXT'" class="tkd-input" type="text" maxlength="500"
        :value="answerOf(question)" @input="setAnswer(question, $event.target.value)" />
      <textarea v-else class="tkd-input" rows="5" maxlength="1000" :value="answerOf(question)"
        @input="setAnswer(question, $event.target.value)"></textarea>

      <p class="tkd-save" aria-live="polite">{{ saveStatus }}</p>
      <p v-if="msg" class="tkd-msg" role="alert">{{ msg }}</p>

      <nav class="tkd-nav">
        <button type="button" data-action="prev" :disabled="index === 0" @click="index -= 1">
          Sebelumnya
        </button>
        <button v-if="index < questions.length - 1" type="button" data-action="next"
          @click="index += 1">
          Berikutnya
        </button>
        <button v-else type="button" data-action="submit" :disabled="submitting" @click="submit">
          {{ submitting ? 'Mengirim…' : 'Selesai' }}
        </button>
      </nav>
    </div>

    <div v-else-if="mode === 'result'" class="tkd-result">
      <h3>Hasil ujian</h3>
      <p v-if="result?.score !== null && result?.score !== undefined">
        Nilai percobaan: {{ fmt(result.score) }}
      </p>
      <p v-if="result?.official_score !== null && result?.official_score !== undefined">
        Skor resmi: {{ fmt(result.official_score) }}
      </p>
      <p :class="result?.passed ? 'tkd-pass' : 'tkd-fail'">
        {{ result?.passed ? 'Lulus' : 'Tidak lulus' }}
      </p>
      <p v-if="remainingAttempts !== null">Sisa kesempatan: {{ remainingAttempts }}</p>
      <p v-if="result?.msg">{{ result.msg }}</p>
      <button v-if="canRetry" type="button" data-action="retry" @click="retry">Coba lagi</button>
      <p v-else>Hubungi Traineer cabang.</p>
    </div>
  </section>
</template>

<style scoped>
.tkd-panel {
  margin: 24px auto 0;
  max-width: 680px;
  padding: 20px;
  border: 1px solid #d1d5db;
  border-radius: 12px;
  background: #fff;
  font-family: system-ui, -apple-system, sans-serif;
  color: #1f2937;
  box-shadow: 0 8px 24px rgb(15 23 42 / 12%);
}
.tkd-head { display: flex; align-items: center; justify-content: space-between; }
.tkd-head h2 { font-size: 1.15rem; margin: 0; }
.tkd-close, .tkd-start button, .tkd-nav button, .tkd-result button, .tkd-state button {
  padding: 8px 14px;
  border: 1px solid #1d4ed8;
  border-radius: 8px;
  background: #fff;
  color: #1d4ed8;
  font-weight: 600;
  cursor: pointer;
}
.tkd-start button, .tkd-result button { background: #1d4ed8; color: #fff; }
button:disabled { opacity: 0.5; cursor: default; }
.tkd-rules { line-height: 1.7; }
.tkd-badge { font-weight: 700; color: #1d4ed8; }
.tkd-msg { color: #b91c1c; }
.tkd-label { display: block; font-weight: 600; margin-bottom: 6px; }
.tkd-start select { padding: 8px; margin-right: 8px; border-radius: 8px; }
.tkd-state { padding: 16px 0; }
.tkd-exam-head { display: flex; justify-content: space-between; font-weight: 600; }
.tkd-progress { height: 6px; background: #e5e7eb; border-radius: 6px; margin: 10px 0 16px; }
.tkd-progress span { display: block; height: 100%; background: #1d4ed8; border-radius: 6px; }
.tkd-category { color: #6b7280; font-size: 0.85rem; margin: 0; }
.tkd-prompt { font-size: 1rem; line-height: 1.5; }
.tkd-options { display: grid; gap: 8px; }
.tkd-option { display: flex; gap: 8px; align-items: center; }
.tkd-input { width: 100%; box-sizing: border-box; padding: 10px; border: 1px solid #d1d5db; border-radius: 8px; }
.tkd-save { color: #6b7280; font-size: 0.85rem; min-height: 1.2em; }
.tkd-nav { display: flex; gap: 8px; justify-content: space-between; }
.tkd-pass { color: #15803d; font-weight: 700; }
.tkd-fail { color: #b91c1c; font-weight: 700; }
</style>
