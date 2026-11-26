<script setup>
/** Master karyawan (Rilis D) — cari nama/NIK, catat keluar/masuk, detail HR. */
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { api } from '../api'
import { useAuthStore } from '../stores/auth'

const route = useRoute()
const auth = useAuthStore()
const role = computed(() => auth?.role || '')
const isHr = computed(() => ['ga_hr', 'admin'].includes(role.value))
const archive = computed(() => String(route.query.archive || '') === '1')

const q = ref('')
const branchCode = ref('')
const active = ref('')
const rows = ref([])
const error = ref('')
const loading = ref(false)
const selected = ref(null)
const detail = ref(null)
const reason = ref('')

async function load() {
  loading.value = true
  error.value = ''
  const params = {}
  if (q.value) params.q = q.value
  if (active.value !== '') params.active = active.value
  if (branchCode.value && isHr.value) params.branch_code = branchCode.value
  try {
    const res = await api('/api/employees', { params })
    rows.value = res?.data || []
    if (selected.value?.id) await openDetail(selected.value.id)
  } catch (e) {
    error.value = e?.message || 'Data karyawan tidak dapat dimuat.'
  } finally {
    loading.value = false
  }
}

async function openDetail(id) {
  selected.value = rows.value.find((r) => r.id === id) || selected.value
  try {
    detail.value = (await api(`/api/employees/${id}`))?.data || null
  } catch { detail.value = null }
}

async function attendance(id, direction) {
  try {
    await api(`/api/employees/${id}/attendance`, {
      method: 'POST', body: { direction, note: '' },
    })
    await load()
  } catch (e) {
    error.value = e?.message || 'Absensi gagal.'
  }
}

async function hrAction(path, body = {}) {
  if (!selected.value) return
  try {
    await api(path, { method: 'POST', body })
    reason.value = ''
    await load()
  } catch (e) {
    error.value = e?.message || 'Aksi gagal.'
  }
}

onMounted(load)
watch([q, branchCode, active], load)
</script>

<template>
  <section class="card card-pad emp-page">
    <div v-if="archive" class="emp-archive">Arsip In-Out lama — data read-only.</div>
    <header class="emp-head">
      <h3>Karyawan</h3>
      <div class="emp-tools">
        <input v-model="q" aria-label="Cari nama atau NIK" placeholder="Cari nama atau NIK" />
        <input v-if="isHr" v-model="branchCode" aria-label="Cabang" placeholder="Cabang" />
        <select v-model="active" aria-label="Status aktif">
          <option value="">Semua status</option>
          <option value="1">Aktif</option><option value="0">Nonaktif</option>
        </select>
        <a v-if="isHr" class="btn btn-sm" href="/api/employees/export.csv">Ekspor CSV</a>
      </div>
    </header>
    <p v-if="error" class="emp-error" role="alert">{{ error }}</p>

    <table class="emp-table">
      <thead><tr><th>Nama</th><th>NIK</th><th>Jabatan</th><th>Cabang</th>
        <th>Status</th><th>Aksi</th></tr></thead>
      <tbody>
        <tr v-for="row in rows" :key="row.id">
          <td>{{ row.nama }}</td>
          <td>{{ row.nik_masked || row.nik || '—' }}</td>
          <td>{{ row.jabatan }}</td>
          <td>{{ row.branch_code }}</td>
          <td>{{ row.status === 'OUT' ? 'Di Luar' : 'Di Kantor' }}</td>
          <td v-if="!archive">
            <button type="button" class="btn btn-sm" data-action="out"
                    @click="attendance(row.id, 'OUT')">Keluar</button>
            <button type="button" class="btn btn-sm" data-action="in"
                    @click="attendance(row.id, 'IN')">Kembali</button>
            <button type="button" class="btn btn-sm" :data-detail="row.id"
                    @click="openDetail(row.id)">Detail</button>
          </td>
        </tr>
      </tbody>
    </table>
    <p v-if="!loading && !rows.length" class="emp-empty">Belum ada karyawan.</p>

    <aside v-if="detail && !archive" class="emp-detail" aria-label="Detail karyawan">
      <header><h4>{{ detail.nama }}</h4>
        <button type="button" class="btn btn-sm" @click="detail = null">Tutup</button></header>
      <p v-if="detail.needs_nik" class="emp-warning">NIK legacy belum dilengkapi GA HR.</p>
      <p>Employee No: {{ detail.employee_no }}</p>
      <p v-if="isHr">NIK: {{ detail.nik || detail.nik_masked }}</p>
      <ol class="emp-events">
        <li v-for="event in detail.events || []" :key="event.id">
          {{ event.event_at }} — {{ event.direction }}
          <span v-if="event.voided_at">(dikoreksi)</span>
        </li>
      </ol>
      <div v-if="isHr" class="emp-hr">
        <input v-model="reason" aria-label="Alasan" placeholder="Alasan (wajib untuk pulang/void)" />
        <button type="button" class="btn btn-sm"
                @click="hrAction(`/api/employees/${selected.id}/deactivate`, { reason })">Nonaktifkan</button>
        <button type="button" class="btn btn-sm"
                @click="hrAction(`/api/employees/${selected.id}/reactivate`)">Aktifkan</button>
        <button type="button" class="btn btn-sm"
                @click="hrAction(`/api/employees/${selected.id}/attendance/1/void`, { reason })">Koreksi absensi</button>
      </div>
    </aside>
  </section>
</template>

<style scoped>
.emp-head { display: flex; justify-content: space-between; gap: 8px; flex-wrap: wrap; }
.emp-tools { display: flex; gap: 6px; flex-wrap: wrap; }
.emp-tools input, .emp-tools select, .emp-hr input {
  padding: 6px 8px; border: 1px solid var(--border); border-radius: 6px;
}
.emp-archive { padding: 8px; margin-bottom: 10px; background: var(--bg-soft); }
.emp-table { width: 100%; border-collapse: collapse; font-size: 13px; }
.emp-table th, .emp-table td { text-align: left; padding: 8px; border-bottom: 1px solid var(--border); }
.emp-detail { margin-top: 14px; padding: 12px; border: 1px solid var(--border); border-radius: 8px; }
.emp-detail header { display: flex; justify-content: space-between; }
.emp-events { font-size: 12px; color: var(--muted); }
.emp-hr { display: flex; gap: 6px; flex-wrap: wrap; margin-top: 8px; }
.emp-error { color: var(--danger); }
.emp-warning { color: var(--warning); }
.emp-empty { color: var(--muted); }
</style>
