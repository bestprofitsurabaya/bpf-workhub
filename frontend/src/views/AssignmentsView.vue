<script setup>
import { onMounted, ref } from 'vue'
import { api } from '../api'
import LoadingState from '../components/LoadingState.vue'
import ErrorState from '../components/ErrorState.vue'
import PageHeader from '../components/PageHeader.vue'

const active = ref([])
const unassigned = ref([])
const drivers = ref([])
const loading = ref(true)
const err = ref('')
const msg = ref('')
const form = ref({ nopol: '', driver_name: '' })
const releaseForm = ref({ nopol: '', reason: '' })
const busy = ref(false)

async function load() {
  loading.value = true; err.value = ''
  try {
    const [a, u, d] = await Promise.all([
      api('/api/assignments/active').catch(() => []),
      api('/api/assignments/unassigned').catch(() => []),
      api('/api/drivers').catch(() => []),
    ])
    active.value = Array.isArray(a) ? a : []
    unassigned.value = Array.isArray(u) ? u : []
    drivers.value = Array.isArray(d) ? d : []
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
    const r = await api('/api/assignments/release', { method: 'POST', body: { nopol: releaseForm.value.nopol, reason: releaseForm.value.reason || 'Dilepas' } })
    msg.value = '✅ ' + (r.msg || 'Kendaraan dilepas'); releaseForm.value = { nopol: '', reason: '' }; load()
  } catch (e) { msg.value = '❌ ' + e.message }
  finally { busy.value = false }
}

onMounted(load)
</script>

<template>
  <div>
    <PageHeader icon="🚗" title="Penugasan Driver" subtitle="Assign & lepas kendaraan ke driver aktif" />
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
      </div>
    </div>

    <div v-if="loading"><LoadingState :rows="4" label="Memuat penugasan…" /></div>
    <div v-else-if="err"><ErrorState :message="err" @retry="load" /></div>
    <div class="card" v-else>
      <div class="table-wrap">
        <table class="tbl">
          <thead><tr><th>Driver</th><th>Nopol</th><th>Tipe</th><th>BBM</th><th>Status</th></tr></thead>
          <tbody>
            <tr v-for="a in active" :key="a.id || a.nopol">
              <td><b>{{ a.driver_name }}</b></td>
              <td>{{ a.nopol }}</td>
              <td>{{ a.vehicle_type }}</td>
              <td>{{ a.bbm_type }}</td>
              <td><span class="badge badge-blue">🚗 Aktif</span></td>
            </tr>
            <tr v-if="!active.length"><td colspan="5" class="empty">Tidak ada penugasan aktif.</td></tr>
          </tbody>
        </table>
      </div>
    </div>
  </div>
</template>
