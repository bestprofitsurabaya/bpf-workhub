<script setup>
import { ref, computed, onMounted, onBeforeUnmount } from 'vue'
import { api } from '../api'
import EmptyState from '../components/EmptyState.vue'

// ---------------------------------------------------------------- state
const urls = ref('')                 // textarea multi-link (per baris / koma)
const formats = ref([])              // format terpilih
const busy = ref(false)
const err = ref('')
const ok = ref('')
const jobs = ref([])
let pollTimer = null            // handle setTimeout siklus polling
let pollAbort = null            // AbortController request in-flight
let pollDelay = 10000
const filter = ref('all')            // all | running | done | failed
const copied = ref('')

const KINDS = [
  { key: 'audio', label: '🎧 Audio', formats: [
    { key: 'mp3', label: 'MP3 192 kbps', hint: 'universal' },
    { key: 'm4a', label: 'M4A (AAC) 128', hint: 'kecil, HP' },
    { key: 'wav', label: 'WAV', hint: 'tanpa kompresi' },
  ]},
  { key: 'video', label: '🎬 Video', formats: [
    { key: 'mp4', label: 'MP4 720p', hint: 'standar' },
    { key: 'mp4hd', label: 'MP4 1080p', hint: 'HD, berat' },
    { key: 'webm', label: 'WebM', hint: 'ringan' },
    { key: 'mkv', label: 'MKV', hint: 'salin ulang, cepat' },
  ]},
]

const parsedUrls = computed(() =>
  urls.value.split(/[\n,]+/).map(u => u.trim()).filter(Boolean)
)
const canSubmit = computed(() => parsedUrls.value.length > 0 && formats.value.length > 0 && !busy.value)
const urlCount = computed(() => parsedUrls.value.length)

const filteredJobs = computed(() => {
  if (filter.value === 'all') return jobs.value
  if (filter.value === 'running') return jobs.value.filter(j => ['queued', 'downloading', 'transcoding'].includes(j.status))
  if (filter.value === 'done') return jobs.value.filter(j => j.status === 'done')
  return jobs.value.filter(j => j.status === 'error' || j.status === 'cancelled')
})

const runningCount = computed(() =>
  jobs.value.filter(j => ['queued', 'downloading', 'transcoding'].includes(j.status)).length
)

const fmtSize = (b) => {
  if (!b) return '–'
  if (b < 1024 * 1024) return (b / 1024).toFixed(0) + ' KB'
  if (b < 1024 * 1024 * 1024) return (b / 1024 / 1024).toFixed(1) + ' MB'
  return (b / 1024 / 1024 / 1024).toFixed(2) + ' GB'
}
const fmtTime = (ts) => {
  if (!ts) return ''
  return new Date(ts * 1000).toLocaleString('id-ID', { day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit' })
}

const STATUS_BADGE = {
  queued:    { cls: 'b-queued',  label: '⏳ Antrean' },
  downloading: { cls: 'b-down',  label: '⬇️ Unduh' },
  transcoding: { cls: 'b-trans', label: '⚙️ Konversi' },
  done:      { cls: 'b-done',   label: '✅ Selesai' },
  error:     { cls: 'b-error',  label: '❌ Gagal' },
  cancelled: { cls: 'b-cancel', label: '🚫 Dibatalkan' },
}
const badge = (s) => STATUS_BADGE[s] || { cls: '', label: s }

// ---------------------------------------------------------------- aksi
function toggleFormat(k) {
  const i = formats.value.indexOf(k)
  if (i >= 0) formats.value.splice(i, 1)
  else formats.value.push(k)
}

async function loadJobs(signal) {
  try {
    const d = await api('/api/transcoder/jobs', { signal })
    jobs.value = d.jobs || []
  } catch (e) {
    if (e?.name === 'AbortError') return  // pembatalan sadar — bukan error
    err.value = e.message
  }
}

async function submit() {
  err.value = ''; ok.value = ''
  if (!canSubmit.value) return
  busy.value = true
  try {
    await api('/api/transcoder/jobs', {
      method: 'POST',
      body: { urls: parsedUrls.value, formats: formats.value },
    })
    ok.value = `Job dibuat — ${urlCount.value} link × ${formats.value.length} format`
    urls.value = ''
    await loadJobs()
  } catch (e) {
    err.value = e.message
  } finally {
    busy.value = false
  }
}

async function cancelJob(j) {
  if (!confirm(`Batalkan job ${j.id}? Proses unduhan/konversi yang sedang jalan dihentikan.`)) return
  try {
    await api(`/api/transcoder/jobs/${j.id}/cancel`, { method: 'POST' })
    await loadJobs()
  } catch (e) { err.value = e.message }
}

async function removeJob(j) {
  const nOut = (j.items || []).reduce((a, it) => a + (it.outputs?.length || 0), 0)
  if (!confirm(`Hapus job ${j.id}${nOut ? ` beserta ${nOut} berkas hasil` : ''}? Tidak bisa dibatalkan.`)) return
  try {
    await api(`/api/transcoder/jobs/${j.id}`, { method: 'DELETE' })
    await loadJobs()
  } catch (e) { err.value = e.message }
}

async function downloadAll(j) {
  const files = []
  for (const it of j.items || []) {
    for (const o of it.outputs || []) files.push({ job: j.id, file: o.file })
  }
  for (const f of files) {
    const a = document.createElement('a')
    a.href = `/api/transcoder/download/${f.job}/${encodeURIComponent(f.file)}`
    a.download = f.file
    document.body.appendChild(a); a.click(); a.remove()
    await new Promise(r => setTimeout(r, 400))
  }
}

function copyLink(j) {
  const text = (j.items || [])
    .flatMap(it => (it.outputs || []).map(o => `${location.origin}/api/transcoder/download/${j.id}/${encodeURIComponent(o.file)}`))
    .join('\n')
  navigator.clipboard?.writeText(text)
  copied.value = j.id
  setTimeout(() => { copied.value = '' }, 1500)
}

// polling: cepat saat ada job jalan, lambat saat idle;
// JEDA otomatis saat tab hidden (visibilitychange) — request tidak lagi
// "terbang" saat tab ditutup/dipindah sehingga console bersih dari
// FetchEvent/abort noise, sekaligus hemat resource server & baterai.
function schedulePoll(delay = pollDelay) {
  clearTimeout(pollTimer)
  if (document.hidden) return
  pollTimer = setTimeout(pollOnce, delay)
}

async function pollOnce() {
  pollAbort?.abort()
  pollAbort = new AbortController()
  await loadJobs(pollAbort.signal)
  pollDelay = runningCount.value ? 2000 : 10000
  schedulePoll(pollDelay)
}

function onVisibility() {
  if (document.hidden) {
    clearTimeout(pollTimer)
    pollAbort?.abort()
  } else {
    pollOnce()  // tab kembali aktif — segarkan langsung
  }
}

onMounted(async () => {
  document.addEventListener('visibilitychange', onVisibility)
  await pollOnce()
})
onBeforeUnmount(() => {
  document.removeEventListener('visibilitychange', onVisibility)
  clearTimeout(pollTimer)
  pollAbort?.abort()
})
</script>

<template>
  <div class="page">
    <header class="head">
      <div>
        <h1>🎬 Transcoder</h1>
        <p class="sub">Konversi link YouTube ke berbagai format audio & video — beberapa link sekaligus.</p>
      </div>
      <div v-if="runningCount" class="run-pill">⚙️ {{ runningCount }} job berjalan</div>
    </header>

    <div v-if="err" class="banner b-err">⚠️ {{ err }} <button class="x" @click="err=''">✕</button></div>
    <div v-if="ok" class="banner b-ok">✅ {{ ok }} <button class="x" @click="ok=''">✕</button></div>

    <!-- ===================== FORM SUBMIT ===================== -->
    <section class="card">
      <h2>Job Baru</h2>
      <div class="grid2">
        <div class="col">
          <label class="lbl">🔗 Link YouTube <span class="muted">(satu per baris atau koma, maks 10)</span></label>
          <textarea v-model="urls" rows="5" class="ta"
            placeholder="https://www.youtube.com/watch?v=...&#10;https://youtu.be/...&#10;https://www.youtube.com/watch?v=..."></textarea>
          <div class="hint-row">
            <span :class="{ over: urlCount > 10 }">{{ urlCount }}/10 link</span>
            <button v-if="urlCount" class="btn btn-ghost btn-xs" @click="urls=''">Bersihkan</button>
          </div>
        </div>
        <div class="col">
          <label class="lbl">📦 Format Output <span class="muted">(boleh lebih dari satu)</span></label>
          <div v-for="g in KINDS" :key="g.key" class="fgroup">
            <div class="flabel">{{ g.label }}</div>
            <div class="chips">
              <button v-for="f in g.formats" :key="f.key" type="button"
                class="chip" :class="{ on: formats.includes(f.key) }"
                :aria-pressed="formats.includes(f.key)"
                @click="toggleFormat(f.key)">
                {{ f.label }} <small>{{ f.hint }}</small>
              </button>
            </div>
          </div>
        </div>
      </div>
      <div class="actions">
        <button class="btn btn-primary" :disabled="!canSubmit" @click="submit">
          {{ busy ? 'Membuat job…' : `🚀 Mulai Konversi${urlCount ? ` (${urlCount} link)` : ''}` }}
        </button>
        <span class="muted">Hasil tersimpan di server 48 jam — unduh sebelum terhapus otomatis.</span>
      </div>
    </section>

    <!-- ===================== DAFTAR JOB ===================== -->
    <section class="card">
      <div class="list-head">
        <h2>Histori & Hasil</h2>
        <div class="tabs">
          <button v-for="t in [['all','Semua'],['running','Berjalan'],['done','Selesai'],['failed','Gagal/Batal']]" :key="t[0]"
            class="tab" :class="{ on: filter === t[0] }" @click="filter = t[0]">{{ t[1] }}</button>
        </div>
      </div>

      <EmptyState v-if="!filteredJobs.length" icon="📥"
        message="Belum ada job" hint="Tempel link YouTube di atas lalu pilih format output." />

      <div v-for="j in filteredJobs" :key="j.id" class="job">
        <div class="job-head">
          <div class="job-id">
            <span class="badge" :class="badge(j.status).cls">{{ badge(j.status).label }}</span>
            <strong>{{ j.id }}</strong>
            <span class="muted">· {{ j.urls.length }} link · {{ j.formats.join(', ') }} · {{ fmtTime(j.created_at) }}</span>
          </div>
          <div class="job-actions">
            <button v-if="['queued','downloading','transcoding'].includes(j.status)"
              class="btn btn-ghost btn-xs" @click="cancelJob(j)">🚫 Batalkan</button>
            <button v-if="j.status === 'done'" class="btn btn-ghost btn-xs" @click="downloadAll(j)">⬇️ Unduh semua</button>
            <button v-if="j.status === 'done'" class="btn btn-ghost btn-xs" @click="copyLink(j)">
              {{ copied === j.id ? '✔ Tersalin' : '🔗 Salin tautan' }}</button>
            <button v-if="['done','error','cancelled'].includes(j.status)"
              class="btn btn-danger btn-xs" @click="removeJob(j)">🗑 Hapus</button>
          </div>
        </div>

        <div class="progress-wrap" v-if="['queued','downloading','transcoding'].includes(j.status)">
          <div class="bar"><div class="fill" :style="{ width: Math.max(j.progress, 3) + '%' }" :class="{ pulse: j.status !== 'queued' }"></div></div>
          <span class="pct">{{ j.stage }} {{ j.progress ? j.progress + '%' : '' }}</span>
        </div>
        <div v-else-if="j.stage" class="muted small">{{ j.stage }}</div>

        <div class="items">
          <div v-for="(it, i) in j.items" :key="i" class="item" :class="'it-' + it.status">
            <div class="item-title">
              <span class="ico">{{ it.status === 'done' ? '🎵' : it.status === 'error' ? '⚠️' : '⏳' }}</span>
              <span class="t">{{ it.title || it.url }}</span>
              <span v-if="it.error" class="err" :title="it.error">— {{ it.error }}</span>
            </div>
            <div class="outputs">
              <a v-for="o in it.outputs" :key="o.file"
                class="out" :href="`/api/transcoder/download/${j.id}/${encodeURIComponent(o.file)}`"
                :download="o.file" :title="`Unduh ${o.label} (${fmtSize(o.size)})`">
                {{ o.kind === 'audio' ? '🎧' : '🎞️' }} {{ o.label }} <small>{{ fmtSize(o.size) }}</small> ⬇️
              </a>
              <span v-if="it.status !== 'error' && !it.outputs.length" class="muted small">menyiapkan…</span>
            </div>
          </div>
        </div>
      </div>
    </section>
  </div>
</template>

<style scoped>
.page { display: flex; flex-direction: column; gap: 16px; }
.head { display: flex; align-items: flex-start; justify-content: space-between; gap: 12px; flex-wrap: wrap; }
h1 { margin: 0; font-size: 22px; }
h2 { margin: 0 0 12px; font-size: 15px; }
.sub { margin: 4px 0 0; font-size: 13px; color: var(--text-2, #64748b); }
.run-pill { font-size: 13px; background: color-mix(in srgb, var(--primary, #2563eb) 12%, transparent); color: var(--primary, #2563eb); border-radius: 999px; padding: 6px 14px; font-weight: 600; }

.banner { border-radius: 10px; padding: 10px 14px; font-size: 13px; display: flex; align-items: center; gap: 8px; }
.b-err { background: color-mix(in srgb, var(--danger, #dc2626) 10%, transparent); color: var(--danger, #b91c1c); }
.b-ok  { background: color-mix(in srgb, var(--success, #16a34a) 12%, transparent); color: var(--success, #15803d); }
.x { margin-left: auto; background: none; border: 0; cursor: pointer; color: inherit; }

.card { background: var(--surface, #fff); border: 1px solid var(--border, #e2e8f0); border-radius: 14px; padding: 18px; }
.grid2 { display: grid; grid-template-columns: 1fr 1fr; gap: 20px; }
@media (max-width: 860px) { .grid2 { grid-template-columns: 1fr; } }
.lbl { display: block; font-weight: 600; font-size: 13px; margin-bottom: 8px; }
.muted { color: var(--text-2, #64748b); font-weight: 400; }
.small { font-size: 12px; }

.ta { width: 100%; box-sizing: border-box; border: 1px solid var(--border, #cbd5e1); border-radius: 10px; padding: 10px 12px; font: 13px/1.6 ui-monospace, monospace; resize: vertical; background: var(--bg, #f8fafc); color: var(--text, #0f172a); }
.ta:focus { outline: 2px solid var(--primary, #2563eb); border-color: transparent; }
.hint-row { display: flex; justify-content: space-between; align-items: center; margin-top: 6px; font-size: 12px; color: var(--text-2, #64748b); }
.over { color: var(--danger, #dc2626); font-weight: 700; }

.fgroup { margin-bottom: 12px; }
.flabel { font-size: 12px; font-weight: 700; margin-bottom: 6px; color: var(--text-2, #475569); }
.chips { display: flex; flex-wrap: wrap; gap: 8px; }
.chip { border: 1.5px solid var(--border, #cbd5e1); background: var(--bg, #f8fafc); color: var(--text, #0f172a); border-radius: 999px; padding: 6px 13px; font-size: 13px; cursor: pointer; transition: all .15s; display: inline-flex; gap: 6px; align-items: baseline; }
.chip small { font-size: 10.5px; opacity: .65; }
.chip:hover { border-color: var(--primary, #2563eb); }
.chip.on { background: var(--primary, #2563eb); border-color: var(--primary, #2563eb); color: #fff; }
.chip.on small { opacity: .8; }
.chip:focus-visible { outline: 2px solid var(--primary, #2563eb); outline-offset: 2px; }

.actions { display: flex; align-items: center; gap: 14px; margin-top: 16px; flex-wrap: wrap; font-size: 12.5px; }
.btn { border: 0; border-radius: 10px; padding: 10px 18px; font-size: 14px; font-weight: 600; cursor: pointer; transition: filter .15s; }
.btn:disabled { opacity: .45; cursor: not-allowed; }
.btn-primary { background: var(--primary, #2563eb); color: #fff; }
.btn-primary:not(:disabled):hover { filter: brightness(1.08); }
.btn-ghost { background: transparent; border: 1px solid var(--border, #cbd5e1); color: var(--text, #0f172a); }
.btn-ghost:hover { border-color: var(--primary, #2563eb); color: var(--primary, #2563eb); }
.btn-danger { background: transparent; border: 1px solid var(--danger, #fca5a5); color: var(--danger, #dc2626); }
.btn-danger:hover { background: color-mix(in srgb, var(--danger, #dc2626) 10%, transparent); }
.btn-xs { padding: 5px 11px; font-size: 12.5px; border-radius: 8px; }

.list-head { display: flex; justify-content: space-between; align-items: center; gap: 10px; flex-wrap: wrap; margin-bottom: 10px; }
.tabs { display: flex; gap: 4px; background: var(--bg, #f1f5f9); border-radius: 10px; padding: 3px; }
.tab { border: 0; background: transparent; padding: 6px 13px; font-size: 12.5px; border-radius: 8px; cursor: pointer; color: var(--text-2, #475569); }
.tab.on { background: var(--surface, #fff); color: var(--text, #0f172a); font-weight: 700; box-shadow: 0 1px 3px rgba(2,6,23,.12); }

.job { border: 1px solid var(--border, #e2e8f0); border-radius: 12px; padding: 13px 15px; margin-top: 12px; }
.job-head { display: flex; justify-content: space-between; align-items: center; gap: 10px; flex-wrap: wrap; }
.job-id { display: flex; align-items: center; gap: 8px; font-size: 13.5px; flex-wrap: wrap; }
.job-actions { display: flex; gap: 6px; flex-wrap: wrap; }
.badge { font-size: 11.5px; font-weight: 700; border-radius: 999px; padding: 3px 10px; white-space: nowrap; }
.b-queued { background: #f1f5f9; color: #475569; }
.b-down  { background: color-mix(in srgb, #f59e0b 15%, transparent); color: #b45309; }
.b-trans { background: color-mix(in srgb, #8b5cf6 15%, transparent); color: #6d28d9; }
.b-done  { background: color-mix(in srgb, #16a34a 14%, transparent); color: #15803d; }
.b-error { background: color-mix(in srgb, #dc2626 12%, transparent); color: #b91c1c; }
.b-cancel{ background: #f1f5f9; color: #94a3b8; }

.progress-wrap { display: flex; align-items: center; gap: 12px; margin: 12px 0 4px; }
.bar { flex: 1; height: 9px; background: var(--bg, #e2e8f0); border-radius: 999px; overflow: hidden; }
.fill { height: 100%; background: linear-gradient(90deg, var(--primary, #2563eb), #7c3aed); border-radius: 999px; transition: width .6s ease; }
.fill.pulse { animation: shimmer 1.6s linear infinite; background-size: 200% 100%; }
@keyframes shimmer { 0% { background-position: 200% 0; } 100% { background-position: -200% 0; } }
.pct { font-size: 12px; color: var(--text-2, #475569); white-space: nowrap; font-variant-numeric: tabular-nums; }

.items { margin-top: 10px; display: flex; flex-direction: column; gap: 8px; }
.item { border: 1px solid var(--border, #eef2f7); border-radius: 10px; padding: 9px 12px; }
.it-error { border-color: color-mix(in srgb, var(--danger, #dc2626) 30%, transparent); background: color-mix(in srgb, var(--danger, #dc2626) 4%, transparent); }
.item-title { display: flex; gap: 8px; align-items: baseline; font-size: 13.5px; flex-wrap: wrap; }
.item-title .t { font-weight: 600; word-break: break-word; }
.err { font-size: 12px; color: var(--danger, #dc2626); }
.outputs { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 7px; }
.out { display: inline-flex; align-items: center; gap: 6px; font-size: 12.5px; font-weight: 600; text-decoration: none; border: 1px solid var(--border, #cbd5e1); border-radius: 8px; padding: 5px 11px; color: var(--text, #0f172a); transition: all .15s; }
.out small { font-weight: 400; opacity: .6; }
.out:hover { border-color: var(--primary, #2563eb); color: var(--primary, #2563eb); transform: translateY(-1px); }
</style>
