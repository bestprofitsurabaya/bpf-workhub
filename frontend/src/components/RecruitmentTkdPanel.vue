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
  session: { type: String, default: '' },
  // Fallback untuk tautan langsung tanpa sesi portal (Rilis A).
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
const closeBtn = ref(null)
let lastFocus = null

const TIERS = [
  { value: '30k', label: '$30.000' },
  { value: '50k', label: '$50.000' },
  { value: '100k', label: '$100.000' },
]

let ticker = null
let saveTimer = null
let disposed = false
// Satu slot pending tidak cukup: jawaban soal sebelumnya bisa tertimpa sebelum
// sempat dikirim. Simpan satu entri per posisi soal.
const pendingSaves = new Map()
const inflight = new Set()

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

// Angka kosong/tidak valid tidak boleh dianggap 0: lebih aman menolak.
function attemptNumbers() {
  const source = result.value || status.value || {}
  const used = source.attempts_used
  const max = source.max_attempts
  if ([used, max].some((v) => v === undefined || v === null || v === '')) return null
  const usedN = Number(used)
  const maxN = Number(max)
  if (!Number.isFinite(usedN) || !Number.isFinite(maxN)) return null
  return { used: usedN, max: maxN }
}

// Setelah submit, hasil dari server yang berwenang menentukan kesempatan.
// Status lama boleh basi (misal refresh gagal), jadi tidak boleh dipakai.
const canRetry = computed(() => {
  if (!result.value) return Boolean(status.value?.can_start)
  const numbers = attemptNumbers()
  return result.value.state === 'BISA_COBA' && Boolean(numbers) && numbers.used < numbers.max
})
const remainingAttempts = computed(() => {
  const numbers = attemptNumbers()
  return numbers ? Math.max(0, numbers.max - numbers.used) : null
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
  const body = { token: props.token }
  if (props.session) {
    body.s = props.session
  } else {
    body.nik = props.nik
    body.dob = props.dob
  }
  return body
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
  pendingSaves.clear()
}

function seedExpiry(data) {
  // `remaining_seconds` adalah sumber waktu resmi dari server. `expires_at`
  // tidak membawa zona waktu, jadi jangan dipakai lebih dulu: perangkat di
  // zona lain bisa menghitung sisa waktu yang salah.
  const rawRemaining = data?.remaining_seconds
  const remaining = Number(rawRemaining)
  const hasRemaining = rawRemaining !== undefined && rawRemaining !== null
    && rawRemaining !== ''
  if (hasRemaining && Number.isFinite(remaining) && remaining >= 0) {
    expiresMs.value = Date.now() + remaining * 1000
  } else {
    const rawExpiry = String(data?.expires_at || '').replace(' ', 'T')
    const parsed = Date.parse(rawExpiry)
    expiresMs.value = Number.isFinite(parsed) ? parsed : 0
  }
  startTicker()
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
    // Ujian yang masih berlangsung punya deadline di payload status. Tampilkan
    // hitung mundurnya sejak intro; ticker tidak akan mengirim submit di intro.
    if (status.value?.state === 'BERLANGSUNG' && status.value?.active_attempt) {
      seedExpiry(status.value.active_attempt)
    } else if (mode.value !== 'exam') {
      stopTicker()
    }
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

  seedExpiry(data)
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

// Satu PUT = satu janji yang tercatat. Menyimpan promise-nya membuat submit
// bisa menunggu semua penulisan jawaban selesai sebelum mengeksekusi grading.
function sendSave(position, body) {
  const attemptId = attempt.value?.attempt_id
  if (!attemptId) return Promise.resolve(false)
  const task = (async () => {
    try {
      const resp = await api(
        `/api/recruitment/tkd/attempts/${encodeURIComponent(attemptId)}/answers/${position}`,
        { method: 'PUT', body })
      if (resp && resp.status && resp.status !== 'success') {
        throw Object.assign(new Error(resp.msg || 'Jawaban gagal disimpan.'),
          { status: resp.status, data: resp })
      }
      if (resp?.data?.result) showResult(resp.data.result)
      return true
    } catch (e) {
      if (e?.status === 409 && (e?.data?.data || e?.data?.result)) {
        showResult(e.data.data || e.data.result)
        return true
      }
      saveStatus.value = 'Gagal menyimpan'
      msg.value = messageOf(e, 'Jawaban gagal disimpan.')
      // Kembali antre supaya klik Selesai/berpindah soal berikutnya bisa retry.
      if (!disposed && mode.value === 'exam' && attempt.value?.attempt_id === attemptId) {
        pendingSaves.set(position, body)
      }
      return false
    }
  })()
  inflight.add(task)
  const done = () => inflight.delete(task)
  task.then(done, done)
  return task
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
  pendingSaves.set(q.position, body)
  saveStatus.value = 'Menyimpan…'
  saveTimer = setTimeout(() => { void flushSave() }, 500)
}

// Kirim semua posisi yang tertunda dan tunggu baik PUT lama maupun PUT baru.
// Mengembalikan false bila ada yang gagal, sehingga submit bisa dibatalkan.
async function flushSave() {
  if (saveTimer !== null) {
    clearTimeout(saveTimer)
    saveTimer = null
  }
  const queued = [...pendingSaves.entries()]
  pendingSaves.clear()
  const running = [...inflight]
  const sends = queued.map(([position, body]) => sendSave(position, body))
  const results = await Promise.allSettled([...running, ...sends])
  const ok = results.every((r) => r.status === 'fulfilled' && r.value !== false)
  if (ok && pendingSaves.size === 0 && (queued.length || running.length)) {
    saveStatus.value = 'Tersimpan'
  }
  return ok
}

async function submit() {
  // Guard submit ganda: tombol cepat dua kali / timer + tombol tidak boleh
  // mengirim dua permintaan finalize.
  if (submitting.value || mode.value !== 'exam' || !attempt.value?.attempt_id) return
  submitting.value = true
  stopTicker()
  const saved = await flushSave()
  if (!saved) {
    // Jangan grading dari jawaban yang belum tersimpan di server.
    msg.value = msg.value || 'Gagal menyimpan jawaban. Coba lagi.'
    saveStatus.value = 'Gagal menyimpan'
    submitting.value = false
    if (mode.value === 'exam' && remainingSeconds.value > 0) startTicker()
    return
  }
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
      // Pada nol detik tidak ada auto-submit lagi: pelamar klik Selesai sendiri.
      if (mode.value === 'exam' && remainingSeconds.value > 0) startTicker()
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

async function goPrev() {
  if (index.value === 0) return
  await flushSave()
  if (mode.value === 'exam') index.value -= 1
}

async function goNext() {
  if (index.value >= questions.value.length - 1) return
  await flushSave()
  if (mode.value === 'exam') index.value += 1
}

async function close() {
  try {
    await flushSave()
  } finally {
    emit('close')
  }
}

onMounted(async () => {
  lastFocus = document.activeElement
  // Panel bukan modal (dirender inline di portal), jadi Tab tidak ditahan.
  // Fokus dipindah ke tombol tutup; Escape ditangani di elemen section.
  closeBtn.value?.focus?.()
  await loadStatus()
  if (mode.value === 'loading') mode.value = 'intro'
})

onBeforeUnmount(() => {
  disposed = true
  lastFocus?.focus?.()
  stopTicker()
  const queued = [...pendingSaves.entries()]
  clearSave()
  // Best effort: PUT tetap dikirim walau komponen sudah tidak dirender.
  for (const [position, body] of queued) void sendSave(position, body)
})
</script>

<template>
  <section class="tkd-panel" role="dialog" aria-label="Tes Kemampuan Dasar"
           @keydown.esc.prevent="close">
    <header class="tkd-head">
      <h2>Tes Kemampuan Dasar</h2>
      <button ref="closeBtn" type="button" class="tkd-close" data-action="close"
              aria-label="Tutup" @click="close">
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
        <button type="button" data-action="prev" :disabled="index === 0" @click="goPrev">
          Sebelumnya
        </button>
        <button v-if="index < questions.length - 1" type="button" data-action="next"
          @click="goNext">
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
      <p v-if="result?.message || result?.msg">{{ result?.message || result?.msg }}</p>
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
