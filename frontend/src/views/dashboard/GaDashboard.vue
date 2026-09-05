<script setup>
import { ref, onMounted, watch } from 'vue'
import { api } from '../../api'
import StatCard from '../../components/StatCard.vue'
import Modal from '../../components/Modal.vue'
import { useRealtimeStore } from '../../stores/realtime'
import { useStepupStore } from '../../stores/stepup'

const stepup = useStepupStore()

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

const fmt = (n) => 'Rp ' + (Number(n) || 0).toLocaleString('id-ID')

const waitingCash = () =>
  (cash.value || []).filter((c) => c.status === 'DRAFT').reduce((a, c) => a + Number(c.total_amount || 0), 0)
const waitingCashCount = () => (cash.value || []).filter((c) => c.status === 'DRAFT').length

async function load() {
  loading.value = true
  try {
    const [s, q, c, t] = await Promise.all([
      api('/api/stats').catch(() => null),
      api('/api/queue', { params: { tab: 'ga' } }).catch(() => []),
      api('/api/cash/history').catch(() => []),
      api('/api/trips', { params: { status: 'pending' } }).catch(() => ({ data: [] })),
    ])
    stats.value = s
    queue.value = q || []
    cash.value = c || []
    trips.value = (t && t.data) || []
  } finally {
    loading.value = false
  }
}

async function doApprove(tx) {
  if (!window.confirm(`Setujui klaim ${tx.display_id || tx.id}?`)) return
  busy.value = true
  try {
    // Step-up (ISO/IEC 27001): approve menggerakkan uang → PIN ulang bila perlu
    await stepup.require(
      () => api(`/api/queue/approve-ga/${tx.id}`, { method: 'POST' }),
      `menyetujui klaim ${tx.display_id || tx.id}`
    )
    await load()
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
const realtime = useRealtimeStore()
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
</script>

<template>
  <div class="page">
    <div class="card card-pad" style="margin-bottom:16px;">
      <h2 style="margin:0;">🧾 Dashboard GA</h2>
      <div class="muted" style="font-size:12px;">Verifikasi klaim BBM, kasbon, dan laporan perjalanan</div>
    </div>

    <div v-if="loading" class="card card-pad muted skeleton">Memuat…</div>
    <template v-else>
      <div class="stat-grid" style="margin-bottom:16px;">
        <StatCard icon="🕐" label="Antrean GA" :value="stats?.pending ?? '—'" color="#dc2626" />
        <StatCard icon="✅" label="Verified GA" :value="stats?.verified_ga ?? '—'" color="#0891b2" />
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
                  <button v-if="!t.ml_anomaly_flag" class="btn btn-sm btn-primary" :disabled="busy" @click="doApprove(t)">✅ Approve</button>
                  <button v-else class="btn btn-sm btn-primary" :disabled="busy" title="Klaim ber-flag anomali ML — verifikasi foto bukti & konfirmasi" @click="openVerify(t)">🛡 Verifikasi</button>
                  <button class="btn btn-sm" :disabled="busy" style="margin-left:6px;" @click="openReject(t)">✕ Tolak</button>
                </td>
              </tr>
              <tr v-if="!queue.length"><td colspan="6" class="muted">Antrean kosong — tidak ada klaim menunggu GA 🎉</td></tr>
            </tbody>
          </table>
          <div class="muted" style="font-size:11px;margin-top:8px;">
            Klaim ber-flag ⚠️ ML diverifikasi di sini (tombol 🛡 Verifikasi — periksa foto bukti lalu konfirmasi).
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
            <router-link class="btn" to="/assignments">🚗 Assignments</router-link>
            <router-link class="btn" to="/cash">💵 Kasbon</router-link>
            <router-link class="btn" to="/water">🚰 Air Minum</router-link>
            <router-link class="btn" to="/analytics">📈 Analytics</router-link>
          </div>
        </div>
      </div>
    </template>

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
</style>
