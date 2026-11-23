<script setup>
import { ref, computed, onMounted, watch } from 'vue'
import { api } from '../../api'
import StatCard from '../../components/StatCard.vue'
import PageHeader from '../../components/PageHeader.vue'
import Modal from '../../components/Modal.vue'
import ConfirmDialog from '../../components/ConfirmDialog.vue'
import ClaimVerifyCard from '../../components/ClaimVerifyCard.vue'
import { formatRupiah } from '../../utils/format.js'
import { useRealtimeStore } from '../../stores/realtime'
import { useStepupStore } from '../../stores/stepup'

const stepup = useStepupStore()
const confirmRef = ref(null)
const ask = (message, opts) => confirmRef.value?.open(message, opts) ?? Promise.resolve(false)

// Toast hasil aksi service memakai jalur toast global (ToastStack) yang sama
// dengan notifikasi realtime. Tidak ada emitToast bawaan di komponen ini —
// guard `typeof` sebelumnya membuat hasil sukses/gagal hilang tanpa jejak.
const realtime = useRealtimeStore()
function emitToast(text, type = 'success') {
  realtime.push(text, type)
}

const stats = ref(null)
const queue = ref([])
const cash = ref([])
const trips = ref([])
const loading = ref(true)
const busy = ref(false)
const rejectFor = ref(null)
const rejectReason = ref('')
const verifyFor = ref(null)
const verifyOk = ref(false)
// Instrumen verifikasi klaim (Detail) — foto bukti + cross-check + Subsidi Tepat
const detailFor = ref(null)
const gaDetail = ref(null) // wave-18A: payload detail (status terbaru) untuk tombol PDF
// v2.131.0 — catatan service mobil dari driver
const serviceReports = ref([])
const serviceFor = ref(null)
const serviceNote = ref('')
// Task 3 — filter & bulk review catatan service
const svcFilterStatus = ref('')
const svcFilterFrom = ref('')
const svcFilterTo = ref('')
const svcFilterQ = ref('')
const svcSelected = ref([])

function openDetail(tx) {
  detailFor.value = tx
  gaDetail.value = null
}

function onDetailLoaded(payload) {
  gaDetail.value = payload?.detail || null
}

// wave-18A: 📄 PDF per transaksi (GA/Finance/Admin diizinkan backend); sembunyikan saat pending
const showGaPdf = computed(() => {
  const st = gaDetail.value?.status || detailFor.value?.status
  return !!st && st !== 'pending'
})
function openTxPdf() {
  const id = gaDetail.value?.id || detailFor.value?.id
  if (id) window.open('/admin/report/' + id)
}

async function detailApprove(tx) {
  const okDone = await doApprove(tx)
  if (okDone !== false) detailFor.value = null
}

function detailReject(tx) {
  detailFor.value = null
  openReject(tx)
}

function detailVerify(tx) {
  detailFor.value = null
  openVerify(tx)
}

function openServiceReview(r) {
  serviceFor.value = r
  serviceNote.value = r.ga_note || ''
}

async function doServiceReview(status) {
  if (!serviceFor.value) return
  busy.value = true
  try {
    await api(`/api/ga/service-reports/${serviceFor.value.id}/review`, {
      method: 'POST',
      body: { status, ga_note: serviceNote.value },
    })
    emitToast(status === 'REVIEWED' ? '✅ Catatan service diselesaikan' : '✕ Catatan service ditolak')
    serviceFor.value = null
    await load()
  } catch (e) {
    emitToast('❌ ' + (e.message || 'Gagal memperbarui'), 'error')
  } finally {
    busy.value = false
  }
}

function printServicePdf(r) {
  window.open(`/api/ga/service-reports/${r.id}/pdf`, '_blank')
}

function applyServiceFilter() {
  svcSelected.value = []
  return load()
}

function resetServiceFilter() {
  svcFilterStatus.value = ''
  svcFilterFrom.value = ''
  svcFilterTo.value = ''
  svcFilterQ.value = ''
  svcSelected.value = []
  return load()
}

function toggleService(id) {
  const i = svcSelected.value.indexOf(id)
  if (i >= 0) svcSelected.value.splice(i, 1)
  else svcSelected.value.push(id)
}

async function bulkServiceReview(status) {
  if (!svcSelected.value.length) return
  const ids = [...svcSelected.value]
  let note = ''
  if (status === 'REJECTED') {
    const answer = await ask(
      `Tolak ${ids.length} laporan service? Catatan GA wajib diisi.`,
      {
        title: 'Tolak laporan service', confirmText: 'Ya, tolak', danger: true,
        input: true, placeholder: 'Alasan penolakan (wajib)',
      }
    )
    if (!answer) return
    note = answer
  } else {
    const ok = await ask(
      `Tandai ${ids.length} laporan service sebagai selesai?`,
      { title: 'Tandai selesai', confirmText: 'Ya, tandai selesai' }
    )
    if (!ok) return
  }
  busy.value = true
  try {
    const body = { ids, status }
    if (status === 'REJECTED') body.ga_note = note
    await api('/api/ga/service-reports/bulk-review', { method: 'POST', body })
    emitToast(status === 'REVIEWED'
      ? `✅ ${ids.length} laporan ditandai selesai`
      : `✕ ${ids.length} laporan ditolak`)
    svcSelected.value = []
    await load()
  } catch (e) {
    emitToast('❌ ' + (e.message || 'Gagal memperbarui'), 'error')
  } finally {
    busy.value = false
  }
}

const fmt = formatRupiah

const waitingCash = () =>
  (cash.value || []).filter((c) => c.status === 'DRAFT').reduce((a, c) => a + Number(c.total_amount || 0), 0)
const waitingCashCount = () => (cash.value || []).filter((c) => c.status === 'DRAFT').length

async function load() {
  loading.value = true
  try {
    const [s, q, c, t, sr] = await Promise.all([
      api('/api/stats').catch(() => null),
      api('/api/queue', { params: { tab: 'ga' } }).catch(() => []),
      api('/api/cash/history').catch(() => []),
      api('/api/trips', { params: { status: 'pending' } }).catch(() => ({ data: [] })),
      api('/api/ga/service-reports', { params: {
        status: svcFilterStatus.value,
        from: svcFilterFrom.value,
        to: svcFilterTo.value,
        q: svcFilterQ.value,
      } }).catch(() => ({ data: [] })),
    ])
    stats.value = s
    queue.value = q || []
    cash.value = c || []
    trips.value = (t && t.data) || []
    serviceReports.value = (sr && sr.data) || []
  } finally {
    loading.value = false
  }
}

async function doApprove(tx) {
  const ok = await ask(`Setujui klaim ${tx.display_id || tx.id}? Klaim akan diteruskan ke Finance untuk pencairan.`, {
    title: 'Setujui klaim',
    confirmText: 'Ya, setujui',
  })
  if (!ok) return
  busy.value = true
  try {
    // Step-up (ISO/IEC 27001): approve menggerakkan uang → PIN ulang bila perlu
    await stepup.require(
      () => api(`/api/queue/approve-ga/${tx.id}`, { method: 'POST' }),
      `menyetujui klaim ${tx.display_id || tx.id}`
    )
    await load()
  } catch (e) {
    // v2.36.0: ACC berjenjang — klaim masih menunggu ACC Chief Driver.
    if (e.status === 409 && e.data && e.data.code === 'SUPERVISOR_APPROVAL_REQUIRED') {
      alert('⏳ Menunggu ACC atasan (' + (e.data.pending_at || 'Chief Driver') + '). Proses dulu lewat menu ACC Atasan.')
      return false // ACC 409: klaim belum disetujui — modal detail tetap terbuka
    } else { throw e }
  } finally {
    busy.value = false
  }
}

function openReject(tx) {
  rejectFor.value = tx
  rejectReason.value = ''
}

function openVerify(tx) {
  verifyFor.value = tx
  verifyOk.value = false
}

async function doVerify() {
  if (!verifyFor.value || !verifyOk.value) return
  busy.value = true
  try {
    // Step-up: verifikasi & persetujuan anomali = menyetujui klaim (uang)
    await stepup.require(
      () => api(`/api/queue/verify/${verifyFor.value.id}`, { method: 'POST', body: { confirm_anomaly: '1' } }),
      `verifikasi & menyetujui klaim ${verifyFor.value.display_id || verifyFor.value.id}`
    )
    verifyFor.value = null
    verifyOk.value = false
    await load()
  } finally {
    busy.value = false
  }
}

async function doReject() {
  if (!rejectFor.value) return
  const reason = rejectReason.value.trim() || 'Ditolak dari Dashboard GA'
  busy.value = true
  try {
    await api(`/api/queue/reject/${rejectFor.value.id}`, { method: 'POST', body: { reason } })
    rejectFor.value = null
    rejectReason.value = ''
    await load()
  } finally {
    busy.value = false
  }
}

onMounted(load)

// v2.9: antrean GA langsung refresh saat ada klaim BBM baru (event realtime new_claim)
let lastClaimToast = null
watch(
  () => realtime.items[0],
  (item) => {
    if (item && item.type === 'new_claim' && item.id !== lastClaimToast && !loading.value) {
      lastClaimToast = item.id
      load()
    }
  }
)

watch(
  () => realtime.items[0],
  (item) => {
    if (item && item.type === 'new_service_report' && !loading.value) load()
  }
)
</script>

<template>
  <div class="page">
    <PageHeader icon="🧾" title="Dashboard GA" subtitle="Verifikasi klaim BBM, kasbon, dan laporan perjalanan" />

    <div v-if="loading" class="card card-pad muted skeleton">Memuat…</div>
    <template v-else>
      <div class="stat-grid" style="margin-bottom:16px;">
        <StatCard icon="🕐" label="Antrean GA" :value="stats?.pending ?? '—'" color="#dc2626" />
        <StatCard icon="✅" label="Terverifikasi GA" :value="stats?.verified_ga ?? '—'" color="#0891b2" />
        <StatCard icon="📦" label="Terarsip" :value="stats?.archived ?? '—'" color="#059669" />
        <StatCard icon="📅" label="Transaksi Hari Ini" :value="stats?.today_tx ?? '—'" color="#2563eb" />
        <StatCard icon="💵" label="Kasbon Menunggu Approve" :value="fmt(waitingCash())" color="#d97706" :sub="waitingCashCount() + ' pengajuan'" />
      </div>

      <div class="row" style="align-items:flex-start;gap:16px;margin-bottom:16px;">
        <!-- Antrean klaim GA -->
        <div class="card card-pad grow">
          <h3 style="margin-top:0;">🕐 Antrean Klaim BBM</h3>
          <table class="table">
            <thead><tr><th>Nomor</th><th>Driver</th><th>Nopol</th><th>Nominal</th><th>Anomali</th><th></th></tr></thead>
            <tbody>
              <tr v-for="t in queue" :key="t.id">
                <td>{{ t.display_id }}</td>
                <td>{{ t.driver_name }}</td>
                <td>{{ t.nopol }}</td>
                <td>{{ fmt(t.nominal) }}</td>
                <td><span v-if="t.ml_anomaly_flag" class="badge badge-amber">⚠️ ML</span><span v-else class="muted">—</span></td>
                <td>
                  <button class="btn btn-sm" :disabled="busy" title="Instrumen verifikasi: foto bukti, cross-check & Subsidi Tepat" @click="openDetail(t)">👁 Detail</button>
                  <button v-if="!t.ml_anomaly_flag" class="btn btn-sm btn-primary" :disabled="busy" style="margin-left:6px;" @click="doApprove(t)">✅ Setujui</button>
                  <button v-else class="btn btn-sm btn-primary" :disabled="busy" title="Klaim ber-flag anomali ML — verifikasi foto bukti & konfirmasi" @click="openVerify(t)">🛡 Verifikasi</button>
                  <button class="btn btn-sm" :disabled="busy" style="margin-left:6px;" @click="openReject(t)">✕ Tolak</button>
                </td>
              </tr>
              <tr v-if="!queue.length"><td colspan="6" class="muted">Antrean kosong — tidak ada klaim menunggu GA 🎉</td></tr>
            </tbody>
          </table>
          <div class="muted" style="font-size:11px;margin-top:8px;">
            Klaim ber-flag ⚠️ ML diverifikasi di sini (tombol 🛡 Verifikasi — periksa foto bukti lalu konfirmasi).
            Tombol 👁 Detail membuka instrumen verifikasi lengkap sebelum memutuskan.
          </div>
        </div>

        <!-- Ringkasan -->
        <div class="card card-pad" style="min-width:300px;">
          <h3 style="margin-top:0;">📋 Ringkasan Lainnya</h3>
          <div class="mini-row">
            <span>🗺️ Laporan perjalanan menunggu review</span>
            <b>{{ trips.length }}</b>
          </div>
          <div class="mini-row">
            <span>💵 Kasbon menunggu approve GA</span>
            <b>{{ waitingCashCount() }}</b>
          </div>
          <div class="mini-row">
            <span>🚰 Pengajuan air minum (semua)</span>
            <b>lihat Dashboard Finance</b>
          </div>
          <h3 style="margin-top:16px;">⚡ Aksi Cepat</h3>
          <div class="quick-links">
            <router-link class="btn" to="/trips">🗺️ Review Trip</router-link>
            <router-link class="btn" to="/assignments">🚗 Penugasan Driver</router-link>
            <router-link class="btn" to="/cash">💵 Kasbon</router-link>
            <router-link class="btn" to="/water">🚰 Air Minum</router-link>
            <router-link class="btn" to="/analytics">📈 Analytics</router-link>
          </div>
        </div>
      </div>
      <!-- v2.131.0 — Catatan Service Mobil dari driver -->
      <div class="card card-pad" style="margin-bottom:16px;">
        <div class="row" style="justify-content:space-between;align-items:center;">
          <h3 style="margin:0;">🔧 Catatan Service Mobil (Driver → GA)</h3>
          <span class="muted" style="font-size:11px;">{{ serviceReports.filter(r => r.status === 'SUBMITTED').length }} menunggu diproses</span>
        </div>
        <div class="row svc-filter" style="gap:8px;align-items:flex-end;margin-top:8px;">
          <label class="muted" style="font-size:11px;">Status
            <select class="inp" v-model="svcFilterStatus" style="display:block;margin-top:4px;">
              <option value="">Semua</option>
              <option value="SUBMITTED">SUBMITTED</option>
              <option value="REVIEWED">REVIEWED</option>
              <option value="REJECTED">REJECTED</option>
            </select>
          </label>
          <label class="muted" style="font-size:11px;">Dari
            <input class="inp" type="date" v-model="svcFilterFrom" style="display:block;margin-top:4px;">
          </label>
          <label class="muted" style="font-size:11px;">Sampai
            <input class="inp" type="date" v-model="svcFilterTo" style="display:block;margin-top:4px;">
          </label>
          <label class="muted" style="font-size:11px;">Cari
            <input class="inp" v-model="svcFilterQ" placeholder="No. form / nopol / keluhan" style="display:block;margin-top:4px;">
          </label>
          <button class="btn btn-sm" @click="applyServiceFilter">Terapkan</button>
          <button class="btn btn-sm" @click="resetServiceFilter">Reset</button>
        </div>
        <div class="row" style="gap:8px;align-items:center;margin-top:8px;">
          <span class="muted" style="font-size:12px;">{{ svcSelected.length }} dipilih</span>
          <button class="btn btn-sm btn-primary" :disabled="busy || !svcSelected.length" @click="bulkServiceReview('REVIEWED')">✅ Tandai selesai ({{ svcSelected.length }})</button>
          <button class="btn btn-sm btn-danger" :disabled="busy || !svcSelected.length" @click="bulkServiceReview('REJECTED')">✕ Tolak ({{ svcSelected.length }})</button>
        </div>
        <table class="table" style="margin-top:8px;">
          <thead><tr><th></th><th>No. Form</th><th>Driver</th><th>Nopol</th><th>KM</th><th>Status</th><th>Tanggal</th><th></th></tr></thead>
          <tbody>
            <tr v-for="r in serviceReports" :key="r.id">
              <td><input type="checkbox" :disabled="r.status !== 'SUBMITTED'" :checked="svcSelected.includes(r.id)" @change="toggleService(r.id)" :title="r.status === 'SUBMITTED' ? 'Pilih untuk aksi bulk' : 'Sudah diproses'"></td>
              <td>{{ r.display_id }}</td>
              <td>{{ r.driver_display_name || r.driver_name }}</td>
              <td>{{ r.nopol }}</td>
              <td>{{ r.km_kendaraan }}</td>
              <td>
                <span class="badge" :class="r.status === 'REVIEWED' ? 'badge-green' : r.status === 'REJECTED' ? 'badge-red' : 'badge-amber'">{{ r.status }}</span>
              </td>
              <td>{{ String(r.created_at || '').slice(0,10) }}</td>
              <td>
                <button class="btn btn-sm" @click="openServiceReview(r)">👁 Detail</button>
                <button class="btn btn-sm" style="margin-left:6px;" @click="printServicePdf(r)" title="Cetak dokumen resmi">📄 Cetak</button>
              </td>
            </tr>
            <tr v-if="!serviceReports.length"><td colspan="8" class="muted">Belum ada catatan service dari driver.</td></tr>
          </tbody>
        </table>
      </div>
    </template>

    <Modal v-if="serviceFor" :title="'🔧 ' + serviceFor.display_id" @close="serviceFor = null">
      <div class="svc-detail-row"><span>Driver</span><b>{{ serviceFor.driver_display_name || serviceFor.driver_name }}</b></div>
      <div class="svc-detail-row"><span>Nopol</span><b>{{ serviceFor.nopol }}</b></div>
      <div class="svc-detail-row"><span>Jenis Mobil</span><b>{{ serviceFor.vehicle_type || '-' }}</b></div>
      <div class="svc-detail-row"><span>KM Kendaraan</span><b>{{ serviceFor.km_kendaraan }}</b></div>
      <label class="muted" style="font-size:12px;display:block;margin-top:10px;">Catatan keluhan driver</label>
      <div class="card card-pad" style="font-size:13px;white-space:pre-wrap;">{{ serviceFor.keluhan }}</div>
      <label class="muted" style="font-size:12px;display:block;margin-top:10px;">Catatan GA</label>
      <textarea v-model="serviceNote" rows="3" class="inp" style="width:100%;" placeholder="Opsional — ikut tercetak di dokumen resmi"></textarea>
      <div class="row" style="justify-content:flex-end;gap:8px;margin-top:12px;">
        <button class="btn" @click="printServicePdf(serviceFor)">📄 Cetak PDF</button>
        <button class="btn" @click="serviceFor = null">Tutup</button>
        <button class="btn btn-danger" :disabled="busy || serviceFor.status !== 'SUBMITTED'" @click="doServiceReview('REJECTED')">✕ Tolak</button>
        <button class="btn btn-primary" :disabled="busy || serviceFor.status !== 'SUBMITTED'" @click="doServiceReview('REVIEWED')">✅ Selesaikan</button>
      </div>
    </Modal>

    <Modal v-if="rejectFor" :title="'✕ Tolak ' + (rejectFor.display_id || '')" @close="rejectFor = null">
      <label class="muted" style="font-size:12px;">Alasan penolakan</label>
      <textarea v-model="rejectReason" rows="3" class="inp" style="width:100%;margin-top:6px;" placeholder="Wajib diisi untuk audit trail"></textarea>
      <div class="row" style="justify-content:flex-end;gap:8px;margin-top:12px;">
        <button class="btn" @click="rejectFor = null">Batal</button>
        <button class="btn btn-danger" :disabled="busy || !rejectReason.trim()" title="Alasan wajib diisi untuk audit trail" @click="doReject">✕ Tolak &amp; Kirim</button>
      </div>
    </Modal>

    <Modal v-if="verifyFor" :title="'🛡 Verifikasi Anomali ' + (verifyFor.display_id || '')" @close="verifyFor = null">
      <p style="margin:0 0 8px;font-size:13px;">
        Klaim ini ditandai anomali oleh deteksi ML. Periksa <b>foto bukti</b> (struk/ODO)
        pada detail transaksi sebelum memutuskan.
      </p>
      <label style="display:flex;gap:8px;font-size:13px;align-items:flex-start;">
        <input v-model="verifyOk" type="checkbox" style="margin-top:2px;" />
        Saya sudah memeriksa foto bukti &amp; mengonfirmasi klaim ini valid
      </label>
      <div class="row" style="justify-content:flex-end;gap:8px;margin-top:12px;">
        <button class="btn" @click="verifyFor = null">Batal</button>
        <button class="btn btn-primary" :disabled="busy || !verifyOk" @click="doVerify">✅ Verifikasi &amp; Setujui</button>
      </div>
    </Modal>

    <!-- Instrumen verifikasi klaim — turunan ringkas modal Detail Admin (tanpa tab) -->
    <Modal v-if="detailFor" :title="'🔍 Detail ' + (detailFor.display_id || detailFor.id)" @close="detailFor = null">
      <ClaimVerifyCard ref="cardRef" :tx-id="detailFor.id" @loaded="onDetailLoaded" />
      <p class="muted" style="font-size:11px;margin:10px 0 0;">
        Kandidat Subsidi Tepat hanya baca — penjodohan klaim ↔ SPBU dilakukan oleh Finance.
      </p>
      <div class="row" style="justify-content:flex-end;gap:8px;margin-top:12px;">
        <button v-if="showGaPdf" class="btn" @click="openTxPdf" title="Unduh PDF laporan transaksi ini">📄 PDF</button>
        <button class="btn" @click="detailFor = null">Tutup</button>
        <button class="btn" :disabled="busy" @click="detailReject(detailFor)">✕ Tolak</button>
        <button v-if="!detailFor.ml_anomaly_flag" class="btn btn-primary" :disabled="busy" @click="detailApprove(detailFor)">✅ Setujui</button>
        <button v-else class="btn btn-primary" :disabled="busy" @click="detailVerify(detailFor)">🛡 Verifikasi Anomali</button>
      </div>
    </Modal>

    <ConfirmDialog ref="confirmRef" />
  </div>
</template>

<style scoped>
.row { display: flex; flex-wrap: wrap; }
.grow { flex: 1; min-width: 300px; }
.inp { padding: 8px 10px; border: 1px solid var(--border, #e2e8f0); border-radius: 8px; background: var(--card, #fff); color: var(--text, #0f172a); }
.table { width: 100%; border-collapse: collapse; font-size: 13px; }
.table th, .table td { text-align: left; padding: 7px 8px; border-bottom: 1px solid var(--border, #e2e8f0); }
.btn-sm { padding: 4px 10px; font-size: 12px; }
.mini-row { display: flex; justify-content: space-between; padding: 8px 0; border-bottom: 1px dashed var(--border, #e2e8f0); font-size: 13px; }
.quick-links { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 8px; }
.badge { font-size:10px; padding:2px 8px; border-radius:8px; font-weight:700; }
.badge-amber { background:#fef3c7; color:#92400e; }
.badge-green { background:#d1fae5; color:#065f46; }
.badge-red { background:#fee2e2; color:#b91c1c; }
.svc-detail-row { display:flex; justify-content:space-between; gap:10px; padding:5px 0; border-bottom:1px dashed var(--border,#e2e8f0); font-size:12px; }
</style>
