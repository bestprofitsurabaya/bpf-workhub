<script setup>
import { onMounted, ref } from 'vue'
import { api } from '../api'
import { useAuthStore } from '../stores/auth'
import Modal from '../components/Modal.vue'

const auth = useAuthStore()
const trips = ref([])
const loading = ref(true)
const err = ref('')
const f = ref({ driver: '', date: '', status: 'pending' })
const detail = ref(null)
const busy = ref(false)
const rejectReason = ref('')

const canVerify = ['ga', 'admin'].includes(auth.role)

async function load() {
  loading.value = true; err.value = ''
  try {
    const d = await api('/api/trips', { params: { ...f.value } })
    trips.value = d.data || []
  } catch (e) { err.value = e.message }
  finally { loading.value = false }
}

async function openDetail(id) {
  detail.value = null
  try { detail.value = await api('/api/trip-detail/' + id) }
  catch (e) { err.value = e.message }
}

async function act(id, action) {
  if (action === 'reject' && !rejectReason.value.trim()) { alert('Alasan penolakan wajib diisi'); return }
  busy.value = true
  try {
    await api(`/api/trips/${action}/${id}`, {
      method: 'POST',
      body: action === 'reject' ? { reason: rejectReason.value } : { admin_name: auth.user?.full_name || auth.user?.user_name || 'GA Officer' },
    })
    detail.value = null; rejectReason.value = ''; load()
  } catch (e) { alert('❌ ' + e.message) }
  finally { busy.value = false }
}

const STATUS = {
  pending: ['⏳ Pending', 'badge-amber'],
  verified_ga: ['✅ Terverifikasi GA', 'badge-blue'],
  rejected: ['❌ Ditolak', 'badge-red'],
}

onMounted(load)
</script>

<template>
  <div>
    <div class="card card-pad" style="margin-bottom:16px;">
      <div class="row">
        <div class="field" style="margin:0;"><label>Driver</label><input class="input" v-model="f.driver" placeholder="Nama driver" /></div>
        <div class="field" style="margin:0;"><label>Tanggal</label><input class="input" type="date" v-model="f.date" /></div>
        <div class="field" style="margin:0;"><label>Status</label>
          <select class="select" v-model="f.status">
            <option value="">Semua</option><option value="pending">Pending</option>
            <option value="verified_ga">Terverifikasi GA</option><option value="rejected">Ditolak</option>
          </select>
        </div>
        <button class="btn btn-primary" @click="load" style="margin-top:18px;">🔍 Terapkan</button>
      </div>
    </div>

    <div v-if="loading" class="empty skeleton">⏳ Memuat…</div>
    <div v-else-if="err" class="alert alert-error">{{ err }}</div>
    <div class="card" v-else>
      <div class="table-wrap">
        <table class="tbl">
          <thead><tr><th>ID</th><th>Driver</th><th>Tanggal</th><th>Rute</th><th>Status</th><th></th></tr></thead>
          <tbody>
            <tr v-for="t in trips" :key="t.id">
              <td><b>{{ t.display_id }}</b></td>
              <td>{{ t.driver_name }}</td>
              <td>{{ t.trip_date }}</td>
              <td>{{ t.total_routes ?? t.total_km ?? '—' }}</td>
              <td><span class="badge" :class="(STATUS[t.status] || STATUS.pending)[1]">{{ (STATUS[t.status] || STATUS.pending)[0] }}</span></td>
              <td><button class="btn btn-sm" @click="openDetail(t.id)">👁️ Detail</button></td>
            </tr>
            <tr v-if="!trips.length"><td colspan="6" class="empty">Tidak ada data log perjalanan.</td></tr>
          </tbody>
        </table>
      </div>
    </div>

    <Modal v-if="detail" title="🗺️ Detail Log Perjalanan" @close="detail = null">
      <div class="row" style="margin-bottom:10px;">
        <span class="badge" :class="(STATUS[detail.master?.status] || STATUS.pending)[1]">{{ (STATUS[detail.master?.status] || STATUS.pending)[0] }}</span>
        <span class="muted">{{ detail.master?.display_id }}</span>
      </div>
      <p class="muted" style="font-size:12px;margin-bottom:10px;">
        Driver: <b style="color:var(--text);">{{ detail.master?.driver_name }}</b> ·
        Tanggal: <b style="color:var(--text);">{{ detail.master?.trip_date }}</b> ·
        KM: {{ detail.master?.km_awal }} → {{ detail.master?.km_akhir }}
      </p>
      <div class="table-wrap" style="margin-bottom:14px;">
        <table class="tbl">
          <thead><tr><th>#</th><th>Dari</th><th>Ke</th><th>Jam</th><th>KM</th><th>Appointment</th></tr></thead>
          <tbody>
            <tr v-for="(d, i) in (detail.details || [])" :key="i">
              <td>{{ i + 1 }}</td><td>{{ d.lokasi_berangkat }}</td><td>{{ d.lokasi_tujuan }}</td>
              <td>{{ d.pukul_berangkat }} – {{ d.pukul_tujuan }}</td>
              <td>{{ d.km_berangkat }} → {{ d.km_tujuan }}</td>
              <td><span v-if="d.appointment_display" class="badge badge-purple">📅 {{ d.appointment_display }} · {{ d.appointment_nasabah }}</span></td>
            </tr>
          </tbody>
        </table>
      </div>
      <div v-if="canVerify && detail.master?.status === 'pending'" class="row">
        <button class="btn btn-success" :disabled="busy" @click="act(detail.master.id, 'verify')">✅ Verify</button>
        <input class="input grow" v-model="rejectReason" placeholder="Alasan penolakan (wajib)" />
        <button class="btn btn-danger" :disabled="busy" @click="act(detail.master.id, 'reject')">❌ Reject</button>
      </div>
    </Modal>
  </div>
</template>
