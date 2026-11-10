<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { api } from '../api'
import PageHeader from '../components/PageHeader.vue'
import StatCard from '../components/StatCard.vue'
import Modal from '../components/Modal.vue'
import ConfirmDialog from '../components/ConfirmDialog.vue'
import LoadingState from '../components/LoadingState.vue'
import ErrorState from '../components/ErrorState.vue'
import EmptyState from '../components/EmptyState.vue'
import { formatDate, formatDateTime } from '../utils/format'
import {
  CATEGORY_LABEL, STATUS_LABEL, STATUS_BADGE, COND_META, EVENT_LABEL,
  assetTitle, categoryLabel, downloadBlob,
} from '../utils/itAssets'

const route = useRoute()
const router = useRouter()

const confirmRef = ref(null)
const ask = (message, opts) => confirmRef.value?.open(message, opts) ?? Promise.resolve(false)

// ---------------------------------------------------------------- state umum
const tab = ref(['dashboard', 'assets', 'discovery', 'labels', 'stocktake'].includes(route.query.tab)
  ? route.query.tab : 'dashboard')
const meta = ref({ categories: [], statuses: [], conditions: [], branch: '' })
const summary = ref(null)
const warranty = ref([])
const loading = ref(true)
const err = ref('')
const msg = ref('')
const msgType = ref('success')

function flash(text, type = 'success') {
  msg.value = text
  msgType.value = type
  window.clearTimeout(flash._t)
  flash._t = window.setTimeout(() => { msg.value = '' }, 6000)
}

// ------------------------------------------------------------------ daftar aset
const assets = ref([])
const total = ref(0)
const page = ref(1)
const perPage = ref(50)
const filters = reactive({ q: '', category: '', status: '', cond: '', room: '' })
const selected = ref([])

const allSelected = computed(() => assets.value.length > 0 && selected.value.length === assets.value.length)
function toggleAll(e) {
  selected.value = e.target.checked ? assets.value.map((a) => a.asset_tag) : []
}
function toggleOne(tag) {
  const i = selected.value.indexOf(tag)
  if (i >= 0) selected.value.splice(i, 1)
  else selected.value.push(tag)
}
const unlabeledOnPage = computed(() => assets.value.filter((a) => !a.label_printed_at))

async function loadMeta() {
  try { meta.value = await api('/api/it/meta') } catch { /* biarkan */ }
}
async function loadSummary() {
  try { summary.value = await api('/api/it/summary') } catch { summary.value = null }
}
async function loadWarranty() {
  try { warranty.value = (await api('/api/it/reports/warranty', { params: { days: 30 } })).data || [] } catch { warranty.value = [] }
}
async function loadAssets() {
  loading.value = true; err.value = ''
  try {
    const res = await api('/api/it/assets', {
      params: { ...filters, page: page.value, per_page: perPage.value },
    })
    assets.value = res.data || []
    total.value = res.total || 0
    selected.value = selected.value.filter((t) => assets.value.some((a) => a.asset_tag === t))
  } catch (e) {
    err.value = e.message
  } finally {
    loading.value = false
  }
}
async function searchAssets() {
  page.value = 1
  await loadAssets()
}
function resetFilters() {
  Object.assign(filters, { q: '', category: '', status: '', cond: '', room: '' })
  searchAssets()
}
const pageCount = computed(() => Math.max(1, Math.ceil(total.value / perPage.value)))
function goPage(p) {
  page.value = Math.min(pageCount.value, Math.max(1, p))
  loadAssets()
}

// -------------------------------------------------------------- tambah aset
const addModal = ref(false)
const saving = ref(false)
function blankAsset() {
  return {
    category: 'pc', brand: '', model: '', serial_number: '', status: 'aktif', cond: 'baik',
    location_room: '', location_detail: '', assigned_to: '', vendor: '',
    purchase_date: '', purchase_price: '', warranty_until: '',
    hostname: '', ip_address: '', mac_address: '', os_name: '', notes: '',
  }
}
const addForm = ref(blankAsset())
function openAdd(category = '') {
  addForm.value = blankAsset()
  if (category) addForm.value.category = category
  addModal.value = true
}
async function saveAsset() {
  if (!addForm.value.category) { flash('Kategori wajib dipilih', 'error'); return }
  saving.value = true
  try {
    const res = await api('/api/it/assets', { method: 'POST', body: addForm.value })
    flash(`✅ ${res.msg}`)
    addModal.value = false
    await Promise.all([loadSummary(), loadAssets()])
  } catch (e) {
    flash('❌ ' + e.message, 'error')
  } finally {
    saving.value = false
  }
}

// ------------------------------------------------------------------- impor
const importModal = ref(false)
const importFile = ref(null)
const importPreview = ref(null)
const importBusy = ref(false)
function openImport() {
  importFile.value = null
  importPreview.value = null
  importModal.value = true
}
async function postImport(commit) {
  if (!importFile.value) { flash('Pilih berkas CSV/XLSX dulu', 'error'); return }
  importBusy.value = true
  try {
    const fd = new FormData()
    fd.append('file', importFile.value)
    const csrf = localStorage.getItem('bpf_csrf') || sessionStorage.getItem('bpf_csrf') || ''
    const r = await fetch(`/api/it/assets/import${commit ? '?commit=1' : ''}`, {
      method: 'POST',
      headers: { Accept: 'application/json', 'X-CSRF-Token': csrf },
      body: fd,
    })
    const data = await r.json().catch(() => ({}))
    if (!r.ok) throw new Error(data.msg || data.error || `HTTP ${r.status}`)
    if (!commit) {
      importPreview.value = data
      flash(`Pratinjau: ${data.valid.length} baris siap, ${data.errors.length} error`)
    } else {
      flash(`✅ ${data.created} aset diimpor${data.errors.length ? `, ${data.errors.length} gagal` : ''}`)
      importModal.value = false
      await Promise.all([loadSummary(), loadAssets()])
    }
  } catch (e) {
    flash('❌ ' + e.message, 'error')
  } finally {
    importBusy.value = false
  }
}

// ------------------------------------------------------------------- ekspor
async function exportCsv() {
  try {
    const blob = await api('/api/it/assets/export.csv', { raw: true })
    downloadBlob(blob, `inventaris_it_${meta.value.branch || 'SBY'}_${new Date().toISOString().slice(0, 10)}.csv`)
  } catch (e) {
    flash('❌ Gagal ekspor: ' + e.message, 'error')
  }
}
async function downloadReport() {
  try {
    const blob = await api('/api/it/reports/assets.pdf', {
      raw: true,
      params: {
        category: filters.category, status: filters.status, cond: filters.cond, room: filters.room,
      },
    })
    downloadBlob(blob, `laporan_inventaris_it_${meta.value.branch || 'SBY'}_${new Date().toISOString().slice(0, 10)}.pdf`)
  } catch (e) {
    flash('❌ Gagal membuat laporan: ' + e.message, 'error')
  }
}

// -------------------------------------------------------------------- label
const labelLayout = ref('a4-24')
const labelBusy = ref(false)
async function printLabels(tags = null, layout = null) {
  const chosen = tags || (selected.value.length ? selected.value : null)
  labelBusy.value = true
  try {
    const blob = await api('/api/it/assets/labels.pdf', {
      method: 'POST',
      raw: true,
      body: { tags: chosen || [], layout: layout || labelLayout.value },
    })
    downloadBlob(blob, `label_aset_${new Date().toISOString().slice(0, 10)}.pdf`)
    flash('✅ PDF label diunduh — cetak pada stiker A4, uji 1 label dulu')
    await Promise.all([loadAssets(), loadSummary()])
  } catch (e) {
    flash('❌ ' + e.message, 'error')
  } finally {
    labelBusy.value = false
  }
}
async function printSingle(tag) {
  try {
    const blob = await api(`/api/it/assets/${encodeURIComponent(tag)}/label.pdf`, { raw: true })
    downloadBlob(blob, `label_${tag}.pdf`)
  } catch (e) {
    flash('❌ ' + e.message, 'error')
  }
}

// ----------------------------------------------------------------- discovery
const candidates = ref([])
const runs = ref([])
const discLoading = ref(false)
const scanning = ref(false)
const discState = ref('new')
const adopting = ref(null)
const adoptForm = reactive({ category: '', brand: '', model: '', location_room: '', assigned_to: '' })

async function loadDiscovery() {
  discLoading.value = true
  try {
    const [c, r] = await Promise.all([
      api('/api/it/discovery/candidates', { params: { state: discState.value } }),
      api('/api/it/discovery/runs'),
    ])
    candidates.value = c.data || []
    runs.value = r.data || []
  } catch (e) {
    flash('❌ ' + e.message, 'error')
  } finally {
    discLoading.value = false
  }
}
async function triggerScan() {
  scanning.value = true
  try {
    const res = await api('/api/it/discovery/scan', { method: 'POST', body: {} })
    flash(`✅ ${res.msg}`)
    window.setTimeout(loadDiscovery, 4000)
  } catch (e) {
    flash('❌ ' + e.message, 'error')
  } finally {
    scanning.value = false
  }
}
function openAdopt(c) {
  adopting.value = c
  adoptForm.category = c.category_suggest || 'other'
  adoptForm.brand = c.vendor || ''
  adoptForm.model = ''
  adoptForm.location_room = ''
  adoptForm.assigned_to = ''
}
async function confirmAdopt() {
  if (!adopting.value) return
  try {
    const res = await api(`/api/it/discovery/candidates/${adopting.value.id}/adopt`, {
      method: 'POST', body: { ...adoptForm },
    })
    flash(`✅ ${res.msg}`)
    adopting.value = null
    await Promise.all([loadDiscovery(), loadSummary()])
  } catch (e) {
    flash('❌ ' + e.message, 'error')
  }
}
async function ignoreCandidate(c) {
  if (!await ask(`Abaikan perangkat ${c.ip}${c.mac ? ' (' + c.mac + ')' : ''}? Kandidat tidak akan mengganggu daftar.`, { title: 'Abaikan kandidat' })) return
  try {
    await api(`/api/it/discovery/candidates/${c.id}/ignore`, { method: 'POST', body: { note: 'Diabaikan IT' } })
    await loadDiscovery()
  } catch (e) {
    flash('❌ ' + e.message, 'error')
  }
}
function confidenceClass(v) {
  const n = Number(v || 0)
  if (n >= 0.75) return 'badge-green'
  if (n >= 0.5) return 'badge-amber'
  return 'badge-gray'
}

// ---------------------------------------------------------------- stok opname
const stSessions = ref([])
const stDetail = ref(null)
const stRoom = ref('')
const stBusy = ref(false)
async function loadStocktake() {
  try { stSessions.value = (await api('/api/it/stocktake')).data || [] } catch (e) { flash('❌ ' + e.message, 'error') }
}
async function startStocktake() {
  stBusy.value = true
  try {
    const res = await api('/api/it/stocktake', { method: 'POST', body: { location_room: stRoom.value } })
    flash(`✅ Sesi #${res.data.id} dimulai (${res.data.expected} aset)`)
    stRoom.value = ''
    await loadStocktake()
    await openStocktake(res.data.id)
  } catch (e) {
    flash('❌ ' + e.message, 'error')
  } finally {
    stBusy.value = false
  }
}
async function openStocktake(id) {
  try { stDetail.value = (await api(`/api/it/stocktake/${id}`)).data } catch (e) { flash('❌ ' + e.message, 'error') }
}
async function closeStocktake() {
  if (!stDetail.value) return
  if (!await ask('Tutup sesi stok opname? Aset yang belum discan ditandai hilang.', { title: 'Tutup sesi', danger: true })) return
  try {
    const res = await api(`/api/it/stocktake/${stDetail.value.session.id}/close`, { method: 'POST', body: {} })
    flash(`✅ ${res.msg}`)
    stDetail.value = null
    await loadStocktake()
  } catch (e) {
    flash('❌ ' + e.message, 'error')
  }
}
const stFound = computed(() => (stDetail.value?.items || []).filter((i) => i.result === 'found').length)
const stMissing = computed(() => (stDetail.value?.items || []).filter((i) => i.result !== 'found').length)

// --------------------------------------------------------------------- tab
async function switchTab(name) {
  tab.value = name
  router.replace({ query: { ...route.query, tab: name } })
  if (name === 'dashboard') await Promise.all([loadSummary(), loadWarranty(), loadAssets()])
  if (name === 'assets') await loadAssets()
  if (name === 'discovery') await loadDiscovery()
  if (name === 'labels') await loadAssets()
  if (name === 'stocktake') await Promise.all([loadStocktake(), loadAssets()])
}

onMounted(async () => {
  await loadMeta()
  await Promise.all([loadSummary(), loadWarranty(), loadAssets()])
  if (tab.value === 'discovery') loadDiscovery()
  if (tab.value === 'stocktake') loadStocktake()
})
</script>

<template>
  <div class="it-inv">
    <PageHeader icon="📦" title="Inventaris IT"
                subtitle="Semua perangkat IT — termasuk yang tidak di jaringan — dengan label QR, kondisi, dan penemuan otomatis.">
      <button class="btn btn-primary" @click="openAdd()">＋ Tambah Aset</button>
      <button class="btn" @click="openImport()">📥 Impor</button>
      <button class="btn" @click="router.push('/it/scan')">📷 Scan</button>
      <button class="btn" :disabled="labelBusy" @click="printLabels(null, 'a4-24')">🏷️ Cetak Label</button>
    </PageHeader>

    <div v-if="msg" class="alert" :class="msgType === 'error' ? 'alert-error' : 'alert-success'" style="margin-bottom:14px;">{{ msg }}</div>

    <nav class="workspace-tabs" role="tablist" aria-label="Menu Inventaris IT">
      <button type="button" role="tab" :aria-selected="tab === 'dashboard'" :class="{ active: tab === 'dashboard' }" @click="switchTab('dashboard')">
        <span class="workspace-tab-icon" aria-hidden="true">📊</span>
        <span class="workspace-tab-text">Dashboard<small>Ringkasan &amp; aksi cepat</small></span>
      </button>
      <button type="button" role="tab" :aria-selected="tab === 'assets'" :class="{ active: tab === 'assets' }" @click="switchTab('assets')">
        <span class="workspace-tab-icon" aria-hidden="true">🗂️</span>
        <span class="workspace-tab-text">Aset<small>Daftar &amp; filter</small></span>
        <span class="workspace-tab-count">{{ total }}</span>
      </button>
      <button type="button" role="tab" :aria-selected="tab === 'discovery'" :class="{ active: tab === 'discovery' }" @click="switchTab('discovery')">
        <span class="workspace-tab-icon" aria-hidden="true">🌐</span>
        <span class="workspace-tab-text">Jaringan<small>Kandidat perangkat</small></span>
        <span v-if="summary" class="workspace-tab-count">{{ summary.candidates }}</span>
      </button>
      <button type="button" role="tab" :aria-selected="tab === 'labels'" :class="{ active: tab === 'labels' }" @click="switchTab('labels')">
        <span class="workspace-tab-icon" aria-hidden="true">🏷️</span>
        <span class="workspace-tab-text">Label &amp; QR<small>Prosedur cetak</small></span>
      </button>
      <button type="button" role="tab" :aria-selected="tab === 'stocktake'" :class="{ active: tab === 'stocktake' }" @click="switchTab('stocktake')">
        <span class="workspace-tab-icon" aria-hidden="true">📋</span>
        <span class="workspace-tab-text">Stok Opname<small>Per ruangan</small></span>
      </button>
    </nav>

    <!-- ============================== DASHBOARD ============================== -->
    <section v-if="tab === 'dashboard'" class="workspace-section">
      <div class="stat-grid" style="margin-bottom:16px;">
        <StatCard icon="📦" label="Total Aset" :value="summary?.total ?? '—'" color="#2563eb" :sub="'Cabang ' + (meta.branch || 'SBY')" />
        <StatCard icon="✅" label="Aktif" :value="summary?.by_status?.aktif ?? 0" color="#059669" />
        <StatCard icon="⛔" label="Rusak Berat" :value="summary?.broken ?? 0" color="#dc2626" />
        <StatCard icon="🏷️" label="Belum Berlabel" :value="summary?.unlabeled ?? 0" color="#d97706" />
        <StatCard icon="🌐" label="Kandidat Baru" :value="summary?.candidates ?? 0" color="#0891b2" />
        <StatCard icon="📅" label="Garansi < 30 hari" :value="summary?.warranty_soon ?? 0" color="#7c3aed" />
      </div>

      <div class="card card-pad" style="margin-bottom:16px;">
        <h3>Aksi Cepat</h3>
        <div class="row">
          <button class="btn btn-primary" @click="openAdd()">＋ Tambah Manual</button>
          <button class="btn" @click="switchTab('discovery')">🌐 Pindai Jaringan</button>
          <button class="btn" @click="switchTab('labels')">🏷️ Cetak Label</button>
          <button class="btn" @click="router.push('/it/scan')">📷 Scan / Ubah Kondisi</button>
          <button class="btn" @click="exportCsv">⬇️ Ekspor CSV</button>
          <button class="btn" @click="downloadReport">📄 Laporan PDF</button>
        </div>
      </div>

      <div class="card card-pad" style="margin-bottom:16px;">
        <h3>Garansi Akan Habis (30 hari)</h3>
        <div v-if="!warranty.length" class="muted">Tidak ada garansi yang segera habis.</div>
        <ul v-else class="timeline">
          <li v-for="w in warranty" :key="w.id">
            <span class="badge badge-amber">📅 {{ formatDate(w.warranty_until) }}</span>
            <router-link :to="`/it/assets/${w.asset_tag}`" class="mono">{{ w.asset_tag }}</router-link>
            <span>{{ assetTitle(w) }}</span>
            <span class="muted">{{ w.location_room || '—' }}</span>
            <span class="when">{{ w.assigned_to || '—' }}</span>
          </li>
        </ul>
      </div>

      <div class="card card-pad">
        <h3>Aktivitas Terakhir</h3>
        <div v-if="!summary?.recent?.length" class="muted">Belum ada aktivitas.</div>
        <ul v-else class="timeline">
          <li v-for="(ev, i) in summary.recent" :key="i">
            <span class="badge badge-gray">{{ EVENT_LABEL[ev.kind] || ev.kind }}</span>
            <router-link :to="`/it/assets/${ev.asset_tag}`" class="mono">{{ ev.asset_tag }}</router-link>
            <span class="muted">{{ ev.note || '' }}</span>
            <span class="when">{{ formatDateTime(ev.created_at) }} · {{ ev.actor || '—' }}</span>
          </li>
        </ul>
      </div>
    </section>

    <!-- ================================ ASET ================================= -->
    <section v-else-if="tab === 'assets'" class="workspace-section">
      <div class="card card-pad" style="margin-bottom:14px;">
        <div class="filters">
          <input class="input grow" v-model="filters.q" placeholder="🔍 Cari tag / merek / model / serial / hostname / PIC…" @keyup.enter="searchAssets" />
          <select class="select" v-model="filters.category" @change="searchAssets">
            <option value="">Semua kategori</option>
            <option v-for="c in meta.categories" :key="c.code" :value="c.code">{{ c.icon }} {{ c.label }}</option>
          </select>
          <select class="select" v-model="filters.status" @change="searchAssets">
            <option value="">Semua status</option>
            <option v-for="s in meta.statuses" :key="s" :value="s">{{ STATUS_LABEL[s] || s }}</option>
          </select>
          <select class="select" v-model="filters.cond" @change="searchAssets">
            <option value="">Semua kondisi</option>
            <option v-for="c in meta.conditions" :key="c" :value="c">{{ COND_META[c]?.label || c }}</option>
          </select>
          <input class="input" v-model="filters.room" placeholder="Ruangan" style="max-width:150px;" @keyup.enter="searchAssets" />
          <button class="btn" @click="searchAssets">Terapkan</button>
          <button class="btn" @click="resetFilters">Reset</button>
        </div>
        <div class="row" style="margin-top:12px;justify-content:space-between;">
          <div class="row">
            <button class="btn btn-sm" :disabled="!selected.length" @click="printLabels(selected)">
              🏷️ Cetak label terpilih ({{ selected.length }})
            </button>
            <button class="btn btn-sm" :disabled="!unlabeledOnPage.length" @click="printLabels(unlabeledOnPage.map(a => a.asset_tag))">
              🏷️ Label yang belum tercetak ({{ unlabeledOnPage.length }})
            </button>
            <button class="btn btn-sm" @click="exportCsv">⬇️ CSV</button>
            <button class="btn btn-sm" @click="downloadReport">📄 Laporan PDF</button>
          </div>
          <div class="muted">Menampilkan {{ assets.length }} dari {{ total }}</div>
        </div>
      </div>

      <LoadingState v-if="loading" />
      <ErrorState v-else-if="err" :message="err" @retry="loadAssets" />
      <EmptyState v-else-if="!assets.length" icon="📦" message="Belum ada aset"
                  hint="Tambah manual, impor CSV/XLSX, atau pindai jaringan untuk menemukan kandidat." />
      <div v-else class="table-wrap">
        <table class="tbl">
          <thead>
            <tr>
              <th style="width:34px;"><input type="checkbox" :checked="allSelected" @change="toggleAll" aria-label="Pilih semua" /></th>
              <th>Tag</th>
              <th>Kategori</th>
              <th>Merek / Model</th>
              <th>Status</th>
              <th>Kondisi</th>
              <th>Ruangan</th>
              <th>PIC</th>
              <th>Jaringan</th>
              <th>Label</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="a in assets" :key="a.id">
              <td><input type="checkbox" :checked="selected.includes(a.asset_tag)" @change="toggleOne(a.asset_tag)" :aria-label="'Pilih ' + a.asset_tag" /></td>
              <td><router-link :to="`/it/assets/${a.asset_tag}`" class="mono strong">{{ a.asset_tag }}</router-link></td>
              <td>{{ categoryLabel(a.category) }}</td>
              <td>{{ assetTitle(a) }}<div v-if="a.serial_number" class="muted tiny">SN {{ a.serial_number }}</div></td>
              <td><span class="badge" :class="STATUS_BADGE[a.status] || 'badge-gray'">{{ STATUS_LABEL[a.status] || a.status }}</span></td>
              <td><span class="badge" :class="COND_META[a.cond]?.badge || 'badge-gray'">{{ COND_META[a.cond]?.icon }} {{ COND_META[a.cond]?.label || a.cond }}</span></td>
              <td>{{ a.location_room || '—' }}</td>
              <td>{{ a.assigned_to || '—' }}</td>
              <td class="tiny">{{ a.hostname || a.ip_address || '—' }}</td>
              <td>
                <span v-if="a.label_printed_at" class="badge badge-green" :title="formatDate(a.label_printed_at)">tercetak</span>
                <span v-else class="badge badge-amber">belum</span>
              </td>
              <td class="ta-r">
                <button class="btn btn-sm" @click="printSingle(a.asset_tag)" title="Cetak label tunggal">🏷️</button>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
      <div v-if="pageCount > 1" class="row" style="justify-content:center;margin-top:14px;">
        <button class="btn btn-sm" :disabled="page === 1" @click="goPage(page - 1)">‹ Sebelumnya</button>
        <span class="muted">Halaman {{ page }} / {{ pageCount }}</span>
        <button class="btn btn-sm" :disabled="page === pageCount" @click="goPage(page + 1)">Berikutnya ›</button>
      </div>
    </section>

    <!-- ============================== JARINGAN =============================== -->
    <section v-else-if="tab === 'discovery'" class="workspace-section">
      <div class="card card-pad" style="margin-bottom:14px;">
        <div class="row" style="justify-content:space-between;">
          <div class="row">
            <button class="btn btn-primary" :disabled="scanning" @click="triggerScan">
              {{ scanning ? '⏳ Memindai…' : '🌐 Pindai Jaringan Sekarang' }}
            </button>
            <select class="select" v-model="discState" @change="loadDiscovery" style="max-width:160px;">
              <option value="new">Kandidat baru</option>
              <option value="ignored">Diabaikan</option>
              <option value="adopted">Sudah jadi aset</option>
              <option value="all">Semua</option>
            </select>
            <button class="btn" @click="loadDiscovery">🔄 Muat ulang</button>
          </div>
          <div class="muted tiny">Agen host: <code>scripts/it_discovery_agent.py</code> · agen WMI: <code>scripts/it_inventory_agent.ps1</code></div>
        </div>
        <p class="muted tiny" style="margin-top:8px;">
          Kandidat tidak pernah menjadi aset otomatis. Tinjau bukti (port, OUI, hostname) lalu pilih
          <strong>Jadikan Aset</strong> atau <strong>Abaikan</strong>.
        </p>
      </div>

      <LoadingState v-if="discLoading" />
      <EmptyState v-else-if="!candidates.length" icon="🌐" message="Belum ada kandidat"
                  hint="Jalankan sapuan dari tombol di atas, atau pasang agen host agar hasil otomatis masuk." />
      <div v-else class="table-wrap">
        <table class="tbl">
          <thead>
            <tr><th>IP</th><th>MAC</th><th>Hostname</th><th>Vendor</th><th>Port</th><th>Saran</th><th>Keyakinan</th><th>Terakhir</th><th></th></tr>
          </thead>
          <tbody>
            <tr v-for="c in candidates" :key="c.id">
              <td class="mono">{{ c.ip || '—' }}</td>
              <td class="mono tiny">{{ c.mac || '—' }}</td>
              <td>{{ c.hostname || '—' }}</td>
              <td>{{ c.vendor || '—' }}</td>
              <td class="tiny">{{ c.open_ports || '—' }}</td>
              <td>{{ categoryLabel(c.category_suggest) }}</td>
              <td>
                <span class="badge" :class="confidenceClass(c.confidence)">{{ Math.round(Number(c.confidence || 0) * 100) }}%</span>
                <div v-if="c.reasons?.length" class="muted tiny">{{ c.reasons.join(' · ') }}</div>
              </td>
              <td class="tiny">{{ formatDateTime(c.last_seen) }}</td>
              <td class="ta-r" style="white-space:nowrap;">
                <template v-if="c.state === 'new'">
                  <button class="btn btn-sm btn-primary" @click="openAdopt(c)">Jadikan Aset</button>
                  <button class="btn btn-sm" @click="ignoreCandidate(c)">Abaikan</button>
                </template>
                <span v-else class="badge badge-gray">{{ c.state }}</span>
              </td>
            </tr>
          </tbody>
        </table>
      </div>

      <div class="card card-pad" style="margin-top:16px;">
        <h3>Riwayat Sapuan</h3>
        <div v-if="!runs.length" class="muted">Belum ada sapuan.</div>
        <ul v-else class="timeline">
          <li v-for="r in runs" :key="r.id">
            <span class="badge" :class="r.status === 'ok' ? 'badge-green' : (r.status === 'error' ? 'badge-red' : 'badge-amber')">{{ r.status }}</span>
            <strong>#{{ r.id }}</strong> {{ r.method }} · {{ r.subnet || '—' }}
            <span class="muted">ditemukan {{ r.found }}, baru {{ r.new_count }}</span>
            <span class="when">{{ formatDateTime(r.started_at) }}</span>
            <div v-if="r.error" class="muted tiny">{{ r.error }}</div>
          </li>
        </ul>
      </div>
    </section>

    <!-- =============================== LABEL ================================= -->
    <section v-else-if="tab === 'labels'" class="workspace-section">
      <div class="card card-pad" style="margin-bottom:16px;">
        <h3>Cetak Label QR</h3>
        <div class="form-grid">
          <div class="field">
            <label>Layout stiker</label>
            <select class="select" v-model="labelLayout">
              <option value="a4-24">A4 · 3×8 (24 label 63×35 mm) — standar</option>
              <option value="a4-16">A4 · 2×8 (16 label lebih besar)</option>
              <option value="a4-12">A4 · 2×6 (12 label besar)</option>
            </select>
          </div>
          <div class="field">
            <label>Cakupan</label>
            <div class="muted" style="font-size:12px;">
              {{ selected.length ? selected.length + ' aset terpilih' : 'semua aset yang belum pernah dicetak (maks 120)' }}
            </div>
          </div>
        </div>
        <div class="row" style="margin-top:8px;">
          <button class="btn btn-primary" :disabled="labelBusy" @click="printLabels(selected.length ? selected : null)">
            {{ labelBusy ? '⏳ Membuat PDF…' : '🏷️ Unduh PDF Label' }}
          </button>
          <router-link class="btn" to="/it/inventory?tab=assets">Pilih aset dulu</router-link>
        </div>
      </div>

      <div class="card card-pad">
        <h3>Prosedur Baku Pelabelan</h3>
        <ol class="procedure">
          <li><strong>Data minimum</strong> — kategori, merek/model, nomor seri, ruangan, PIC sudah terisi.</li>
          <li><strong>Cetak</strong> pada stiker vinyl A4 tahan air; gunakan layout 3×8 (24 label) untuk perangkat biasa.</li>
          <li><strong>Uji scan satu label</strong> dengan kamera HP sebelum mencetak banyak.</li>
          <li><strong>Tempel</strong> sesuai jenis perangkat:
            <ul>
              <li>PC desktop: panel depan kanan atas casing (jangan menutup tombol/daya).</li>
              <li>Laptop: alas bawah dekat nomor seri; jangan menutup baut/garansi.</li>
              <li>Monitor: pangkal belakang, menghadap ke bawah.</li>
              <li>Printer: panel depan kanan.</li>
              <li>Switch/router/AP: panel depan kanan; di rack pakai label gantung.</li>
              <li>UPS: panel depan atas. Proyektor/TV: sisi belakang, tidak menutup ventilasi.</li>
              <li>Kabel/adaptor: label mini pada konektor.</li>
            </ul>
          </li>
          <li><strong>Foto perangkat berlabel</strong> lalu unggah lewat detail aset (riwayat tercatat).</li>
          <li><strong>Cetak ulang</strong> wajib mengisi alasan; cabut label lama agar tidak ganda.</li>
        </ol>
        <p class="muted tiny">Isi QR: URL publik aplikasi menuju detail aset. Bila perangkat tanpa akses internet, tag tetap bisa dicari manual di halaman Scan.</p>
      </div>
    </section>

    <!-- ============================ STOK OPNAME ============================== -->
    <section v-else-if="tab === 'stocktake'" class="workspace-section">
      <div class="card card-pad" style="margin-bottom:16px;">
        <h3>Mulai Sesi Stok Opname</h3>
        <div class="row">
          <input class="input" v-model="stRoom" placeholder="Ruangan (kosongkan = semua aset cabang)" style="max-width:340px;" />
          <button class="btn btn-primary" :disabled="stBusy" @click="startStocktake">▶ Mulai Sesi</button>
        </div>
        <p class="muted tiny" style="margin-top:8px;">Setiap aset pada ruangan otomatis masuk daftar perkiraan; scan QR di halaman Scan (atau pilih sesi) menandai ditemukan.</p>
      </div>

      <div v-if="stDetail" class="card card-pad" style="margin-bottom:16px;">
        <div class="row" style="justify-content:space-between;">
          <h3 style="margin:0;">Sesi #{{ stDetail.session.id }} — {{ stDetail.session.location_room || 'Semua ruangan' }}</h3>
          <div class="row">
            <span class="badge badge-green">✅ {{ stFound }} ditemukan</span>
            <span class="badge badge-red">⛔ {{ stMissing }} belum</span>
            <button class="btn btn-sm" @click="stDetail = null">Tutup tampilan</button>
            <button v-if="!stDetail.session.closed_at" class="btn btn-sm btn-danger" @click="closeStocktake">Akhiri Sesi</button>
          </div>
        </div>
        <div class="table-wrap" style="margin-top:12px;max-height:420px;">
          <table class="tbl">
            <thead><tr><th>Tag</th><th>Kategori</th><th>Merek/Model</th><th>Ruangan</th><th>Hasil</th><th>Waktu scan</th></tr></thead>
            <tbody>
              <tr v-for="i in stDetail.items" :key="i.id">
                <td class="mono">{{ i.asset_tag }}</td>
                <td>{{ categoryLabel(i.category) }}</td>
                <td>{{ assetTitle(i) }}</td>
                <td>{{ i.location_room || '—' }}</td>
                <td><span class="badge" :class="i.result === 'found' ? 'badge-green' : 'badge-red'">{{ i.result }}</span></td>
                <td class="tiny">{{ i.result === 'found' ? formatDateTime(i.scanned_at) : '—' }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>

      <div class="card card-pad">
        <h3>Riwayat Sesi</h3>
        <EmptyState v-if="!stSessions.length" icon="📋" message="Belum ada sesi stok opname" />
        <div v-else class="table-wrap">
          <table class="tbl">
            <thead><tr><th>#</th><th>Ruangan</th><th>Oleh</th><th>Mulai</th><th>Ditutup</th><th>Ditemukan</th><th></th></tr></thead>
            <tbody>
              <tr v-for="s in stSessions" :key="s.id">
                <td>#{{ s.id }}</td>
                <td>{{ s.location_room || 'Semua ruangan' }}</td>
                <td>{{ s.started_by }}</td>
                <td class="tiny">{{ formatDateTime(s.started_at) }}</td>
                <td class="tiny">{{ s.closed_at ? formatDateTime(s.closed_at) : '—' }}</td>
                <td>{{ s.total_found }} / {{ s.total_expected }}</td>
                <td class="ta-r"><button class="btn btn-sm" @click="openStocktake(s.id)">Lihat</button></td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </section>

    <!-- ============================== MODAL TAMBAH =========================== -->
    <Modal v-if="addModal" title="＋ Tambah Aset IT" wide @close="addModal = false">
      <div class="form-grid">
        <div class="field">
          <label>Kategori <span class="req">*</span></label>
          <select class="select" v-model="addForm.category">
            <option v-for="c in meta.categories" :key="c.code" :value="c.code">{{ c.icon }} {{ c.label }}</option>
          </select>
        </div>
        <div class="field"><label>Merek</label><input class="input" v-model="addForm.brand" placeholder="cth: Dell" /></div>
        <div class="field"><label>Model</label><input class="input" v-model="addForm.model" placeholder="cth: OptiPlex 7080" /></div>
        <div class="field"><label>Nomor Seri</label><input class="input" v-model="addForm.serial_number" placeholder="SN perangkat" /></div>
        <div class="field">
          <label>Status</label>
          <select class="select" v-model="addForm.status">
            <option v-for="s in meta.statuses" :key="s" :value="s">{{ STATUS_LABEL[s] || s }}</option>
          </select>
        </div>
        <div class="field">
          <label>Kondisi</label>
          <select class="select" v-model="addForm.cond">
            <option v-for="c in meta.conditions" :key="c" :value="c">{{ COND_META[c]?.label || c }}</option>
          </select>
        </div>
        <div class="field"><label>Ruangan</label><input class="input" v-model="addForm.location_room" placeholder="cth: Lantai 2 - Trading" /></div>
        <div class="field"><label>Detail Lokasi</label><input class="input" v-model="addForm.location_detail" placeholder="cth: Meja TRD02" /></div>
        <div class="field"><label>PIC / Pemakai</label><input class="input" v-model="addForm.assigned_to" placeholder="Nama karyawan" /></div>
        <div class="field"><label>Vendor / Toko</label><input class="input" v-model="addForm.vendor" /></div>
        <div class="field"><label>Tanggal Beli</label><input class="input" type="date" v-model="addForm.purchase_date" /></div>
        <div class="field"><label>Harga Beli (Rp)</label><input class="input" type="number" min="0" v-model="addForm.purchase_price" /></div>
        <div class="field"><label>Garansi Sampai</label><input class="input" type="date" v-model="addForm.warranty_until" /></div>
        <div class="field"><label>Hostname</label><input class="input" v-model="addForm.hostname" placeholder="cth: PC-TRD02" /></div>
        <div class="field"><label>IP Address</label><input class="input" v-model="addForm.ip_address" placeholder="192.168.2.10" /></div>
        <div class="field"><label>MAC Address</label><input class="input" v-model="addForm.mac_address" placeholder="AA:BB:CC:DD:EE:FF" /></div>
        <div class="field"><label>OS</label><input class="input" v-model="addForm.os_name" placeholder="cth: Windows 11 Pro" /></div>
      </div>
      <div class="field"><label>Catatan</label><textarea class="textarea" rows="2" v-model="addForm.notes"></textarea></div>
      <p class="muted tiny">Tag inventaris dibuat otomatis: <code>{{ meta.branch }}-IT-{{ (addForm.category || 'pc').toUpperCase() }}-0001</code> dst.</p>
      <div class="row" style="justify-content:flex-end;margin-top:10px;">
        <button class="btn" @click="addModal = false">Batal</button>
        <button class="btn btn-primary" :disabled="saving" @click="saveAsset">{{ saving ? 'Menyimpan…' : 'Simpan Aset' }}</button>
      </div>
    </Modal>

    <!-- =============================== MODAL IMPOR =========================== -->
    <Modal v-if="importModal" title="📥 Impor Massal Aset" wide @close="importModal = false">
      <p class="muted" style="font-size:12px;">
        Unggah CSV atau XLSX. Kolom yang dikenali: <code>kategori, merek, model, serial, status, kondisi,
        ruangan, detail_lokasi, pic, hostname, ip, mac, os, tanggal_beli, garansi, harga, vendor, catatan</code>.
        Kolom <code>asset_tag</code> opsional — kosong berarti dibuat otomatis.
      </p>
      <div class="field">
        <label>Berkas</label>
        <input class="input" type="file" accept=".csv,.xlsx,.xlsm" @change="e => { importFile = e.target.files[0]; importPreview = null }" />
      </div>
      <div v-if="importPreview" style="margin-top:10px;">
        <div class="row" style="margin-bottom:8px;">
          <span class="badge badge-green">{{ importPreview.valid.length }} baris siap</span>
          <span class="badge badge-red">{{ importPreview.errors.length }} error</span>
          <span class="muted">dari {{ importPreview.total }} baris</span>
        </div>
        <div v-if="importPreview.errors.length" class="table-wrap" style="max-height:180px;">
          <table class="tbl">
            <thead><tr><th>Baris</th><th>Masalah</th></tr></thead>
            <tbody><tr v-for="e in importPreview.errors" :key="e.row"><td>{{ e.row }}</td><td>{{ e.msg }}</td></tr></tbody>
          </table>
        </div>
        <details style="margin-top:8px;">
          <summary class="muted tiny">Lihat contoh baris valid</summary>
          <pre class="tiny" style="overflow:auto;max-height:160px;">{{ JSON.stringify(importPreview.valid.slice(0, 5), null, 2) }}</pre>
        </details>
      </div>
      <div class="row" style="justify-content:flex-end;margin-top:12px;">
        <button class="btn" @click="importModal = false">Batal</button>
        <button class="btn" :disabled="importBusy || !importFile" @click="postImport(false)">🔍 Pratinjau</button>
        <button class="btn btn-primary" :disabled="importBusy || !importPreview || !importPreview.valid.length" @click="postImport(true)">
          ✅ Impor {{ importPreview?.valid.length || 0 }} baris
        </button>
      </div>
    </Modal>

    <!-- =============================== MODAL ADOPSI ========================= -->
    <Modal v-if="adopting" :title="`Jadikan Aset — ${adopting.ip || adopting.mac}`" @close="adopting = null">
      <p class="muted" style="font-size:12px;">
        {{ adopting.hostname || 'tanpa hostname' }} · {{ adopting.vendor || 'vendor tidak dikenal' }}
        · port {{ adopting.open_ports || '—' }}
      </p>
      <div v-if="adopting.reasons?.length" class="muted tiny" style="margin-bottom:10px;">Bukti: {{ adopting.reasons.join(' · ') }}</div>
      <div class="form-grid">
        <div class="field">
          <label>Kategori</label>
          <select class="select" v-model="adoptForm.category">
            <option v-for="c in meta.categories" :key="c.code" :value="c.code">{{ c.icon }} {{ c.label }}</option>
          </select>
        </div>
        <div class="field"><label>Merek</label><input class="input" v-model="adoptForm.brand" /></div>
        <div class="field"><label>Model</label><input class="input" v-model="adoptForm.model" /></div>
        <div class="field"><label>Ruangan</label><input class="input" v-model="adoptForm.location_room" /></div>
        <div class="field"><label>PIC</label><input class="input" v-model="adoptForm.assigned_to" /></div>
      </div>
      <div class="row" style="justify-content:flex-end;margin-top:10px;">
        <button class="btn" @click="adopting = null">Batal</button>
        <button class="btn btn-primary" @click="confirmAdopt">Buat Aset</button>
      </div>
    </Modal>

    <ConfirmDialog ref="confirmRef" />
  </div>
</template>

<style scoped>
.it-inv { display: flex; flex-direction: column; }
.filters { display: flex; gap: 8px; flex-wrap: wrap; align-items: center; }
.filters .grow { flex: 1; min-width: 220px; }
.mono { font-family: ui-monospace, SFMono-Regular, Menlo, monospace; }
.strong { font-weight: 700; }
.tiny { font-size: 11px; }
.timeline { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: 8px; }
.timeline li { display: flex; gap: 8px; align-items: baseline; flex-wrap: wrap; font-size: 12.5px; padding-bottom: 8px; border-bottom: 1px dashed var(--border); }
.timeline li:last-child { border-bottom: none; }
.timeline .when { margin-left: auto; color: var(--text-3); font-size: 11px; }
.procedure { font-size: 13px; line-height: 1.7; padding-left: 18px; }
.procedure ul { margin-top: 4px; }
</style>
