<script setup>
import { onMounted, ref } from 'vue'
import { api } from '../../api'
import StatCard from '../../components/StatCard.vue'

const list = ref([])
const stats = ref(null)
const lastSync = ref('')
const loading = ref(true)
const err = ref('')
const msg = ref('')
const syncing = ref(false)

// Filter
const f = ref({ date_from: '', date_to: '', search: '' })

async function load() {
  loading.value = true; err.value = ''
  try {
    const d = await api('/api/receptionist/inout', { params: { ...f.value } })
    list.value = d.data || []
    stats.value = d.stats || null
    lastSync.value = d.last_sync || ''
  } catch (e) { err.value = e.message }
  finally { loading.value = false }
}

async function doSync() {
  syncing.value = true; msg.value = ''
  try {
    const r = await api('/api/receptionist/sync/inout', { method: 'POST' })
    msg.value = '✅ ' + (r.summary || `${r.replaced ?? 0} baris tersinkron`)
    load()
  } catch (e) { msg.value = '❌ ' + e.message }
  finally { syncing.value = false }
}

function fmtWaktu(w) {
  return (w || '').slice(0, 16) || '—'
}

onMounted(load)
</script>

<template>
  <div>
    <div class="card card-pad" style="margin-bottom:16px;">
      <div class="row" style="flex-wrap:wrap;gap:10px;align-items:flex-end;">
        <div class="field" style="margin:0;"><label>Dari Tanggal</label>
          <input class="input" type="date" v-model="f.date_from" @change="load" /></div>
        <div class="field" style="margin:0;"><label>Sampai Tanggal</label>
          <input class="input" type="date" v-model="f.date_to" @change="load" /></div>
        <div class="field" style="margin:0;flex:1;min-width:180px;"><label>🔍 Cari (nama/jabatan/keterangan)</label>
          <input class="input" v-model="f.search" placeholder="Ketik lalu Enter…" @keyup.enter="load" /></div>
        <button class="btn" @click="load">🔍 Cari</button>
        <div class="spacer"></div>
        <button class="btn btn-primary" :disabled="syncing" @click="doSync" title="Tarik data terbaru dari Google Sheet In-Out Karyawan">
          {{ syncing ? '⏳ Menyinkronkan…' : '🔄 Sync Google Sheet' }}
        </button>
      </div>
      <div v-if="msg" class="alert" :class="msg.startsWith('✅') ? 'alert-success' : 'alert-error'" style="margin-top:10px;">{{ msg }}</div>
      <div v-if="lastSync" class="muted" style="font-size:11px;margin-top:8px;">Sinkron terakhir: {{ lastSync }}</div>
    </div>

    <div v-if="loading" class="empty skeleton">⏳ Memuat…</div>
    <div v-else-if="err" class="alert alert-error">{{ err }}</div>
    <template v-else>
      <div class="stat-grid" style="margin-bottom:16px;">
        <StatCard icon="📋" label="Total Catatan" :value="stats?.total ?? 0" color="#2563eb" />
        <StatCard icon="🚶" label="Masih di Luar" :value="stats?.out_now ?? 0" color="#d97706" />
        <StatCard icon="📤" label="Pergi Hari Ini" :value="stats?.pergi_today ?? 0" color="#0891b2" />
        <StatCard icon="📥" label="Datang Hari Ini" :value="stats?.datang_today ?? 0" color="#059669" />
      </div>

      <div class="card">
        <div class="table-wrap">
          <table class="tbl">
            <thead>
              <tr><th>Nama</th><th>Jabatan/Posisi</th><th>Pergi</th><th>Waktu Pergi</th><th>Datang</th><th>Waktu Datang</th><th>Keterangan</th></tr>
            </thead>
            <tbody>
              <tr v-for="r in list" :key="r.id">
                <td><b>{{ r.nama || '—' }}</b></td>
                <td>{{ r.jabatan || '—' }}</td>
                <td><span class="badge" :class="r.pergi ? 'badge-green' : 'badge-gray'">{{ r.pergi ? '✅' : '—' }}</span></td>
                <td style="font-size:12px;">{{ fmtWaktu(r.waktu_pergi) }}</td>
                <td><span class="badge" :class="r.datang ? 'badge-green' : 'badge-gray'">{{ r.datang ? '✅' : '—' }}</span></td>
                <td style="font-size:12px;">{{ fmtWaktu(r.waktu_datang) }}</td>
                <td>{{ r.keterangan || '—' }}</td>
              </tr>
              <tr v-if="!list.length"><td colspan="7" class="empty">Belum ada data. Tekan "🔄 Sync Google Sheet" untuk menarik data.</td></tr>
            </tbody>
          </table>
        </div>
      </div>
    </template>
  </div>
</template>
