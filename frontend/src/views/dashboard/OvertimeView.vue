<script setup>
import { ref, onMounted, watch } from 'vue'
import { api } from '../../api'
import StatCard from '../../components/StatCard.vue'
import Modal from '../../components/Modal.vue'

const tab = ref('driver') // 'driver' | 'ob'
const loading = ref(true)
const err = ref('')
const stats = ref(null)

// Filter Driver
const dFrom = ref('')
const dTo = ref('')
const dSearch = ref('')
const dSource = ref('')  // '' | 'sheet' | 'form'
const dList = ref([])

// Filter OB/Security
const oFrom = ref('')
const oTo = ref('')
const oSearch = ref('')
const oPosisi = ref('')
const oList = ref([])

const refreshing = ref(false)
const refreshMsg = ref('')
const showConfig = ref(false)
const cfgUrl = ref('')
const cfgSaving = ref(false)

// Edit & hapus data overtime
const editModul = ref('driver')
const editing = ref(null)   // row asli
const editForm = ref({})    // salinan utk diedit
const savingEdit = ref(false)
const confirmDel = ref(null) // { modul, id, nama } utk konfirmasi hapus

const formLink = window.location.origin + '/app/overtime-form'

async function loadStats() {
  try { stats.value = await api('/api/overtime/stats') } catch { stats.value = null }
}

async function loadDriver() {
  loading.value = true
  try {
    const d = await api('/api/overtime/driver', { params: { date_from: dFrom.value, date_to: dTo.value, search: dSearch.value, source: dSource.value } })
    dList.value = d.data || []
  } catch (e) { err.value = e.message } finally { loading.value = false }
}

async function loadOb() {
  loading.value = true
  try {
    const d = await api('/api/overtime/ob-security', { params: { date_from: oFrom.value, date_to: oTo.value, search: oSearch.value, posisi: oPosisi.value } })
    oList.value = d.data || []
  } catch (e) { err.value = e.message } finally { loading.value = false }
}

function loadTab() {
  err.value = ''
  if (tab.value === 'driver') loadDriver()
  else loadOb()
}

async function doRefresh() {
  refreshing.value = true
  refreshMsg.value = ''
  try {
    const d = await api('/api/overtime/driver/refresh', { method: 'POST' })
    refreshMsg.value = d.summary
    await Promise.all([loadDriver(), loadStats()])
  } catch (e) {
    refreshMsg.value = ''
    err.value = e.message
  } finally {
    refreshing.value = false
  }
}

async function openConfig() {
  showConfig.value = true
  cfgSaving.value = false
  try {
    const d = await api('/api/overtime/config')
    cfgUrl.value = d.sheet_url || ''
  } catch { cfgUrl.value = '' }
}

async function saveConfig() {
  cfgSaving.value = true
  try {
    await api('/api/overtime/config', { method: 'PATCH', body: { sheet_url: cfgUrl.value } })
    showConfig.value = false
  } catch (e) { alert('❌ ' + e.message) } finally { cfgSaving.value = false }
}

function downloadBlob(blob, fname) {
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = fname
  a.click()
  URL.revokeObjectURL(url)
}

async function downloadDriverPdf() {
  try {
    const blob = await api('/api/overtime/report', {
      raw: true,
      params: { modul: 'driver', date_from: dFrom.value, date_to: dTo.value, nama: dSearch.value, source: dSource.value },
    })
    const suffix = dSource.value ? `_${dSource.value}` : ''
    downloadBlob(blob, `Laporan_Overtime_Driver${suffix}_${new Date().toISOString().slice(0, 10)}.pdf`)
  } catch (e) { err.value = '❌ Gagal unduh PDF: ' + e.message }
}

async function downloadObPdf() {
  try {
    const blob = await api('/api/overtime/report', {
      raw: true,
      params: { modul: 'ob', date_from: oFrom.value, date_to: oTo.value, posisi: oPosisi.value, nama: oSearch.value },
    })
    downloadBlob(blob, `Laporan_Overtime_OB_Security_${new Date().toISOString().slice(0, 10)}.pdf`)
  } catch (e) { err.value = '❌ Gagal unduh PDF: ' + e.message }
}

// === Detail Report per Driver (File 2 format) ===
const detailDriver = ref('')
const detailFrom = ref('')
const detailTo = ref('')
const showDetailModal = ref(false)

async function downloadDetailPdf(nama) {
  const driverName = nama || detailDriver.value
  if (!driverName) { err.value = '⚠️ Pilih nama driver'; return }
  try {
    const blob = await api('/api/overtime/detail-report', {
      raw: true,
      params: { nama: driverName, date_from: detailFrom.value, date_to: detailTo.value, format: 'pdf' },
    })
    downloadBlob(blob, `Overtime_${driverName.replace(/\s+/g, '_')}_${new Date().toISOString().slice(0, 10)}.pdf`)
  } catch (e) { err.value = '❌ Gagal unduh PDF: ' + e.message }
}

async function downloadDetailExcel(nama) {
  const driverName = nama || detailDriver.value
  if (!driverName) { err.value = '⚠️ Pilih nama driver'; return }
  try {
    const blob = await api('/api/overtime/detail-report', {
      raw: true,
      params: { nama: driverName, date_from: detailFrom.value, date_to: detailTo.value, format: 'xlsx' },
    })
    downloadBlob(blob, `Overtime_${driverName.replace(/\s+/g, '_')}_${new Date().toISOString().slice(0, 10)}.xlsx`)
  } catch (e) { err.value = '❌ Gagal unduh Excel: ' + e.message }
}

function fmtWaktu(r) {
  const a = r.waktu_mulai || '—'
  const b = r.waktu_selesai || ''
  return b ? `${a} – ${b}` : a
}

function openEdit(r, modul) {
  editModul.value = modul
  editing.value = r
  editForm.value = {
    nama: r.nama || '',
    posisi: r.posisi || '',
    no_kendaraan: r.no_kendaraan || '',
    tanggal: r.tanggal || '',
    waktu_mulai: r.waktu_mulai || '',
    waktu_selesai: r.waktu_selesai || '',
    keterangan: r.keterangan || '',
    broker: r.broker || '',
    manager: r.manager || '',
    email: r.email || '',
  }
}

async function saveEdit() {
  if (!editing.value) return
  savingEdit.value = true
  try {
    const body = {}
    for (const k of ['nama', 'posisi', 'no_kendaraan', 'tanggal', 'waktu_mulai', 'waktu_selesai', 'keterangan', 'broker', 'manager', 'email']) {
      if (k in editForm.value) body[k] = editForm.value[k]
    }
    await api(`/api/overtime/${editModul.value}/${editing.value.id}`, { method: 'PATCH', body })
    editing.value = null
    await loadTab()
  } catch (e) { alert('❌ ' + e.message) } finally { savingEdit.value = false }
}

function askDelete(r, modul) {
  confirmDel.value = { modul, id: r.id, nama: r.nama || '', display: r.display_id || `#${r.id}` }
}

async function doDelete() {
  if (!confirmDel.value) return
  const { modul, id } = confirmDel.value
  try {
    await api(`/api/overtime/${modul}/${id}`, { method: 'DELETE' })
    confirmDel.value = null
    await Promise.all([loadTab(), loadStats()])
  } catch (e) { alert('❌ ' + e.message) }
}

onMounted(() => {
  loadStats()
  loadTab()
})

watch(tab, loadTab)
</script>

<template>
  <div class="page">
    <div class="card card-pad" style="margin-bottom:16px;display:flex;align-items:center;gap:12px;flex-wrap:wrap;">
      <div class="grow">
        <h2 style="margin:0;">⏰ Data Overtime</h2>
        <div class="muted" style="font-size:12px;">
          Overtime Driver (sinkronisasi Google Sheet) &amp; OB/Security (form publik) — khusus GA HR
        </div>
      </div>
      <a class="btn btn-primary" :href="formLink" target="_blank" rel="noopener">🔗 Form Publik OB/Security</a>
    </div>

    <div v-if="refreshMsg" class="alert alert-success">✅ Refresh selesai: {{ refreshMsg }}</div>
    <div v-if="err" class="alert alert-error">{{ err }}</div>

    <div class="stat-grid" style="margin-bottom:16px;">
      <StatCard icon="🚗" label="Overtime Driver" :value="stats?.driver?.total ?? '—'" color="#2563eb" :sub="'Refresh terakhir: ' + (stats?.driver?.last_refresh || 'belum')" />
      <StatCard icon="🧑‍🔧" label="Overtime OB/Security" :value="stats?.ob_security?.total ?? '—'" color="#7e22ce" :sub="(stats?.ob_security?.by_position?.OB ?? 0) + ' OB · ' + (stats?.ob_security?.by_position?.Security ?? 0) + ' Security'" />
    </div>

    <div class="card card-pad">
      <div class="tabs">
        <button class="tab" :class="{ on: tab === 'driver' }" @click="tab = 'driver'">🚗 Driver</button>
        <button class="tab" :class="{ on: tab === 'ob' }" @click="tab = 'ob'">🧑‍🔧 OB &amp; Security</button>
      </div>

      <!-- ===== TAB DRIVER ===== -->
      <template v-if="tab === 'driver'">
        <div class="filters">
          <input class="input" type="date" v-model="dFrom" @change="loadDriver" />
          <span class="muted">s/d</span>
          <input class="input" type="date" v-model="dTo" @change="loadDriver" />
          <input class="input grow" v-model="dSearch" placeholder="🔍 Cari nama / kendaraan / broker / keterangan…" @keyup.enter="loadDriver" />
          <select class="select" v-model="dSource" @change="loadDriver" style="max-width:140px;">
            <option value="">Semua Sumber</option>
            <option value="sheet">📥 Google Sheet</option>
            <option value="form">📝 Aplikasi</option>
          </select>
          <button class="btn" @click="loadDriver">🔍 Cari</button>
          <button class="btn" :disabled="refreshing" @click="doRefresh">{{ refreshing ? '⏳ Menyinkronkan…' : '🔄 Refresh dari Google Sheet' }}</button>
          <button class="btn" @click="openConfig">⚙️ Sumber Data</button>
          <button class="btn" @click="downloadDriverPdf">📄 PDF</button>
          <button class="btn" @click="showDetailModal = true">📋 Detail/Excel</button>
        </div>

        <div v-if="loading" class="empty skeleton">⏳ Memuat…</div>
        <div v-else>
          <div class="muted" style="font-size:12px;margin:8px 0;">{{ dList.length }} catatan ditampilkan</div>
          <div class="table-wrap">
            <table class="tbl">
              <thead><tr><th>Tanggal</th><th>Nama</th><th>No. Kendaraan</th><th>Waktu</th><th>Keterangan</th><th>Broker / Manager</th><th>Sumber</th><th></th></tr></thead>
              <tbody>
                <tr v-for="r in dList" :key="r.id" :data-id="r.id">
                  <td>{{ r.tanggal || '—' }}</td>
                  <td><b>{{ r.nama }}</b></td>
                  <td class="muted">{{ r.no_kendaraan || '—' }}</td>
                  <td>{{ fmtWaktu(r) }}</td>
                  <td class="muted">{{ r.keterangan || '—' }}</td>
                  <td class="muted">{{ (r.broker || r.manager) ? (r.broker || '—') + ' / ' + (r.manager || '—') : '—' }}</td>
                  <td><span class="badge badge-gray">{{ r.source === 'sheet' ? '📥 Sheet' : '📝 App' }}</span></td>
                  <td class="row-actions">
                    <button class="btn btn-xs" title="Edit" aria-label="Edit data" @click="openEdit(r, 'driver')">✏️</button>
                    <button class="btn btn-xs btn-danger" title="Hapus" aria-label="Hapus data" @click="askDelete(r, 'driver')">🗑️</button>
                  </td>
                </tr>
                <tr v-if="!dList.length"><td colspan="8" class="empty">Belum ada data — klik 🔄 Refresh untuk menarik data dari Google Sheet.</td></tr>
              </tbody>
            </table>
          </div>
        </div>
      </template>

      <!-- ===== TAB OB & SECURITY ===== -->
      <template v-else>
        <div class="filters">
          <select class="select" v-model="oPosisi" @change="loadOb">
            <option value="">Semua Posisi</option>
            <option value="OB">OB</option>
            <option value="Security">Security</option>
          </select>
          <input class="input" type="date" v-model="oFrom" @change="loadOb" />
          <span class="muted">s/d</span>
          <input class="input" type="date" v-model="oTo" @change="loadOb" />
          <input class="input grow" v-model="oSearch" placeholder="🔍 Cari nama / keterangan / nomor…" @keyup.enter="loadOb" />
          <button class="btn" @click="loadOb">🔍 Cari</button>
          <button class="btn" @click="downloadObPdf">📄 PDF</button>
        </div>

        <div v-if="loading" class="empty skeleton">⏳ Memuat…</div>
        <div v-else>
          <div class="muted" style="font-size:12px;margin:8px 0;">{{ oList.length }} catatan ditampilkan</div>
          <div class="table-wrap">
            <table class="tbl">
              <thead><tr><th>No.</th><th>Tanggal</th><th>Nama</th><th>Posisi</th><th>Waktu</th><th>Keterangan</th><th>Sumber</th><th></th></tr></thead>
              <tbody>
                <tr v-for="r in oList" :key="r.id">
                  <td class="muted">{{ r.display_id }}</td>
                  <td>{{ r.tanggal || '—' }}</td>
                  <td><b>{{ r.nama }}</b></td>
                  <td><span class="badge" :class="r.posisi === 'Security' ? 'badge-purple' : 'badge-cyan'">{{ r.posisi }}</span></td>
                  <td>{{ fmtWaktu(r) }}</td>
                  <td class="muted">{{ r.keterangan || '—' }}</td>
                  <td><span class="badge badge-gray">{{ r.source === 'migrasi' ? '📥 Migrasi' : '📝 Form' }}</span></td>
                  <td class="row-actions">
                    <button class="btn btn-xs" title="Edit" aria-label="Edit data" @click="openEdit(r, 'ob')">✏️</button>
                    <button class="btn btn-xs btn-danger" title="Hapus" aria-label="Hapus data" @click="askDelete(r, 'ob')">🗑️</button>
                  </td>
                </tr>
                <tr v-if="!oList.length"><td colspan="8" class="empty">Belum ada data overtime OB/Security.</td></tr>
              </tbody>
            </table>
          </div>
        </div>
      </template>
    </div>

    <Modal v-if="editing" :title="'✏️ Edit Overtime ' + (editModul === 'driver' ? 'Driver' : 'OB/Security')" @close="editing = null">
      <div class="field">
        <label>Nama</label>
        <input class="input" v-model="editForm.nama" placeholder="Nama karyawan" />
      </div>
      <div v-if="editModul === 'ob'" class="field">
        <label>Posisi</label>
        <select class="select" v-model="editForm.posisi">
          <option value="OB">OB</option>
          <option value="Security">Security</option>
        </select>
      </div>
      <div v-else class="field">
        <label>No. Kendaraan</label>
        <input class="input" v-model="editForm.no_kendaraan" placeholder="mis. W 6283 TV" />
      </div>
      <div class="field">
        <label>Tanggal</label>
        <input class="input" type="date" v-model="editForm.tanggal" />
      </div>
      <div class="row" style="gap:10px;">
        <div class="field grow">
          <label>Waktu Mulai</label>
          <input class="input" type="time" v-model="editForm.waktu_mulai" />
        </div>
        <div class="field grow">
          <label>Waktu Selesai</label>
          <input class="input" type="time" v-model="editForm.waktu_selesai" />
        </div>
      </div>
      <div class="field">
        <label>Keterangan</label>
        <input class="input" v-model="editForm.keterangan" placeholder="Keterangan…" />
      </div>
      <template v-if="editModul === 'driver'">
        <div class="row" style="gap:10px;">
          <div class="field grow">
            <label>Broker / Marketing</label>
            <input class="input" v-model="editForm.broker" />
          </div>
          <div class="field grow">
            <label>Manager / Team Leader</label>
            <input class="input" v-model="editForm.manager" />
          </div>
        </div>
      </template>
      <div class="row" style="justify-content:flex-end;margin-top:12px;">
        <button class="btn" @click="editing = null">Batal</button>
        <button class="btn btn-primary" :disabled="savingEdit" @click="saveEdit">{{ savingEdit ? '⏳ Menyimpan…' : '💾 Simpan' }}</button>
      </div>
    </Modal>

    <Modal v-if="confirmDel" title="🗑️ Hapus Data Overtime" @close="confirmDel = null">
      <p style="font-size:13px;">Yakin ingin menghapus <b>{{ confirmDel.nama }}</b> ({{ confirmDel.display }})?<br />Tindakan ini tidak bisa dibatalkan.</p>
      <div class="row" style="justify-content:flex-end;margin-top:12px;">
        <button class="btn" @click="confirmDel = null">Batal</button>
        <button class="btn btn-danger" @click="doDelete">🗑️ Hapus</button>
      </div>
    </Modal>

    <Modal v-if="showConfig" title="⚙️ Sumber Data Overtime Driver" @close="showConfig = false">
      <p class="muted" style="font-size:12px;margin-bottom:10px;">
        URL yang dibaca server saat tombol <b>Refresh</b> ditekan. Mendukung:
      </p>
      <ul class="cfg-list">
        <li><b>CSV publik</b> — sheet di-share "Anyone with the link" → pakai URL <code>…/gviz/tq?tqx=out:csv</code></li>
        <li><b>Google Apps Script Web App</b> — sheet tetap private; cukup akun Google mana pun yang SUDAH punya akses ke sheet (termasuk view/read-only) membuat script standalone (<code>scripts/apps_script_overtime_driver.gs</code>) dan mengembalikan <code>{"rows":[…]}</code> — tidak perlu akses pemilik</li>
      </ul>
      <div class="field">
        <label>URL sumber data</label>
        <input class="input" v-model="cfgUrl" placeholder="https://…" />
      </div>
      <div class="row" style="justify-content:flex-end;margin-top:12px;">
        <button class="btn" @click="showConfig = false">Batal</button>
        <button class="btn btn-primary" :disabled="cfgSaving" @click="saveConfig">💾 Simpan</button>
      </div>
    </Modal>

    <!-- Modal: Detail Report per Driver -->
    <Modal v-if="showDetailModal" title="📋 Detail Report per Driver" @close="showDetailModal = false">
      <p style="font-size:13px;color:var(--text-2);margin-bottom:12px;">Generate report detail overtime per driver (PDF atau Excel). Kolom Biaya kosong untuk diisi GA HR.</p>
      <div class="field">
        <label>Nama Driver *</label>
        <input class="input" v-model="detailDriver" placeholder="Cari nama driver..." list="driver-names" />
        <datalist id="driver-names">
          <option v-for="n in [...new Set(dList.map(r => r.nama))].sort()" :key="n" :value="n" />
        </datalist>
      </div>
      <div class="row" style="gap:8px;">
        <div class="field grow"><label>Dari</label><input class="input" type="date" v-model="detailFrom" /></div>
        <div class="field grow"><label>Sampai</label><input class="input" type="date" v-model="detailTo" /></div>
      </div>
      <div class="row" style="justify-content:flex-end;margin-top:12px;gap:8px;">
        <button class="btn" @click="showDetailModal = false">Batal</button>
        <button class="btn" :disabled="!detailDriver" @click="downloadDetailPdf()">📄 PDF</button>
        <button class="btn btn-primary" :disabled="!detailDriver" @click="downloadDetailExcel()">📊 Excel</button>
      </div>
    </Modal>
  </div>
</template>

<style scoped>
.tabs { display: flex; gap: 6px; margin-bottom: 14px; border-bottom: 1px solid var(--border); }
.tab {
  border: none; background: none; padding: 9px 16px; font-size: 13px; font-weight: 600;
  color: var(--text-2); border-bottom: 2px solid transparent; border-radius: 8px 8px 0 0;
}
.tab:hover { background: var(--surface-2); }
.tab.on { color: var(--primary); border-bottom-color: var(--primary); background: var(--primary-soft); }
.filters { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; margin-bottom: 12px; }
.filters .input, .filters .select { max-width: 180px; }
.cfg-list { margin: 6px 0 12px 18px; font-size: 12px; color: var(--text-2); display: grid; gap: 6px; }
.cfg-list code { background: var(--surface-2); padding: 1px 5px; border-radius: 5px; font-size: 11px; }
.row-actions { display: flex; gap: 4px; justify-content: flex-end; }
.btn-xs { padding: 3px 8px; font-size: 12px; }
</style>
