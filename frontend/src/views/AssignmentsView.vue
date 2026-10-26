<script setup>
import { onMounted, ref, computed } from 'vue'
import { api } from '../api'
import { useAuthStore } from '../stores/auth'
import LoadingState from '../components/LoadingState.vue'
import ErrorState from '../components/ErrorState.vue'
import PageHeader from '../components/PageHeader.vue'

const auth = useAuthStore()
const active = ref([])
const unassigned = ref([])
const drivers = ref([])
const swaps = ref([])
const loading = ref(true)
const err = ref('')
const msg = ref('')
const form = ref({ nopol: '', driver_name: '' })
const releaseForm = ref({ nopol: '', reason: '' })
const busy = ref(false)

// v2.73.0 — tukar driver (fitur swap yang dulu terbenam)
const tab = ref('aktif') // 'aktif' | 'swap'
const swapOpen = ref(false)
const swapForm = ref({ nopol: '', new_driver: '', category: 'driver_request', reason: '' })
const CATEGORIES = [
  { value: 'driver_request', label: 'Permintaan driver' },
  { value: 'vehicle_issue', label: 'Masalah kendaraan' },
  { value: 'mutasi', label: 'Mutasi / rotasi' },
  { value: 'other', label: 'Lainnya' },
]
function categoryLabel(c) {
  return (CATEGORIES.find((x) => x.value === c) || {}).label || c || '-'
}
const gaName = computed(() => auth.user?.full_name || 'GA Officer')

// v2.73.0 — catatan GA per penugasan (driver_notes, dibaca PDF cross-check)
const remarkTarget = ref(null)
const remarkText = ref('')

// v2.73.0 — antrean konfirmasi serah terima (confirmed_by_driver = 0)
const pendingCount = computed(() => active.value.filter((a) => !a.confirmed_by_driver).length)

async function load() {
  loading.value = true; err.value = ''
  try {
    const [a, u, d, s] = await Promise.all([
      api('/api/assignments/active').catch(() => []),
      api('/api/assignments/unassigned').catch(() => []),
      api('/api/drivers').catch(() => []),
      api('/api/assignments/swap-history').catch(() => []),
    ])
    active.value = Array.isArray(a) ? a : []
    unassigned.value = Array.isArray(u) ? u : []
    drivers.value = Array.isArray(d) ? d : []
    swaps.value = Array.isArray(s) ? s : []
  } catch (e) { err.value = e.message }
  finally { loading.value = false }
}

async function assign() {
  if (!form.value.nopol || !form.value.driver_name) return
  busy.value = true; msg.value = ''
  try {
    const r = await api('/api/assignments/create', { method: 'POST', body: { driver_name: form.value.driver_name, nopol: form.value.nopol } })
    msg.value = '✅ ' + (r.msg || 'Assign berhasil'); form.value.nopol = ''; form.value.driver_name = ''; load()
  } catch (e) { msg.value = '❌ ' + e.message }
  finally { busy.value = false }
}

async function release() {
  if (!releaseForm.value.nopol) return
  busy.value = true; msg.value = ''
  try {
    const r = await api('/api/assignments/release', { method: 'POST', body: { nopol: releaseForm.value.nopol, reason: releaseForm.value.reason || 'Dilepas', ga_name: gaName.value } })
    msg.value = '✅ ' + (r.msg || 'Kendaraan dilepas'); releaseForm.value = { nopol: '', reason: '' }; load()
  } catch (e) { msg.value = '❌ ' + e.message }
  finally { busy.value = false }
}

function openSwap(a) {
  swapForm.value = { nopol: a ? a.nopol : '', new_driver: '', category: 'driver_request', reason: '' }
  swapOpen.value = true
}

async function submitSwap() {
  const f = swapForm.value
  if (!f.nopol || !f.new_driver || !f.reason) return
  busy.value = true; msg.value = ''
  try {
    const r = await api('/api/assignments/swap', {
      method: 'POST',
      body: { nopol: f.nopol, new_driver: f.new_driver, category: f.category, reason: f.reason, ga_name: gaName.value },
    })
    msg.value = '✅ ' + (r.msg || 'Tukar driver berhasil'); swapOpen.value = false; tab.value = 'aktif'; load()
  } catch (e) { msg.value = '❌ ' + e.message }
  finally { busy.value = false }
}

function openRemark(a) {
  remarkTarget.value = a
  remarkText.value = a.driver_notes || ''
}

async function saveRemark() {
  if (!remarkTarget.value || !remarkText.value.trim()) return
  busy.value = true; msg.value = ''
  try {
    await api('/api/assignment-remark', {
      method: 'POST',
      body: { nopol: remarkTarget.value.nopol, driver_name: remarkTarget.value.driver_name, remark: remarkText.value },
    })
    msg.value = '✅ Catatan disimpan'; remarkTarget.value = null; load()
  } catch (e) { msg.value = '❌ ' + e.message }
  finally { busy.value = false }
}

onMounted(load)
</script>

<template>
  <div>
    <PageHeader icon="🚗" title="Penugasan Driver" subtitle="Assign, tukar driver, konfirmasi serah terima & catatan kendaraan" />
    <div class="card card-pad" style="margin-bottom:16px;">
      <h3>➕ Assign Kendaraan</h3>
      <div class="row">
        <select class="select" v-model="form.nopol" style="min-width:200px;">
          <option value="">Pilih kendaraan kosong…</option>
          <option v-for="v in unassigned" :key="v.nopol || v.id" :value="v.nopol">{{ v.nopol }} · {{ v.vehicle_type }}</option>
        </select>
        <select class="select" v-model="form.driver_name" style="min-width:160px;">
          <option value="">Pilih driver…</option>
          <option v-for="dr in drivers.filter((x) => x.is_active)" :key="dr.name" :value="dr.name">{{ dr.name }}</option>
        </select>
        <button class="btn btn-primary" :disabled="busy || !form.nopol || !form.driver_name" @click="assign">➕ Assign</button>
        <input class="input" v-model="releaseForm.nopol" placeholder="Nopol untuk dilepas" style="width:150px;" />
        <button class="btn btn-warning" :disabled="busy || !releaseForm.nopol" @click="release">✕ Lepas</button>
        <span v-if="msg" class="alert" :class="msg.startsWith('✅') ? 'alert-success' : 'alert-error'" style="margin:0;">{{ msg }}</span>
        <button class="btn" :disabled="!active.length" title="Tukar pengemudi sebuah kendaraan aktif" @click="openSwap(null)">🔄 Tukar Driver</button>
      </div>
    </div>

    <div style="margin-bottom:10px;">
      <button class="btn" :class="tab === 'aktif' ? 'btn-primary' : ''" @click="tab = 'aktif'">
        Saat Ini ({{ active.length }})<span v-if="pendingCount" class="badge badge-red" style="margin-left:6px;">⏳ {{ pendingCount }} belum konfirmasi</span>
      </button>
      <button class="btn" :class="tab === 'swap' ? 'btn-primary' : ''" @click="tab = 'swap'">🔄 Riwayat Tukar Driver ({{ swaps.length }})</button>
    </div>

    <div v-if="loading"><LoadingState :rows="4" label="Memuat penugasan…" /></div>
    <div v-else-if="err"><ErrorState :message="err" @retry="load" /></div>

    <div class="card" v-else-if="tab === 'aktif'">
      <div class="table-wrap">
        <table class="tbl">
          <thead><tr>
            <th>Driver</th><th>Nopol</th><th>Tipe</th><th>BBM</th>
            <th>Serah Terima</th><th>Catatan</th><th>Aksi</th>
          </tr></thead>
          <tbody>
            <tr v-for="a in active" :key="a.id || a.nopol">
              <td><b>{{ a.driver_name }}</b></td>
              <td>{{ a.nopol }}</td>
              <td>{{ a.vehicle_type }}</td>
              <td>{{ a.bbm_type }}</td>
              <td>
                <span v-if="a.confirmed_by_driver" class="badge badge-green">✅ Sudah dikonfirmasi</span>
                <span v-else class="badge badge-red">⏳ Belum dikonfirmasi</span>
              </td>
              <td>{{ a.driver_notes || '—' }}</td>
              <td style="white-space:nowrap;">
                <button class="btn btn-sm btn-primary" @click="openSwap(a)">🔄 Tukar</button>
                <button class="btn btn-sm" style="margin-left:6px;" @click="openRemark(a)">✍️ Catatan</button>
              </td>
            </tr>
            <tr v-if="!active.length"><td colspan="7" class="empty">Tidak ada penugasan aktif.</td></tr>
          </tbody>
        </table>
      </div>
    </div>

    <div class="card" v-else>
      <div class="table-wrap">
        <table class="tbl">
          <thead><tr>
            <th>Waktu</th><th>Nopol</th><th>Perubahan</th><th>Kategori</th><th>Alasan</th><th>GA</th>
          </tr></thead>
          <tbody>
            <tr v-for="s in swaps" :key="s.id">
              <td>{{ s.created_at }}</td>
              <td><b>{{ s.nopol }}</b></td>
              <td>{{ s.old_driver || '—' }} → <b>{{ s.new_driver || '—' }}</b></td>
              <td>{{ categoryLabel(s.category) }}</td>
              <td>{{ s.reason || '—' }}</td>
              <td>{{ s.ga_name || '—' }}</td>
            </tr>
            <tr v-if="!swaps.length"><td colspan="6" class="empty">Belum ada riwayat tukar driver.</td></tr>
          </tbody>
        </table>
      </div>
    </div>

    <!-- Modal Tukar Driver (v2.73.0) -->
    <div v-if="swapOpen" class="modal-overlay" role="dialog" aria-modal="true" aria-label="Tukar driver" @click.self="swapOpen = false" @keydown.esc="swapOpen = false">
      <div class="card card-pad" style="max-width:460px;width:92vw;">
        <h3>🔄 Tukar Driver</h3>
        <div class="field" style="margin-bottom:8px;">
          <label>Nopol (kendaraan aktif)</label>
          <select class="select" v-model="swapForm.nopol">
            <option value="">— Pilih kendaraan —</option>
            <option v-for="a in active" :key="a.nopol" :value="a.nopol">{{ a.nopol }} · {{ a.driver_name }}</option>
          </select>
        </div>
        <div class="field" style="margin-bottom:8px;">
          <label>Driver baru</label>
          <select class="select" v-model="swapForm.new_driver">
            <option value="">— Pilih driver —</option>
            <option v-for="dr in drivers.filter((x) => x.is_active)" :key="dr.name" :value="dr.name">{{ dr.name }}</option>
          </select>
        </div>
        <div class="field" style="margin-bottom:8px;">
          <label>Kategori</label>
          <select class="select" v-model="swapForm.category">
            <option v-for="c in CATEGORIES" :key="c.value" :value="c.value">{{ c.label }}</option>
          </select>
        </div>
        <div class="field" style="margin-bottom:10px;">
          <label>Alasan <span class="req">*</span></label>
          <input class="input" v-model="swapForm.reason" placeholder="cth: driver lama cuti, kendaraan bermasalah…" />
        </div>
        <div class="row" style="justify-content:flex-end;gap:6px;">
          <button class="btn" @click="swapOpen = false">Batal</button>
          <button class="btn btn-primary" :disabled="busy || !swapForm.nopol || !swapForm.new_driver || !swapForm.reason" @click="submitSwap">{{ busy ? '⏳ Menyimpan…' : '✅ Tukar' }}</button>
        </div>
      </div>
    </div>

    <!-- Modal Catatan (v2.73.0) -->
    <div v-if="remarkTarget" class="modal-overlay" role="dialog" aria-modal="true" aria-label="Catatan kendaraan" @click.self="remarkTarget = null" @keydown.esc="remarkTarget = null">
      <div class="card card-pad" style="max-width:460px;width:92vw;">
        <h3>✍️ Catatan Kendaraan — {{ remarkTarget.nopol }}</h3>
        <p class="muted" style="font-size:12px;margin-top:2px;">Catatan GA untuk <b>{{ remarkTarget.driver_name }}</b> — dibaca di laporan PDF cross-check.</p>
        <textarea class="textarea" v-model="remarkText" rows="4" placeholder="cth: kaca depan retak, tarik periksa bengkel…" style="margin-bottom:10px;"></textarea>
        <div class="row" style="justify-content:flex-end;gap:6px;">
          <button class="btn" @click="remarkTarget = null">Batal</button>
          <button class="btn btn-primary" :disabled="busy || !remarkText.trim()" @click="saveRemark">{{ busy ? '⏳ Menyimpan…' : '💾 Simpan' }}</button>
        </div>
      </div>
    </div>
  </div>
</template>
