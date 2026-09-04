<script setup>
import { computed, onMounted, ref } from 'vue'
import { api } from '../api'
import Modal from '../components/Modal.vue'
import { identity } from '../stores/identity'

const drivers = ref([])
const vehicles = ref([])
const bbms = ref([])
const loading = ref(true)
const err = ref('')
const msg = ref('')
const busy = ref(false)

// Buat akun sekaligus (v2.19): semua driver + semua user di dropdown marketing
const bulkBusy = ref(false)
const bulkMsg = ref('')
const bulkResult = ref(null) // { scope, created: [], skipped: [] }
const showBulk = ref(false)

async function bulkCreate(scope) {
  const label = scope === 'driver' ? 'SEMUA driver aktif' : scope === 'marketing' ? 'SEMUA user di dropdown marketing' : 'semua akun'
  if (!confirm(`Buat akun login (PIN 123456) untuk ${label} yang belum punya akun?`)) return
  bulkBusy.value = true; bulkMsg.value = ''; bulkResult.value = null
  try {
    const r = await api('/api/users/bulk-create', { method: 'POST', body: { scope } })
    bulkMsg.value = '✅ ' + (r.msg || 'Akun dibuat')
    bulkResult.value = r
    showBulk.value = true
  } catch (e) { bulkMsg.value = '❌ ' + e.message }
  finally { bulkBusy.value = false }
}

const showDriverForm = ref(false)
const driverForm = ref({ driver_name: '', nopol: '', vehicle_type: 'AVANZA', bbm_type: 'PERTALITE' })
const showVehicleForm = ref(false)
const vehicleForm = ref({ nopol: '', vehicle_type: 'AVANZA', brand: 'Toyota', bbm_default: 'PERTALITE' })

// Identitas perusahaan / cabang (v2.19.2) — multi-cabang
const identityForm = ref({ company_name: '', company_subtitle: '', system_name: '', system_version: '', company_address: '', company_phone: '' })
const identityMsg = ref('')
const identityBusy = ref(false)

async function loadIdentityForm() {
  try {
    const d = await api('/api/system-config/identity')
    if (d && !d.error) {
      identityForm.value = {
        company_name: d.company_name || '',
        company_subtitle: d.company_subtitle || '',
        system_name: d.system_name || '',
        system_version: d.system_version || '',
        company_address: d.company_address || '',
        company_phone: d.company_phone || '',
      }
    }
  } catch { /* noop */ }
}

async function saveIdentity() {
  identityBusy.value = true; identityMsg.value = ''
  try {
    const r = await api('/api/system-config/identity', { method: 'PUT', body: { ...identityForm.value } })
    identityMsg.value = '✅ ' + (r.msg || 'Identitas perusahaan disimpan')
    Object.assign(identity, r.identity || identityForm.value)
    document.title = identity.system_name
  } catch (e) { identityMsg.value = '❌ ' + e.message }
  finally { identityBusy.value = false }
}

// Cabang (v2.19.2) — multi-cabang: satu instalasi, banyak cabang (DB terpisah)
const branches = ref([])
const currentBranch = ref(null)
const branchBusy = ref(false)
const branchMsg = ref('')
const showBranchForm = ref(false)
const branchForm = ref({ id: null, code: '', name: '', db_name: '', city: '', address: '', phone: '', company_name: '', company_subtitle: '', system_name: '', system_version: '', is_active: true, ensure_db: true })

async function loadBranches() {
  try {
    const d = await api('/api/branches/current')
    currentBranch.value = d.current || null
    branches.value = Array.isArray(d.branches) ? d.branches : []
  } catch { /* noop */ }
}

function openBranchForm(b) {
  if (b && b.id) {
    branchForm.value = {
      id: b.id, code: b.code, name: b.name, db_name: b.db_name, city: b.city || '',
      address: b.address || '', phone: b.phone || '', company_name: b.company_name || '',
      company_subtitle: b.company_subtitle || '', system_name: b.system_name || '',
      system_version: b.system_version || '', is_active: !!b.is_active, ensure_db: false,
    }
  } else {
    branchForm.value = { id: null, code: '', name: '', db_name: '', city: '', address: '', phone: '', company_name: '', company_subtitle: '', system_name: '', system_version: '', is_active: true, ensure_db: true }
  }
  showBranchForm.value = true
}

async function saveBranch() {
  branchBusy.value = true; branchMsg.value = ''
  try {
    const body = { ...branchForm.value }
    body.code = (body.code || '').trim().toUpperCase()
    if (!body.code || !body.name || !body.db_name) { branchMsg.value = '❌ code, nama, dan db_name wajib'; return }
    const r = await api('/api/branches/save', { method: 'POST', body })
    branchMsg.value = '✅ ' + (r.msg || 'Cabang disimpan')
    showBranchForm.value = false
    loadBranches()
  } catch (e) { branchMsg.value = '❌ ' + e.message }
  finally { branchBusy.value = false }
}

async function toggleBranch(code, active) {
  branchBusy.value = true; branchMsg.value = ''
  try {
    const r = await api(`/api/branches/${encodeURIComponent(code)}/${active ? 'activate' : 'deactivate'}`, { method: 'POST' })
    branchMsg.value = '✅ ' + (r.msg || 'Status cabang diperbarui')
    loadBranches()
  } catch (e) { branchMsg.value = '❌ ' + e.message }
  finally { branchBusy.value = false }
}

async function ensureDb(code) {
  branchBusy.value = true; branchMsg.value = ''
  try {
    const r = await api(`/api/branches/${encodeURIComponent(code)}/ensure-db`, { method: 'POST' })
    branchMsg.value = '✅ ' + (r.msg || 'Database cabang siap')
  } catch (e) { branchMsg.value = '❌ ' + e.message }
  finally { branchBusy.value = false }
}

async function seedDemoBranch(code) {
  if (!confirm(`Tanam data demo (rute + transaksi dummy) ke cabang ${code}? Idempoten — data asli aman.`)) return
  branchBusy.value = true; branchMsg.value = ''
  try {
    const r = await api(`/api/branches/${encodeURIComponent(code)}/seed-demo`, { method: 'POST' })
    branchMsg.value = '✅ ' + (r.msg || 'Data demo ditanam')
  } catch (e) { branchMsg.value = '❌ ' + e.message }
  finally { branchBusy.value = false }
}

async function switchBranch(code) {
  if (!code || code === currentBranch.value?.code) return
  branchBusy.value = true; branchMsg.value = ''
  try {
    const r = await api('/api/branches/switch', { method: 'POST', body: { code } })
    branchMsg.value = '✅ ' + (r.msg || 'Cabang diganti')
    setTimeout(() => window.location.reload(), 600)
  } catch (e) { branchMsg.value = '❌ ' + e.message }
  finally { branchBusy.value = false }
}

// Data demo (v2.19.2) — dibuat & dibersihkan Admin
const demoStatus = ref(null)
const demoBusy = ref(false)
const demoMsg = ref('')

async function loadDemoStatus() {
  try { demoStatus.value = await api('/api/demo/status') } catch { demoStatus.value = null }
}

async function demoSeed() {
  if (!confirm('Buat data demo (rute appointment + transaksi dummy)? Aman — idempoten, tidak mengubah data asli.')) return
  demoBusy.value = true; demoMsg.value = ''
  try {
    const r = await api('/api/demo/seed', { method: 'POST', body: { scope: 'all' } })
    demoMsg.value = '✅ ' + (r.msg || 'Data demo dibuat') + (r.summary ? ` (rute baru ${r.summary.routes}, transaksi ${r.summary.transactions})` : '')
    loadDemoStatus()
  } catch (e) { demoMsg.value = '❌ ' + e.message }
  finally { demoBusy.value = false }
}

async function demoClean() {
  if (!confirm('BERSIHKAN semua data demo (rute appointment DEMO-* + transaksi dummy)? Data asli TIDAK terpengaruh.')) return
  demoBusy.value = true; demoMsg.value = ''
  try {
    const r = await api('/api/demo/clean', { method: 'POST', body: { scope: 'all' } })
    demoMsg.value = '✅ ' + (r.msg || 'Data demo dibersihkan') + (r.summary ? ` (rute ${r.summary.routes}, transaksi ${r.summary.transactions})` : '')
    loadDemoStatus()
  } catch (e) { demoMsg.value = '❌ ' + e.message }
  finally { demoBusy.value = false }
}

// Tanda tangan tanda terima air minum (v2.6): Finance = penyerah, GA = penerima
const waterNames = ref({ ga: '', finance: '' })
const waterMsg = ref('')

async function loadWaterNames() {
  try {
    const [ga, finance] = await Promise.all([
      api('/api/system-config/water_ga_name').catch(() => ({ value: '' })),
      api('/api/system-config/water_finance_name').catch(() => ({ value: '' })),
    ])
    waterNames.value = { ga: ga.value || '', finance: finance.value || '' }
  } catch { /* noop */ }
}

async function saveWaterNames() {
  busy.value = true; waterMsg.value = ''
  try {
    await api('/api/system-config/water_ga_name', { method: 'PUT', body: { value: waterNames.value.ga } })
    await api('/api/system-config/water_finance_name', { method: 'PUT', body: { value: waterNames.value.finance } })
    waterMsg.value = '✅ Nama penandatangan air minum disimpan'
  } catch (e) { waterMsg.value = '❌ ' + e.message }
  finally { busy.value = false }
}

const vehicleTypes = computed(() => ['AVANZA', ...[...new Set(vehicles.value.map((v) => (v.vehicle_type || '').trim()).filter(Boolean))].sort()].filter((v, i, a) => a.indexOf(v) === i).slice(0, 12))
const bbmNames = computed(() => bbms.value.map((b) => b.name).filter(Boolean))

async function load() {
  loading.value = true; err.value = ''
  try {
    const [d, v, b] = await Promise.all([
      api('/api/drivers').catch(() => []),
      api('/api/vehicles').catch(() => []),
      api('/api/bbm_types').catch(() => []),
    ])
    drivers.value = Array.isArray(d) ? d : []
    vehicles.value = Array.isArray(v) ? v : []
    bbms.value = Array.isArray(b) ? b : []
  } catch (e) { err.value = e.message }
  finally { loading.value = false }
}

async function toggleDriver(name, active) {
  busy.value = true; msg.value = ''
  try {
    await api(`/api/drivers/${encodeURIComponent(name)}/${active ? 'activate' : 'deactivate'}`, { method: 'POST' })
    msg.value = '✅ Status driver diperbarui'; load()
  } catch (e) { msg.value = '❌ ' + e.message }
  finally { busy.value = false }
}

async function addDriver() {
  busy.value = true; msg.value = ''
  try {
    const body = { ...driverForm.value }
    body.driver_name = body.driver_name.trim().toUpperCase()
    body.nopol = body.nopol.trim().toUpperCase()
    if (!body.driver_name) { msg.value = '❌ Nama driver wajib diisi'; return }
    await api('/api/drivers/sync', { method: 'POST', body })
    msg.value = '✅ Driver tersimpan'
    showDriverForm.value = false
    driverForm.value = { driver_name: '', nopol: '', vehicle_type: 'AVANZA', bbm_type: 'PERTALITE' }
    load()
  } catch (e) { msg.value = '❌ ' + e.message }
  finally { busy.value = false }
}

async function deleteDriver(name) {
  if (!confirm(`HAPUS permanen driver "${name}"?`)) return
  busy.value = true; msg.value = ''
  try {
    await api(`/api/drivers/${encodeURIComponent(name)}/delete`, { method: 'POST' })
    msg.value = '✅ Driver dihapus'; load()
  } catch (e) { msg.value = '❌ ' + e.message }
  finally { busy.value = false }
}

/** Reset PIN massal seluruh akun driver ke 123456 (onboarding cepat). */
async function resetDriverPinMassal() {
  if (!confirm('Reset PIN SEMUA akun driver menjadi 123456?')) return
  busy.value = true; msg.value = ''
  try {
    const r = await api('/api/drivers/pin-reset', { method: 'POST', body: { new_pin: '123456' } })
    msg.value = '✅ ' + (r.msg || 'PIN semua driver direset ke 123456')
  } catch (e) { msg.value = '❌ ' + e.message }
  finally { busy.value = false }
}

async function addVehicle() {
  busy.value = true; msg.value = ''
  try {
    const body = { ...vehicleForm.value }
    body.nopol = body.nopol.trim().toUpperCase()
    if (!body.nopol) { msg.value = '❌ No. Polisi wajib diisi'; return }
    await api('/api/vehicles/add', { method: 'POST', body })
    msg.value = '✅ Kendaraan tersimpan'
    showVehicleForm.value = false
    vehicleForm.value = { nopol: '', vehicle_type: 'AVANZA', brand: 'Toyota', bbm_default: 'PERTALITE' }
    load()
  } catch (e) { msg.value = '❌ ' + e.message }
  finally { busy.value = false }
}

onMounted(() => { load(); loadWaterNames(); loadIdentityForm(); loadDemoStatus(); loadBranches() })
</script>

<template>
  <div>
    <div v-if="msg" class="alert" :class="msg.startsWith('✅') ? 'alert-success' : 'alert-error'">{{ msg }}</div>
    <div v-if="loading" class="empty skeleton">⏳ Memuat…</div>
    <div v-else-if="err" class="alert alert-error">{{ err }}</div>
    <template v-else>
      <div class="card card-pad" style="margin-bottom:16px;display:flex;align-items:center;">
        <div class="grow">
          <h3 style="margin:0;">🚗 Data Master</h3>
          <p class="muted" style="font-size:11px;">Khusus Admin · pengelolaan driver, kendaraan &amp; tipe BBM</p>
        </div>
        <button class="btn btn-primary btn-sm" @click="showDriverForm = true">➕ Tambah Driver</button>
        <button class="btn btn-sm" style="margin-left:8px;" @click="showVehicleForm = true">🚙 Tambah Kendaraan</button>
        <button class="btn btn-sm" style="margin-left:8px;" :disabled="busy" @click="resetDriverPinMassal" title="Set PIN semua akun driver ke 123456">🔑 PIN Driver = 123456</button>
      </div>

      <div class="card card-pad" style="margin-bottom:16px;">
        <h3 style="margin:0;">👥 Buat Akun Sekaligus</h3>
        <p class="muted" style="font-size:11px;">
          Buat akun login (role driver / marketing, PIN default <b>123456</b>) untuk semua driver aktif dan
          semua user di dropdown marketing yang belum punya akun. Akun yang sudah ada dilewati — idempoten.
        </p>
        <div class="row" style="margin-top:10px;gap:8px;">
          <button class="btn btn-primary btn-sm" :disabled="bulkBusy" @click="bulkCreate('driver')">🚗 Buat Akun Semua Driver</button>
          <button class="btn btn-sm" :disabled="bulkBusy" @click="bulkCreate('marketing')">📣 Buat Akun User Marketing</button>
          <span v-if="bulkMsg" class="alert" :class="bulkMsg.startsWith('✅') ? 'alert-success' : 'alert-error'" style="margin:0;padding:6px 10px;">{{ bulkMsg }}</span>
        </div>
      </div>

      <div class="card card-pad" style="margin-bottom:16px;">
        <h3 style="margin:0;">🚰 Tanda Terima Air Minum</h3>
        <p class="muted" style="font-size:11px;">Nama penandatangan dokumen PDF pembelian air minum — Finance selaku <b>Menyerahkan</b> &amp; GA selaku <b>Menerima</b></p>
        <div class="form-grid" style="margin-top:12px;">
          <div class="field"><label>Nama Finance (Menyerahkan)</label><input class="input" v-model="waterNames.finance" placeholder="mis. Rina Wijaya" /></div>
          <div class="field"><label>Nama GA (Menerima)</label><input class="input" v-model="waterNames.ga" placeholder="mis. Andi Prasetyo" /></div>
        </div>
        <div class="row" style="justify-content:flex-end;gap:8px;margin-top:8px;">
          <span class="muted" style="font-size:12px;">{{ waterMsg }}</span>
          <button class="btn btn-primary btn-sm" :disabled="busy" @click="saveWaterNames">💾 Simpan Nama TTD</button>
        </div>
      </div>

      <div class="card card-pad" style="margin-bottom:16px;">
        <h3 style="margin:0;">🏢 Cabang (Multi-Cabang)</h3>
        <p class="muted" style="font-size:11px;">
          Satu instalasi melayani banyak cabang — setiap cabang punya <b>database sendiri</b> (isolasi data penuh).
          Cabang aktif: <b>{{ currentBranch?.name || '—' }}</b>
        </p>
        <div class="row" style="margin-top:10px;gap:8px;align-items:center;flex-wrap:wrap;">
          <button class="btn btn-primary btn-sm" @click="openBranchForm(null)">➕ Tambah Cabang</button>
          <label class="muted" style="font-size:12px;">Ganti cabang (Admin):</label>
          <select class="select" style="width:auto;" :value="currentBranch?.code" :disabled="branchBusy" @change="switchBranch($event.target.value)">
            <option v-for="b in branches" :key="b.code" :value="b.code">{{ b.name }} ({{ b.code }})</option>
          </select>
          <span v-if="branchMsg" class="alert" :class="branchMsg.startsWith('✅') ? 'alert-success' : 'alert-error'" style="margin:0;padding:6px 10px;">{{ branchMsg }}</span>
        </div>
        <div class="table-wrap" style="margin-top:10px;">
          <table class="tbl">
            <thead><tr><th>Kode</th><th>Nama Cabang</th><th>Database</th><th>Kota</th><th>Status</th><th></th></tr></thead>
            <tbody>
              <tr v-for="b in branches" :key="b.code">
                <td><b>{{ b.code }}</b></td>
                <td>{{ b.name }}</td>
                <td>{{ b.db_name }}</td>
                <td>{{ b.city || '—' }}</td>
                <td><span class="badge" :class="b.is_active ? 'badge-green' : 'badge-red'">{{ b.is_active ? 'Aktif' : 'Nonaktif' }}</span></td>
                <td>
                  <button class="btn btn-sm" @click="ensureDb(b.code)" title="Buat/sinkronkan database cabang">🗄️ DB</button>
                  <button class="btn btn-sm" @click="seedDemoBranch(b.code)" title="Tanam data demo (rute + transaksi dummy) ke cabang ini">🧪 Demo</button>
                  <button class="btn btn-sm" @click="toggleBranch(b.code, !b.is_active)" :disabled="branchBusy">{{ b.is_active ? '🔴 Nonaktifkan' : '🟢 Aktifkan' }}</button>
                </td>
              </tr>
              <tr v-if="!branches.length"><td colspan="6" class="empty">Belum ada cabang.</td></tr>
            </tbody>
          </table>
        </div>
      </div>

      <div class="card card-pad" style="margin-bottom:16px;">
        <h3 style="margin:0;">🏢 Identitas Perusahaan / Cabang</h3>
        <p class="muted" style="font-size:11px;">
          Variabel branding dipakai di PDF (kop surat &amp; footer), halaman login, sidebar &amp; watermark foto —
          bisa diubah Admin saat aplikasi dipakai cabang lain (siap multi-cabang).
        </p>
        <div class="form-grid" style="margin-top:12px;">
          <div class="field"><label>Nama Perusahaan</label><input class="input" v-model="identityForm.company_name" placeholder="PT BESTPROFIT FUTURES" /></div>
          <div class="field"><label>Nama Sistem / Aplikasi</label><input class="input" v-model="identityForm.system_name" placeholder="BPF WorkHub" /></div>
          <div class="field"><label>Subjudul (kantor | kota)</label><input class="input" v-model="identityForm.company_subtitle" placeholder="Kantor Pusat | Jakarta" /></div>
          <div class="field"><label>Versi</label><input class="input" v-model="identityForm.system_version" placeholder="v2.20.1" /></div>
          <div class="field"><label>Alamat Kantor</label><input class="input" v-model="identityForm.company_address" placeholder="Jl. Darmo 45, Surabaya" /></div>
          <div class="field"><label>Telepon</label><input class="input" v-model="identityForm.company_phone" placeholder="031-1234567" /></div>
        </div>
        <div class="row" style="justify-content:flex-end;gap:8px;margin-top:8px;">
          <span class="muted" style="font-size:12px;">{{ identityMsg }}</span>
          <button class="btn btn-primary btn-sm" :disabled="identityBusy" @click="saveIdentity">💾 Simpan Identitas</button>
        </div>
      </div>

      <div class="card card-pad" style="margin-bottom:16px;">
        <h3 style="margin:0;">🧪 Data Demo</h3>
        <p class="muted" style="font-size:11px;">
          Buat atau bersihkan data demo (rute appointment <code>DEMO-*</code> &amp; transaksi dummy) — data asli tidak terpengaruh.
          Memudahkan gladi resik / pelatihan user baru.
        </p>
        <div class="row" style="margin-top:10px;gap:8px;align-items:center;flex-wrap:wrap;">
          <button class="btn btn-primary btn-sm" :disabled="demoBusy" @click="demoSeed">✨ Buat Data Demo</button>
          <button class="btn btn-sm btn-danger" :disabled="demoBusy" @click="demoClean">🧹 Bersihkan Data Demo</button>
          <span v-if="demoStatus" class="muted" style="font-size:12px;">Rute demo: <b>{{ demoStatus.demo_appointments }}</b> · Transaksi demo: <b>{{ demoStatus.demo_transactions }}</b></span>
          <span v-if="demoMsg" class="alert" :class="demoMsg.startsWith('✅') ? 'alert-success' : 'alert-error'" style="margin:0;padding:6px 10px;">{{ demoMsg }}</span>
        </div>
      </div>

      <div class="card" style="margin-bottom:16px;">
        <h3 style="padding:14px 18px 0;">👤 Driver</h3>
        <div class="table-wrap">
          <table class="tbl">
            <thead><tr><th>Nama</th><th>Nopol</th><th>Tipe</th><th>BBM</th><th>Status</th><th></th></tr></thead>
            <tbody>
              <tr v-for="d in drivers" :key="d.name">
                <td><b>{{ d.name }}</b></td><td>{{ d.nopol || '—' }}</td><td>{{ d.vehicle_type }}</td>
                <td>{{ d.bbm_type }}</td>
                <td><span class="badge" :class="d.is_active ? 'badge-green' : 'badge-red'">{{ d.is_active ? 'Aktif' : 'Nonaktif' }}</span></td>
                <td>
                  <button class="btn btn-sm" :disabled="busy" @click="toggleDriver(d.name, !d.is_active)">
                    {{ d.is_active ? '🔴 Nonaktifkan' : '🟢 Aktifkan' }}
                  </button>
                  <button class="btn btn-sm btn-danger" :disabled="busy" style="margin-left:6px;" @click="deleteDriver(d.name)" title="Hapus permanen">🗑</button>
                </td>
              </tr>
              <tr v-if="!drivers.length"><td colspan="6" class="empty">Belum ada driver.</td></tr>
            </tbody>
          </table>
        </div>
      </div>

      <div class="stat-grid">
        <div class="card card-pad">
          <h3>🚙 Kendaraan</h3>
          <div class="table-wrap">
            <table class="tbl">
              <thead><tr><th>Tipe</th><th>Merk</th><th>Kapasitas</th><th>Status</th></tr></thead>
              <tbody>
                <tr v-for="v in vehicles" :key="v.id || v.vehicle_type">
                  <td><b>{{ v.vehicle_type }}</b></td><td>{{ v.brand }}</td><td>{{ v.fuel_capacity }}</td>
                  <td><span class="badge" :class="v.is_active ? 'badge-green' : 'badge-red'">{{ v.is_active ? 'Aktif' : 'Nonaktif' }}</span></td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>
        <div class="card card-pad">
          <h3>⛽ Tipe BBM</h3>
          <div class="table-wrap">
            <table class="tbl">
              <thead><tr><th>Nama</th><th>Harga/L</th><th>Status</th></tr></thead>
              <tbody>
                <tr v-for="b in bbms" :key="b.id || b.name">
                  <td><b>{{ b.name }}</b></td><td>{{ 'Rp ' + Number(b.price_per_liter || 0).toLocaleString('id-ID') }}</td>
                  <td><span class="badge" :class="b.is_active ? 'badge-green' : 'badge-red'">{{ b.is_active ? 'Aktif' : 'Nonaktif' }}</span></td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </template>

    <Modal v-if="showBulk && bulkResult" title="✅ Hasil Buat Akun Sekaligus" @close="showBulk = false">
      <p class="alert alert-info" style="font-size:12px;">{{ bulkResult.msg }}</p>
      <h4 style="margin:10px 0 6px;">🆕 Akun dibuat ({{ bulkResult.created.length }})</h4>
      <div v-if="bulkResult.created.length" class="table-wrap">
        <table class="tbl">
          <thead><tr><th>Username</th><th>Role</th><th>Tim</th></tr></thead>
          <tbody>
            <tr v-for="c in bulkResult.created" :key="c.username">
              <td><b>{{ c.username }}</b></td><td>{{ c.role }}</td><td>{{ c.team || '—' }}</td>
            </tr>
          </tbody>
        </table>
      </div>
      <p v-else class="muted" style="font-size:12px;">Tidak ada akun baru (semua sudah ada / tidak ada data).</p>
      <h4 style="margin:12px 0 6px;">⏭ Dilewati ({{ bulkResult.skipped.length }})</h4>
      <ul v-if="bulkResult.skipped.length" style="font-size:11px;margin:0;padding-left:18px;">
        <li v-for="(s, i) in bulkResult.skipped" :key="i">{{ s.name }} — {{ s.reason }}</li>
      </ul>
      <p v-else class="muted" style="font-size:12px;">—</p>
      <div class="row" style="justify-content:flex-end;margin-top:12px;">
        <button class="btn btn-primary" @click="showBulk = false">Tutup</button>
      </div>
    </Modal>

    <Modal v-if="showDriverForm" title="➕ Tambah Driver" @close="showDriverForm = false">
      <div class="form-grid">
        <div class="field"><label>Nama Driver *</label><input class="input" v-model="driverForm.driver_name" placeholder="mis. RIVAN" /></div>
        <div class="field"><label>No. Polisi</label><input class="input" v-model="driverForm.nopol" placeholder="mis. L 1234 AB" /></div>
        <div class="field"><label>Tipe Kendaraan</label>
          <select class="select" v-model="driverForm.vehicle_type"><option v-for="t in vehicleTypes" :key="t" :value="t">{{ t }}</option></select>
        </div>
        <div class="field"><label>Tipe BBM</label>
          <select class="select" v-model="driverForm.bbm_type"><option v-for="b in bbmNames" :key="b" :value="b">{{ b }}</option></select>
        </div>
      </div>
      <div class="row" style="justify-content:flex-end;margin-top:12px;">
        <button class="btn" @click="showDriverForm = false">Batal</button>
        <button class="btn btn-primary" :disabled="busy" @click="addDriver">💾 Simpan</button>
      </div>
    </Modal>

    <Modal v-if="showBranchForm" :title="branchForm.id ? `✏️ Edit Cabang ${branchForm.code}` : '➕ Tambah Cabang'" @close="showBranchForm = false">
      <div class="form-grid">
        <div class="field"><label>Kode Cabang *</label><input class="input" v-model="branchForm.code" placeholder="mis. MLG" :disabled="!!branchForm.id" /></div>
        <div class="field"><label>Nama Cabang *</label><input class="input" v-model="branchForm.name" placeholder="mis. Cabang Malang" /></div>
        <div class="field"><label>Nama Database *</label><input class="input" v-model="branchForm.db_name" placeholder="mis. bpf_branch_malang" :disabled="!!branchForm.id" /></div>
        <div class="field"><label>Kota</label><input class="input" v-model="branchForm.city" placeholder="Malang" /></div>
        <div class="field"><label>Alamat</label><input class="input" v-model="branchForm.address" /></div>
        <div class="field"><label>Telepon</label><input class="input" v-model="branchForm.phone" /></div>
        <div class="field"><label>Nama Perusahaan</label><input class="input" v-model="branchForm.company_name" placeholder="PT BESTPROFIT FUTURES" /></div>
        <div class="field"><label>Subjudul (kantor | kota)</label><input class="input" v-model="branchForm.company_subtitle" placeholder="Sistem Operasional | Malang" /></div>
        <div class="field"><label>Nama Sistem</label><input class="input" v-model="branchForm.system_name" placeholder="BPF WorkHub" /></div>
        <div class="field"><label>Versi</label><input class="input" v-model="branchForm.system_version" placeholder="v2.20.1" /></div>
      </div>
      <label class="muted" style="font-size:12px;display:flex;align-items:center;gap:6px;margin-top:8px;">
        <input type="checkbox" v-model="branchForm.ensure_db" /> Buat database cabang langsung (salinan skema)
      </label>
      <div class="row" style="justify-content:flex-end;margin-top:12px;">
        <button class="btn" @click="showBranchForm = false">Batal</button>
        <button class="btn btn-primary" :disabled="branchBusy" @click="saveBranch">💾 Simpan Cabang</button>
      </div>
    </Modal>

    <Modal v-if="showVehicleForm" title="🚙 Tambah Kendaraan" @close="showVehicleForm = false">
      <div class="form-grid">
        <div class="field"><label>No. Polisi *</label><input class="input" v-model="vehicleForm.nopol" placeholder="mis. L 1234 AB" /></div>
        <div class="field"><label>Tipe Kendaraan</label>
          <select class="select" v-model="vehicleForm.vehicle_type"><option v-for="t in vehicleTypes" :key="t" :value="t">{{ t }}</option></select>
        </div>
        <div class="field"><label>Merk</label><input class="input" v-model="vehicleForm.brand" /></div>
        <div class="field"><label>BBM Default</label>
          <select class="select" v-model="vehicleForm.bbm_default"><option v-for="b in bbmNames" :key="b" :value="b">{{ b }}</option></select>
        </div>
      </div>
      <div class="row" style="justify-content:flex-end;margin-top:12px;">
        <button class="btn" @click="showVehicleForm = false">Batal</button>
        <button class="btn btn-primary" :disabled="busy" @click="addVehicle">💾 Simpan</button>
      </div>
    </Modal>
  </div>
</template>
