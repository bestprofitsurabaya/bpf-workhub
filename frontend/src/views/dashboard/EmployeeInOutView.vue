<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { api } from '../../api'
import StatCard from '../../components/StatCard.vue'
import Modal from '../../components/Modal.vue'
import { useStepupStore } from '../../stores/stepup'
import { useRealtimeStore } from '../../stores/realtime'
import ConfirmDialog from '../../components/ConfirmDialog.vue'
import PageHeader from '../../components/PageHeader.vue'

const confirmRef = ref(null)
const ask = (message, opts) => confirmRef.value?.open(message, opts) ?? Promise.resolve(false)

const stepup = useStepupStore()
const realtime = useRealtimeStore()
const list = ref([])
const stats = ref(null)
const roster = ref([])
const mode = ref('hybrid')
const lastSync = ref('')
const loading = ref(true)
const err = ref('')
const msg = ref('')
const busy = ref(false)
const syncing = ref(false)

// Filter
const f = ref({ date_from: '', date_to: '', search: '', status: '', source: '' })

async function load() {
  loading.value = true; err.value = ''
  try {
    const d = await api('/api/receptionist/inout', { params: { ...f.value } })
    list.value = d.data || []
    stats.value = d.stats || null
    roster.value = d.roster || []
    mode.value = d.mode || 'hybrid'
    lastSync.value = d.last_sync || ''
  } catch (e) { err.value = e.message }
  finally { loading.value = false }
}

// ---- Sync sheet (sumber baris sheet tetap dijaga) ----
async function doSync() {
  syncing.value = true; msg.value = ''
  try {
    const r = await api('/api/receptionist/sync/inout', { method: 'POST' })
    msg.value = '✅ ' + (r.summary || `${r.replaced ?? 0} baris sheet tersinkron`)
    load()
  } catch (e) { msg.value = '❌ ' + e.message }
  finally { syncing.value = false }
}

// ---- Catat keluar / masuk (v2.42.0) ----
const catatModal = ref(false)
const catatForm = ref({ nama: '', jabatan: '', arah: 'keluar', keterangan: '' })
const savingCatat = ref(false)
const catatMsg = ref('') // pesan di dalam modal — error utama tersembunyi di balik backdrop

function openCatat(arah) {
  catatForm.value = { nama: '', jabatan: '', arah, keterangan: '' }
  catatMsg.value = ''
  catatModal.value = true
}
function pickRoster(r) {
  catatForm.value.nama = r.nama
  catatForm.value.jabatan = r.jabatan || catatForm.value.jabatan
}
function pickRosterFromList(r) {
  // Klik chip roster: bila masih di luar, default catat MASUK (kembali).
  catatForm.value = { nama: r.nama, jabatan: r.jabatan || '', arah: r.di_luar ? 'masuk' : 'keluar', keterangan: '' }
  catatMsg.value = ''
  catatModal.value = true
}
async function saveCatat() {
  if (!catatForm.value.nama.trim()) {
    catatMsg.value = '⚠️ Nama karyawan wajib diisi.'
    return
  }
  savingCatat.value = true; catatMsg.value = ''
  try {
    const r = await api('/api/receptionist/inout', { method: 'POST', body: catatForm.value })
    msg.value = '✅ ' + (r.msg || 'Tercatat')
    catatModal.value = false
    load()
  } catch (e) { catatMsg.value = '❌ ' + e.message }
  finally { savingCatat.value = false }
}

// ---- Edit catatan app (step-up PIN) ----
const editModal = ref(false)
const editForm = ref({ nama: '', jabatan: '', keterangan: '', pergi: false, waktu_pergi: '', datang: false, waktu_datang: '' })
const editRow = ref(null)
const savingEdit = ref(false)
const editMsg = ref('') // pesan di dalam modal

function toLocalInput(dt) {
  return (dt || '').slice(0, 16) // 'YYYY-MM-DDTHH:MM' utk input datetime-local
}
function openEdit(r) {
  editRow.value = r
  editForm.value = {
    nama: r.nama || '', jabatan: r.jabatan || '', keterangan: r.keterangan || '',
    pergi: !!r.pergi, waktu_pergi: toLocalInput((r.waktu_pergi || '').replace(' ', 'T')),
    datang: !!r.datang, waktu_datang: toLocalInput((r.waktu_datang || '').replace(' ', 'T')),
  }
  editMsg.value = ''
  editModal.value = true
}
async function saveEdit() {
  const r = editRow.value
  if (!r) return
  savingEdit.value = true; editMsg.value = ''
  const body = {
    nama: editForm.value.nama, jabatan: editForm.value.jabatan,
    keterangan: editForm.value.keterangan,
    pergi: editForm.value.pergi ? 1 : 0,
    datang: editForm.value.datang ? 1 : 0,
  }
  if (editForm.value.waktu_pergi) body.waktu_pergi = editForm.value.waktu_pergi.replace('T', ' ') + ':00'
  if (editForm.value.waktu_datang) body.waktu_datang = editForm.value.waktu_datang.replace('T', ' ') + ':00'
  try {
    const res = await stepup.require(
      () => api(`/api/receptionist/inout/${r.id}`, { method: 'PATCH', body }),
      'mengubah catatan in-out karyawan',
    )
    msg.value = '✅ ' + (res.msg || 'Disimpan')
    editModal.value = false
    load()
  } catch (e) { editMsg.value = '❌ ' + e.message }
  finally { savingEdit.value = false }
}

// ---- Hapus catatan app (step-up PIN) ----
async function doDelete(r) {
  if (!(await ask(`Hapus catatan in-out ${r.nama || ''}? Tercatat di audit log.`, { confirmText: 'Ya, lanjutkan', danger: true }))) return
  busy.value = true; msg.value = ''
  try {
    const res = await stepup.require(
      () => api(`/api/receptionist/inout/${r.id}`, { method: 'DELETE' }),
      'menghapus catatan in-out karyawan',
    )
    msg.value = '✅ ' + (res.msg || 'Dihapus')
    load()
  } catch (e) { msg.value = '❌ ' + e.message }
  finally { busy.value = false }
}

// ---- Riwayat audit per catatan ----
const logModal = ref(false)
const logRow = ref(null)
const logList = ref([])
async function openLog(r) {
  logRow.value = r
  logList.value = []
  logModal.value = true
  try {
    const d = await api(`/api/receptionist/inout/${r.id}/events`)
    logList.value = d.data || []
  } catch (e) { /* modal tetap terbuka dgn daftar kosong */ }
}
const EVENT_LABEL = {
  registrasi: '🆕 Registrasi karyawan',
  app_keluar: '📤 Catat keluar',
  app_masuk: '📥 Catat masuk',
  app_edit: '✏️ Edit',
  app_delete: '🗑️ Hapus',
}

// ---- Laporan harian PDF ----
function reportUrl() {
  const today = new Date().toISOString().slice(0, 10)
  const d = f.value.date_from || f.value.date_to || today
  return '/api/receptionist/inout/report?date=' + d
}

const editable = (r) => r.source !== 'sheet' || r.locked === true
const isApp = (r) => r.source !== 'sheet'
const SOURCE_LABEL = { app: '📱 App', registrasi: '🆕 Karyawan', sheet: '📄 Sheet' }
const STATUS_LABELS = {
  total: '📋 Total Catatan',
  out_now: '🚶 Masih di Luar',
  pergi_today: '📤 Keluar Hari Ini',
  datang_today: '📥 Kembali Hari Ini',
  app_today: '📱 Dicatat via App',
}

// v2.42.1: realtime — minta sync pull sekali saat halaman dibuka (debounce
// server 15 dtk), lalu muat ulang otomatis tiap push webhook / sync diterima.
let _lastSeq = 0
watch(() => realtime.receptionistSeq, (seq) => {
  if (seq !== _lastSeq) { _lastSeq = seq; load() }
})

onMounted(() => {
  load()
  api('/api/receptionist/realtime-sync', { method: 'POST' }).catch(() => {})
})
</script>

<template>
  <div>
    <PageHeader icon="🚪" title="In-Out Karyawan" subtitle="Catatan keluar-masuk karyawan & sinkronisasi Google Sheet" />
    <div class="card card-pad" style="margin-bottom:16px;">
      <div class="row" style="flex-wrap:wrap;gap:10px;align-items:flex-end;">
        <div class="field" style="margin:0;"><label>Dari Tanggal</label>
          <input class="input" type="date" v-model="f.date_from" @change="load" /></div>
        <div class="field" style="margin:0;"><label>Sampai Tanggal</label>
          <input class="input" type="date" v-model="f.date_to" @change="load" /></div>
        <div class="field" style="margin:0;"><label>Status</label>
          <select class="select" v-model="f.status" @change="load" style="min-width:130px;">
            <option value="">Semua</option>
            <option value="out">Masih di luar</option>
            <option value="in">Sudah kembali</option>
          </select></div>
        <div class="field" style="margin:0;"><label>Sumber</label>
          <select class="select" v-model="f.source" @change="load" style="min-width:120px;">
            <option value="">Semua sumber</option>
            <option value="app">📱 App</option>
            <option value="registrasi">🆕 Karyawan</option>
            <option value="sheet">📄 Sheet</option>
          </select></div>
        <div class="field" style="margin:0;flex:1;min-width:170px;"><label>🔍 Cari (nama/jabatan/keterangan)</label>
          <input class="input" v-model="f.search" placeholder="Ketik lalu Enter…" @keyup.enter="load" /></div>
        <button class="btn" @click="load">🔍 Cari</button>
        <div class="spacer"></div>
        <a class="btn" :href="reportUrl()" target="_blank" title="Laporan harian PDF (tanggal filter pertama / hari ini)">📄 Laporan Harian</a>
        <button v-if="mode === 'hybrid'" class="btn btn-primary" @click="openCatat('keluar')" title="Catat karyawan keluar kantor">📤 Keluar</button>
        <button v-if="mode === 'hybrid'" class="btn btn-primary" @click="openCatat('masuk')" title="Catat karyawan kembali">📥 Masuk</button>
        <button class="btn" :disabled="syncing" @click="doSync" title="Tarik data terbaru dari Google Sheet In-Out Karyawan">
          {{ syncing ? '⏳…' : '🔄 Sync Sheet' }}
        </button>
      </div>
      <div v-if="msg" class="alert" :class="msg.startsWith('✅') ? 'alert-success' : msg.startsWith('⚠️') ? 'alert-warning' : 'alert-error'" style="margin-top:10px;">{{ msg }}</div>
      <div v-else-if="mode !== 'hybrid'" class="alert alert-warning" style="margin-top:10px;font-size:12px;">
        Mode pencatatan: <b>sheet</b> — halaman ini read-only. Admin bisa mengaktifkan mode <b>hybrid</b> di Pengaturan agar resepsionis bisa mencatat keluar/masuk langsung dari aplikasi.
      </div>
      <div v-if="lastSync" class="muted" style="font-size:11px;margin-top:8px;">Sinkron sheet terakhir: {{ lastSync }}</div>
    </div>

    <div v-if="loading" class="empty skeleton">⏳ Memuat…</div>
    <div v-else-if="err" class="alert alert-error">{{ err }}</div>
    <template v-else>
      <div class="stat-grid" style="margin-bottom:16px;">
        <StatCard v-for="(label, key) in STATUS_LABELS" :key="key" :icon="label.split(' ')[0]"
                  :label="label.split(' ').slice(1).join(' ')" :value="stats?.[key] ?? 0"
                  :color="{ total: '#2563eb', out_now: '#d97706', pergi_today: '#0891b2', datang_today: '#059669', app_today: '#7c3aed' }[key]" />
      </div>

      <div class="card" style="margin-bottom:16px;">
        <div class="table-wrap">
          <table class="tbl">
            <thead>
              <tr><th>Nama</th><th>Jabatan/Posisi</th><th>Keluar</th><th>Waktu Keluar</th><th>Kembali</th><th>Waktu Kembali</th><th>Keterangan</th><th>Sumber</th><th style="min-width:150px;">Aksi</th></tr>
            </thead>
            <tbody>
              <tr v-for="r in list" :key="r.id">
                <td><b>{{ r.nama || '—' }}</b></td>
                <td>{{ r.jabatan || '—' }}</td>
                <td><span class="badge" :class="r.pergi ? 'badge-green' : 'badge-gray'">{{ r.pergi ? '✅' : '—' }}</span></td>
                <td style="font-size:12px;">{{ (r.waktu_pergi || '').slice(5, 16) || '—' }}</td>
                <td><span class="badge" :class="r.datang ? 'badge-green' : 'badge-gray'">{{ r.datang ? '✅' : '—' }}</span></td>
                <td style="font-size:12px;">{{ (r.waktu_datang || '').slice(5, 16) || '—' }}</td>
                <td>{{ r.keterangan || '—' }}</td>
                <td><span class="badge" :class="isApp(r) ? 'badge-purple' : 'badge-gray'" :title="'Sumber: ' + (SOURCE_LABEL[r.source] || r.source)">{{ SOURCE_LABEL[r.source] || r.source }}</span></td>
                <td style="white-space:nowrap;">
                  <button v-if="editable(r)" class="btn btn-sm" title="Edit catatan (perlu PIN)" @click="openEdit(r)">✏️</button>
                  <button class="btn btn-sm" title="Riwayat perubahan" @click="openLog(r)">🕘</button>
                  <button v-if="editable(r)" class="btn btn-sm btn-danger" title="Hapus catatan (perlu PIN)" @click="doDelete(r)">🗑</button>
                </td>
              </tr>
              <tr v-if="!list.length">
                <td colspan="9" class="empty">
                  Belum ada data. <template v-if="mode === 'hybrid'">Gunakan tombol <b>📤 Keluar</b> / <b>📥 Masuk</b> untuk mencatat, atau <b>🔄 Sync Sheet</b> untuk menarik data Google Sheet.</template>
                  <template v-else>Tekan <b>🔄 Sync Sheet</b> untuk menarik data Google Sheet.</template>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>

      <!-- Roster karyawan (agregat dari riwayat) -->
      <div class="card card-pad">
        <h3 style="margin:0 0 10px;">👥 Daftar Karyawan <span class="badge badge-blue" style="font-size:10px;vertical-align:middle;">{{ roster.length }} orang</span></h3>
        <p class="muted" style="font-size:11px;margin:0 0 10px;">
          Agregat dari seluruh riwayat in-out — klik nama untuk mengisi form pencatatan cepat.
        </p>
        <div class="roster-grid">
          <button v-for="r in roster" :key="r.nama" class="roster-chip" :class="{ 'roster-out': r.di_luar }"
                  :disabled="mode !== 'hybrid'" :title="r.di_luar ? `${r.nama} masih di luar` : r.jabatan || r.nama"
                  @click="pickRosterFromList(r)">
            <span class="roster-dot" :class="{ 'dot-out': r.di_luar }"></span>
            {{ r.nama }}<small v-if="r.jabatan"> · {{ r.jabatan }}</small>
            <em v-if="r.di_luar"> · di luar</em>
          </button>
          <div v-if="!roster.length" class="empty">Belum ada data karyawan — akan terisi otomatis dari riwayat in-out.</div>
        </div>
      </div>
    </template>

    <!-- Modal Catat Keluar/Masuk -->
    <Modal v-if="catatModal" :title="catatForm.arah === 'keluar' ? '📤 Catat Keluar Kantor' : '📥 Catat Masuk (Kembali)'" @close="catatModal = false">
      <p class="muted" style="font-size:12px;margin-bottom:10px;">
        Waktu diambil otomatis dari <b>sekarang</b>.
        <template v-if="catatForm.arah === 'keluar'"> Saat karyawan kembali, klik <b>📥 Masuk</b> — catatan keluarnya otomatis dilengkapi.</template>
      </p>
      <div v-if="catatMsg" class="alert" :class="catatMsg.startsWith('⚠️') ? 'alert-warning' : 'alert-error'" style="margin-bottom:10px;font-size:12px;">{{ catatMsg }}</div>
      <div class="form-grid">
        <div class="field"><label>Nama Karyawan <span class="req">*</span></label>
          <input class="input" v-model="catatForm.nama" list="roster-names" placeholder="Ketik atau pilih dari daftar" @keyup.enter="saveCatat" />
          <datalist id="roster-names">
            <option v-for="r in roster" :key="r.nama" :value="r.nama">{{ r.jabatan || '' }}</option>
          </datalist>
        </div>
        <div class="field"><label>Jabatan/Posisi</label><input class="input" v-model="catatForm.jabatan" placeholder="cth: STAFF" /></div>
        <div class="field" style="grid-column:1/-1;"><label>Arah</label>
          <div class="row" style="gap:8px;">
            <label class="radio-pill" :class="{ active: catatForm.arah === 'keluar' }">
              <input type="radio" value="keluar" v-model="catatForm.arah" /> 📤 Keluar
            </label>
            <label class="radio-pill" :class="{ active: catatForm.arah === 'masuk' }">
              <input type="radio" value="masuk" v-model="catatForm.arah" /> 📥 Masuk
            </label>
          </div>
        </div>
        <div class="field" style="grid-column:1/-1;"><label>Keterangan</label>
          <input class="input" v-model="catatForm.keterangan" placeholder="cth: survei pasar, antar dokumen" /></div>
      </div>
      <div v-if="roster.length" class="muted" style="font-size:11px;margin-top:8px;">
        Cepat: klik salah satu —
        <button v-for="r in roster.slice(0, 8)" :key="r.nama" class="btn btn-sm" style="margin:2px;" @click="pickRoster(r)">{{ r.nama }}</button>
      </div>
      <div class="row" style="justify-content:flex-end;gap:6px;margin-top:10px;">
        <button class="btn" @click="catatModal = false">Batal</button>
        <button class="btn btn-primary" :disabled="savingCatat || !catatForm.nama.trim()" @click="saveCatat">
          {{ savingCatat ? '⏳…' : (catatForm.arah === 'keluar' ? '📤 Catat Keluar' : '📥 Catat Masuk') }}
        </button>
      </div>
    </Modal>

    <!-- Modal Edit (step-up PIN) -->
    <Modal v-if="editModal" :title="'✏️ Edit Catatan — ' + (editRow?.nama || '')" @close="editModal = false">
      <div v-if="editMsg" class="alert alert-error" style="margin-bottom:10px;font-size:12px;">{{ editMsg }}</div>
      <div class="form-grid">
        <div class="field"><label>Nama <span class="req">*</span></label><input class="input" v-model="editForm.nama" /></div>
        <div class="field"><label>Jabatan/Posisi</label><input class="input" v-model="editForm.jabatan" /></div>
        <div class="field"><label>✅ Keluar</label>
          <label class="check-line"><input type="checkbox" v-model="editForm.pergi" /> sudah keluar</label></div>
        <div class="field"><label>Waktu Keluar</label>
          <input class="input" type="datetime-local" v-model="editForm.waktu_pergi" :disabled="!editForm.pergi" /></div>
        <div class="field"><label>✅ Kembali</label>
          <label class="check-line"><input type="checkbox" v-model="editForm.datang" /> sudah kembali</label></div>
        <div class="field"><label>Waktu Kembali</label>
          <input class="input" type="datetime-local" v-model="editForm.waktu_datang" :disabled="!editForm.datang" /></div>
        <div class="field" style="grid-column:1/-1;"><label>Keterangan</label>
          <input class="input" v-model="editForm.keterangan" /></div>
      </div>
      <p class="muted" style="font-size:11px;margin-top:8px;">🔒 Menyimpan perlu verifikasi PIN (step-up) dan tercatat di audit log.</p>
      <div class="row" style="justify-content:flex-end;gap:6px;margin-top:10px;">
        <button class="btn" @click="editModal = false">Batal</button>
        <button class="btn btn-primary" :disabled="savingEdit" @click="saveEdit">{{ savingEdit ? '⏳…' : '💾 Simpan' }}</button>
      </div>
    </Modal>

    <!-- Modal Riwayat -->
    <Modal v-if="logModal" :title="'🕘 Riwayat — ' + (logRow?.nama || '')" @close="logModal = false">
      <div class="att-edit-list">
        <div v-for="e in logList" :key="e.id" class="att-edit-row">
          <span class="badge badge-blue">{{ EVENT_LABEL[e.event_type] || e.event_type }}</span>
          <div style="flex:1;font-size:12px;">
            <div>{{ (e.event_at || '').slice(0, 16) }} · {{ e.actor_name || e.actor_username || '?' }}</div>
            <div v-if="e.keterangan" class="muted">{{ e.keterangan }}</div>
          </div>
        </div>
        <div v-if="!logList.length" class="empty">Belum ada peristiwa tercatat untuk catatan ini.</div>
      </div>
      <div class="row" style="justify-content:flex-end;margin-top:10px;">
        <button class="btn" @click="logModal = false">Tutup</button>
      </div>
    </Modal>
  </div>
  <ConfirmDialog ref="confirmRef" />
</template>

<style scoped>
.att-edit-list { display: grid; gap: 6px; }
.att-edit-row {
  display: flex; align-items: center; gap: 10px; padding: 8px 10px;
  border: 1px solid var(--border); border-radius: 10px; background: var(--bg);
}
.roster-grid { display: flex; flex-wrap: wrap; gap: 6px; }
.roster-chip {
  display: inline-flex; align-items: center; gap: 6px; padding: 5px 10px;
  border: 1px solid var(--border); border-radius: 999px; background: var(--bg);
  cursor: pointer; font-size: 12px; color: var(--text-2);
}
.roster-chip:disabled { opacity: 0.55; cursor: not-allowed; }
.roster-chip small { color: var(--text-3); }
.roster-chip em { font-style: normal; color: #d97706; font-size: 10px; font-weight: 700; }
.roster-dot { width: 8px; height: 8px; border-radius: 50%; background: #059669; }
.roster-dot.dot-out { background: #d97706; }
.radio-pill {
  display: inline-flex; align-items: center; gap: 6px; padding: 6px 12px;
  border: 1px solid var(--border); border-radius: 999px; cursor: pointer; font-size: 13px;
}
.radio-pill.active { border-color: #2563eb; background: rgba(37, 99, 235, 0.08); font-weight: 600; }
.check-line { display: inline-flex; gap: 6px; align-items: center; font-size: 12px; }
</style>
