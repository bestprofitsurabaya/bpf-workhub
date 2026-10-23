<script setup>
import { ref, onMounted } from 'vue'
import { api } from '../../api'
import StatCard from '../../components/StatCard.vue'
import PageHeader from '../../components/PageHeader.vue'

const from = ref('')
const to = ref('')
const loading = ref(true)
const data = ref(null)

const fmtRp = (n) => 'Rp ' + (Number(n) || 0).toLocaleString('id-ID')
const fmtNum = (n) => (Number(n) || 0).toLocaleString('id-ID')

// v2.53.0: Klaim BBM — pintasan pekerjaan utama Finance (restrukturisasi UI)
const bbm = ref({ ready: 0, confirm: 0 })
const arrLen = (v) => (Array.isArray(v) ? v.length : 0)
async function loadBbm() {
  try {
    const [finQ, drvQ] = await Promise.all([
      api('/api/queue', { params: { tab: 'finance' } }).catch(() => null),
      api('/api/queue', { params: { tab: 'driver_confirm' } }).catch(() => null),
    ])
    bbm.value = { ready: arrLen(finQ), confirm: arrLen(drvQ) }
  } catch { bbm.value = { ready: 0, confirm: 0 } }
}

function buildQuery() {
  const q = new URLSearchParams()
  if (from.value) q.set('from', from.value)
  if (to.value) q.set('to', to.value)
  const s = q.toString()
  return s ? '?' + s : ''
}

async function load() {
  loading.value = true
  try {
    data.value = await api('/api/water/recap' + buildQuery())
  } catch {
    data.value = null
  } finally {
    loading.value = false
  }
}

function exportCsv() {
  window.location.href = '/api/water/recap/export' + buildQuery()
}

function statusBadge(s) {
  return (
    { pending: ['⏳', 'badge-amber'], verified: ['✅', 'badge-blue'], rejected: ['✕', 'badge-gray'] }[s] || [s, 'badge-gray']
  )
}

onMounted(() => { load(); loadBbm() })
</script>

<template>
  <div class="page">
    <!-- Header + filter (v2.54.0: PageHeader standar) -->
    <PageHeader icon="💰" title="Dashboard Finance" subtitle="Rekap air minum & pekerjaan yang menunggu Anda">
      <label class="ph-filter">Dari
        <input v-model="from" type="date" class="inp" />
      </label>
      <label class="ph-filter">Sampai
        <input v-model="to" type="date" class="inp" />
      </label>
      <button class="btn btn-primary" @click="load">🔍 Terapkan</button>
      <button class="btn" @click="exportCsv" title="Unduh rekap sebagai CSV">⬇️ Export CSV</button>
    </PageHeader>

    <div v-if="loading" class="card card-pad muted skeleton">Memuat…</div>
    <template v-else-if="data">
      <!-- v2.53.0/v2.54.0: Klaim BBM — pintasan pekerjaan utama Finance -->
      <div class="card card-pad attention-card" data-testid="bbm-quick">
        <div class="ac-icon">⛽</div>
        <div class="grow">
          <div class="ac-title">Klaim BBM menunggu keputusan Anda</div>
          <div class="ac-sub" style="user-select:text;">
            <b :style="bbm.ready ? 'color:var(--warning);' : ''">{{ bbm.ready }}</b> klaim terverifikasi GA siap dicairkan
            <template v-if="bbm.confirm"> · <b>{{ bbm.confirm }}</b> menunggu konfirmasi driver / arsip</template>
            — verifikasi Subsidi Tepat (riwayat SPBU resmi) langsung dari modal detail.
          </div>
        </div>
        <router-link to="/dashboard" class="btn btn-primary" style="text-decoration:none;">🕐 Buka Antrean Verifikasi</router-link>
      </div>

      <!-- Statistik air minum -->
      <div class="stat-grid" style="margin-bottom:16px;">
        <StatCard icon="📄" label="Total Pengajuan" :value="fmtNum(data.summary.total)" color="#2563eb" />
        <StatCard icon="⏳" label="Menunggu Verifikasi" :value="fmtNum(data.summary.pending)" color="#d97706" />
        <StatCard icon="✅" label="Terverifikasi" :value="fmtNum(data.summary.verified)" color="#059669" />
        <StatCard icon="✕" label="Ditolak" :value="fmtNum(data.summary.rejected)" color="#dc2626" />
        <StatCard icon="🚰" label="Total Kuantitas" :value="fmtNum(data.summary.qty)" color="#0d9488" />
      </div>

      <!-- Kasbon menunggu Finance -->
      <div class="stat-grid" style="margin-bottom:16px;">
        <StatCard icon="💵" label="Kasbon Menunggu Approve" :value="fmtRp(data.kasbon.waiting_approve.nominal)" color="#059669" :sub="data.kasbon.waiting_approve.count + ' pengajuan'" />
        <StatCard icon="🧾" label="LPJ Menunggu Approve" :value="fmtNum(data.kasbon.waiting_lpj.count) + ' pengajuan'" color="#7c3aed" sub="link ke halaman Kasbon" />
        <div class="stat-card">
          <span class="s-icon" style="background:#0d94881a;">🚰</span>
          <div class="s-value" style="color:#0d9488;">{{ data.per_ob.length }} OB</div>
          <div class="s-label">OB Aktif</div>
          <div class="s-bar" style="background:#0d9488;"></div>
        </div>
      </div>

      <div class="row" style="align-items:flex-start;gap:16px;margin-bottom:16px;">
        <!-- Antrean verifikasi -->
        <div class="card card-pad grow">
          <h3 style="margin-top:0;">🛡 Antrean Verifikasi Air Minum</h3>
          <table class="table">
            <thead><tr><th>Nomor</th><th>OB</th><th>Tanggal</th><th>Item</th><th></th></tr></thead>
            <tbody>
              <tr v-for="q in data.queue" :key="q.id">
                <td>{{ q.display_id }}</td>
                <td>{{ q.ob_name }}</td>
                <td>{{ q.purchase_date }}</td>
                <td>{{ q.item_count }}</td>
                <td><router-link class="btn btn-sm" to="/water">Verifikasi →</router-link></td>
              </tr>
              <tr v-if="!data.queue.length"><td colspan="5" class="muted">Tidak ada pengajuan menunggu verifikasi 🎉</td></tr>
            </tbody>
          </table>
          <div class="muted" style="font-size:11px;margin-top:8px;">
            {{ data.summary.pending }} pengajuan menunggu — verifikasi di halaman <router-link to="/water">Air Minum</router-link>
          </div>
        </div>

        <!-- Per OB -->
        <div class="card card-pad" style="min-width:320px;">
          <h3 style="margin-top:0;">👥 Ringkasan per OB</h3>
          <table class="table">
            <thead><tr><th>OB</th><th>Total</th><th>⏳</th><th>✅</th><th>✕</th></tr></thead>
            <tbody>
              <tr v-for="o in data.per_ob" :key="o.ob_name">
                <td>{{ o.ob_name }}</td>
                <td>{{ o.total }}</td>
                <td class="muted">{{ o.pending }}</td>
                <td class="muted">{{ o.verified }}</td>
                <td class="muted">{{ o.rejected }}</td>
              </tr>
              <tr v-if="!data.per_ob.length"><td colspan="5" class="muted">Belum ada pengajuan</td></tr>
            </tbody>
          </table>
        </div>
      </div>

      <div class="row" style="align-items:flex-start;gap:16px;">
        <!-- Per jenis -->
        <div class="card card-pad grow">
          <h3 style="margin-top:0;">🥤 Per Jenis</h3>
          <div v-for="t in data.per_type" :key="t.name" class="bar-row">
            <span class="bar-label">{{ t.name }} — {{ fmtNum(t.qty) }} unit ({{ t.purchases }} pengajuan)</span>
            <div class="bar-track"><div class="bar-fill" :style="{ width: Math.min(100, t.qty / Math.max(1, data.per_type[0].qty) * 100) + '%' }"></div></div>
          </div>
          <div v-if="!data.per_type.length" class="muted">Belum ada data</div>
        </div>
        <!-- Per merk -->
        <div class="card card-pad grow">
          <h3 style="margin-top:0;">🏷️ Per Merk</h3>
          <div v-for="b in data.per_brand" :key="b.name" class="bar-row">
            <span class="bar-label">{{ b.name }} — {{ fmtNum(b.qty) }} unit ({{ b.purchases }} pengajuan)</span>
            <div class="bar-track"><div class="bar-fill" style="background:#0d9488;" :style="{ width: Math.min(100, b.qty / Math.max(1, data.per_brand[0].qty) * 100) + '%' }"></div></div>
          </div>
          <div v-if="!data.per_brand.length" class="muted">Belum ada data</div>
        </div>
      </div>
    </template>
    <div v-else class="card card-pad muted">Gagal memuat data.</div>
  </div>
</template>

<style scoped>
.row { display: flex; flex-wrap: wrap; }
.grow { flex: 1; min-width: 280px; }
.inp { padding: 6px 10px; border: 1px solid var(--border, #e2e8f0); border-radius: 8px; background: var(--card, #fff); color: var(--text, #0f172a); }
.table { width: 100%; border-collapse: collapse; font-size: 13px; }
.table th, .table td { text-align: left; padding: 7px 8px; border-bottom: 1px solid var(--border, #e2e8f0); }
.bar-row { margin-bottom: 8px; }
.bar-label { font-size: 12px; display: block; margin-bottom: 3px; }
.bar-track { height: 8px; background: var(--border, #e2e8f0); border-radius: 6px; overflow: hidden; }
.bar-fill { height: 100%; background: #2563eb; border-radius: 6px; transition: width .3s; }
.btn-sm { padding: 4px 10px; font-size: 12px; }
</style>
