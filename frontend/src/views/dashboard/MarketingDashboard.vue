<script setup>
import { onMounted, ref } from 'vue'
import { api } from '../../api'
import StatCard from '../../components/StatCard.vue'
import Modal from '../../components/Modal.vue'

const today = new Date().toISOString().slice(0, 10)
const list = ref([])
const stats = ref(null)
const loading = ref(true)
const err = ref('')

const form = ref({ appointment_date: today, sesi: '1', visit_time: '', nasabah_name: '', nasabah_phone: '', alamat: '', marketing_member: '', notes: '' })
const saving = ref(false)
const msg = ref('')

const members = ref([]) // saran nama marketing anggota (datalist)
const areaPreview = ref('') // hasil deteksi area otomatis dari alamat

// Rentang jam kunjungan per sesi (sinkron dengan SESI_TIME_RANGE backend)
const SESI_RANGES = { 1: ['08:00', '12:59'], 2: ['13:00', '17:59'] }
const rangeLabel = (s) => { const r = SESI_RANGES[s] || []; return r.length ? ` (${r[0]}–${r[1]})` : '' }

// Modal edit appointment (hanya milik sendiri & status scheduled)
const editAppt = ref(null)
const editForm = ref({ nasabah_name: '', nasabah_phone: '', alamat: '', sesi: '1', visit_time: '', marketing_member: '', notes: '' })
const savingEdit = ref(false)
const editMsg = ref('')

const VISIT_LABELS = { ditemui: '😊 Ditemui', prospek: '🤝 Prospek', gagal: '❌ Gagal' }

// Tab: today vs completed
const activeTab = ref('today') // 'today' | 'completed'
const completedList = ref([])
const completedLoading = ref(false)

async function loadCompleted() {
  completedLoading.value = true
  try {
    // Riwayat selesai milik marketing sendiri (endpoint khusus marketing,
    // bukan /completed yang khusus driver PWA) — v2.29.8
    const d = await api('/api/appointments/history', { params: { limit: 50 } })
    completedList.value = d.data || d.list || []
  } catch { completedList.value = [] }
  finally { completedLoading.value = false }
}

async function load() {
  try {
    const d = await api('/api/appointments', { params: { date: today } })
    list.value = d.data || d.list || []
    stats.value = d.stats || null
  } catch (e) { err.value = e.message }
  finally { loading.value = false }
}

async function loadMembers() {
  try {
    const d = await api('/api/marketing/members')
    members.value = d.members || []
  } catch { members.value = [] }
}

async function detectArea() {
  const alamat = form.value.alamat.trim()
  if (!alamat) { areaPreview.value = ''; return }
  try {
    const d = await api('/api/appointments/detect-area', { params: { alamat } })
    areaPreview.value = d.area || ''
  } catch { areaPreview.value = '' }
}

async function submit() {
  msg.value = ''
  if (!form.value.nasabah_name || !form.value.alamat || !form.value.marketing_member) {
    msg.value = '⚠️ Nama nasabah, alamat, dan nama marketing wajib diisi.'; return
  }
  saving.value = true
  try {
    const d = await api('/api/appointments', { method: 'POST', body: [form.value] })
    msg.value = '✅ ' + (d.message || d.msg || 'Appointment tersimpan')
    form.value = { appointment_date: today, sesi: '1', visit_time: '', nasabah_name: '', nasabah_phone: '', alamat: '', marketing_member: '', notes: '' }
    areaPreview.value = ''
    load()
  } catch (e) { msg.value = '❌ ' + e.message }
  finally { saving.value = false }
}

function openEdit(a) {
  editAppt.value = a
  editMsg.value = ''
  editForm.value = {
    nasabah_name: a.nasabah_name || '',
    nasabah_phone: a.nasabah_phone || '',
    alamat: a.alamat || '',
    sesi: a.sesi || '1',
    visit_time: (a.visit_time || '').slice(0, 5),
    marketing_member: a.marketing_member || '',
    notes: a.notes || '',
  }
}

async function saveEdit() {
  editMsg.value = ''
  if (!editForm.value.nasabah_name || !editForm.value.alamat || !editForm.value.marketing_member) {
    editMsg.value = '⚠️ Nama nasabah, alamat, dan nama marketing wajib diisi.'; return
  }
  savingEdit.value = true
  try {
    const d = await api(`/api/appointments/${editAppt.value.id}`, { method: 'PATCH', body: { ...editForm.value } })
    editMsg.value = '✅ ' + (d.msg || 'Appointment diperbarui')
    editAppt.value = null
    load()
  } catch (e) { editMsg.value = '❌ ' + e.message }
  finally { savingEdit.value = false }
}

const canceling = ref(false)
async function doCancel(a) {
  const reason = prompt(`Alasan membatalkan ${a.display_id} (${a.nasabah_name}):`, '')
  if (reason === null) return
  canceling.value = true
  msg.value = ''
  try {
    const d = await api(`/api/appointments/${a.id}/cancel`, { method: 'POST', body: { reason } })
    msg.value = '✅ ' + (d.msg || 'Appointment dibatalkan')
    load()
  } catch (e) { msg.value = '❌ ' + e.message }
  finally { canceling.value = false }
}

function visitBadge(a) { return a.visit_result ? (VISIT_LABELS[a.visit_result] || a.visit_result) : '' }

const STATUS = { scheduled: ['⏳ Menunggu Driver', 'badge-amber'], assigned: ['🚗 Ditugaskan', 'badge-blue'], completed: ['✅ Selesai', 'badge-green'], cancelled: ['✕ Batal', 'badge-gray'] }

onMounted(() => { load(); loadMembers(); loadCompleted() })
</script>

<template>
  <div>
    <div class="card card-pad" style="margin-bottom:16px;">
      <h3>📣 Input Appointment Baru</h3>
      <form @submit.prevent="submit">
        <div class="form-grid">
          <div class="field"><label>Tanggal <span class="req">*</span></label><input class="input" type="date" v-model="form.appointment_date" required /></div>
          <div class="field"><label>Sesi <span class="req">*</span></label>
            <select class="select" v-model="form.sesi">
              <option value="1">🌅 Sesi 1 (08.30)</option>
              <option value="2">🌆 Sesi 2 (14.30)</option>
            </select>
          </div>
          <div class="field"><label>Jam Kunjungan{{ rangeLabel(form.sesi) }}</label>
            <input class="input" type="time" v-model="form.visit_time" step="60" />
            <div class="muted" style="font-size:11px;">Kosongkan = otomatis jam mulai sesi ({{ form.sesi === '2' ? '14:30' : '08:30' }})</div>
          </div>
          <div class="field"><label>Nama Calon Nasabah <span class="req">*</span></label><input class="input" v-model="form.nasabah_name" placeholder="Nama nasabah" required /></div>
          <div class="field"><label>Nama Marketing (prospek) <span class="req">*</span></label>
            <input class="input" v-model="form.marketing_member" list="mk-members-list" placeholder="Anggota tim yang memprospek" required />
            <datalist id="mk-members-list">
              <option v-for="m in members" :key="m" :value="m">{{ m }}</option>
            </datalist>
          </div>
          <div class="field"><label>No. HP</label><input class="input" v-model="form.nasabah_phone" placeholder="08xx…" /></div>
          <div class="field"><label>Alamat lengkap <span class="req">*</span></label>
            <input class="input" v-model="form.alamat" placeholder="Alamat calon nasabah" required @change="detectArea" />
            <span v-if="areaPreview" class="badge badge-blue" style="margin-top:4px;">📍 Area terdeteksi: {{ areaPreview }}</span>
          </div>
          <div class="field" style="grid-column:1/-1;"><label>Catatan</label><textarea class="textarea" v-model="form.notes" rows="2"></textarea></div>
        </div>
        <div class="row">
          <button class="btn btn-primary" :disabled="saving">{{ saving ? '⏳ Menyimpan…' : '📤 Simpan Appointment' }}</button>
          <span v-if="msg" :class="msg.startsWith('✅') ? 'alert-success' : msg.startsWith('❌') ? 'alert-error' : 'alert-info'" class="alert" style="margin:0;padding:8px 12px;">{{ msg }}</span>
        </div>
      </form>
    </div>

    <div v-if="loading" class="empty skeleton">⏳ Memuat…</div>
    <div v-else-if="err" class="alert alert-error">{{ err }}</div>
    <template v-else>
      <div class="stat-grid" style="margin-bottom:16px;">
        <StatCard icon="📅" label="Total Hari Ini" :value="stats?.total ?? list.length" color="#2563eb" />
        <StatCard icon="🌅" label="Sesi 1" :value="stats?.sesi1 ?? 0" color="#d97706" />
        <StatCard icon="🌆" label="Sesi 2" :value="stats?.sesi2 ?? 0" color="#7c3aed" />
        <StatCard icon="✅" label="Selesai" :value="stats?.completed ?? 0" color="#059669" />
      </div>

      <!-- Tabs: Hari Ini / Selesai -->
      <div class="card" style="margin-bottom:16px;">
        <div class="card-pad row" style="border-bottom:1px solid var(--border);gap:8px;align-items:center;">
          <button class="btn btn-sm" :class="activeTab === 'today' ? 'btn-primary' : ''" @click="activeTab = 'today'">📅 Hari Ini</button>
          <button class="btn btn-sm" :class="activeTab === 'completed' ? 'btn-primary' : ''" @click="activeTab = 'completed'">✅ Selesai ({{ completedList.length }})</button>
        </div>
      </div>

      <div v-if="activeTab === 'completed'" class="card">
        <div v-if="completedLoading" class="empty skeleton">⏳ Memuat…</div>
        <div v-else-if="!completedList.length" class="empty">Belum ada appointment selesai.</div>
        <div v-else class="table-wrap">
          <table class="tbl">
            <thead><tr><th>Nasabah</th><th>Marketing</th><th>Tanggal</th><th>Sesi</th><th>Area</th><th>Driver</th><th>Hasil</th></tr></thead>
            <tbody>
              <tr v-for="a in completedList" :key="a.id">
                <td><b>{{ a.nasabah_name }}</b><div class="muted" style="font-size:11px;">{{ a.display_id }}</div></td>
                <td>{{ a.marketing_member }}</td>
                <td>{{ a.appointment_date }}</td>
                <td>{{ a.sesi === '2' ? '🌆' : '🌅' }}</td>
                <td>{{ a.area }}</td>
                <td>{{ a.driver_name || '—' }}</td>
                <td><span v-if="visitBadge(a)" class="badge badge-green">{{ visitBadge(a) }}</span><span v-else class="muted">—</span></td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>

      <div v-if="activeTab === 'today'" class="card">
        <div class="table-wrap">
          <table class="tbl">
            <thead><tr><th>Nasabah</th><th>Marketing</th><th>HP</th><th>Sesi</th><th>Area</th><th>Status</th><th>Hasil</th><th></th></tr></thead>
            <tbody>
              <tr v-for="a in list" :key="a.id">
                <td><b>{{ a.nasabah_name }}</b><div class="muted" style="font-size:11px;">{{ a.display_id }}</div></td>
                <td>{{ a.marketing_member }}</td>
                <td>{{ a.nasabah_phone || '—' }}</td>
                <td>{{ a.sesi === '2' ? '🌆' : '🌅' }} {{ (a.visit_time || (a.sesi === '2' ? '14:30' : '08:30')).slice(0, 5) }}</td>
                <td>{{ a.area }}</td>
                <td><span class="badge" :class="(STATUS[a.status] || STATUS.scheduled)[1]">{{ (STATUS[a.status] || STATUS.scheduled)[0] }}</span></td>
                <td><span v-if="visitBadge(a)" class="badge badge-green">{{ visitBadge(a) }}</span><span v-else class="muted">—</span></td>
                <td style="white-space:nowrap;">
                  <template v-if="a.status === 'scheduled'">
                    <button class="btn btn-sm" title="Edit appointment" @click="openEdit(a)">✏️ Edit</button>
                    <button class="btn btn-sm btn-danger" :disabled="canceling" style="margin-left:4px;" title="Batalkan appointment" @click="doCancel(a)">✕ Batal</button>
                  </template>
                  <span v-else class="muted" style="font-size:11px;">—</span>
                </td>
              </tr>
              <tr v-if="!list.length"><td colspan="8" class="empty">Belum ada appointment hari ini.</td></tr>
            </tbody>
          </table>
        </div>
      </div>
    </template>

    <!-- Modal Edit Appointment -->
    <Modal v-if="editAppt" :title="'✏️ Edit ' + editAppt.display_id" @close="editAppt = null">
      <form @submit.prevent="saveEdit">
        <div class="form-grid">
          <div class="field"><label>Nama Calon Nasabah <span class="req">*</span></label><input class="input" v-model="editForm.nasabah_name" required /></div>
          <div class="field"><label>Nama Marketing (prospek) <span class="req">*</span></label><input class="input" v-model="editForm.marketing_member" list="mk-members-list" required /></div>
          <div class="field"><label>No. HP</label><input class="input" v-model="editForm.nasabah_phone" /></div>
          <div class="field"><label>Sesi</label>
            <select class="select" v-model="editForm.sesi">
              <option value="1">🌅 Sesi 1 (08.30)</option>
              <option value="2">🌆 Sesi 2 (14.30)</option>
            </select>
          </div>
          <div class="field"><label>Jam Kunjungan{{ rangeLabel(editForm.sesi) }}</label>
            <input class="input" type="time" v-model="editForm.visit_time" step="60" />
            <div class="muted" style="font-size:11px;">Kosongkan = otomatis jam mulai sesi</div>
          </div>
          <div class="field" style="grid-column:1/-1;"><label>Alamat lengkap <span class="req">*</span></label><textarea class="textarea" v-model="editForm.alamat" rows="2" required></textarea></div>
          <div class="field" style="grid-column:1/-1;"><label>Catatan</label><textarea class="textarea" v-model="editForm.notes" rows="2"></textarea></div>
        </div>
        <div class="row" style="justify-content:flex-end;gap:6px;margin-top:10px;">
          <span v-if="editMsg" class="alert" :class="editMsg.startsWith('✅') ? 'alert-success' : 'alert-error'" style="margin:0;">{{ editMsg }}</span>
          <div class="spacer"></div>
          <button type="button" class="btn" @click="editAppt = null">Batal</button>
          <button class="btn btn-primary" :disabled="savingEdit">{{ savingEdit ? '⏳ Menyimpan…' : '💾 Simpan Perubahan' }}</button>
        </div>
      </form>
    </Modal>
  </div>
</template>
