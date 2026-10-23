<script setup>
import { computed, onMounted, ref } from 'vue'
import { api } from '../../api'
import StatCard from '../../components/StatCard.vue'
import Modal from '../../components/Modal.vue'
import ConfirmDialog from '../../components/ConfirmDialog.vue'
import PageHeader from '../../components/PageHeader.vue'

const confirmRef = ref(null)
const ask = (message, opts) => confirmRef.value?.open(message, opts) ?? Promise.resolve(false)

const tab = ref('ac') // ac | vehicles | recommendations | components
const list = ref([])
const summary = ref(null)
const loading = ref(true)
const err = ref('')
const msg = ref('')

// Filter
const f = ref({ search: '', status: '' })

// ---- Data tab ----
const acList = ref([])
const vehList = ref([])
const recList = ref([])
const compList = ref([])

async function loadSummary() {
  try { summary.value = await api('/api/assets/summary') } catch { summary.value = null }
}

async function loadTab() {
  loading.value = true; err.value = ''
  try {
    if (tab.value === 'ac') {
      acList.value = (await api('/api/assets/ac', { params: { ...f.value } })).data || []
    } else if (tab.value === 'vehicles') {
      vehList.value = (await api('/api/assets/vehicles')).data || []
    } else if (tab.value === 'recommendations') {
      recList.value = (await api('/api/assets/recommendations')).data || []
    } else {
      compList.value = (await api('/api/assets/components')).data || []
    }
  } catch (e) { err.value = e.message }
  finally { loading.value = false }
}

function switchTab(t) {
  tab.value = t; f.value = { search: '', status: '' }; loadTab()
}

// ---- Modal AC ----
const acModal = ref(false)
const acForm = ref({})
function openAcModal(a) {
  acModal.value = true
  acForm.value = a ? { ...a } : { asset_id: '', merk: '', tipe: '', kapasitas: '', lokasi: '', refrigerant: '', status: 'Aktif', installation_date: '', warranty_until: '', last_maintenance: '' }
}
async function saveAc() {
  try {
    const body = { ...acForm.value }
    if (acForm.value.id) {
      await api(`/api/assets/ac/${encodeURIComponent(acForm.value.asset_id)}`, { method: 'PATCH', body })
    } else {
      await api('/api/assets/ac', { method: 'POST', body })
    }
    msg.value = '✅ Data AC disimpan'
    acModal.value = false; loadTab(); loadSummary()
  } catch (e) { msg.value = '❌ ' + e.message }
}
async function delAc(a) {
  if (!(await ask(`Hapus AC ${a.asset_id} beserta seluruh log servisnya?`, { confirmText: 'Ya, lanjutkan', danger: true }))) return
  try {
    const r = await api(`/api/assets/ac/${encodeURIComponent(a.asset_id)}`, { method: 'DELETE' })
    msg.value = '✅ ' + (r.msg || 'Dihapus'); loadTab(); loadSummary()
  } catch (e) { msg.value = '❌ ' + e.message }
}

// ---- Modal Log Servis AC ----
const acLogModal = ref(false)
const acLogTarget = ref(null)
const acLogList = ref([])
const acLogForm = ref({})
async function openAcLog(a) {
  acLogTarget.value = a
  acLogForm.value = { tanggal: new Date().toISOString().slice(0, 10), teknisi: '', v_supply: '', amp_kompresor: '', low_p: '', high_p: '', temp_ret: '', temp_sup: '', temp_outdoor: '', delta_t: '', drainage: '', test_run: '', sparepart_cost: '', catatan: '', next_service_date: '' }
  acLogList.value = (await api(`/api/assets/ac/${encodeURIComponent(a.asset_id)}/logs`)).data || []
  acLogModal.value = true
}
async function saveAcLog() {
  try {
    const r = await api(`/api/assets/ac/${encodeURIComponent(acLogTarget.value.asset_id)}/logs`, { method: 'POST', body: acLogForm.value })
    msg.value = '✅ ' + (r.msg || 'Log tercatat') + (r.health_score != null ? ` (health: ${r.health_score}/100)` : '')
    openAcLog(acLogTarget.value) // reload list
  } catch (e) { msg.value = '❌ ' + e.message }
}
async function delAcLog(log) {
  if (!(await ask('Hapus log servis ini?', { confirmText: 'Ya, lanjutkan', danger: true }))) return
  try {
    await api(`/api/assets/ac-logs/${log.id}`, { method: 'DELETE' })
    openAcLog(acLogTarget.value)
  } catch (e) { msg.value = '❌ ' + e.message }
}

// ---- Modal Kendaraan ----
const vehModal = ref(false)
const vehForm = ref({})
function openVehModal(v) {
  vehModal.value = true
  vehForm.value = v ? { ...v } : { nopol: '', vehicle_type: '', brand: 'Toyota', model: '', year: '', color: '', fuel_type: 'Bensin', status: 'Aktif', last_odometer: 0 }
}
async function saveVeh() {
  try {
    const body = { ...vehForm.value }
    if (vehForm.value.id) {
      await api(`/api/assets/vehicles/${vehForm.value.id}`, { method: 'PATCH', body })
    } else {
      await api('/api/assets/vehicles', { method: 'POST', body })
    }
    msg.value = '✅ Data kendaraan disimpan'
    vehModal.value = false; loadTab(); loadSummary()
  } catch (e) { msg.value = '❌ ' + e.message }
}
async function delVeh(v) {
  if (!(await ask(`Hapus kendaraan ${v.nopol} beserta seluruh log servisnya?`, { confirmText: 'Ya, lanjutkan', danger: true }))) return
  try {
    const r = await api(`/api/assets/vehicles/${v.id}`, { method: 'DELETE' })
    msg.value = '✅ ' + (r.msg || 'Dihapus'); loadTab(); loadSummary()
  } catch (e) { msg.value = '❌ ' + e.message }
}

// ---- Modal Log Servis Kendaraan ----
const vehSvcModal = ref(false)
const vehSvcTarget = ref(null)
const vehSvcList = ref([])
const vehSvcForm = ref({})
async function openVehSvc(v) {
  vehSvcTarget.value = v
  vehSvcForm.value = { service_date: new Date().toISOString().slice(0, 10), odometer: v.last_odometer || 0, service_type: 'Servis Rutin', component_name: '', cost: '', mechanic_name: '', parts_replaced: '', invoice_number: '', notes: '' }
  vehSvcList.value = (await api(`/api/assets/vehicles/${v.id}/services`)).data || []
  vehSvcModal.value = true
}
async function saveVehSvc() {
  try {
    const r = await api(`/api/assets/vehicles/${vehSvcTarget.value.id}/services`, { method: 'POST', body: vehSvcForm.value })
    msg.value = '✅ ' + (r.msg || 'Log tercatat')
    openVehSvc(vehSvcTarget.value); loadTab()
  } catch (e) { msg.value = '❌ ' + e.message }
}
async function delVehSvc(svc) {
  if (!(await ask('Hapus log servis ini?', { confirmText: 'Ya, lanjutkan', danger: true }))) return
  try {
    await api(`/api/assets/vehicle-services/${svc.id}`, { method: 'DELETE' })
    openVehSvc(vehSvcTarget.value); loadTab()
  } catch (e) { msg.value = '❌ ' + e.message }
}

// ---- Rekomendasi ----
async function refreshRecs() {
  busy.value = true
  try {
    const r = await api('/api/assets/recommendations/refresh', { method: 'POST' })
    msg.value = '✅ ' + (r.msg || 'Diperbarui'); loadTab()
  } catch (e) { msg.value = '❌ ' + e.message }
  finally { busy.value = false }
}
async function setRecStatus(rec, status) {
  try {
    await api(`/api/assets/recommendations/${rec.id}`, { method: 'PATCH', body: { status } })
    loadTab()
  } catch (e) { msg.value = '❌ ' + e.message }
}

// ---- Komponen ----
const compModal = ref(false)
const compForm = ref({})
function openCompModal(c) {
  compModal.value = true
  compForm.value = c ? { ...c } : { component_name: '', standard_life_km: '', standard_life_months: '', category: '', priority: 1, estimated_cost: '', is_active: true }
}
async function saveComp() {
  try {
    const body = { ...compForm.value }
    if (compForm.value.id) {
      await api(`/api/assets/components/${compForm.value.id}`, { method: 'PATCH', body })
    } else {
      await api('/api/assets/components', { method: 'POST', body })
    }
    msg.value = '✅ Komponen disimpan'; compModal.value = false; loadTab()
  } catch (e) { msg.value = '❌ ' + e.message }
}

// ---- PDF ----
function reportUrl(kind) {
  return `/api/assets/report?kind=${kind}`
}

const busy = ref(false)
const badge = (s) => ({ Aktif: 'badge-green', Rusak: 'badge-red', Maintenance: 'badge-orange', Nonaktif: 'badge-gray' })[s] || 'badge-gray'
const recBadge = (p) => ({ Kritis: 'badge-red', Tinggi: 'badge-orange', Sedang: 'badge-yellow', Rutin: 'badge-gray' })[p] || 'badge-gray'
const fmtMoney = (v) => v ? 'Rp ' + Number(v).toLocaleString('id-ID') : '—'
const fmtDate = (v) => v ? String(v).slice(0, 10) : '—'

const acStats = computed(() => ({
  total: acList.value.length,
  aktif: acList.value.filter((a) => a.status === 'Aktif').length,
  rusak: acList.value.filter((a) => a.status === 'Rusak' || a.status === 'Maintenance').length,
}))

onMounted(() => { loadSummary(); loadTab() })
</script>

<template>
  <div>
    <PageHeader icon="🔧" title="Aset & Pemeliharaan" subtitle="Pemeliharaan unit AC kantor & kendaraan — data hasil migrasi dari sistem aset lama.">
      <span v-if="summary" class="badge badge-blue">{{ summary.ac_total }} AC · {{ summary.vehicle_total }} kendaraan</span>
      <span v-if="summary && summary.urgent" class="badge badge-red">⚠️ {{ summary.urgent }} rekomendasi mendesak</span>
      <button class="btn" :class="tab==='ac' ? 'btn-primary' : ''" @click="switchTab('ac')">❄️ AC ({{ acList.length }})</button>
      <button class="btn" :class="tab==='vehicles' ? 'btn-primary' : ''" @click="switchTab('vehicles')">🚗 Kendaraan ({{ vehList.length }})</button>
      <button class="btn" :class="tab==='recommendations' ? 'btn-primary' : ''" @click="switchTab('recommendations')">📋 Rekomendasi ({{ recList.filter(r=>r.status==='Pending').length }})</button>
      <button class="btn" :class="tab==='components' ? 'btn-primary' : ''" @click="switchTab('components')">🧩 Komponen ({{ compList.length }})</button>
    </PageHeader>

    <div v-if="msg" class="alert" :class="msg.startsWith('✅') ? 'alert-success' : 'alert-error'" style="margin-bottom:16px;">{{ msg }}</div>

    <!-- ============ TAB AC ============ -->
    <template v-if="tab === 'ac'">
      <div class="stat-grid" style="margin-bottom:16px;" v-if="summary">
        <StatCard icon="❄️" label="Total Unit AC" :value="summary.ac_total" color="#0ea5e9" />
        <StatCard icon="✅" label="Aktif" :value="summary.ac_aktif" color="#059669" />
        <StatCard icon="⚠️" label="Rusak / Maintenance" :value="summary.ac_total - summary.ac_aktif" color="#dc2626" />
        <StatCard icon="📋" label="Rekomendasi Pending" :value="summary.pending" color="#d97706" />
      </div>
      <div class="card card-pad" style="margin-bottom:16px;">
        <div class="row" style="flex-wrap:wrap;gap:10px;align-items:flex-end;">
          <div class="field" style="margin:0;flex:1;min-width:200px;"><label>🔍 Cari (ID/merk/lokasi)</label>
            <input class="input" v-model="f.search" placeholder="cth: AC-01 atau Lounge…" @keyup.enter="loadTab" /></div>
          <div class="field" style="margin:0;"><label>Status</label>
            <select class="select" v-model="f.status" @change="loadTab" style="min-width:130px;">
              <option value="">Semua</option>
              <option v-for="s in ['Aktif','Rusak','Maintenance','Nonaktif']" :key="s" :value="s">{{ s }}</option>
            </select></div>
          <button class="btn" @click="loadTab">🔍 Cari</button>
          <div class="spacer"></div>
          <a class="btn btn-primary" :href="reportUrl('ac')" target="_blank">📄 Laporan PDF AC</a>
          <button class="btn btn-primary" @click="openAcModal(null)">＋ Tambah AC</button>
        </div>
      </div>
      <div v-if="loading" class="empty skeleton">⏳ Memuat…</div>
      <div v-else-if="err" class="alert alert-error">{{ err }}</div>
      <div v-else class="card">
        <div class="table-wrap">
          <table class="tbl">
            <thead>
              <tr><th>Asset ID</th><th>Merk / Tipe</th><th>Kapasitas</th><th>Lokasi</th><th>Servis Terakhir</th><th>Health</th><th>Status</th><th style="min-width:170px;">Aksi</th></tr>
            </thead>
            <tbody>
              <tr v-for="a in acList" :key="a.asset_id">
                <td><b>{{ a.asset_id }}</b></td>
                <td>{{ a.merk }} · {{ a.tipe || '—' }}</td>
                <td>{{ a.kapasitas || '—' }}</td>
                <td>{{ a.lokasi }}</td>
                <td style="font-size:11px;">{{ fmtDate(a.last_maintenance) }}</td>
                <td>
                  <span v-if="a.last_log && a.last_log.health_score != null" class="badge" :class="a.last_log.health_score >= 70 ? 'badge-green' : a.last_log.health_score >= 50 ? 'badge-orange' : 'badge-red'">{{ a.last_log.health_score }}</span>
                  <span v-else class="muted" style="font-size:11px;">—</span>
                </td>
                <td><span class="badge" :class="badge(a.status)">{{ a.status }}</span></td>
                <td style="white-space:nowrap;">
                  <button class="btn btn-sm" title="Log servis AC" @click="openAcLog(a)">🛠️</button>
                  <button class="btn btn-sm" title="Edit" @click="openAcModal(a)">✏️</button>
                  <button class="btn btn-sm btn-danger" title="Hapus" @click="delAc(a)">🗑</button>
                </td>
              </tr>
              <tr v-if="!acList.length"><td colspan="8" class="empty">Belum ada unit AC dengan filter ini.</td></tr>
            </tbody>
          </table>
        </div>
      </div>
    </template>

    <!-- ============ TAB KENDARAAN ============ -->
    <template v-else-if="tab === 'vehicles'">
      <div class="stat-grid" style="margin-bottom:16px;" v-if="summary">
        <StatCard icon="🚗" label="Total Kendaraan" :value="summary.vehicle_total" color="#2563eb" />
        <StatCard icon="✅" label="Aktif" :value="summary.vehicle_aktif" color="#059669" />
        <StatCard icon="🔧" label="Rusak" :value="summary.vehicle_total - summary.vehicle_aktif" color="#dc2626" />
        <StatCard icon="📋" label="Rekomendasi Pending" :value="summary.pending" color="#d97706" />
      </div>
      <div class="card card-pad" style="margin-bottom:16px;">
        <div class="row" style="flex-wrap:wrap;gap:10px;align-items:flex-end;justify-content:flex-end;">
          <a class="btn btn-primary" :href="reportUrl('vehicle')" target="_blank">📄 Laporan PDF Kendaraan</a>
          <button class="btn btn-primary" @click="openVehModal(null)">＋ Tambah Kendaraan</button>
        </div>
      </div>
      <div v-if="loading" class="empty skeleton">⏳ Memuat…</div>
      <div v-else-if="err" class="alert alert-error">{{ err }}</div>
      <div v-else class="card">
        <div class="table-wrap">
          <table class="tbl">
            <thead>
              <tr><th>Nopol</th><th>Tipe</th><th>Merk / Model</th><th>Tahun</th><th>Odometer</th><th>Servis Terakhir</th><th>Status</th><th style="min-width:170px;">Aksi</th></tr>
            </thead>
            <tbody>
              <tr v-for="v in vehList" :key="v.id">
                <td><b>{{ v.nopol }}</b></td>
                <td>{{ v.vehicle_type || '—' }}</td>
                <td>{{ v.brand || '—' }} {{ v.model || '' }}</td>
                <td>{{ v.year || '—' }}</td>
                <td>{{ Number(v.last_odometer || 0).toLocaleString('id-ID') }} km</td>
                <td style="font-size:11px;">{{ fmtDate(v.last_service?.service_date) }} · {{ v.last_service?.component_name || '—' }}</td>
                <td><span class="badge" :class="badge(v.status)">{{ v.status }}</span></td>
                <td style="white-space:nowrap;">
                  <button class="btn btn-sm" title="Log servis kendaraan" @click="openVehSvc(v)">🛠️</button>
                  <button class="btn btn-sm" title="Edit" @click="openVehModal(v)">✏️</button>
                  <button class="btn btn-sm btn-danger" title="Hapus" @click="delVeh(v)">🗑</button>
                </td>
              </tr>
              <tr v-if="!vehList.length"><td colspan="8" class="empty">Belum ada kendaraan terdaftar.</td></tr>
            </tbody>
          </table>
        </div>
      </div>
    </template>

    <!-- ============ TAB REKOMENDASI ============ -->
    <template v-else-if="tab === 'recommendations'">
      <div class="card card-pad" style="margin-bottom:16px;">
        <div class="row" style="gap:8px;align-items:center;">
          <div class="grow">
            <p class="muted" style="font-size:12px;margin:0;">
              Rekomendasi otomatis dari aturan pemeliharaan: AC yang sudah &gt; 90 hari tanpa servis, health score rendah, dan komponen kendaraan yang melewati umur pakai (km/bulan).
            </p>
          </div>
          <button class="btn btn-primary" :disabled="busy" @click="refreshRecs">{{ busy ? '⏳…' : '🔄 Perbarui Rekomendasi' }}</button>
        </div>
      </div>
      <div v-if="loading" class="empty skeleton">⏳ Memuat…</div>
      <div v-else-if="err" class="alert alert-error">{{ err }}</div>
      <div v-else class="card">
        <div class="table-wrap">
          <table class="tbl">
            <thead>
              <tr><th>Prioritas</th><th>Aset</th><th>Tindakan</th><th>Batas (hari)</th><th>Status</th><th>Aksi</th></tr>
            </thead>
            <tbody>
              <tr v-for="r in recList" :key="r.id">
                <td><span class="badge" :class="recBadge(r.priority)">{{ r.priority }}</span></td>
                <td>{{ r.asset_ref }}</td>
                <td style="max-width:340px;">{{ r.actions }}</td>
                <td>{{ r.urgency_days }}</td>
                <td><span class="badge" :class="r.status === 'Pending' ? 'badge-orange' : r.status === 'Selesai' ? 'badge-green' : 'badge-gray'">{{ r.status }}</span></td>
                <td style="white-space:nowrap;">
                  <button v-if="r.status === 'Pending'" class="btn btn-sm" title="Tandai selesai" @click="setRecStatus(r, 'Selesai')">✅ Selesai</button>
                  <button v-if="r.status === 'Pending'" class="btn btn-sm" title="Batalkan" @click="setRecStatus(r, 'Dibatalkan')">✕</button>
                  <button v-if="r.status !== 'Pending'" class="btn btn-sm" title="Kembalikan ke pending" @click="setRecStatus(r, 'Pending')">↩</button>
                </td>
              </tr>
              <tr v-if="!recList.length"><td colspan="6" class="empty">Belum ada rekomendasi. Klik 🔄 Perbarui Rekomendasi.</td></tr>
            </tbody>
          </table>
        </div>
      </div>
    </template>

    <!-- ============ TAB KOMPONEN ============ -->
    <template v-else>
      <div class="card card-pad" style="margin-bottom:16px;">
        <div class="row" style="justify-content:flex-end;">
          <button class="btn btn-primary" @click="openCompModal(null)">＋ Tambah Komponen</button>
        </div>
      </div>
      <div v-if="loading" class="empty skeleton">⏳ Memuat…</div>
      <div v-else-if="err" class="alert alert-error">{{ err }}</div>
      <div v-else class="card">
        <div class="table-wrap">
          <table class="tbl">
            <thead>
              <tr><th>Komponen</th><th>Kategori</th><th>Umur Standar</th><th>Estimasi Biaya</th><th>Status</th><th>Aksi</th></tr>
            </thead>
            <tbody>
              <tr v-for="c in compList" :key="c.id">
                <td><b>{{ c.component_name }}</b></td>
                <td>{{ c.category || '—' }}</td>
                <td>{{ c.standard_life_km ? c.standard_life_km.toLocaleString('id-ID') + ' km' : '—' }} / {{ c.standard_life_months || '—' }} bln</td>
                <td>{{ fmtMoney(c.estimated_cost) }}</td>
                <td><span class="badge" :class="c.is_active ? 'badge-green' : 'badge-gray'">{{ c.is_active ? 'Aktif' : 'Nonaktif' }}</span></td>
                <td><button class="btn btn-sm" title="Edit" @click="openCompModal(c)">✏️</button></td>
              </tr>
              <tr v-if="!compList.length"><td colspan="6" class="empty">Belum ada komponen.</td></tr>
            </tbody>
          </table>
        </div>
      </div>
    </template>

    <!-- Modal AC -->
    <Modal v-if="acModal" :title="(acForm.id ? '✏️ Edit' : '＋ Tambah') + ' Unit AC'" @close="acModal = false">
      <div class="form-grid">
        <div class="field"><label>Asset ID <span class="req">*</span></label><input class="input" v-model="acForm.asset_id" placeholder="cth: AC-01-R. BEST 8" :disabled="!!acForm.id" /></div>
        <div class="field"><label>Merk <span class="req">*</span></label><input class="input" v-model="acForm.merk" placeholder="cth: Daikin" /></div>
        <div class="field"><label>Tipe</label><input class="input" v-model="acForm.tipe" placeholder="cth: Split Duct" /></div>
        <div class="field"><label>Kapasitas</label><input class="input" v-model="acForm.kapasitas" placeholder="cth: 60.000 Btu/h" /></div>
        <div class="field" style="grid-column:1/-1;"><label>Lokasi <span class="req">*</span></label><input class="input" v-model="acForm.lokasi" placeholder="cth: R. BEST 8" /></div>
        <div class="field"><label>Refrigerant</label><input class="input" v-model="acForm.refrigerant" /></div>
        <div class="field"><label>Status</label>
          <select class="select" v-model="acForm.status"><option v-for="s in ['Aktif','Rusak','Maintenance','Nonaktif']" :key="s" :value="s">{{ s }}</option></select></div>
        <div class="field"><label>Tgl Pasang</label><input class="input" type="date" v-model="acForm.installation_date" /></div>
        <div class="field"><label>Garansi s/d</label><input class="input" type="date" v-model="acForm.warranty_until" /></div>
        <div class="field"><label>Servis Terakhir</label><input class="input" type="date" v-model="acForm.last_maintenance" /></div>
      </div>
      <div class="row" style="justify-content:flex-end;gap:6px;margin-top:10px;">
        <button class="btn" @click="acModal = false">Batal</button>
        <button class="btn btn-primary" @click="saveAc">💾 Simpan</button>
      </div>
    </Modal>

    <!-- Modal Log Servis AC -->
    <Modal v-if="acLogModal" :title="'🛠️ Log Servis — ' + acLogTarget.asset_id" @close="acLogModal = false">
      <p class="muted" style="font-size:12px;margin-bottom:8px;">{{ acLogTarget.lokasi }} · servis terakhir {{ fmtDate(acLogTarget.last_maintenance) }}</p>
      <div class="form-grid">
        <div class="field"><label>Tanggal Servis</label><input class="input" type="date" v-model="acLogForm.tanggal" /></div>
        <div class="field"><label>Teknisi <span class="req">*</span></label><input class="input" v-model="acLogForm.teknisi" /></div>
        <div class="field"><label>V Supply</label><input class="input" type="number" step="0.1" v-model="acLogForm.v_supply" /></div>
        <div class="field"><label>Ampere Kompresor</label><input class="input" type="number" step="0.1" v-model="acLogForm.amp_kompresor" /></div>
        <div class="field"><label>Tekanan Rendah (low P)</label><input class="input" type="number" step="0.1" v-model="acLogForm.low_p" /></div>
        <div class="field"><label>Tekanan Tinggi (high P)</label><input class="input" type="number" step="0.1" v-model="acLogForm.high_p" /></div>
        <div class="field"><label>Temp Return</label><input class="input" type="number" step="0.1" v-model="acLogForm.temp_ret" /></div>
        <div class="field"><label>Temp Supply</label><input class="input" type="number" step="0.1" v-model="acLogForm.temp_sup" /></div>
        <div class="field"><label>Temp Outdoor</label><input class="input" type="number" step="0.1" v-model="acLogForm.temp_outdoor" /></div>
        <div class="field"><label>Delta T</label><input class="input" type="number" step="0.1" v-model="acLogForm.delta_t" /></div>
        <div class="field"><label>Drainage</label><input class="input" v-model="acLogForm.drainage" placeholder="cth: Lancar" /></div>
        <div class="field"><label>Test Run</label><input class="input" v-model="acLogForm.test_run" placeholder="cth: Normal" /></div>
        <div class="field"><label>Biaya Sparepart (Rp)</label><input class="input" type="number" v-model="acLogForm.sparepart_cost" /></div>
        <div class="field"><label>Servis Berikutnya</label><input class="input" type="date" v-model="acLogForm.next_service_date" /></div>
        <div class="field" style="grid-column:1/-1;"><label>Catatan</label><textarea class="textarea" v-model="acLogForm.catatan" rows="2"></textarea></div>
      </div>
      <div class="row" style="justify-content:flex-end;gap:6px;margin-top:10px;">
        <button class="btn" @click="acLogModal = false">Tutup</button>
        <button class="btn btn-primary" @click="saveAcLog">💾 Simpan Log</button>
      </div>
      <hr style="border:none;border-top:1px solid var(--border);margin:14px 0;" />
      <div class="att-edit-list">
        <div v-for="lg in acLogList" :key="lg.id" class="att-edit-row">
          <span class="badge badge-blue">{{ fmtDate(lg.tanggal) }}</span>
          <span style="font-size:12px;">{{ lg.teknisi }}</span>
          <span v-if="lg.health_score != null" class="badge" :class="lg.health_score >= 70 ? 'badge-green' : lg.health_score >= 50 ? 'badge-orange' : 'badge-red'">H {{ lg.health_score }}</span>
          <span v-if="lg.sparepart_cost" class="muted" style="font-size:11px;">{{ fmtMoney(lg.sparepart_cost) }}</span>
          <div class="spacer"></div>
          <button class="btn btn-sm btn-danger" @click="delAcLog(lg)">🗑</button>
        </div>
        <div v-if="!acLogList.length" class="empty">Belum ada log servis untuk unit ini.</div>
      </div>
    </Modal>

    <!-- Modal Kendaraan -->
    <Modal v-if="vehModal" :title="(vehForm.id ? '✏️ Edit' : '＋ Tambah') + ' Kendaraan'" @close="vehModal = false">
      <div class="form-grid">
        <div class="field"><label>No. Polisi <span class="req">*</span></label><input class="input" v-model="vehForm.nopol" placeholder="cth: B 1126 DFC" /></div>
        <div class="field"><label>Tipe <span class="req">*</span></label><input class="input" v-model="vehForm.vehicle_type" placeholder="cth: AVANZA" /></div>
        <div class="field"><label>Merk</label><input class="input" v-model="vehForm.brand" /></div>
        <div class="field"><label>Model</label><input class="input" v-model="vehForm.model" /></div>
        <div class="field"><label>Tahun</label><input class="input" type="number" v-model="vehForm.year" /></div>
        <div class="field"><label>Warna</label><input class="input" v-model="vehForm.color" /></div>
        <div class="field"><label>Bahan Bakar</label>
          <select class="select" v-model="vehForm.fuel_type"><option value="Bensin">Bensin</option><option value="Solar">Solar</option></select></div>
        <div class="field"><label>Status</label>
          <select class="select" v-model="vehForm.status"><option v-for="s in ['Aktif','Rusak','Nonaktif']" :key="s" :value="s">{{ s }}</option></select></div>
        <div class="field"><label>Odometer (km)</label><input class="input" type="number" v-model="vehForm.last_odometer" /></div>
        <div class="field"><label>Tgl Beli</label><input class="input" type="date" v-model="vehForm.purchase_date" /></div>
        <div class="field"><label>Asuransi s/d</label><input class="input" type="date" v-model="vehForm.insurance_until" /></div>
        <div class="field"><label>Pajak s/d</label><input class="input" type="date" v-model="vehForm.tax_until" /></div>
        <div class="field" style="grid-column:1/-1;"><label>Catatan</label><textarea class="textarea" v-model="vehForm.notes" rows="2"></textarea></div>
      </div>
      <div class="row" style="justify-content:flex-end;gap:6px;margin-top:10px;">
        <button class="btn" @click="vehModal = false">Batal</button>
        <button class="btn btn-primary" @click="saveVeh">💾 Simpan</button>
      </div>
    </Modal>

    <!-- Modal Log Servis Kendaraan -->
    <Modal v-if="vehSvcModal" :title="'🛠️ Log Servis — ' + vehSvcTarget.nopol" @close="vehSvcModal = false">
      <p class="muted" style="font-size:12px;margin-bottom:8px;">{{ vehSvcTarget.vehicle_type }} · odometer {{ Number(vehSvcTarget.last_odometer || 0).toLocaleString('id-ID') }} km</p>
      <div class="form-grid">
        <div class="field"><label>Tanggal Servis</label><input class="input" type="date" v-model="vehSvcForm.service_date" /></div>
        <div class="field"><label>Odometer</label><input class="input" type="number" v-model="vehSvcForm.odometer" /></div>
        <div class="field"><label>Jenis Servis</label>
          <select class="select" v-model="vehSvcForm.service_type">
            <option>Servis Rutin</option><option>Perbaikan</option><option>Ganti Oli</option><option>Ganti Komponen</option><option>Lainnya</option>
          </select></div>
        <div class="field"><label>Komponen <span class="req">*</span></label>
          <input class="input" v-model="vehSvcForm.component_name" list="comp-list" placeholder="cth: Oli Mesin" />
          <datalist id="comp-list"><option v-for="c in compList" :key="c.id" :value="c.component_name" /></datalist></div>
        <div class="field"><label>Biaya (Rp)</label><input class="input" type="number" v-model="vehSvcForm.cost" /></div>
        <div class="field"><label>Montir</label><input class="input" v-model="vehSvcForm.mechanic_name" /></div>
        <div class="field"><label>No. Invoice</label><input class="input" v-model="vehSvcForm.invoice_number" /></div>
        <div class="field" style="grid-column:1/-1;"><label>Komponen Diganti</label><input class="input" v-model="vehSvcForm.parts_replaced" /></div>
        <div class="field" style="grid-column:1/-1;"><label>Catatan</label><textarea class="textarea" v-model="vehSvcForm.notes" rows="2"></textarea></div>
      </div>
      <div class="row" style="justify-content:flex-end;gap:6px;margin-top:10px;">
        <button class="btn" @click="vehSvcModal = false">Tutup</button>
        <button class="btn btn-primary" @click="saveVehSvc">💾 Simpan Log</button>
      </div>
      <hr style="border:none;border-top:1px solid var(--border);margin:14px 0;" />
      <div class="att-edit-list">
        <div v-for="svc in vehSvcList" :key="svc.id" class="att-edit-row">
          <span class="badge badge-blue">{{ fmtDate(svc.service_date) }}</span>
          <span style="font-size:12px;">{{ svc.component_name }}</span>
          <span class="muted" style="font-size:11px;">{{ Number(svc.odometer || 0).toLocaleString('id-ID') }} km</span>
          <span v-if="svc.cost" class="muted" style="font-size:11px;">{{ fmtMoney(svc.cost) }}</span>
          <div class="spacer"></div>
          <button class="btn btn-sm btn-danger" @click="delVehSvc(svc)">🗑</button>
        </div>
        <div v-if="!vehSvcList.length" class="empty">Belum ada log servis untuk kendaraan ini.</div>
      </div>
    </Modal>

    <!-- Modal Komponen -->
    <Modal v-if="compModal" :title="(compForm.id ? '✏️ Edit' : '＋ Tambah') + ' Komponen'" @close="compModal = false">
      <div class="form-grid">
        <div class="field"><label>Nama Komponen <span class="req">*</span></label><input class="input" v-model="compForm.component_name" /></div>
        <div class="field"><label>Kategori</label><input class="input" v-model="compForm.category" placeholder="cth: Mesin" /></div>
        <div class="field"><label>Umur Standar (km)</label><input class="input" type="number" v-model="compForm.standard_life_km" /></div>
        <div class="field"><label>Umur Standar (bulan)</label><input class="input" type="number" v-model="compForm.standard_life_months" /></div>
        <div class="field"><label>Estimasi Biaya (Rp)</label><input class="input" type="number" v-model="compForm.estimated_cost" /></div>
        <div class="field"><label>Prioritas</label><input class="input" type="number" v-model="compForm.priority" /></div>
        <div class="field" style="grid-column:1/-1;"><label>Catatan</label><textarea class="textarea" v-model="compForm.notes" rows="2"></textarea></div>
      </div>
      <div class="row" style="justify-content:flex-end;gap:6px;margin-top:10px;">
        <button class="btn" @click="compModal = false">Batal</button>
        <button class="btn btn-primary" @click="saveComp">💾 Simpan</button>
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
.att-edit-row .spacer { flex: 1; }
</style>
