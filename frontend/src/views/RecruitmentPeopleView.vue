<script setup>
/** Data Rekrutment — satu daftar orang berbasis NIK (Rilis C). */
import { computed, onMounted, ref, watch } from 'vue'
import { api } from '../api'
import { useAuthStore } from '../stores/auth'
import RecruitmentPersonDetail from './RecruitmentPersonDetail.vue'

const props = defineProps({
  embedded: { type: Boolean, default: false },
  view: { type: String, default: '' },
})
const auth = useAuthStore()
const role = computed(() => auth?.role || '')
const readOnly = computed(() => role.value === 'finance')

const q = ref('')
const branchCode = ref('')
const stage = ref('')
const status = ref('')
const link = ref('')
const rows = ref([])
const error = ref('')
const loading = ref(false)
const selected = ref(null)

async function load() {
  loading.value = true
  error.value = ''
  const params = {}
  if (q.value) params.q = q.value
  if (branchCode.value) params.branch_code = branchCode.value
  if (stage.value) params.stage = stage.value
  if (status.value) params.status = status.value
  if (link.value) params.link = link.value
  if (props.view || readOnly.value) params.view = props.view || 'firstwork'
  try {
    const res = await api('/api/recruitment/people', { params })
    rows.value = res?.data || []
  } catch (e) {
    error.value = e?.message || 'Data tidak dapat dimuat.'
  } finally {
    loading.value = false
  }
}

onMounted(load)
watch([q, branchCode, stage, status, link], () => { load() })

function label(row) {
  return row.nama || row.display_id || 'Tanpa nama'
}

function open(row) {
  if (!row.case_id) {
    selected.value = { case_id: null, display_id: row.display_id,
                       nama: row.nama, nik_masked: row.nik_masked }
    return
  }
  selected.value = row
}
</script>

<template>
  <section class="card card-pad rp-people">
    <header class="rp-head">
      <h3>Data Rekrutment</h3>
      <div class="rp-tools">
        <button v-if="role === 'receptionist' && !readOnly" type="button" class="btn btn-sm">Sync Sheet</button>
        <button type="button" class="btn btn-sm">Ekspor {{ readOnly ? 'FirstWork' : 'Data' }}</button>
        <button v-if="role === 'admin'" type="button" class="btn btn-sm">Pengaturan-user</button>
      </div>
    </header>

    <div class="rp-filters">
      <input v-model="q" aria-label="Cari nama atau NIK" placeholder="Cari nama atau NIK" />
      <input v-model="branchCode" aria-label="Cabang" placeholder="Cabang" />
      <select v-model="stage" aria-label="Tahap">
        <option value="">Semua tahap</option>
        <option>CV</option><option>TRAINING</option><option>TKD</option><option>FIRSTWORK</option>
      </select>
      <label><input v-model="link" type="checkbox" value="unlinked" /> Belum tertaut</label>
    </div>

    <p v-if="error" class="rp-error" role="alert">{{ error }}</p>

    <table class="rp-table">
      <thead><tr><th>Nama</th><th>NIK</th><th>Cabang</th><th>Tahap</th><th>Status</th><th>Kejadian terakhir</th></tr></thead>
      <tbody>
        <tr v-for="row in rows" :key="row.case_id || row.display_id"
            tabindex="0" @click="open(row)" @keydown.enter="open(row)">
          <td>{{ label(row) }}</td>
          <td>{{ row.nik_masked || '—' }}</td>
          <td>{{ row.branch_code }}</td>
          <td>{{ row.stage }}</td>
          <td>{{ row.status }}</td>
          <td>{{ row.last_event || '—' }}</td>
        </tr>
      </tbody>
    </table>
    <p v-if="!loading && !rows.length" class="rp-empty">Belum ada data. Mulai dari CV Online atau tautkan NIK pelamar lama.</p>

    <RecruitmentPersonDetail v-if="selected" :person="selected" :read-only="readOnly"
                             @close="selected = null" @saved="load" />
  </section>
</template>

<style scoped>
.rp-head { display: flex; justify-content: space-between; align-items: center; gap: 8px; }
.rp-tools { display: flex; gap: 6px; flex-wrap: wrap; }
.rp-filters { display: flex; gap: 8px; flex-wrap: wrap; margin: 12px 0; }
.rp-filters input, .rp-filters select { padding: 6px 8px; border: 1px solid var(--border); border-radius: 6px; }
.rp-table { width: 100%; border-collapse: collapse; font-size: 13px; }
.rp-table th, .rp-table td { text-align: left; padding: 8px; border-bottom: 1px solid var(--border); }
.rp-table tbody tr { cursor: pointer; }
.rp-table tbody tr:hover { background: var(--bg-soft); }
.rp-error { color: var(--danger); }
.rp-empty { color: var(--muted); padding: 12px 0; }
</style>
