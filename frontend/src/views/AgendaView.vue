<script setup>
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { api } from '../api'
import { useAuthStore } from '../stores/auth'
import { useStepupStore } from '../stores/stepup'
import PageHeader from '../components/PageHeader.vue'
import Modal from '../components/Modal.vue'

const auth = useAuthStore()
const stepup = useStepupStore()

const canManage = computed(() => ['admin', 'content_creator'].includes(auth.role))
const isHo = computed(() => auth.role === 'admin' && auth.isHoAdmin)
const isAdmin = computed(() => auth.role === 'admin')
const ownBranch = computed(() => auth.user?.branch_code || '')
const canCrossBranch = computed(() => isHo.value)

const CATEGORIES = [
  ['umum', '📌 Umum'], ['rapat', '🤝 Rapat'], ['libur', '🏖️ Libur'],
  ['event', '🎉 Event'], ['pengumuman', '📢 Pengumuman'],
]
const AUDIENCES = [
  ['all', 'Semua'], ['marketing', 'Marketing'], ['backoffice', 'Backoffice'],
  ['roles', 'Role tertentu'],
]
const DAY_NAMES = ['Sen', 'Sel', 'Rab', 'Kam', 'Jum', 'Sab', 'Min']

const today = isoDate(new Date())
const month = ref(today.slice(0, 7))
const selected = ref(today)
const items = ref([])
const loading = ref(true)
const err = ref('')
const msg = ref('')
const tab = ref('kalender')
const filters = reactive({ category: '', audience: '' })
const branchFilter = ref('')
const branches = ref([])

function isoDate(d) {
  const y = d.getFullYear()
  const m = String(d.getMonth() + 1).padStart(2, '0')
  const day = String(d.getDate()).padStart(2, '0')
  return `${y}-${m}-${day}`
}

function monthLabel(m) {
  const [y, mm] = String(m || month.value).split('-').map(Number)
  return new Date(y, mm - 1, 1).toLocaleDateString('id-ID', { month: 'long', year: 'numeric' })
}

function addMonth(m, delta) {
  const [y, mm] = String(m).split('-').map(Number)
  const d = new Date(y, mm - 1 + delta, 1)
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}`
}

const grid = computed(() => {
  const [y, m] = month.value.split('-').map(Number)
  const first = new Date(y, m - 1, 1)
  const startOffset = (first.getDay() + 6) % 7 // Senin = 0
  const start = new Date(y, m - 1, 1 - startOffset)
  const cells = []
  for (let i = 0; i < 42; i++) {
    const d = new Date(start.getFullYear(), start.getMonth(), start.getDate() + i)
    const key = isoDate(d)
    cells.push({ date: key, day: d.getDate(), inMonth: key.slice(0, 7) === month.value, today: key === today })
  }
  // bulan yang butuh 5 baris dipangkas (minggu terakhir kosong)
  while (cells.length > 35 && cells.slice(-7).every((c) => !c.inMonth || !byDate.value[c.date]?.length)) cells.splice(-7)
  return cells
})

const byDate = computed(() => {
  const map = {}
  for (const it of items.value) (map[it.date] ||= []).push(it)
  for (const k of Object.keys(map)) {
    map[k].sort((a, b) => Number(b.pinned) - Number(a.pinned) || a.title.localeCompare(b.title))
  }
  return map
})

const filteredItems = computed(() => items.value.filter((it) => {
  if (filters.category && it.category !== filters.category) return false
  if (filters.audience && filters.audience !== 'all' && it.audience !== filters.audience) return false
  return true
}))

const filteredByDate = computed(() => {
  const map = {}
  for (const it of filteredItems.value) (map[it.date] ||= []).push(it)
  return map
})

const selectedItems = computed(() => filteredByDate.value[selected.value] || [])
const upcoming = computed(() => filteredItems.value
  .filter((it) => it.date >= today && it.date !== selected.value)
  .slice(0, 8))
const monthCount = computed(() => filteredItems.value.length)

const branchOptions = computed(() => branches.value.filter((b) => b.is_active !== 0))

async function loadBranches() {
  if (!isAdmin.value) return
  try {
    const d = await api('/api/branches')
    branches.value = d?.branches || []
  } catch { branches.value = [] }
}

function scopeParams() {
  const p = {}
  if (branchFilter.value) p.branch = branchFilter.value
  return p
}

async function loadMonth() {
  loading.value = true
  err.value = ''
  try {
    const d = await api('/api/agenda/month', { params: { month: month.value, ...scopeParams() } })
    items.value = d?.items || []
  } catch (e) {
    err.value = e.message
    items.value = []
  } finally {
    loading.value = false
  }
}

function moveMonth(delta) {
  month.value = addMonth(month.value, delta)
  loadMonth()
}

function goToday() {
  month.value = today.slice(0, 7)
  selected.value = today
  loadMonth()
}

function pickDay(cell) {
  selected.value = cell.date
  if (!cell.inMonth) {
    month.value = cell.date.slice(0, 7)
    loadMonth()
  }
}

watch([branchFilter, () => filters.audience], () => loadMonth())

// ---------------------------------------------------------------------------
// Editor
// ---------------------------------------------------------------------------
const showEditor = ref(false)
const editing = ref(null)
const saving = ref(false)
const form = reactive({
  agenda_date: today, title: '', body: '', category: 'umum',
  audience: 'all', audience_roles: '', publish_mode: 'now',
  publish_at: '', end_at: '', repeat_rule: 'none', repeat_until: '',
  media_url: '', pinned: false, notify_on_day: false,
  branch_code: '', scope_all: false,
  apply_batch: true,
})

function resetForm(date = today) {
  Object.assign(form, {
    agenda_date: date, title: '', body: '', category: 'umum',
    audience: 'all', audience_roles: '', publish_mode: 'now',
    publish_at: '', end_at: '', repeat_rule: 'none', repeat_until: '',
    media_url: '', pinned: false, notify_on_day: false,
    branch_code: branchFilter.value || ownBranch.value,
    scope_all: false, apply_batch: true,
  })
}

function openCreate(date = selected.value) {
  editing.value = null
  resetForm(date)
  showEditor.value = true
}

function toInput(v) {
  return v ? String(v).replace(' ', 'T').slice(0, 16) : ''
}

function openEdit(item) {
  editing.value = item
  Object.assign(form, {
    agenda_date: item.date, title: item.title || '', body: item.body || '',
    category: item.category || 'umum', audience: item.audience || 'all',
    audience_roles: item.audience_roles || '',
    publish_mode: item.publish_mode || 'now',
    publish_at: toInput(item.publish_at), end_at: toInput(item.end_at),
    repeat_rule: item.repeat_rule || 'none',
    repeat_until: item.repeat_until || '',
    media_url: item.media_url || '', pinned: !!item.pinned,
    notify_on_day: !!item.notify_on_day,
    branch_code: item.branch_code || ownBranch.value,
    scope_all: false, apply_batch: true,
  })
  showEditor.value = true
}

function payload() {
  const p = {
    agenda_date: form.agenda_date, title: form.title, body: form.body,
    category: form.category, audience: form.audience,
    audience_roles: form.audience_roles, publish_mode: form.publish_mode,
    publish_at: form.publish_mode === 'scheduled' ? form.publish_at : '',
    end_at: form.end_at, repeat_rule: form.repeat_rule,
    repeat_until: form.repeat_until, media_url: form.media_url,
    pinned: form.pinned, notify_on_day: form.notify_on_day,
    branch_code: form.branch_code,
  }
  if (!editing.value && isHo.value && form.scope_all) p.scope = 'all'
  if (editing.value) p.apply_batch = form.apply_batch
  return p
}

async function save() {
  if (!form.title.trim()) { msg.value = 'Judul wajib diisi.'; return }
  saving.value = true
  msg.value = ''
  try {
    if (editing.value) {
      await api(`/api/admin/agenda/items/${editing.value.id}`,
        { method: 'PUT', body: payload() })
      msg.value = '✅ Agenda diperbarui.'
    } else {
      await api('/api/admin/agenda/items', { method: 'POST', body: payload() })
      msg.value = '✅ Agenda disimpan.'
    }
    showEditor.value = false
    month.value = form.agenda_date.slice(0, 7)
    selected.value = form.agenda_date
    await loadMonth()
    if (tab.value === 'cakupan') loadCoverage()
  } catch (e) {
    msg.value = '⚠️ ' + e.message
  } finally {
    saving.value = false
  }
}

async function removeItem() {
  if (!editing.value) return
  const body = { branch_code: editing.value.branch_code, apply_batch: form.apply_batch }
  try {
    await stepup.require(
      () => api(`/api/admin/agenda/items/${editing.value.id}`, { method: 'DELETE', body }),
      'Hapus agenda (PIN)')
    showEditor.value = false
    msg.value = '🗑️ Agenda dihapus.'
    await loadMonth()
  } catch (e) {
    msg.value = '⚠️ ' + e.message
  }
}

async function duplicateItem() {
  if (!editing.value) return
  try {
    await api(`/api/admin/agenda/items/${editing.value.id}/duplicate`,
      { method: 'POST', body: { branch_code: editing.value.branch_code, agenda_date: form.agenda_date } })
    showEditor.value = false
    msg.value = '📋 Agenda diduplikasi.'
    await loadMonth()
  } catch (e) {
    msg.value = '⚠️ ' + e.message
  }
}

const uploading = ref(false)
async function uploadMedia(ev) {
  const file = ev.target.files?.[0]
  if (!file) return
  uploading.value = true
  msg.value = ''
  try {
    const fd = new FormData()
    fd.append('file', file)
    const csrf = localStorage.getItem('bpf_csrf') || ''
    const r = await fetch('/api/admin/agenda/upload', {
      method: 'POST', headers: { 'X-CSRF-Token': csrf }, body: fd,
    })
    const d = await r.json().catch(() => null)
    if (!r.ok || !d?.ok) throw new Error(d?.msg || `HTTP ${r.status}`)
    form.media_url = d.url
    msg.value = '📎 Media diunggah.'
  } catch (e) {
    msg.value = '⚠️ ' + e.message
  } finally {
    uploading.value = false
    ev.target.value = ''
  }
}

// ---------------------------------------------------------------------------
// Cakupan (Admin Pusat)
// ---------------------------------------------------------------------------
const coverage = ref(null)
const covLoading = ref(false)
async function loadCoverage() {
  if (!isHo.value) return
  covLoading.value = true
  try {
    const d = await api('/api/admin/agenda/coverage', { params: { month: month.value } })
    coverage.value = d?.coverage || null
  } catch (e) {
    msg.value = '⚠️ ' + e.message
    coverage.value = null
  } finally {
    covLoading.value = false
  }
}
watch(tab, (v) => {
  if (v === 'cakupan') loadCoverage()
})

function exportUrl(kind) {
  const q = new URLSearchParams({ month: month.value })
  if (branchFilter.value) q.set('branch', branchFilter.value)
  return `/api/agenda/${kind}?${q.toString()}`
}

onMounted(async () => {
  await loadBranches()
  await loadMonth()
})
</script>

<template>
  <div class="ag-view">
    <PageHeader icon="📅" title="Agenda"
                :subtitle="`Jadwal kegiatan ${isHo ? 'lintas cabang' : 'cabang ' + (auth.user?.branch_name || ownBranch)}`">
      <button class="btn btn-sm" @click="goToday">Hari ini</button>
      <a class="btn btn-sm" :href="exportUrl('ics')" target="_blank" rel="noopener">📆 ICS</a>
      <a class="btn btn-sm" :href="exportUrl('export.pdf')" target="_blank" rel="noopener">🧾 PDF</a>
      <button v-if="canManage" class="btn btn-primary btn-sm" @click="openCreate()">＋ Tambah agenda</button>
    </PageHeader>

    <div v-if="msg" class="alert" :class="msg.startsWith('⚠️') ? 'alert-error' : 'alert-success'">{{ msg }}</div>

    <div class="ag-tabs">
      <button class="ag-tab" :class="{ active: tab === 'kalender' }" @click="tab = 'kalender'">🗓️ Kalender</button>
      <button v-if="isHo" class="ag-tab" :class="{ active: tab === 'cakupan' }" @click="tab = 'cakupan'">📊 Cakupan cabang</button>
    </div>

    <template v-if="tab === 'kalender'">
      <div class="card card-pad ag-toolbar">
        <div class="ag-monthnav">
          <button class="btn-icon" aria-label="Bulan sebelumnya" @click="moveMonth(-1)">‹</button>
          <b>{{ monthLabel() }}</b>
          <button class="btn-icon" aria-label="Bulan berikutnya" @click="moveMonth(1)">›</button>
          <span class="ag-count">{{ monthCount }} agenda</span>
        </div>
        <select v-if="isAdmin" v-model="branchFilter" class="select ag-filter" aria-label="Filter cabang">
          <option value="">{{ isHo ? 'Semua cabang' : 'Cabang saya' }}</option>
          <option v-for="b in branchOptions" :key="b.code" :value="b.code">{{ b.code }} — {{ b.name }}</option>
        </select>
        <select v-model="filters.category" class="select ag-filter" aria-label="Filter kategori">
          <option value="">Semua kategori</option>
          <option v-for="[v, l] in CATEGORIES" :key="v" :value="v">{{ l }}</option>
        </select>
        <select v-model="filters.audience" class="select ag-filter" aria-label="Filter audiens">
          <option value="">Semua audiens</option>
          <option v-for="[v, l] in AUDIENCES" :key="v" :value="v">{{ l }}</option>
        </select>
      </div>

      <div v-if="err" class="alert alert-error">{{ err }}</div>

      <div class="ag-layout">
        <div class="card card-pad ag-calendar">
          <div v-if="loading" class="ag-loading">Memuat agenda…</div>
          <div class="ag-grid ag-head">
            <div v-for="d in DAY_NAMES" :key="d" class="ag-dayname">{{ d }}</div>
          </div>
          <div class="ag-grid">
            <button v-for="c in grid" :key="c.date" type="button"
                    class="ag-cell" :class="{ out: !c.inMonth, today: c.today, sel: c.date === selected }"
                    @click="pickDay(c)">
              <span class="ag-daynum">{{ c.day }}</span>
              <span v-for="it in (filteredByDate[c.date] || []).slice(0, 3)" :key="it.id"
                    class="ag-pill" :class="'cat-' + it.category">
                <span v-if="it.pinned">📌</span>{{ it.title }}
              </span>
              <span v-if="(filteredByDate[c.date] || []).length > 3" class="ag-more">
                +{{ filteredByDate[c.date].length - 3 }} lagi
              </span>
            </button>
          </div>
          <div v-if="canManage" class="ag-hint">Klik tanggal untuk menambah agenda. Klik agenda di panel kanan untuk mengedit.</div>
        </div>

        <aside class="ag-rail">
          <div class="card card-pad">
            <div class="ag-rail-head">
              <b>{{ selected === today ? 'Hari ini' : selected }}</b>
              <button v-if="canManage" class="btn btn-sm" @click="openCreate(selected)">＋</button>
            </div>
            <div v-if="!selectedItems.length" class="ag-empty">Tidak ada agenda.</div>
            <article v-for="it in selectedItems" :key="it.id" class="ag-item" :class="'cat-' + it.category">
              <div class="ag-item-top">
                <b>{{ it.title }}</b>
                <span v-if="it.pinned" title="Disematkan">📌</span>
              </div>
              <div class="ag-meta">
                <span>{{ CATEGORIES.find((x) => x[0] === it.category)?.[1] || it.category }}</span>
                <span v-if="it.publish_mode === 'scheduled'">🕒 {{ toInput(it.publish_at) }}</span>
                <span v-if="it.repeat_rule !== 'none'">🔁 {{ it.repeat_rule }}</span>
                <span v-if="it.branches?.length > 1">🏢 {{ it.branches.join(', ') }}</span>
              </div>
              <p v-if="it.body" class="ag-body">{{ it.body }}</p>
              <a v-if="it.media_url" :href="it.media_url" target="_blank" rel="noopener" class="ag-media">
                {{ it.media_type === 'image' ? '🖼️ Lihat gambar' : it.media_type === 'video' ? '🎬 Buka video' : '🔗 Buka tautan' }}
              </a>
              <div v-if="canManage" class="ag-item-actions">
                <button class="btn btn-sm" @click="openEdit(it)">✏️ Edit</button>
              </div>
            </article>
          </div>

          <div class="card card-pad">
            <b>Mendatang</b>
            <div v-if="!upcoming.length" class="ag-empty">Belum ada agenda berikutnya.</div>
            <button v-for="it in upcoming" :key="it.id" class="ag-up" @click="selected = it.date">
              <span class="ag-up-date">{{ it.date.slice(5) }}</span>
              <span class="ag-up-title">{{ it.title }}</span>
            </button>
          </div>
        </aside>
      </div>
    </template>

    <template v-else-if="tab === 'cakupan'">
      <div class="card card-pad">
        <div class="ag-toolbar" style="padding:0;border:0;margin-bottom:10px;">
          <b>Cakupan {{ monthLabel() }}</b>
          <button class="btn btn-sm" @click="loadCoverage">Muat ulang</button>
        </div>
        <div v-if="covLoading" class="ag-loading">Menghitung…</div>
        <div v-else-if="!coverage" class="ag-empty">Belum ada data.</div>
        <div v-else class="ag-table-wrap">
          <table class="ag-table">
            <thead>
              <tr>
                <th>Cabang</th>
                <th v-for="w in coverage.weeks" :key="w.start">{{ w.start.slice(8) }}–{{ w.end.slice(8) }}</th>
                <th>Total</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="r in coverage.branches" :key="r.branch_code">
                <td><b>{{ r.branch_code }}</b> {{ r.branch_name }}</td>
                <td v-for="(n, i) in r.weeks" :key="i" :class="{ zero: !n }">{{ n }}</td>
                <td><b>{{ r.total }}</b></td>
              </tr>
            </tbody>
            <tfoot>
              <tr><td colspan="99">Total agenda bulan ini: <b>{{ coverage.total }}</b></td></tr>
            </tfoot>
          </table>
        </div>
      </div>
    </template>

    <Modal v-if="showEditor" :title="editing ? 'Edit agenda' : 'Tambah agenda'" wide @close="showEditor = false">
      <div class="ag-form">
        <label>Tanggal
          <input v-model="form.agenda_date" type="date" class="input" />
        </label>
        <label>Judul
          <input v-model="form.title" class="input" maxlength="200" placeholder="Nama kegiatan" />
        </label>
        <label v-if="isHo && !editing">Cabang
          <select v-model="form.branch_code" class="select" :disabled="form.scope_all">
            <option v-for="b in branchOptions" :key="b.code" :value="b.code">{{ b.code }} — {{ b.name }}</option>
          </select>
        </label>
        <label v-else-if="isAdmin && !editing">Cabang
          <select v-model="form.branch_code" class="select">
            <option v-for="b in branchOptions" :key="b.code" :value="b.code">{{ b.code }} — {{ b.name }}</option>
          </select>
        </label>
        <label class="ag-check" v-if="isHo && !editing">
          <input v-model="form.scope_all" type="checkbox" />
          Terbitkan ke <b>semua cabang</b> (batch)
        </label>
        <label>Kategori
          <select v-model="form.category" class="select">
            <option v-for="[v, l] in CATEGORIES" :key="v" :value="v">{{ l }}</option>
          </select>
        </label>
        <label>Audiens
          <select v-model="form.audience" class="select">
            <option v-for="[v, l] in AUDIENCES" :key="v" :value="v">{{ l }}</option>
          </select>
        </label>
        <label v-if="form.audience === 'roles'">Role audiens (pisah koma)
          <input v-model="form.audience_roles" class="input" placeholder="finance,ga,marketing" />
        </label>
        <label>Status terbit
          <select v-model="form.publish_mode" class="select">
            <option value="now">Langsung tayang</option>
            <option value="scheduled">Terjadwal</option>
          </select>
        </label>
        <label v-if="form.publish_mode === 'scheduled'">Mulai tayang
          <input v-model="form.publish_at" type="datetime-local" class="input" />
        </label>
        <label v-if="form.publish_mode === 'scheduled'">Berakhir (opsional)
          <input v-model="form.end_at" type="datetime-local" class="input" />
        </label>
        <label>Pengulangan
          <select v-model="form.repeat_rule" class="select">
            <option value="none">Tidak berulang</option>
            <option value="weekly">Mingguan</option>
            <option value="monthly">Bulanan</option>
          </select>
        </label>
        <label v-if="form.repeat_rule !== 'none'">Sampai tanggal
          <input v-model="form.repeat_until" type="date" class="input" />
        </label>
        <label class="ag-span">Isi agenda
          <textarea v-model="form.body" class="input" rows="4" maxlength="5000" />
        </label>
        <label class="ag-span">Media (URL atau unggah)
          <input v-model="form.media_url" class="input" placeholder="https://… atau unggah file" />
          <input type="file" accept="image/*,video/*,.pdf,audio/*" @change="uploadMedia" />
          <small v-if="uploading">Mengunggah…</small>
        </label>
        <label class="ag-check">
          <input v-model="form.pinned" type="checkbox" /> Sematkan di atas
        </label>
        <label class="ag-check">
          <input v-model="form.notify_on_day" type="checkbox" /> Kirim notifikasi di hari H (opsional)
        </label>
        <label class="ag-check" v-if="editing">
          <input v-model="form.apply_batch" type="checkbox" /> Terapkan ke semua cabang pada batch ini
        </label>
      </div>
      <div class="ag-form-actions">
        <button v-if="editing" class="btn" @click="duplicateItem">📋 Duplikat</button>
        <button v-if="editing" class="btn ag-danger" @click="removeItem">🗑️ Hapus</button>
        <span class="grow"></span>
        <button class="btn" @click="showEditor = false">Batal</button>
        <button class="btn btn-primary" :disabled="saving" @click="save">
          {{ saving ? 'Menyimpan…' : 'Simpan' }}
        </button>
      </div>
    </Modal>
  </div>
</template>

<style scoped>
.ag-view { display: grid; gap: 12px; }
.ag-tabs { display: flex; gap: 8px; flex-wrap: wrap; }
.ag-tab { border: 1px solid var(--border); background: var(--surface); color: var(--text-2); border-radius: 10px; padding: 7px 14px; font-size: 12px; font-weight: 600; cursor: pointer; }
.ag-tab.active { border-color: var(--primary, #7c3aed); color: var(--primary, #7c3aed); }
.ag-toolbar { display: flex; flex-wrap: wrap; align-items: center; gap: 8px; padding: 8px 12px; }
.ag-monthnav { display: flex; align-items: center; gap: 8px; text-transform: capitalize; }
.ag-monthnav b { min-width: 150px; text-align: center; }
.ag-count { font-size: 11px; color: var(--text-3); }
.ag-filter { max-width: 190px; }
.ag-layout { display: grid; gap: 12px; grid-template-columns: minmax(0, 1fr) 320px; align-items: start; }
.ag-calendar { min-width: 0; }
.ag-grid { display: grid; grid-template-columns: repeat(7, minmax(0, 1fr)); }
.ag-head { border-bottom: 1px solid var(--border); margin-bottom: 4px; }
.ag-dayname { font-size: 11px; font-weight: 700; color: var(--text-3); text-align: center; padding: 4px 0; }
.ag-cell { position: relative; min-height: 92px; text-align: left; border: 1px solid var(--border); background: var(--surface); padding: 4px 5px; display: flex; flex-direction: column; gap: 3px; cursor: pointer; border-radius: 6px; }
.ag-cell:hover { border-color: var(--primary, #7c3aed); }
.ag-cell.out { opacity: .45; }
.ag-cell.today .ag-daynum { background: var(--primary, #7c3aed); color: #fff; border-radius: 999px; }
.ag-cell.sel { outline: 2px solid var(--primary, #7c3aed); }
.ag-daynum { font-size: 11px; font-weight: 700; width: 22px; height: 22px; display: grid; place-items: center; }
.ag-pill { display: block; font-size: 10px; line-height: 1.25; padding: 2px 4px; border-radius: 4px; background: var(--bg); color: var(--text-2); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.ag-more { font-size: 9px; color: var(--text-3); }
.ag-pill.cat-rapat, .ag-item.cat-rapat { border-left-color: #2563eb; }
.ag-pill.cat-libur, .ag-item.cat-libur { border-left-color: #059669; }
.ag-pill.cat-event, .ag-item.cat-event { border-left-color: #d97706; }
.ag-pill.cat-pengumuman, .ag-item.cat-pengumuman { border-left-color: #dc2626; }
.ag-pill { border-left: 3px solid #7c3aed; }
.ag-loading, .ag-empty { padding: 18px; text-align: center; color: var(--text-3); font-size: 12px; }
.ag-hint { font-size: 10px; color: var(--text-3); margin-top: 8px; }
.ag-rail { display: grid; gap: 12px; }
.ag-rail-head { display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; }
.ag-item { border: 1px solid var(--border); border-left: 4px solid #7c3aed; border-radius: 8px; padding: 8px 10px; margin-bottom: 8px; }
.ag-item-top { display: flex; justify-content: space-between; gap: 6px; font-size: 12px; }
.ag-meta { display: flex; flex-wrap: wrap; gap: 8px; font-size: 10px; color: var(--text-3); margin: 3px 0; }
.ag-body { font-size: 11px; color: var(--text-2); white-space: pre-wrap; margin: 4px 0; }
.ag-media { font-size: 11px; color: var(--primary, #7c3aed); }
.ag-item-actions { margin-top: 6px; }
.ag-up { display: flex; gap: 8px; width: 100%; text-align: left; background: none; border: 0; border-bottom: 1px dashed var(--border); padding: 6px 0; cursor: pointer; font-size: 11px; }
.ag-up-date { color: var(--text-3); min-width: 42px; }
.ag-up-title { color: var(--text-2); }
.ag-table-wrap { overflow-x: auto; }
.ag-table { width: 100%; border-collapse: collapse; font-size: 12px; }
.ag-table th, .ag-table td { border-bottom: 1px solid var(--border); padding: 7px 9px; text-align: left; }
.ag-table th { font-size: 10px; color: var(--text-3); text-transform: uppercase; }
.ag-table td.zero { color: var(--text-3); }
.ag-form { display: grid; grid-template-columns: repeat(auto-fit, minmax(210px, 1fr)); gap: 10px; }
.ag-form label { display: grid; gap: 4px; font-size: 11px; color: var(--text-3); font-weight: 600; }
.ag-span { grid-column: 1 / -1; }
.ag-check { display: flex !important; align-items: center; gap: 6px; font-size: 12px; color: var(--text-2); }
.ag-check input { width: auto; }
.ag-form-actions { display: flex; gap: 8px; align-items: center; margin-top: 14px; }
.ag-danger { color: #dc2626; border-color: #dc2626; }
@media (max-width: 900px) {
  .ag-layout { grid-template-columns: 1fr; }
  .ag-cell { min-height: 64px; }
  .ag-pill { display: none; }
}
</style>
