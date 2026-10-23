<script setup>
import { computed, onMounted, ref } from 'vue'
import { api } from '../../api'
import StatCard from '../../components/StatCard.vue'
import LoadingState from '../../components/LoadingState.vue'
import ErrorState from '../../components/ErrorState.vue'
import Modal from '../../components/Modal.vue'
import ConfirmDialog from '../../components/ConfirmDialog.vue'
import PageHeader from '../../components/PageHeader.vue'

const confirmRef = ref(null)
const ask = (message, opts) => confirmRef.value?.open(message, opts) ?? Promise.resolve(false)

const today = new Date().toISOString().slice(0, 10)
const date = ref(today)
const list = ref([])
const stats = ref(null)
const drivers = ref([])
const sug = ref({}) // saran driver per sesi { '1': 'RIVAN', '2': 'BUDI' }
const members = ref([]) // semua marketing anggota (untuk filter board)
const member = ref('') // filter anggota aktif
const memberSummary = ref([])
const sesiFilter = ref('all')
const loading = ref(true)
const err = ref('')
const selDriver = ref({}) // select assign per baris "Belum Ditugaskan"
const selGanti = ref({}) // select ganti driver per baris "Tugas Per Driver"
const busy = ref(false)
const msg = ref('')

// Modal hasil kunjungan (✅ Selesai / 🎯 ubah hasil)
const visitAppt = ref(null)
const visitForm = ref({ result: '', note: '' })
const savingVisit = ref(false)

// Modal Atur Rute Otomatis (v2.15)
const showPlan = ref(false)
const plan = ref(null)
const planLoading = ref(false)
const planErr = ref('')
const applying = ref(false)

const VISIT_LABELS = { ditemui: '😊 Ditemui', prospek: '🤝 Prospek', gagal: '❌ Gagal' }
const jam = (a) => (a.visit_time || (a.sesi === '2' ? '14:30' : '08:30')).slice(0, 5)

async function load() {
  loading.value = true; err.value = ''
  const params = { date: date.value }
  if (member.value) params.member = member.value
  try {
    const d = await api('/api/appointments', { params })
    list.value = d.data || d.list || []
    stats.value = d.stats || null
  } catch (e) { err.value = e.message }
  try { drivers.value = await api('/api/drivers') } catch { drivers.value = [] }
  try { sug.value = await api('/api/appointments/suggestions', { params: { date: date.value } }) } catch { sug.value = {} }
  try {
    const m = await api('/api/marketing/members')
    members.value = m.members || []
  } catch { members.value = [] }
  try {
    const ms = await api('/api/appointments/member-summary', { params: { date: date.value } })
    memberSummary.value = ms.members || []
  } catch { memberSummary.value = [] }
  // Isi default select assign dengan saran load-balancing per sesi (bila belum dipilih)
  for (const a of list.value) {
    if (a.status === 'scheduled' && !selDriver.value[a.id]) {
      selDriver.value[a.id] = sug.value[a.sesi] || ''
    }
  }
  loading.value = false
}

const scheduledRows = computed(() =>
  list.value.filter((a) => a.status === 'scheduled' && (sesiFilter.value === 'all' || a.sesi === sesiFilter.value)))

const byDriver = computed(() => {
  // Board menampilkan tugas berjalan (assigned) + kunjungan selesai (completed)
  // agar badge hasil kunjungan & tombol 🎯 Hasil tetap bisa diakses.
  const m = {}
  for (const a of list.value) {
    if ((a.status === 'assigned' || a.status === 'completed') && a.driver_name) {
      (m[a.driver_name] = m[a.driver_name] || []).push(a)
    }
  }
  return Object.entries(m)
})

function suggestFor(a) { return sug.value[a.sesi] || '' }

async function doAssign(a) {
  const driver = selDriver.value[a.id]
  if (!driver) return
  busy.value = true; msg.value = ''
  try {
    const r = await api(`/api/appointments/${a.id}/assign`, { method: 'POST', body: { driver_name: driver } })
    msg.value = '✅ ' + (r.message || r.msg || 'Ditugaskan')
    selDriver.value[a.id] = ''
    load()
  } catch (e) { msg.value = '❌ ' + e.message }
  finally { busy.value = false }
}

async function doGanti(a) {
  const driver = selGanti.value[a.id]
  if (!driver) return
  if (!(await ask(`Ganti driver ${a.driver_name || '-'} → ${driver} untuk ${a.display_id}?`, { confirmText: 'Ya, lanjutkan' }))) return
  busy.value = true; msg.value = ''
  try {
    const r = await api(`/api/appointments/${a.id}/assign`, { method: 'POST', body: { driver_name: driver } })
    msg.value = '✅ ' + (r.message || r.msg || 'Driver diganti')
    selGanti.value[a.id] = ''
    load()
  } catch (e) { msg.value = '❌ ' + e.message }
  finally { busy.value = false }
}

async function doUnassign(a) {
  if (!(await ask(`Batalkan penugasan ${a.display_id} dari ${a.driver_name}?`, { confirmText: 'Ya, lanjutkan', danger: true }))) return
  busy.value = true; msg.value = ''
  try {
    const r = await api(`/api/appointments/${a.id}/unassign`, { method: 'POST' })
    msg.value = '✅ ' + (r.msg || 'Penugasan dibatalkan')
    load()
  } catch (e) { msg.value = '❌ ' + e.message }
  finally { busy.value = false }
}

async function doCancel(a) {
  const reason = await ask(`Alasan membatalkan ${a.display_id} (${a.nasabah_name}):`, {
    title: 'Batalkan penugasan',
    confirmText: 'Batalkan',
    danger: true,
    input: true,
    required: true,
    placeholder: 'mis. nasabah membatalkan perjalanan',
  })
  if (reason === null) return
  busy.value = true; msg.value = ''
  try {
    const r = await api(`/api/appointments/${a.id}/cancel`, { method: 'POST', body: { reason } })
    msg.value = '✅ ' + (r.msg || 'Appointment dibatalkan')
    load()
  } catch (e) { msg.value = '❌ ' + e.message }
  finally { busy.value = false }
}

async function doArea(a) {
  const area = await ask(`Area untuk ${a.nasabah_name} (${a.display_id}):`, {
    title: 'Ubah area',
    confirmText: 'Simpan area',
    input: true,
    required: true,
    value: a.area || '',
    placeholder: 'mis. Surabaya Barat',
  })
  if (area === null || !area.trim()) return
  busy.value = true; msg.value = ''
  try {
    const r = await api(`/api/appointments/${a.id}`, { method: 'PATCH', body: { area: area.trim() } })
    msg.value = '✅ ' + (r.msg || 'Area diperbarui')
    load()
  } catch (e) { msg.value = '❌ ' + e.message }
  finally { busy.value = false }
}

function openVisit(a, edit = false) {
  visitAppt.value = a
  visitForm.value = { result: edit ? (a.visit_result || '') : '', note: edit ? (a.visit_note || '') : '' }
}

async function saveVisit() {
  const a = visitAppt.value
  if (!a) return
  savingVisit.value = true; msg.value = ''
  try {
    if (a.status === 'assigned') {
      // Chief Driver menandai selesai + mencatat hasil kunjungan (wajib pilih hasil)
      if (!visitForm.value.result) {
        msg.value = '⚠️ Pilih hasil kunjungan terlebih dahulu.'
        return
      }
      const r = await api(`/api/appointments/${a.id}/complete`, {
        method: 'POST', body: { result: visitForm.value.result, note: visitForm.value.note },
      })
      msg.value = '✅ ' + (r.msg || 'Appointment selesai')
    } else {
      // Edit hasil kunjungan kapan saja (PATCH visit_result/visit_note)
      const body = { visit_result: visitForm.value.result || '', visit_note: visitForm.value.note }
      const r = await api(`/api/appointments/${a.id}`, { method: 'PATCH', body })
      msg.value = '✅ ' + (r.msg || 'Hasil kunjungan disimpan')
    }
    visitAppt.value = null
    load()
  } catch (e) { msg.value = '❌ ' + e.message }
  finally { savingVisit.value = false }
}

function applyMemberFilter(name) {
  member.value = member.value === name ? '' : name
  load()
}

async function genPlan() {
  planErr.value = ''; plan.value = null; planLoading.value = true; showPlan.value = true
  try {
    plan.value = await api('/api/appointments/route-plan', { params: { date: date.value } })
  } catch (e) { planErr.value = e.message }
  finally { planLoading.value = false }
}

async function applyPlan() {
  if (!plan.value) return
  applying.value = true; msg.value = ''
  try {
    const r = await api('/api/appointments/route-plan/apply', { method: 'POST', body: { date: date.value } })
    msg.value = '✅ ' + (r.msg || 'Rute diterapkan')
    showPlan.value = false
    load()
  } catch (e) { msg.value = '❌ ' + e.message }
  finally { applying.value = false }
}

// Modal Atur Rute Manual (v2.19) — keputusan sepenuhnya di tangan Chief Driver:
// pilih driver + urutan kunjungan sendiri, tanpa menjalankan algoritma.
const showManual = ref(false)
const manualRows = ref([])
const manualBusy = ref(false)
const manualErr = ref('')

function openManual() {
  manualErr.value = ''
  const orderMap = {} // urutan default per sesi (1,2,3…)
  manualRows.value = list.value
    .filter((a) => a.status === 'scheduled' || a.status === 'assigned')
    .sort((x, y) => (x.sesi === y.sesi
      ? String(x.visit_time || '').localeCompare(String(y.visit_time || ''))
      : String(x.sesi).localeCompare(String(y.sesi))))
    .map((a) => {
      orderMap[a.sesi] = (orderMap[a.sesi] || 0) + 1
      return {
        id: a.id,
        display_id: a.display_id,
        nasabah_name: a.nasabah_name,
        alamat: a.alamat,
        area: a.area,
        sesi: a.sesi,
        visit_time: a.visit_time,
        driver: a.driver_name || sug.value[a.sesi] || '',
        order: a.route_order || orderMap[a.sesi],
      }
    })
  showManual.value = true
}

async function applyManual() {
  const assignments = manualRows.value
    .filter((r) => r.driver)
    .map((r) => ({ id: r.id, driver_name: r.driver, order: r.order }))
  if (!assignments.length) { manualErr.value = 'Pilih minimal 1 driver untuk diterapkan.'; return }
  manualBusy.value = true; manualErr.value = ''; msg.value = ''
  try {
    const r = await api('/api/appointments/route-manual/apply', {
      method: 'POST', body: { date: date.value, assignments },
    })
    msg.value = '✅ ' + (r.msg || 'Rute manual diterapkan')
    showManual.value = false
    load()
  } catch (e) { manualErr.value = '❌ ' + e.message }
  finally { manualBusy.value = false }
}

function visitBadge(a) { return a.visit_result ? (VISIT_LABELS[a.visit_result] || a.visit_result) : '' }

const STATUS = { scheduled: 'badge-amber', assigned: 'badge-blue', completed: 'badge-green', cancelled: 'badge-gray' }

onMounted(load)
</script>

<template>
  <div>
    <PageHeader icon="🚛" title="Chief Driver" subtitle="Papan penugasan driver & rute kunjungan hari ini" />
    <div class="card card-pad" style="margin-bottom:16px;">
      <div class="row" style="flex-wrap:wrap;gap:10px;">
        <div class="field" style="margin:0;"><label>Tanggal Board</label>
          <input class="input" type="date" v-model="date" @change="load" />
        </div>
        <div class="field" style="margin:0;"><label>Filter Marketing Anggota</label>
          <select class="select" v-model="member" @change="load" style="min-width:180px;">
            <option value="">Semua anggota</option>
            <option v-for="m in members" :key="m" :value="m">{{ m }}</option>
          </select>
        </div>
        <span v-if="msg" class="alert" :class="msg.startsWith('✅') ? 'alert-success' : 'alert-error'" style="margin:0;">{{ msg }}</span>
        <div class="spacer"></div>
        <button class="btn btn-primary" title="Bagi appointment ke driver: rute searah + urut jam kunjungan (hemat BBM)" @click="genPlan">⚡ Atur Rute Otomatis</button>
        <button class="btn" title="Tentukan sendiri driver + urutan kunjungan per appointment (tanpa algoritma)" @click="openManual">🖐️ Atur Rute Manual</button>
        <a class="btn" :href="`/api/appointments/export?date=${date}${member ? '&member=' + encodeURIComponent(member) : ''}`" target="_blank">📥 Unduh Rekap Excel</a>
      </div>
    </div>

    <div v-if="loading"><LoadingState :rows="4" label="Memuat dashboard rute…" /></div>
    <div v-else-if="err"><ErrorState :message="err" @retry="load" /></div>
    <template v-else>
      <div class="stat-grid" style="margin-bottom:16px;">
        <StatCard icon="📋" label="Total" :value="stats?.total ?? list.length" color="#2563eb" />
        <StatCard icon="⏳" label="Belum Ditugaskan" :value="stats?.scheduled ?? 0" color="#d97706" />
        <StatCard icon="🚗" label="Ditugaskan" :value="stats?.assigned ?? 0" color="#0891b2" />
        <StatCard icon="✅" label="Selesai" :value="stats?.completed ?? 0" color="#059669" />
        <StatCard icon="✕" label="Batal" :value="stats?.cancelled ?? 0" color="#dc2626" />
      </div>

      <!-- Ringkasan per Marketing Anggota -->
      <div v-if="memberSummary.length" class="card card-pad" style="margin-bottom:16px;">
        <h3>📊 Ringkasan per Marketing Anggota</h3>
        <div class="table-wrap">
          <table class="tbl">
            <thead><tr><th>Anggota</th><th>Total</th><th>⏳</th><th>🚗</th><th>✅</th><th>✕</th><th>😊 Ditemui</th><th>🤝 Prospek</th><th>❌ Gagal</th><th>🌅 Sesi 1</th><th>🌆 Sesi 2</th></tr></thead>
            <tbody>
              <tr v-for="m in memberSummary" :key="m.marketing_member"
                  :class="member === m.marketing_member ? 'row-active' : ''"
                  style="cursor:pointer;" :title="member === m.marketing_member ? 'Klik untuk lepas filter' : 'Klik untuk filter board ke anggota ini'"
                  @click="applyMemberFilter(m.marketing_member)">
                <td><b>{{ m.marketing_member }}</b></td>
                <td>{{ m.total }}</td>
                <td>{{ m.scheduled }}</td>
                <td>{{ m.assigned }}</td>
                <td>{{ m.completed }}</td>
                <td>{{ m.cancelled }}</td>
                <td>{{ m.ditemui }}</td>
                <td>{{ m.prospek }}</td>
                <td>{{ m.gagal }}</td>
                <td>{{ m.sesi1 }}</td>
                <td>{{ m.sesi2 }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>

      <div class="card card-pad" style="margin-bottom:16px;">
        <div class="row" style="flex-wrap:wrap;gap:8px;margin-bottom:10px;">
          <h3 style="margin:0;">📋 Belum Ditugaskan</h3>
          <button class="btn btn-sm" :class="sesiFilter === 'all' ? 'btn-primary' : ''" @click="sesiFilter = 'all'">Semua</button>
          <button class="btn btn-sm" :class="sesiFilter === '1' ? 'btn-primary' : ''" @click="sesiFilter = '1'">🌅 Sesi 1</button>
          <button class="btn btn-sm" :class="sesiFilter === '2' ? 'btn-primary' : ''" @click="sesiFilter = '2'">🌆 Sesi 2</button>
        </div>
        <div class="table-wrap">
          <table class="tbl">
            <thead><tr><th>Nasabah</th><th>Sesi</th><th>Area</th><th>Marketing</th><th>Tugaskan ke</th><th></th></tr></thead>
            <tbody>
              <tr v-for="a in scheduledRows" :key="a.id">
                <td><b>{{ a.nasabah_name }}</b><div class="muted" style="font-size:11px;">{{ a.alamat }}</div></td>
                <td>{{ a.sesi === '2' ? '🌆' : '🌅' }} {{ jam(a) }}</td>
                <td>
                  {{ a.area }}
                  <button class="btn-icon" style="margin-left:4px;" title="Ubah area manual (override deteksi otomatis)" @click="doArea(a)">🌍</button>
                </td>
                <td>{{ a.marketing_member }}</td>
                <td>
                  <select class="select assign-select" v-model="selDriver[a.id]" style="min-width:150px;">
                    <option value="">Pilih driver…</option>
                    <option v-for="dr in drivers.filter((x) => x.is_active)" :key="dr.name" :value="dr.name">{{ dr.name }}</option>
                  </select>
                  <div v-if="suggestFor(a)" class="muted" style="font-size:11px;">💡 Saran: {{ suggestFor(a) }}</div>
                </td>
                <td>
                  <button class="btn btn-primary btn-sm" :disabled="busy || !selDriver[a.id]" @click="doAssign(a)">Tugaskan</button>
                  <button class="btn btn-sm btn-danger" :disabled="busy" style="margin-left:6px;" title="Batalkan appointment" @click="doCancel(a)">✕</button>
                </td>
              </tr>
              <tr v-if="!scheduledRows.length"><td colspan="6" class="empty">Semua sudah ditugaskan. 🎉</td></tr>
            </tbody>
          </table>
        </div>
      </div>

      <div class="card card-pad">
        <h3>🚛 Tugas Per Driver</h3>
        <div v-for="[driver, apps] in byDriver" :key="driver" style="margin-bottom:14px;">
          <div class="role-chip" style="background:#7c3aed;margin-bottom:6px;">{{ driver }} · {{ apps.length }} kunjungan</div>
          <div class="table-wrap">
            <table class="tbl">
              <thead><tr><th>Nasabah</th><th>Alamat</th><th>Sesi</th><th>Status</th><th>Hasil</th><th>Aksi</th></tr></thead>
              <tbody>
                <tr v-for="a in apps" :key="a.id">
                  <td><b>{{ a.route_order ? '#' + a.route_order + ' ' : '' }}{{ a.nasabah_name }}</b><div class="muted" style="font-size:11px;">{{ a.display_id }} · {{ a.marketing_member }}</div></td>
                  <td class="muted">{{ a.alamat }}</td>
                  <td>{{ a.sesi === '2' ? '🌆' : '🌅' }} {{ jam(a) }}</td>
                  <td><span class="badge" :class="STATUS[a.status] || 'badge-gray'">{{ a.status }}</span></td>
                  <td><span v-if="visitBadge(a)" class="badge badge-green">{{ visitBadge(a) }}</span><span v-else class="muted">—</span></td>
                  <td style="white-space:nowrap;">
                    <template v-if="a.status === 'assigned'">
                      <select class="select ganti-select" v-model="selGanti[a.id]" style="min-width:110px;margin-right:4px;">
                        <option value="">Ganti ke…</option>
                        <option v-for="dr in drivers.filter((x) => x.is_active)" :key="dr.name" :value="dr.name">{{ dr.name }}</option>
                      </select>
                      <button class="btn btn-sm" :disabled="busy || !selGanti[a.id]" title="Ganti driver" @click="doGanti(a)">🔄</button>
                      <button class="btn btn-sm" :disabled="busy" style="margin-left:4px;" title="Batalkan tugas" @click="doUnassign(a)">↩️</button>
                      <button class="btn btn-sm btn-primary" :disabled="busy" style="margin-left:4px;" title="Tandai selesai + catat hasil kunjungan" @click="openVisit(a)">✅</button>
                      <button class="btn btn-sm btn-danger" :disabled="busy" style="margin-left:4px;" title="Batalkan appointment" @click="doCancel(a)">✕</button>
                    </template>
                    <button v-else class="btn btn-sm" :disabled="busy" title="Ubah hasil kunjungan" @click="openVisit(a, true)">🎯 Hasil</button>
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>
        <div v-if="!byDriver.length" class="empty">Belum ada penugasan.</div>
      </div>
    </template>

    <!-- Modal Atur Rute Otomatis -->
    <Modal v-if="showPlan" title="⚡ Atur Rute Otomatis" wide @close="showPlan = false">
      <div v-if="planLoading" class="empty skeleton">⏳ Menghitung rute terbaik…</div>
      <div v-else-if="planErr" class="alert alert-error">{{ planErr }}</div>
      <template v-else-if="plan">
        <div class="alert alert-info" style="font-size:12px;">
          Algoritma membagi appointment per sesi: rute <b>searah</b> secara geografis, urut sesuai <b>jam kunjungan</b>,
          beban antar driver merata. Penugasan manual yang sudah ada tetap dihormati (bisa diubah manual setelahnya 🌍).
        </div>
        <div class="stat-grid" style="margin:12px 0;">
          <StatCard icon="🗺️" label="Kunjungan Terbagi" :value="plan.totals.assigned" color="#2563eb" />
          <StatCard icon="📏" label="Total Jarak" :value="plan.totals.km + ' km'" color="#0891b2" />
          <StatCard icon="⛽" label="Estimasi BBM" :value="plan.totals.bbm_liter + ' L'" color="#d97706" />
          <StatCard icon="💰" label="Estimasi Biaya" :value="'Rp ' + plan.totals.bbm_cost.toLocaleString('id-ID')" color="#059669" />
          <StatCard icon="⚠️" label="Belum Terpetakan" :value="plan.totals.unassigned" color="#dc2626" />
        </div>
        <div v-if="plan.totals.savings_percent > 0" class="alert alert-success" style="margin-bottom:12px;">
          💚 <b>Hemat {{ plan.totals.savings_percent }}% jarak</b> — {{ plan.totals.savings_km }} km, ±{{ plan.totals.savings_bbm_liter }} L
          (≈ Rp {{ plan.totals.savings_bbm_cost.toLocaleString('id-ID') }}) dibanding penugasan tanpa optimasi ({{ plan.totals.baseline_km }} km).
        </div>
        <div v-for="d in plan.drivers" :key="d.driver" style="margin-bottom:14px;">
          <div class="role-chip" style="background:#7c3aed;">
            {{ d.driver }} · {{ d.visits.length }} kunjungan · {{ d.total_km }} km · ±{{ d.est_bbm_liter }} L
            (Rp {{ d.est_bbm_cost.toLocaleString('id-ID') }})
          </div>
          <ol class="route-list" style="margin:6px 0 0 20px;padding:0;">
            <li v-for="v in d.visits" :key="v.id" style="margin-bottom:4px;">
              <b>{{ jam(v) }}</b> — {{ v.nasabah_name }}
              <span class="muted" style="font-size:11px;">{{ v.display_id }} · {{ v.area }}</span>
            </li>
          </ol>
        </div>
        <div v-if="plan.unassigned.length" class="alert alert-error">
          ⚠️ {{ plan.unassigned.length }} appointment belum terpetakan (alamat belum punya koordinat):
          {{ plan.unassigned.map(u => u.display_id).join(', ') }} — perbaiki/deteksi ulang alamatnya.
        </div>
        <div class="muted" style="font-size:11px;">
          Titik awal (kantor): lat {{ plan.depot.lat }}, lng {{ plan.depot.lng }} — sesuaikan env DEPOT_LAT/DEPOT_LNG bila perlu.
        </div>
        <div class="row" style="justify-content:flex-end;gap:6px;margin-top:12px;">
          <button class="btn" @click="showPlan = false">Tutup</button>
          <button class="btn btn-primary" :disabled="applying || !plan.drivers.length" @click="applyPlan">
            {{ applying ? '⏳ Menerapkan…' : '✅ Terapkan Rute' }}
          </button>
        </div>
      </template>
    </Modal>

    <!-- Modal Atur Rute Manual -->
    <Modal v-if="showManual" title="🖐️ Atur Rute Manual" wide @close="showManual = false">
      <div class="alert alert-info" style="font-size:12px;">
        Tentukan sendiri <b>driver</b> dan <b>urutan kunjungan</b> per appointment pada tanggal
        <b>{{ date }}</b>. Baris tanpa driver dilewati (appointment tetap seperti sebelumnya).
      </div>
      <div v-if="manualErr" class="alert alert-error" style="font-size:12px;">{{ manualErr }}</div>
      <div class="table-wrap" style="max-height:52vh;overflow-y:auto;">
        <table class="tbl">
          <thead><tr><th>Urutan</th><th>Nasabah / Alamat</th><th>Sesi</th><th>Driver</th><th>No. Urut Kunjungan</th></tr></thead>
          <tbody>
            <tr v-for="r in manualRows" :key="r.id">
              <td>{{ r.order }}</td>
              <td><b>{{ r.nasabah_name }}</b><div class="muted" style="font-size:11px;">{{ r.display_id }} · {{ r.alamat }} · {{ r.area }}</div></td>
              <td>{{ r.sesi === '2' ? '🌆' : '🌅' }} {{ jam(r) }}</td>
              <td>
                <select class="select" v-model="r.driver" style="min-width:130px;">
                  <option value="">— Pilih driver —</option>
                  <option v-for="dr in drivers.filter((x) => x.is_active)" :key="dr.name" :value="dr.name">{{ dr.name }}</option>
                </select>
              </td>
              <td><input class="input" type="number" min="1" style="width:80px;" v-model.number="r.order" /></td>
            </tr>
            <tr v-if="!manualRows.length"><td colspan="5" class="empty">Tidak ada appointment (scheduled/assigned) pada tanggal ini.</td></tr>
          </tbody>
        </table>
      </div>
      <div class="row" style="justify-content:flex-end;gap:6px;margin-top:12px;">
        <button class="btn" @click="showManual = false">Tutup</button>
        <button class="btn btn-primary" :disabled="manualBusy || !manualRows.length" @click="applyManual">
          {{ manualBusy ? '⏳ Menerapkan…' : '✅ Terapkan Rute Manual' }}
        </button>
      </div>
    </Modal>

    <!-- Modal Hasil Kunjungan -->
    <Modal v-if="visitAppt" :title="visitAppt.status === 'assigned' ? '✅ Selesaikan ' + visitAppt.display_id : '🎯 Hasil Kunjungan — ' + visitAppt.display_id" @close="visitAppt = null">
      <p class="muted" style="font-size:12px;margin-bottom:10px;">
        {{ visitAppt.nasabah_name }} · {{ visitAppt.alamat }} · {{ visitAppt.sesi === '2' ? '🌆 Sesi 2' : '🌅 Sesi 1' }}
        <span v-if="visitAppt.driver_name"> · 🚗 {{ visitAppt.driver_name }}</span>
      </p>
      <div class="field"><label>Hasil kunjungan <span v-if="visitAppt.status === 'assigned'" class="req">*</span></label>
        <select class="select" v-model="visitForm.result">
          <option value="">— Pilih hasil —</option>
          <option value="ditemui">😊 Ditemui</option>
          <option value="prospek">🤝 Prospek</option>
          <option value="gagal">❌ Gagal</option>
        </select>
      </div>
      <div class="field" style="margin-top:8px;"><label>Alasan / catatan (opsional)</label>
        <textarea class="textarea" v-model="visitForm.note" rows="2" placeholder="Catatan hasil kunjungan…"></textarea>
      </div>
      <div class="row" style="justify-content:flex-end;gap:6px;margin-top:10px;">
        <span v-if="msg" class="alert" :class="msg.startsWith('✅') ? 'alert-success' : 'alert-error'" style="margin:0;">{{ msg }}</span>
        <div class="spacer"></div>
        <button class="btn" @click="visitAppt = null">Batal</button>
        <button class="btn btn-primary" :disabled="savingVisit" @click="saveVisit">{{ visitAppt.status === 'assigned' ? '✅ Selesai' : '💾 Simpan Hasil' }}</button>
      </div>
    </Modal>
  </div>
  <ConfirmDialog ref="confirmRef" />
</template>
