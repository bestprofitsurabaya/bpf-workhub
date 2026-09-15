<script setup>
import { computed, onMounted, ref } from 'vue'
import { api } from '../../api'
import StatCard from '../../components/StatCard.vue'
import Modal from '../../components/Modal.vue'

const list = ref([])
const stats = ref(null)
const meta = ref({ uplines: [], users: [], statuses: [], user_options: [] })
const loading = ref(true)
const err = ref('')
const msg = ref('')
const busy = ref(false)

// Filter
const f = ref({ date_from: '', date_to: '', upline: '', user: '', status: '', search: '' })
const reportStage = ref('interview')

const STAGES = ['interview', 'training_1', 'training_2', 'training_3', 'training_4']
const STAGE_SHORT = { interview: 'I', training_1: 'H1', training_2: 'H2', training_3: 'H3', training_4: 'H4' }
const STATUS_BADGE = {
  interview: 'badge-blue', training_1: 'badge-cyan', training_2: 'badge-green',
  training_3: 'badge-purple', training_4: 'badge-orange', lulus: 'badge-green',
  resigned: 'badge-gray', rejected: 'badge-red',
}
const STATUS_LABELS = {
  interview: '📅 Interview', training_1: '📘 H1', training_2: '📗 H2',
  training_3: '📙 H3', training_4: '📕 H4', lulus: '🎓 Lulus',
  resigned: '🚪 Mengundurkan Diri', rejected: '✕ Ditolak',
}

async function load() {
  loading.value = true; err.value = ''
  try {
    const d = await api('/api/applicants', { params: { ...f.value } })
    list.value = d.data || []
    stats.value = d.stats || null
  } catch (e) { err.value = e.message }
  finally { loading.value = false }
}

async function loadMeta() {
  try { meta.value = await api('/api/applicants/meta') } catch { meta.value = { uplines: [], users: [], statuses: [] } }
}

// ---- Modal edit ----
const editAppt = ref(null)
const editForm = ref({ nama_lengkap: '', pendidikan: '', no_hp: '', upline: '', user: '', posisi: '', notes: '' })
const savingEdit = ref(false)

function openEdit(a) {
  editAppt.value = a
  editForm.value = {
    nama_lengkap: a.nama_lengkap || '', pendidikan: a.pendidikan || '', no_hp: a.no_hp || '',
    upline: a.upline || '', user: a.user_field || '', posisi: a.posisi || '', notes: a.notes || '',
  }
}
async function saveEdit() {
  savingEdit.value = true; msg.value = ''
  try {
    const r = await api(`/api/applicants/${editAppt.value.id}`, { method: 'PATCH', body: editForm.value })
    msg.value = '✅ ' + (r.msg || 'Disimpan')
    editAppt.value = null
    load()
  } catch (e) { msg.value = '❌ ' + e.message }
  finally { savingEdit.value = false }
}

// ---- Verifikasi ----
async function doVerify(a) {
  busy.value = true; msg.value = ''
  try {
    const r = await api(`/api/applicants/${a.id}/verify`, { method: 'POST' })
    msg.value = '✅ ' + (r.msg || 'Terverifikasi')
    load()
  } catch (e) { msg.value = '❌ ' + e.message }
  finally { busy.value = false }
}

// ---- Kehadiran ----
const attAppt = ref(null)
const attForm = ref({ note: '' })
const savingAtt = ref(false)
const attNow = new Date().toISOString().slice(0, 19).replace('T', ' ')

function openAttendance(a) {
  attAppt.value = a
  attForm.value = { note: '' }
}
async function markAttendance(stage) {
  savingAtt.value = true; msg.value = ''
  try {
    const r = await api(`/api/applicants/${attAppt.value.id}/attendance`, {
      method: 'POST', body: { stage, note: attForm.value.note },
    })
    msg.value = '✅ ' + (r.msg || 'Kehadiran tercatat')
    load()
  } catch (e) { msg.value = '❌ ' + e.message }
  finally { savingAtt.value = false }
}

// ---- Status (resign / lulus / tolak) ----
const statusAppt = ref(null)
const statusType = ref('resigned')
const statusForm = ref({ reason: '' })
const savingStatus = ref(false)

function openStatus(a, type) {
  statusAppt.value = a
  statusType.value = type
  statusForm.value = { reason: '' }
}
async function saveStatus() {
  const a = statusAppt.value
  if (!a) return
  if (statusType.value === 'resigned' && !statusForm.value.reason.trim()) {
    msg.value = '⚠️ Alasan mengundurkan diri wajib diisi (pelamar sudah pernah hadir).'
    return
  }
  savingStatus.value = true; msg.value = ''
  try {
    const r = await api(`/api/applicants/${a.id}/status`, {
      method: 'POST', body: { status: statusType.value, reason: statusForm.value.reason },
    })
    msg.value = '✅ ' + (r.msg || 'Status diperbarui')
    statusAppt.value = null
    load()
  } catch (e) { msg.value = '❌ ' + e.message }
  finally { savingStatus.value = false }
}

// ---- Hapus ----
async function doDelete(a) {
  if (!confirm(`Hapus ${a.display_id} (${a.nama_lengkap}) beserta seluruh riwayat kehadirannya?`)) return
  busy.value = true; msg.value = ''
  try {
    const r = await api(`/api/applicants/${a.id}`, { method: 'DELETE' })
    msg.value = '✅ ' + (r.msg || 'Dihapus')
    load()
  } catch (e) { msg.value = '❌ ' + e.message }
  finally { busy.value = false }
}

// ---- SYNC Google Sheet pelamar (v2.41.0) ----
const syncing = ref(false)
async function syncSheet() {
  if (!confirm('Tarik data terbaru dari Google Sheet pelamar? Baris sheet baru akan ditambahkan, data yang dikelola di sini (status/kehadiran) tidak tersentuh.')) return
  syncing.value = true; msg.value = ''
  try {
    const r = await api('/api/receptionist/sync/applicants', { method: 'POST' })
    msg.value = '✅ ' + (r.summary || 'Sinkronisasi selesai')
    load(); loadMeta()
  } catch (e) { msg.value = '❌ ' + e.message }
  finally { syncing.value = false }
}

// ---- Input manual pelamar (form dalam aplikasi, v2.41.0) ----
const addModal = ref(false)
const addForm = ref({ nama_lengkap: '', pendidikan: '', no_hp: '', upline: '', user: '', posisi: '', interview_at: '', h2_date: '' })
const savingAdd = ref(false)

function openAdd() {
  addForm.value = { nama_lengkap: '', pendidikan: '', no_hp: '', upline: '', user: '', posisi: '', interview_at: '', h2_date: '' }
  addModal.value = true
}
async function saveAdd() {
  if (!addForm.value.nama_lengkap.trim()) {
    msg.value = '⚠️ Nama Lengkap wajib diisi.'
    return
  }
  savingAdd.value = true; msg.value = ''
  try {
    const r = await api('/api/applicants/manual', { method: 'POST', body: addForm.value })
    msg.value = '✅ ' + (r.msg || 'Pelamar tercatat')
    addModal.value = false
    load()
  } catch (e) { msg.value = '❌ ' + e.message }
  finally { savingAdd.value = false }
}

// ---- Laporan PDF ----
function reportUrl() {
  const p = new URLSearchParams({ stage: reportStage.value })
  if (f.value.date_from) p.set('date_from', f.value.date_from)
  if (f.value.date_to) p.set('date_to', f.value.date_to)
  if (f.value.upline) p.set('upline', f.value.upline)
  if (f.value.user) p.set('user', f.value.user)
  return '/api/applicants/report?' + p.toString()
}

// ---- Kelola opsi User (dropdown) ----
const optModal = ref(false)
const optList = ref([])
const optNew = ref('')
const optBusy = ref(false)

async function loadOptions() {
  try {
    const d = await api('/api/applicants/user-options/manage')
    optList.value = d.options || []
  } catch { optList.value = [] }
}

function openOptions() {
  optModal.value = true; optNew.value = ''; loadOptions()
}

async function addOption() {
  const name = optNew.value.trim()
  if (!name) return
  optBusy.value = true; msg.value = ''
  try {
    const r = await api('/api/applicants/user-options', { method: 'POST', body: { name } })
    msg.value = '✅ ' + (r.msg || 'Ditambahkan')
    optNew.value = ''; loadOptions(); loadMeta()
  } catch (e) { msg.value = '❌ ' + e.message }
  finally { optBusy.value = false }
}

async function toggleOption(o) {
  optBusy.value = true
  try {
    await api(`/api/applicants/user-options/${o.id}`, { method: 'PATCH', body: { is_active: !o.is_active } })
    loadOptions(); loadMeta()
  } catch (e) { msg.value = '❌ ' + e.message }
  finally { optBusy.value = false }
}

async function delOption(o) {
  if (!confirm(`Hapus opsi User "${o.name}"?`)) return
  optBusy.value = true
  try {
    const r = await api(`/api/applicants/user-options/${o.id}`, { method: 'DELETE' })
    msg.value = '✅ ' + (r.msg || 'Dihapus')
    loadOptions(); loadMeta()
  } catch (e) { msg.value = '❌ ' + e.message }
  finally { optBusy.value = false }
}

const badge = (s) => STATUS_BADGE[s] || 'badge-gray'
const attended = (a, stage) => !!(a.attendance && a.attendance[stage] && a.attendance[stage].attended_at)
const terminal = (a) => ['lulus', 'resigned', 'rejected'].includes(a.status)

const totalAtt = computed(() => list.value.length)

onMounted(() => { load(); loadMeta() })
</script>

<template>
  <div>
    <div class="card card-pad" style="margin-bottom:16px;">
      <div class="row" style="flex-wrap:wrap;gap:10px;align-items:flex-end;">
        <div class="field" style="margin:0;"><label>Dari Tanggal</label>
          <input class="input" type="date" v-model="f.date_from" @change="load" /></div>
        <div class="field" style="margin:0;"><label>Sampai Tanggal</label>
          <input class="input" type="date" v-model="f.date_to" @change="load" /></div>
        <div class="field" style="margin:0;"><label>Upline</label>
          <select class="select" v-model="f.upline" @change="load" style="min-width:140px;">
            <option value="">Semua</option>
            <option v-for="u in meta.uplines" :key="u" :value="u">{{ u }}</option>
          </select></div>
        <div class="field" style="margin:0;"><label>User</label>
          <select class="select" v-model="f.user" @change="load" style="min-width:120px;">
            <option value="">Semua</option>
            <option v-for="u in meta.user_options" :key="u.id" :value="u.name">{{ u.name }}</option>
          </select></div>
        <div class="field" style="margin:0;"><label>Status</label>
          <select class="select" v-model="f.status" @change="load" style="min-width:140px;">
            <option value="">Semua status</option>
            <option v-for="s in meta.statuses" :key="s.value" :value="s.value">{{ s.label }}</option>
          </select></div>
        <div class="field" style="margin:0;flex:1;min-width:180px;"><label>🔍 Cari (nama/HP/posisi)</label>
          <input class="input" v-model="f.search" placeholder="Ketik lalu Enter…" @keyup.enter="load" /></div>
        <button class="btn" @click="load" title="Terapkan filter">🔍 Cari</button>
        <div class="spacer"></div>
        <div class="field" style="margin:0;"><label>Tahap Laporan</label>
          <select class="select" v-model="reportStage" style="min-width:150px;">
            <option value="interview">📅 Interview</option>
            <option value="training_1">📘 Training H1</option>
            <option value="training_2">📗 Training H2</option>
            <option value="training_3">📙 Training H3</option>
            <option value="training_4">📕 Training H4</option>
          </select></div>
        <a class="btn btn-primary" :href="reportUrl()" target="_blank">📄 Laporan PDF</a>
        <button class="btn btn-primary" :disabled="syncing" title="Tarik data terbaru dari Google Sheet pelamar (Google Form lama)" @click="syncSheet">{{ syncing ? '⏳ Sinkron…' : '🔄 Sync Sheet' }}</button>
        <button class="btn btn-primary" title="Catat pelamar baru langsung dari aplikasi" @click="openAdd">＋ Input Pelamar</button>
        <button class="btn" title="Kelola pilihan User untuk dropdown form" @click="openOptions">⚙️ Kelola User</button>
      </div>
      <div v-if="msg" class="alert" :class="msg.startsWith('✅') ? 'alert-success' : msg.startsWith('⚠️') ? 'alert-warning' : 'alert-error'" style="margin-top:10px;">{{ msg }}</div>
    </div>

    <div v-if="loading" class="empty skeleton">⏳ Memuat…</div>
    <div v-else-if="err" class="alert alert-error">{{ err }}</div>
    <template v-else>
      <div class="stat-grid" style="margin-bottom:16px;">
        <StatCard icon="👥" label="Total Pelamar" :value="stats?.total ?? totalAtt" color="#2563eb" />
        <StatCard icon="🕐" label="Hari Ini" :value="stats?.today ?? 0" color="#0891b2" />
        <StatCard icon="📅" label="Interview" :value="stats?.interview ?? 0" color="#d97706" />
        <StatCard icon="📘" label="Dalam Training" :value="(stats?.training_1 ?? 0) + (stats?.training_2 ?? 0) + (stats?.training_3 ?? 0) + (stats?.training_4 ?? 0)" color="#7c3aed" />
        <StatCard icon="🎓" label="Lulus" :value="stats?.lulus ?? 0" color="#059669" />
        <StatCard icon="🚪" label="Mengundurkan Diri" :value="stats?.resigned ?? 0" color="#dc2626" />
      </div>

      <div class="card">
        <div class="table-wrap">
          <table class="tbl">
            <thead>
              <tr><th>Pelamar</th><th>Posisi</th><th>Upline</th><th>User</th><th>Interview</th><th>Kehadiran</th><th>Status</th><th style="min-width:230px;">Aksi</th></tr>
            </thead>
            <tbody>
              <tr v-for="a in list" :key="a.id">
                <td>
                  <b>{{ a.nama_lengkap }}</b>
                  <div class="muted" style="font-size:11px;">{{ a.display_id }} · {{ a.no_hp || '—' }} · {{ a.pendidikan || '—' }}</div>
                  <div v-if="a.verified_by" class="muted" style="font-size:10px;color:#059669;">✅ Verifikasi: {{ a.verified_by }}</div>
                </td>
                <td>{{ a.posisi || '—' }}</td>
                <td>{{ a.upline || '—' }}</td>
                <td>{{ a.user_field || '—' }}</td>
                <td style="font-size:11px;">{{ (a.interview_at || '').slice(0, 16) }}</td>
                <td>
                  <div class="att-row">
                    <span v-for="s in STAGES" :key="s" class="att-chip" :class="attended(a, s) ? 'att-on' : ''"
                          :title="s + (attended(a, s) ? ' · ' + a.attendance[s].attended_at : ' — belum')">
                      {{ STAGE_SHORT[s] }}
                    </span>
                  </div>
                </td>
                <td><span class="badge" :class="badge(a.status)">{{ STATUS_LABELS[a.status] || a.status }}</span></td>
                <td style="white-space:nowrap;">
                  <button class="btn btn-sm" title="Edit / perbaiki data" @click="openEdit(a)">✏️</button>
                  <button v-if="!a.verified_by" class="btn btn-sm" title="Verifikasi data" @click="doVerify(a)">✅</button>
                  <button class="btn btn-sm" :disabled="terminal(a)" title="Catat kehadiran (interview / training)" @click="openAttendance(a)">🎯</button>
                  <button class="btn btn-sm" :disabled="terminal(a)" title="Mengundurkan diri (alasan wajib)" @click="openStatus(a, 'resigned')">🚪</button>
                  <button class="btn btn-sm" :disabled="terminal(a)" title="Lulus training" @click="openStatus(a, 'lulus')">🏁</button>
                  <button class="btn btn-sm btn-danger" :disabled="terminal(a)" title="Tolak" @click="openStatus(a, 'rejected')">✕</button>
                  <button class="btn btn-sm btn-danger" title="Hapus" @click="doDelete(a)">🗑</button>
                </td>
              </tr>
              <tr v-if="!list.length"><td colspan="8" class="empty">Belum ada data pelamar dengan filter ini.</td></tr>
            </tbody>
          </table>
        </div>
      </div>
    </template>

    <!-- Modal Edit -->
    <Modal v-if="editAppt" :title="'✏️ Edit ' + editAppt.display_id" @close="editAppt = null">
      <div class="form-grid">
        <div class="field"><label>Nama Lengkap <span class="req">*</span></label><input class="input" v-model="editForm.nama_lengkap" required /></div>
        <div class="field"><label>Pendidikan Terakhir</label><input class="input" v-model="editForm.pendidikan" /></div>
        <div class="field"><label>Nomor Telepon/HP</label><input class="input" v-model="editForm.no_hp" /></div>
        <div class="field"><label>UPLINE</label><input class="input" v-model="editForm.upline" /></div>
        <div class="field"><label>User</label>
          <select class="select" v-model="editForm.user">
            <option value="">— (kosong) —</option>
            <option v-for="u in meta.user_options" :key="u.id" :value="u.name">{{ u.name }}</option>
            <option v-if="editForm.user && !meta.user_options.some(u => u.name === editForm.user)" :value="editForm.user">{{ editForm.user }} (nilai lama)</option>
          </select></div>
        <div class="field"><label>Posisi Yang Dilamar</label><input class="input" v-model="editForm.posisi" /></div>
        <div class="field" style="grid-column:1/-1;"><label>Catatan</label><textarea class="textarea" v-model="editForm.notes" rows="2"></textarea></div>
      </div>
      <div class="row" style="justify-content:flex-end;gap:6px;margin-top:10px;">
        <button class="btn" @click="editAppt = null">Batal</button>
        <button class="btn btn-primary" :disabled="savingEdit" @click="saveEdit">{{ savingEdit ? '⏳…' : '💾 Simpan' }}</button>
      </div>
    </Modal>

    <!-- Modal Input Manual Pelamar (v2.41.0) -->
    <Modal v-if="addModal" title="＋ Input Pelamar Baru" @close="addModal = false">
      <p class="muted" style="font-size:12px;margin-bottom:10px;">
        Pengganti input manual di Google Sheet/Google Form. Kolom tanggal & jam kosong = otomatis sekarang.
      </p>
      <div class="form-grid">
        <div class="field"><label>Nama Lengkap <span class="req">*</span></label><input class="input" v-model="addForm.nama_lengkap" placeholder="cth: YOGA DWI REGAFIT" /></div>
        <div class="field"><label>Pendidikan Terakhir</label>
          <select class="select" v-model="addForm.pendidikan">
            <option value="">— pilih —</option>
            <option>SMP</option><option>SMA</option><option>SMK</option><option>D3</option><option>S1</option><option>S2</option>
          </select></div>
        <div class="field"><label>Nomor Telepon/HP</label><input class="input" v-model="addForm.no_hp" inputmode="tel" placeholder="cth: 85648127317" /></div>
        <div class="field"><label>UPLINE</label><input class="input" v-model="addForm.upline" placeholder="cth: BELA" /></div>
        <div class="field"><label>User</label>
          <select class="select" v-model="addForm.user">
            <option value="">— (kosong) —</option>
            <option v-for="u in meta.user_options" :key="u.id" :value="u.name">{{ u.name }}</option>
          </select></div>
        <div class="field"><label>Posisi Yang Dilamar</label>
          <select class="select" v-model="addForm.posisi">
            <option value="">— pilih —</option>
            <option>STAFF</option><option>ADMIN</option><option>MARKETING</option><option>DRIVER</option><option>OB</option><option>SECURITY</option>
          </select></div>
        <div class="field"><label>Tanggal & Jam Interview</label><input class="input" type="datetime-local" v-model="addForm.interview_at" /></div>
        <div class="field"><label>Tanggal H2 (opsional)</label><input class="input" type="date" v-model="addForm.h2_date" /></div>
      </div>
      <div class="row" style="justify-content:flex-end;gap:6px;margin-top:10px;">
        <button class="btn" @click="addModal = false">Batal</button>
        <button class="btn btn-primary" :disabled="savingAdd" @click="saveAdd">{{ savingAdd ? '⏳…' : '💾 Simpan' }}</button>
      </div>
    </Modal>

    <!-- Modal Kehadiran -->
    <Modal v-if="attAppt" :title="'🎯 Kehadiran — ' + attAppt.nama_lengkap" @close="attAppt = null">
      <p class="muted" style="font-size:12px;margin-bottom:10px;">{{ attAppt.display_id }} · {{ attAppt.posisi || '—' }} · Interview: {{ (attAppt.interview_at || '').slice(0, 16) }}</p>
      <div class="att-edit-list">
        <div v-for="s in STAGES" :key="s" class="att-edit-row">
          <span class="badge" :class="attended(attAppt, s) ? 'badge-green' : 'badge-gray'">
            {{ s === 'interview' ? '📅 Interview' : '📘 Training ' + s.slice(-1) }}
          </span>
          <span v-if="attended(attAppt, s)" class="muted" style="font-size:11px;">{{ (attAppt.attendance[s].attended_at || '').slice(0, 16) }}</span>
          <button class="btn btn-sm" :class="attended(attAppt, s) ? '' : 'btn-primary'"
                  :disabled="savingAtt" @click="markAttendance(s)">
            {{ attended(attAppt, s) ? '🔄 Perbarui' : '✅ Hadir' }}
          </button>
        </div>
      </div>
      <div class="field" style="margin-top:10px;"><label>Catatan kehadiran (opsional)</label>
        <input class="input" v-model="attForm.note" placeholder="cth: hadir tepat waktu" /></div>
      <div class="row" style="justify-content:flex-end;margin-top:10px;">
        <button class="btn" @click="attAppt = null">Tutup</button>
      </div>
    </Modal>

    <!-- Modal Kelola Opsi User -->
    <Modal v-if="optModal" title="⚙️ Kelola Pilihan User (Dropdown)" @close="optModal = false">
      <p class="muted" style="font-size:12px;margin-bottom:10px;">
        Pilihan ini muncul di dropdown form pendaftaran (publik) dan saat edit data pelamar.
        Nilai awal berasal dari data Google Sheet lama.
      </p>
      <div class="row" style="gap:6px;margin-bottom:12px;">
        <input class="input" v-model="optNew" placeholder="Nama User baru, cth: TEAM YUSIE 3" @keyup.enter="addOption" style="flex:1;" />
        <button class="btn btn-primary" :disabled="optBusy || !optNew.trim()" @click="addOption">＋ Tambah</button>
      </div>
      <div class="att-edit-list">
        <div v-for="o in optList" :key="o.id" class="att-edit-row">
          <span class="badge" :class="o.is_active ? 'badge-green' : 'badge-gray'">{{ o.is_active ? 'Aktif' : 'Nonaktif' }}</span>
          <b style="font-size:13px;">{{ o.name }}</b>
          <div class="spacer"></div>
          <button class="btn btn-sm" :disabled="optBusy" @click="toggleOption(o)" :title="o.is_active ? 'Nonaktifkan' : 'Aktifkan'">
            {{ o.is_active ? '🚫 Nonaktifkan' : '✅ Aktifkan' }}
          </button>
          <button class="btn btn-sm btn-danger" :disabled="optBusy" @click="delOption(o)" title="Hapus">🗑</button>
        </div>
        <div v-if="!optList.length" class="empty">Belum ada opsi. Tambahkan di atas.</div>
      </div>
      <div class="row" style="justify-content:flex-end;margin-top:12px;">
        <button class="btn" @click="optModal = false">Tutup</button>
      </div>
    </Modal>

    <!-- Modal Status -->
    <Modal v-if="statusAppt" :title="(statusType === 'lulus' ? '🏁 Lulus Training' : statusType === 'rejected' ? '✕ Tolak Pelamar' : '🚪 Mengundurkan Diri') + ' — ' + statusAppt.nama_lengkap" @close="statusAppt = null">
      <p class="muted" style="font-size:12px;">{{ statusAppt.display_id }}</p>
      <div v-if="statusType === 'resigned'" class="field" style="margin-top:8px;">
        <label>Alasan mengundurkan diri <span class="req">*</span></label>
        <textarea class="textarea" v-model="statusForm.reason" rows="3" required placeholder="Wajib diisi — pelamar sudah pernah hadir"></textarea>
        <div class="muted" style="font-size:11px;margin-top:4px;">Alasan ini tersimpan sebagai jejak resmi (audit).</div>
      </div>
      <div v-else-if="statusType === 'rejected'" class="field" style="margin-top:8px;">
        <label>Alasan penolakan</label>
        <textarea class="textarea" v-model="statusForm.reason" rows="2"></textarea>
      </div>
      <div v-else class="alert alert-info" style="font-size:12px;">Pastikan pelamar sudah menyelesaikan 4 hari training sebelum dinyatakan lulus.</div>
      <div class="row" style="justify-content:flex-end;gap:6px;margin-top:12px;">
        <button class="btn" @click="statusAppt = null">Batal</button>
        <button class="btn btn-primary" :disabled="savingStatus" @click="saveStatus">{{ savingStatus ? '⏳…' : '💾 Simpan Status' }}</button>
      </div>
    </Modal>
  </div>
</template>

<style scoped>
.att-row { display: flex; gap: 3px; }
.att-chip {
  min-width: 22px; height: 20px; padding: 0 4px; border-radius: 6px; font-size: 10px; font-weight: 700;
  display: inline-flex; align-items: center; justify-content: center;
  background: var(--bg); border: 1px solid var(--border); color: var(--text-3);
}
.att-chip.att-on { background: #059669; border-color: #059669; color: #fff; }
.att-edit-list { display: grid; gap: 6px; }
.att-edit-row {
  display: flex; align-items: center; gap: 10px; padding: 8px 10px;
  border: 1px solid var(--border); border-radius: 10px; background: var(--bg);
}
.att-edit-row .spacer { flex: 1; }
.att-edit-row button { margin-left: auto; }
</style>
