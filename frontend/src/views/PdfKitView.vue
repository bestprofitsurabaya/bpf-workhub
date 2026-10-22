<script setup>
import { ref, computed, onMounted, onBeforeUnmount } from 'vue'
import { api } from '../api'
import EmptyState from '../components/EmptyState.vue'
import ConfirmDialog from '../components/ConfirmDialog.vue'

const confirmRef = ref(null)
const ask = (message, opts) => confirmRef.value?.open(message, opts) ?? Promise.resolve(false)

// ---------------------------------------------------------------- state
const files = ref([])                 // File[] yang dipilih (belum diunggah)
const mode = ref('ringan')
const targetMb = ref(0.5)
const modes = ref([])
const limits = ref({ max_files: 10, max_file_mb: 100, max_total_mb: 250 })
const busy = ref(false)
const err = ref('')
const ok = ref('')
const jobs = ref([])
const filter = ref('all')
const dragOver = ref(false)
const fileInput = ref(null)
let pollTimer = null
let pollAbort = null
let pollDelay = 10000

const STATUS_BADGE = {
  queued:    { cls: 'b-queued', label: '⏳ Antrean' },
  running:   { cls: 'b-run',    label: '⚙️ Mengompres' },
  done:      { cls: 'b-done',   label: '✅ Selesai' },
  error:     { cls: 'b-error',  label: '❌ Gagal' },
  cancelled: { cls: 'b-cancel', label: '🚫 Dibatalkan' },
}
const ITEM_BADGE = {
  pending:   { cls: 'b-queued',  ico: '⏳', label: 'Menunggu' },
  running:   { cls: 'b-run',     ico: '⚙️', label: 'Diproses' },
  done:      { cls: 'b-done',    ico: '✅', label: 'Selesai' },
  skipped:   { cls: 'b-skip',    ico: '➖', label: 'Dilewati' },
  protected: { cls: 'b-prot',    ico: '🛡️', label: 'Dilindungi' },
  error:     { cls: 'b-error',   ico: '❌', label: 'Gagal' },
}
const badge = (s) => STATUS_BADGE[s] || { cls: '', label: s }
const itemBadge = (s) => ITEM_BADGE[s] || { cls: '', ico: '•', label: s }

const activeModes = computed(() => modes.value.length ? modes.value : [
  { key: 'lossless', label: 'Lossless (aman)', hint: '', needs_target: false },
  { key: 'ringan', label: 'Ringan — 150 dpi', hint: '', needs_target: false },
])
const needsTarget = computed(() => !!activeModes.value.find(m => m.key === mode.value)?.needs_target)
const totalMb = computed(() => files.value.reduce((a, f) => a + f.size, 0) / (1024 * 1024))
const runningCount = computed(() => jobs.value.filter(j => ['queued', 'running'].includes(j.status)).length)
const filteredJobs = computed(() => {
  if (filter.value === 'all') return jobs.value
  if (filter.value === 'running') return jobs.value.filter(j => ['queued', 'running'].includes(j.status))
  if (filter.value === 'done') return jobs.value.filter(j => j.status === 'done')
  return jobs.value.filter(j => ['error', 'cancelled'].includes(j.status))
})
const canSubmit = computed(() => files.value.length > 0 && !busy.value && !overLimit.value)
const overLimit = computed(() =>
  files.value.length > limits.value.max_files || totalMb.value > limits.value.max_total_mb)

const fmtSize = (b) => {
  if (!b) return '–'
  if (b < 1024) return b + ' B'
  if (b < 1024 * 1024) return (b / 1024).toFixed(0) + ' KB'
  return (b / 1024 / 1024).toFixed(2) + ' MB'
}
const fmtTime = (ts) => ts
  ? new Date(ts * 1000).toLocaleString('id-ID', { day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit' })
  : ''

// ---------------------------------------------------------------- pilih berkas
function addFiles(list) {
  const picked = Array.from(list || [])
  const rejected = []
  for (const f of picked) {
    if (!/\.pdf$/i.test(f.name)) { rejected.push(`${f.name} (bukan PDF)`); continue }
    if (f.size > limits.value.max_file_mb * 1024 * 1024) {
      rejected.push(`${f.name} (> ${limits.value.max_file_mb} MB)`); continue
    }
    if (files.value.some(x => x.name === f.name && x.size === f.size)) continue   // duplikat
    files.value.push(f)
  }
  if (rejected.length) err.value = `Ditolak: ${rejected.join(', ')}`
}

function onPick(e) {
  addFiles(e.target.files)
  if (fileInput.value) fileInput.value.value = ''    // boleh pilih berkas sama lagi
}

function onDrop(e) {
  dragOver.value = false
  addFiles(e.dataTransfer?.files)
}

function removeFile(i) {
  files.value.splice(i, 1)
}

// ---------------------------------------------------------------- muat & aksi
async function loadInit() {
  try {
    const d = await api('/api/pdfkit/modes')
    modes.value = d.modes || []
    if (d.limits) limits.value = d.limits
  } catch (e) { err.value = e.message }
}

async function loadJobs(signal) {
  try {
    const d = await api('/api/pdfkit/jobs', { signal })
    jobs.value = d.jobs || []
  } catch (e) {
    if (e?.name === 'AbortError') return   // pembatalan sadar — bukan error
    err.value = e.message
  }
}

async function submit() {
  err.value = ''; ok.value = ''
  if (!canSubmit.value) return
  busy.value = true
  try {
    const fd = new FormData()
    fd.append('mode', mode.value)
    if (needsTarget.value) fd.append('target_mb', String(targetMb.value))
    for (const f of files.value) fd.append('files', f)
    const csrf = localStorage.getItem('bpf_csrf') || sessionStorage.getItem('bpf_csrf') || ''
    const r = await fetch('/api/pdfkit/jobs', {
      method: 'POST', body: fd,
      headers: { Accept: 'application/json', ...(csrf ? { 'X-CSRF-Token': csrf } : {}) },
    })
    const d = await r.json().catch(() => null)
    if (!r.ok) throw new Error((d && d.msg) || `HTTP ${r.status}`)
    ok.value = `Job ${d.job.id} dibuat — ${files.value.length} berkas sedang diproses`
    files.value = []
    await loadJobs()
  } catch (e) {
    err.value = e.message
  } finally {
    busy.value = false
  }
}

async function cancelJob(j) {
  if (!(await ask(`Batalkan job ${j.id}?`, { confirmText: 'Ya, lanjutkan', danger: true }))) return
  try {
    await api(`/api/pdfkit/jobs/${j.id}/cancel`, { method: 'POST' })
    await loadJobs()
  } catch (e) { err.value = e.message }
}

async function removeJob(j) {
  const n = (j.items || []).reduce((a, it) => a + (it.outputs?.length || 0), 0)
  if (!(await ask(`Hapus job ${j.id}${n ? ` beserta ${n} berkas hasil` : ''}? Tidak bisa dibatalkan.`, { confirmText: 'Ya, lanjutkan', danger: true }))) return
  try {
    await api(`/api/pdfkit/jobs/${j.id}`, { method: 'DELETE' })
    await loadJobs()
  } catch (e) { err.value = e.message }
}

async function downloadAll(j) {
  for (const it of j.items || []) {
    for (const o of it.outputs || []) {
      const a = document.createElement('a')
      a.href = `/api/pdfkit/download/${j.id}/${encodeURIComponent(o.file)}`
      a.download = o.file
      document.body.appendChild(a); a.click(); a.remove()
      await new Promise(r => setTimeout(r, 400))
    }
  }
}

// polling: cepat saat ada job jalan, lambat saat idle; jeda saat tab hidden
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
    pollOnce()
  }
}

onMounted(async () => {
  document.addEventListener('visibilitychange', onVisibility)
  await loadInit()
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
        <h1>📄 PDF Kit</h1>
        <p class="sub">Kompres berkas PDF — dari mode aman (lossless) sampai paling kecil (72 dpi + JPEG).</p>
      </div>
      <div v-if="runningCount" class="run-pill">⚙️ {{ runningCount }} job berjalan</div>
    </header>

    <div v-if="err" class="banner b-err">⚠️ {{ err }} <button class="x" @click="err=''">✕</button></div>
    <div v-if="ok" class="banner b-ok">✅ {{ ok }} <button class="x" @click="ok=''">✕</button></div>

    <!-- ===================== FORM SUBMIT ===================== -->
    <section class="card">
      <h2>Kompresi Baru</h2>
      <div class="grid2">
        <div class="col">
          <label class="lbl">📎 Berkas PDF <span class="muted">(maks {{ limits.max_files }} berkas, {{ limits.max_file_mb }} MB/berkas)</span></label>
          <div class="drop" :class="{ over: dragOver }"
            @dragover.prevent="dragOver = true" @dragleave="dragOver = false" @drop.prevent="onDrop"
            @click="fileInput?.click()">
            <input ref="fileInput" type="file" accept="application/pdf,.pdf" multiple
              style="display:none" @change="onPick" />
            <div class="drop-ico">📥</div>
            <div class="drop-t">Tarik berkas PDF ke sini atau <u>pilih dari komputer</u></div>
            <div class="muted small">Berkas asli tidak pernah diubah — hasil selalu berkas baru.</div>
          </div>
          <div v-if="files.length" class="picked">
            <div v-for="(f, i) in files" :key="f.name + i" class="picked-row">
              <span class="ico">📄</span>
              <span class="t">{{ f.name }}</span>
              <span class="muted small">{{ fmtSize(f.size) }}</span>
              <button class="btn btn-ghost btn-xs" @click="removeFile(i)">Hapus</button>
            </div>
            <div class="hint-row">
              <span :class="{ over: overLimit }">{{ files.length }}/{{ limits.max_files }} berkas · total {{ totalMb.toFixed(1) }} MB</span>
              <button class="btn btn-ghost btn-xs" @click="files = []">Bersihkan</button>
            </div>
          </div>
        </div>

        <div class="col">
          <label class="lbl">🎚️ Mode Kompresi</label>
          <div class="modes">
            <button v-for="m in activeModes" :key="m.key" type="button"
              class="mode" :class="{ on: mode === m.key }" :aria-pressed="mode === m.key"
              @click="mode = m.key">
              <b>{{ m.label }}</b>
              <small v-if="m.hint">{{ m.hint }}</small>
            </button>
          </div>
          <div v-if="needsTarget" class="target">
            <label class="lbl">🎯 Target ukuran (MB) <span class="muted">0,1–50</span></label>
            <input v-model.number="targetMb" class="inp" type="number" min="0.1" max="50" step="0.1" />
            <p class="muted small" style="margin:6px 0 0">
              Mode ini mencoba <strong>lossless → ringan → kuat → maksimal</strong> dan berhenti begitu
              target tercapai, jadi kualitas terbaik tetap dipakai.
            </p>
          </div>
        </div>
      </div>

      <div class="actions">
        <button class="btn btn-primary" :disabled="!canSubmit" @click="submit">
          {{ busy ? 'Mengunggah…' : `🗜️ Kompres${files.length ? ` (${files.length} berkas)` : ''}` }}
        </button>
        <span class="muted">Hasil tersimpan di server 48 jam — unduh sebelum terhapus otomatis.</span>
      </div>

      <div class="note">
        <b>🛡️ Daftar lindungi otomatis:</b> berkas yang <strong>diterbitkan aplikasi</strong>
        (kuitansi air minum, laporan overtime, laporan in-out — terdaftar di registri integritas)
        dan PDF <strong>bertanda tangan digital</strong> <em>tidak</em> akan dikompres, karena
        mengompresnya mematahkan verifikasi keaslian dokumen. PDF terenkripsi juga dilewati
        (butuh password). Statusnya muncul sebagai <b>Dilindungi</b> / <b>Dilewati</b> pada hasil.
      </div>
    </section>

    <!-- ===================== DAFTAR JOB ===================== -->
    <section class="card">
      <div class="list-head">
        <h2>Histori & Hasil</h2>
        <div class="tabs">
          <button v-for="t in [['all','Semua'],['running','Berjalan'],['done','Selesai'],['failed','Gagal/Batal']]"
            :key="t[0]" class="tab" :class="{ on: filter === t[0] }" @click="filter = t[0]">{{ t[1] }}</button>
        </div>
      </div>

      <EmptyState v-if="!filteredJobs.length" icon="🗜️"
        message="Belum ada job" hint="Unggah berkas PDF di atas lalu pilih mode kompresi." />

      <div v-for="j in filteredJobs" :key="j.id" class="job">
        <div class="job-head">
          <div class="job-id">
            <span class="badge" :class="badge(j.status).cls">{{ badge(j.status).label }}</span>
            <strong>{{ j.id }}</strong>
            <span class="muted">· {{ j.items.length }} berkas · mode {{ j.mode }}<template v-if="j.target_mb"> → target {{ j.target_mb }} MB</template> · {{ fmtTime(j.created_at) }}</span>
          </div>
          <div class="job-actions">
            <button v-if="['queued','running'].includes(j.status)" class="btn btn-ghost btn-xs" @click="cancelJob(j)">🚫 Batalkan</button>
            <button v-if="j.status === 'done'" class="btn btn-ghost btn-xs" @click="downloadAll(j)">⬇️ Unduh semua</button>
            <button v-if="['done','error','cancelled'].includes(j.status)" class="btn btn-danger btn-xs" @click="removeJob(j)">🗑 Hapus</button>
          </div>
        </div>

        <div class="progress-wrap" v-if="['queued','running'].includes(j.status)">
          <div class="bar"><div class="fill" :style="{ width: Math.max(j.progress, 3) + '%' }" :class="{ pulse: j.status === 'running' }"></div></div>
          <span class="pct">{{ j.stage }} {{ j.progress ? j.progress + '%' : '' }}</span>
        </div>
        <div v-else class="saveline">
          <span v-if="j.ratio_pct > 0" class="save-pill">📉 Hemat {{ j.ratio_pct }}% ({{ fmtSize(j.saved_bytes) }})</span>
          <span v-else class="muted small">{{ j.stage }}</span>
        </div>

        <div class="items">
          <div v-for="(it, i) in j.items" :key="i" class="item" :class="'it-' + it.status">
            <div class="item-title">
              <span class="ico">{{ itemBadge(it.status).ico }}</span>
              <span class="t">{{ it.name }}</span>
              <span class="badge" :class="itemBadge(it.status).cls">{{ itemBadge(it.status).label }}</span>
              <span class="muted small">
                {{ fmtSize(it.size_before) }}<template v-if="it.size_after && it.status === 'done'"> → <b>{{ fmtSize(it.size_after) }}</b></template>
                <template v-if="it.pages"> · {{ it.pages }} hlm</template>
                <template v-if="it.mode_used"> · mode {{ it.mode_used }}</template>
              </span>
            </div>
            <div v-if="it.note" class="note-row" :class="{ warn: ['protected', 'skipped'].includes(it.status) }">{{ it.note }}</div>
            <div v-if="it.error" class="err">⚠️ {{ it.error }}</div>
            <div v-if="it.text_kept === false" class="note-row warn">⚠️ Teks tidak lagi bisa dicari pada hasil ini.</div>
            <div class="outputs">
              <a v-for="o in it.outputs" :key="o.file"
                class="out" :href="`/api/pdfkit/download/${j.id}/${encodeURIComponent(o.file)}`"
                :download="o.file" :title="`Unduh ${o.file} (${fmtSize(o.size)})`">
                📄 {{ o.file }} <small>{{ fmtSize(o.size) }}</small> ⬇️
              </a>
              <span v-if="it.status === 'running'" class="muted small">sedang diproses…</span>
            </div>
          </div>
        </div>
      </div>
    </section>
  </div>
  <ConfirmDialog ref="confirmRef" />
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

.drop { border: 1.5px dashed var(--border, #cbd5e1); border-radius: 12px; padding: 20px; text-align: center; cursor: pointer; background: var(--bg, #f8fafc); transition: border-color .15s, background .15s; }
.drop:hover, .drop.over { border-color: var(--primary, #2563eb); background: color-mix(in srgb, var(--primary, #2563eb) 6%, transparent); }
.drop-ico { font-size: 26px; }
.drop-t { font-size: 13.5px; margin: 6px 0 4px; }
.drop-t u { color: var(--primary, #2563eb); }

.picked { margin-top: 10px; display: flex; flex-direction: column; gap: 6px; }
.picked-row { display: flex; align-items: center; gap: 8px; font-size: 13px; border: 1px solid var(--border, #eef2f7); border-radius: 9px; padding: 7px 10px; }
.picked-row .t { flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-weight: 600; }
.hint-row { display: flex; justify-content: space-between; align-items: center; margin-top: 8px; font-size: 12px; color: var(--text-2, #64748b); }
.over { color: var(--danger, #dc2626); font-weight: 700; }

.modes { display: flex; flex-direction: column; gap: 8px; }
.mode { text-align: left; border: 1.5px solid var(--border, #cbd5e1); background: var(--bg, #f8fafc); color: var(--text, #0f172a); border-radius: 10px; padding: 9px 13px; cursor: pointer; transition: all .15s; display: flex; flex-direction: column; gap: 2px; }
.mode b { font-size: 13.5px; }
.mode small { font-size: 11.5px; opacity: .7; }
.mode:hover { border-color: var(--primary, #2563eb); }
.mode.on { background: var(--primary, #2563eb); border-color: var(--primary, #2563eb); color: #fff; }
.mode.on small { opacity: .85; }
.target { margin-top: 12px; }
.inp { width: 100%; box-sizing: border-box; border: 1px solid var(--border, #cbd5e1); border-radius: 8px; padding: 8px 12px; font-size: 13px; background: var(--surface, #fff); color: var(--text, #0f172a); }
.inp:focus { outline: 2px solid var(--primary, #2563eb); border-color: transparent; }

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

.note { margin-top: 14px; border: 1px dashed var(--border, #cbd5e1); border-radius: 10px; padding: 12px 14px; font-size: 12.5px; line-height: 1.65; background: var(--bg, #f8fafc); color: var(--text-2, #475569); }
.note b { color: var(--text, #0f172a); }

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
.b-run    { background: color-mix(in srgb, #8b5cf6 15%, transparent); color: #6d28d9; }
.b-done   { background: color-mix(in srgb, #16a34a 14%, transparent); color: #15803d; }
.b-error  { background: color-mix(in srgb, #dc2626 12%, transparent); color: #b91c1c; }
.b-cancel { background: #f1f5f9; color: #94a3b8; }
.b-skip   { background: #f1f5f9; color: #64748b; }
.b-prot   { background: color-mix(in srgb, #f59e0b 18%, transparent); color: #b45309; }

.progress-wrap { display: flex; align-items: center; gap: 12px; margin: 12px 0 4px; }
.bar { flex: 1; height: 9px; background: var(--bg, #e2e8f0); border-radius: 999px; overflow: hidden; }
.fill { height: 100%; background: linear-gradient(90deg, var(--primary, #2563eb), #7c3aed); border-radius: 999px; transition: width .6s ease; }
.fill.pulse { animation: shimmer 1.6s linear infinite; background-size: 200% 100%; }
@keyframes shimmer { 0% { background-position: 200% 0; } 100% { background-position: -200% 0; } }
.pct { font-size: 12px; color: var(--text-2, #475569); white-space: nowrap; font-variant-numeric: tabular-nums; }
.saveline { margin: 10px 0 2px; }
.save-pill { font-size: 12.5px; font-weight: 700; background: color-mix(in srgb, #16a34a 14%, transparent); color: #15803d; border-radius: 999px; padding: 4px 12px; }

.items { margin-top: 10px; display: flex; flex-direction: column; gap: 8px; }
.item { border: 1px solid var(--border, #eef2f7); border-radius: 10px; padding: 9px 12px; }
.it-error { border-color: color-mix(in srgb, var(--danger, #dc2626) 30%, transparent); background: color-mix(in srgb, var(--danger, #dc2626) 4%, transparent); }
.it-protected { border-color: color-mix(in srgb, #f59e0b 35%, transparent); background: color-mix(in srgb, #f59e0b 6%, transparent); }
.item-title { display: flex; gap: 8px; align-items: baseline; font-size: 13.5px; flex-wrap: wrap; }
.item-title .t { font-weight: 600; word-break: break-word; }
.note-row { font-size: 12px; color: var(--text-2, #475569); margin-top: 5px; line-height: 1.6; }
.note-row.warn { color: #b45309; }
.err { font-size: 12px; color: var(--danger, #dc2626); }
.outputs { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 7px; align-items: center; }
.out { display: inline-flex; align-items: center; gap: 6px; font-size: 12.5px; font-weight: 600; text-decoration: none; border: 1px solid var(--border, #cbd5e1); border-radius: 8px; padding: 5px 11px; color: var(--text, #0f172a); transition: all .15s; }
.out small { font-weight: 400; opacity: .6; }
.out:hover { border-color: var(--primary, #2563eb); color: var(--primary, #2563eb); transform: translateY(-1px); }
</style>
