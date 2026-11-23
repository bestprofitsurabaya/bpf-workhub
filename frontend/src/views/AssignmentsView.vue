<script setup>
import { onBeforeUnmount, onMounted, ref, computed } from 'vue'
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

// v2.132.0 — pengajuan tukar / pindah kendaraan dari driver
const swapRequests = ref([])
const reqBusy = ref(false)
const reqModal = ref(null)      // { mode: 'approve' | 'reject', row }
const reqNote = ref('')
const reqConflict = ref(null)
const ackSupersede = ref(false)
const pendingRequests = computed(() => swapRequests.value.filter((r) => r.status === 'pending'))
const REQ_STATUS = {
  pending: { label: '⏳ Menunggu', cls: '' },
  approved: { label: '✅ Disetujui', cls: 'badge-green' },
  completed: { label: '✔ Selesai', cls: 'badge-green' },
  rejected: { label: '✕ Ditolak', cls: 'badge-red' },
  cancelled: { label: '✕ Dibatalkan', cls: '' },
  superseded: { label: '↪ Ditutup', cls: '' },
}
function reqStatusLabel(status) {
  return (REQ_STATUS[status] || {}).label || status || '-'
}
function reqStatusClass(status) {
  return (REQ_STATUS[status] || {}).cls || ''
}
function requestTarget(row) {
  return row.swap_type === 'move' ? 'kosong' : `${row.target_driver} · ${row.target_nopol}`
}

function openApprove(row) {
  reqModal.value = { mode: 'approve', row }
  reqConflict.value = null
  ackSupersede.value = false
  reqNote.value = ''
  msg.value = ''
}

function openReject(row) {
  reqModal.value = { mode: 'reject', row }
  reqConflict.value = null
  reqNote.value = ''
  msg.value = ''
}

async function submitDecision() {
  const modal = reqModal.value
  if (!modal) return
  reqBusy.value = true
  msg.value = ''
  try {
    if (modal.mode === 'approve') {
      const r = await api(`/api/assignments/swap-requests/${modal.row.id}/approve`, {
        method: 'POST',
        body: { acknowledge_supersede: ackSupersede.value },
      })
      msg.value = `✅ ${r.msg || 'Pengajuan disetujui'}`
    } else {
      if (!reqNote.value.trim()) return
      const r = await api(`/api/assignments/swap-requests/${modal.row.id}/reject`, {
        method: 'POST',
        body: { note: reqNote.value.trim() },
      })
      msg.value = `✅ ${r.msg || 'Pengajuan ditolak'}`
    }
    reqModal.value = null
    reqConflict.value = null
    await load()
  } catch (e) {
    msg.value = '❌ ' + e.message
    if (e.data && e.data.code === 'supersede_required') {
      reqConflict.value = e.data
      ackSupersede.value = false
    }
  } finally {
    reqBusy.value = false
  }
}

async function load() {
  loading.value = true; err.value = ''
  try {
    const [a, u, d, s, q] = await Promise.all([
      api('/api/assignments/active').catch(() => []),
      api('/api/assignments/unassigned').catch(() => []),
      api('/api/drivers').catch(() => []),
      api('/api/assignments/swap-history').catch(() => []),
      api('/api/assignments/swap-requests').catch(() => []),
    ])
    active.value = Array.isArray(a) ? a : []
    unassigned.value = Array.isArray(u) ? u : []
    drivers.value = Array.isArray(d) ? d : []
    swaps.value = Array.isArray(s) ? s : []
    swapRequests.value = Array.isArray(q) ? q : []
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

let pollTimer = null
onMounted(() => {
  load()
  // Pengajuan driver bisa masuk kapan saja — segarkan diam-diam tiap 60 detik.
  pollTimer = setInterval(load, 60000)
})
onBeforeUnmount(() => {
  if (pollTimer) clearInterval(pollTimer)
  pollTimer = null
})
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
      <button class="btn" :class="tab === 'pengajuan' ? 'btn-primary' : ''" @click="tab = 'pengajuan'">
        📨 Pengajuan<span v-if="pendingRequests.length" class="badge badge-red" style="margin-left:6px;">{{ pendingRequests.length }}</span>
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

    <div class="card" v-else-if="tab === 'pengajuan'">
      <div class="table-wrap">
        <table class="tbl">
          <thead><tr>
            <th>Waktu</th><th>Jenis</th><th>Pengaju</th><th>Tujuan</th>
            <th>Kategori</th><th>Alasan</th><th>Status</th><th>Aksi</th>
          </tr></thead>
          <tbody>
            <tr v-for="r in swapRequests" :key="r.id" :data-request-id="r.id">
              <td>{{ r.created_at }}<br><span class="muted">{{ r.request_code }}</span></td>
              <td>{{ r.swap_type === 'move' ? '➡️ Pindah' : '🔄 Tukar' }}</td>
              <td><b>{{ r.requester_driver }}</b><br><span class="muted">{{ r.requester_nopol }}</span></td>
              <td>
                <template v-if="r.swap_type === 'move'"><span class="muted">kosong</span></template>
                <template v-else><b>{{ r.target_driver }}</b><br><span class="muted">{{ r.target_nopol }}</span></template>
              </td>
              <td>{{ categoryLabel(r.category) }}</td>
              <td>{{ r.reason }}</td>
              <td><span class="badge" :class="reqStatusClass(r.status)">{{ reqStatusLabel(r.status) }}</span></td>
              <td style="white-space:nowrap;">
                <template v-if="r.status === 'pending'">
                  <button class="btn btn-sm btn-primary" @click="openApprove(r)">Setujui</button>
                  <button class="btn btn-sm btn-danger" style="margin-left:6px;" @click="openReject(r)">Tolak</button>
                </template>
                <span v-else class="muted">{{ r.ga_name || '—' }}</span>
              </td>
            </tr>
            <tr v-if="!swapRequests.length"><td colspan="8" class="empty">Belum ada pengajuan driver.</td></tr>
          </tbody>
        </table>
      </div>
    </div>

    <div class="card" v-else-if="tab === 'swap'">
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

    <!-- Modal keputusan pengajuan driver (v2.132.0) -->
    <div v-if="reqModal" class="modal-overlay" role="dialog" aria-modal="true"
         aria-label="Keputusan pengajuan" @click.self="reqModal = null">
      <div class="card card-pad" style="max-width:480px;width:92vw;">
        <h3>{{ reqModal.mode === 'approve' ? '✅ Setujui Pengajuan' : '✕ Tolak Pengajuan' }}</h3>
        <p class="muted" style="font-size:12px;margin-top:2px;">
          {{ reqModal.row.request_code || ('#' + reqModal.row.id) }} ·
          {{ reqModal.row.swap_type === 'move' ? 'Pindah kendaraan' : 'Tukar kendaraan' }} ·
          <b>{{ reqModal.row.requester_driver }}</b> ({{ reqModal.row.requester_nopol }})
          → {{ requestTarget(reqModal.row) }}
        </p>
        <p style="font-size:12px;">Alasan: {{ reqModal.row.reason }}</p>

        <template v-if="reqModal.mode === 'approve'">
          <p class="muted" style="font-size:12px;">
            <template v-if="reqModal.row.swap_type === 'move'">
              Kendaraan {{ reqModal.row.requester_nopol }} akan masuk pool dan
              {{ reqModal.row.requester_driver }} menerima {{ reqModal.row.target_nopol }}.
            </template>
            <template v-else>
              Kedua kendaraan langsung bertukar pengemudi setelah disetujui.
            </template>
          </p>
          <div v-if="reqConflict" class="alert alert-error" style="font-size:12px;">
            Ada serah terima lain yang belum selesai:
            <b>{{ (reqConflict.conflicts || []).join(', ') }}</b>.
            Pengajuan lama akan ditutup bila Anda lanjutkan.
          </div>
          <label v-if="reqConflict" style="display:flex;gap:8px;align-items:center;font-size:12px;margin:8px 0;">
            <input type="checkbox" v-model="ackSupersede" />
            Ya, tutup serah terima sebelumnya dan setujui pengajuan ini
          </label>
        </template>
        <template v-else>
          <div class="field" style="margin-bottom:10px;">
            <label>Catatan penolakan <span class="req">*</span></label>
            <textarea class="textarea" rows="3" v-model="reqNote"
                      placeholder="cth: kendaraan masih dipakai untuk shift malam…"></textarea>
          </div>
        </template>

        <div class="row" style="justify-content:flex-end;gap:6px;">
          <button class="btn" @click="reqModal = null">Batal</button>
          <button v-if="reqModal.mode === 'approve'" class="btn btn-primary"
                  :disabled="reqBusy || (reqConflict && !ackSupersede)" @click="submitDecision">
            {{ reqBusy ? '⏳ Memproses…' : '✅ Setujui' }}
          </button>
          <button v-else class="btn btn-danger"
                  :disabled="reqBusy || !reqNote.trim()" @click="submitDecision">
            {{ reqBusy ? '⏳ Memproses…' : '✕ Tolak' }}
          </button>
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
