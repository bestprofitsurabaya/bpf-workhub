<script setup>
import { nextTick, onBeforeUnmount, onMounted, ref } from 'vue'
import { Chart, registerables } from 'chart.js'
import { api } from '../api'
import LoadingState from '../components/LoadingState.vue'
import ErrorState from '../components/ErrorState.vue'
import PageHeader from '../components/PageHeader.vue'

Chart.register(...registerables)

const today = new Date().toISOString().slice(0, 10)
const start = ref(new Date(Date.now() - 30 * 864e5).toISOString().slice(0, 10))
const end = ref(today)
const d = ref(null)
const loading = ref(true)
const err = ref('')
const cMonthly = ref(null)
const cFreq = ref(null)
const cEff = ref(null)
let ch1 = null
let ch2 = null
let ch3 = null

// Fleet Health
const vehicleHealth = ref(null)
const vehicleHealthLoading = ref(false)

async function loadVehicleHealth() {
  vehicleHealthLoading.value = true
  try { vehicleHealth.value = await api('/api/vehicle-health') } catch { vehicleHealth.value = null }
  finally { vehicleHealthLoading.value = false }
}

const fmt = (n) => 'Rp ' + Number(n || 0).toLocaleString('id-ID')
const num = (n) => Number(n || 0).toLocaleString('id-ID')
const axis = () => (document.documentElement.classList.contains('dark') ? '#94a3b8' : '#64748b')

function drawChart(canvas, type, labels, values, color, label) {
  if (!canvas) return null
  return new Chart(canvas, {
    type,
    data: {
      labels: labels || [],
      datasets: [{
        label, data: values || [],
        borderColor: color,
        backgroundColor: type === 'line' ? color + '26' : color + '59',
        fill: type === 'line', tension: .35, borderRadius: 6, pointRadius: 3,
      }],
    },
    options: {
      responsive: true, maintainAspectRatio: false,
      plugins: { legend: { labels: { color: axis(), boxWidth: 12 } } },
      scales: {
        x: { ticks: { color: axis(), maxTicksLimit: 10 }, grid: { color: axis() + '22' } },
        y: { ticks: { color: axis(), callback: (v) => (v >= 1e6 ? (v / 1e6).toFixed(1) + 'jt' : v >= 1e3 ? (v / 1e3).toFixed(0) + 'rb' : v) }, grid: { color: axis() + '22' } },
      },
    },
  })
}

function draw() {
  ;[ch1, ch2, ch3].forEach((c) => c && c.destroy())
  const fin = d.value?.finance || {}
  const ga = d.value?.ga || {}
  const fl = d.value?.fleet || {}
  ch1 = drawChart(cMonthly.value, 'line', fin.monthly_labels, fin.monthly_amounts, '#2563eb', 'Nominal (Rp)')
  ch2 = drawChart(cFreq.value, 'bar', ga.freq_labels, ga.freq_values, '#8b5cf6', 'Jumlah transaksi')
  ch3 = drawChart(cEff.value, 'bar', fl.eff_labels, fl.eff_values, '#059669', 'Efisiensi (km/liter)')
}

async function load() {
  loading.value = true; err.value = ''
  try {
    d.value = await api('/api/analytics/data', { params: { start_date: start.value, end_date: end.value } })
  } catch (e) { err.value = e.message }
  finally {
    loading.value = false
    nextTick(draw)
    loadVehicleHealth()
  }
}

onMounted(load)
onBeforeUnmount(() => { [ch1, ch2, ch3].forEach((c) => c && c.destroy()) })
</script>

<template>
  <div>
    <PageHeader icon="📈" title="Analytics" subtitle="Tren keuangan, cabang, dan pemakaian BBM" />
    <div class="card card-pad" style="margin-bottom:16px;">
      <div class="row">
        <div class="field" style="margin:0;"><label>Dari</label><input class="input" type="date" v-model="start" /></div>
        <div class="field" style="margin:0;"><label>Sampai</label><input class="input" type="date" v-model="end" /></div>
        <button class="btn btn-primary" @click="load" style="margin-top:18px;">📈 Tampilkan</button>
      </div>
    </div>

    <div v-if="loading"><LoadingState :rows="4" label="Memuat analitik…" /></div>
    <div v-else-if="err"><ErrorState :message="err" @retry="load" /></div>
    <template v-else>
      <!-- Finance -->
      <div class="stat-grid" style="margin-bottom:16px;">
        <div class="stat-card"><div class="s-icon" style="background:#2563eb1a;">💵</div><div class="s-value" style="color:#2563eb;">{{ fmt(d?.finance?.total_month) }}</div><div class="s-label">Total Nominal (Periode)</div><div class="s-bar" style="background:#2563eb;"></div></div>
        <div class="stat-card"><div class="s-icon" style="background:#0596691a;">🧾</div><div class="s-value" style="color:#059669;">{{ num(d?.finance?.total_tx) }}</div><div class="s-label">Jumlah Transaksi</div><div class="s-bar" style="background:#059669;"></div></div>
        <div class="stat-card"><div class="s-icon" style="background:#d977061a;">📅</div><div class="s-value" style="color:#d97706;">{{ fmt(d?.finance?.avg_per_day) }}</div><div class="s-label">Rata-rata / Hari</div><div class="s-bar" style="background:#d97706;"></div></div>
        <div class="stat-card"><div class="s-icon" style="background:#8b5cf61a;">🎯</div><div class="s-value" style="color:#8b5cf6;">{{ fmt(d?.finance?.avg_per_tx) }}</div><div class="s-label">Rata-rata / Transaksi</div><div class="s-bar" style="background:#8b5cf6;"></div></div>
      </div>

      <!-- GA + Cash + Fleet -->
      <div class="stat-grid" style="margin-bottom:16px;">
        <div class="stat-card"><div class="s-icon" style="background:#0ea5e91a;">👥</div><div class="s-value" style="color:#0ea5e9;">{{ num(d?.ga?.total_drivers) }}</div><div class="s-label">Driver Aktif</div><div class="s-bar" style="background:#0ea5e9;"></div></div>
        <div class="stat-card"><div class="s-icon" style="background:#ef44441a;">📬</div><div class="s-value" style="color:#ef4444;">{{ num(d?.ga?.total_claims) }}</div><div class="s-label">Total Klaim</div><div class="s-bar" style="background:#ef4444;"></div></div>
        <div class="stat-card"><div class="s-icon" style="background:#84cc161a;">📅</div><div class="s-value" style="color:#65a30d;">{{ num(d?.ga?.total_appt) }}</div><div class="s-label">Total Appointment</div><div class="s-bar" style="background:#65a30d;"></div></div>
        <div class="stat-card"><div class="s-icon" style="background:#f973161a;">🏆</div><div class="s-value" style="color:#f97316;font-size:14px;">{{ d?.ga?.top_driver || '—' }}</div><div class="s-label">Driver Teratas</div><div class="s-bar" style="background:#f97316;"></div></div>
        <div class="stat-card"><div class="s-icon" style="background:#10b9811a;">💳</div><div class="s-value" style="color:#10b981;">{{ num(d?.cash?.total) }}</div><div class="s-label">Kasbon Selesai (LPJ)</div><div class="s-bar" style="background:#10b981;"></div></div>
        <div class="stat-card"><div class="s-icon" style="background:#ec48991a;">🚀</div><div class="s-value" style="color:#ec4899;font-size:14px;">{{ d?.fleet?.best_vehicle || '—' }}</div><div class="s-label">Kendaraan Paling Efisien</div><div class="s-bar" style="background:#ec4899;"></div></div>
        <div class="stat-card"><div class="s-icon" style="background:#64748b1a;">⛽</div><div class="s-value" style="color:#64748b;">{{ d?.fleet?.avg_kml || 0 }}</div><div class="s-label">Rata-rata Efisiensi (km/L)</div><div class="s-bar" style="background:#64748b;"></div></div>
      </div>

      <div class="card card-pad" style="margin-bottom:16px;">
        <h3 style="margin:0 0 12px;">📈 Tren Nominal Bulanan</h3>
        <div style="height:240px;"><canvas ref="cMonthly"></canvas></div>
      </div>

      <div class="stat-grid" style="margin-bottom:16px;">
        <div class="card card-pad">
          <h3 style="margin:0 0 12px;">📊 Frekuensi Transaksi per Driver</h3>
          <div style="height:220px;"><canvas ref="cFreq"></canvas></div>
        </div>
        <div class="card card-pad">
          <h3 style="margin:0 0 12px;">⛽ Efisiensi per Kendaraan</h3>
          <div style="height:220px;"><canvas ref="cEff"></canvas></div>
        </div>
      </div>

      <!-- Fleet Health -->
      <div v-if="vehicleHealth" class="card card-pad" style="margin-bottom:16px;">
        <div class="row" style="align-items:center;gap:12px;margin-bottom:12px;">
          <h3 style="margin:0;">🚗 Fleet Health</h3>
          <span class="muted" style="font-size:12px;">Skor kesehatan kendaraan berdasarkan efisiensi &amp; aktivitas</span>
          <div class="spacer"></div>
          <span class="badge badge-blue">{{ vehicleHealth.total_active_units }} unit</span>
          <span class="badge" :class="vehicleHealth.avg_fleet_health >= 70 ? 'badge-green' : vehicleHealth.avg_fleet_health >= 40 ? 'badge-amber' : 'badge-red'">Avg: {{ vehicleHealth.avg_fleet_health }}/100</span>
        </div>
        <div class="table-wrap">
          <table class="tbl">
            <thead><tr><th>Nopol</th><th>Kendaraan</th><th>Driver</th><th>Avg KM/L</th><th>Transaksi</th><th>Nominal</th><th>Health</th><th>Status</th></tr></thead>
            <tbody>
              <tr v-for="u in (vehicleHealth.units || [])" :key="u.nopol">
                <td><b>{{ u.nopol }}</b></td>
                <td>{{ u.vehicle_type }}</td>
                <td>{{ u.current_driver || '—' }}</td>
                <td>{{ u.avg_kml || 0 }}</td>
                <td>{{ num(u.total_tx) }}</td>
                <td>{{ fmt(u.total_nominal) }}</td>
                <td><b :style="{ color: u.health_score >= 70 ? '#059669' : u.health_score >= 40 ? '#d97706' : '#dc2626' }">{{ u.health_score }}</b>/100</td>
                <td><span class="badge" :class="u.status === 'good' ? 'badge-green' : u.status === 'warning' ? 'badge-amber' : 'badge-red'">{{ u.status === 'good' ? '✅ Baik' : u.status === 'warning' ? '⚠️ Warning' : '🔴 Danger' }}</span></td>
              </tr>
              <tr v-if="!(vehicleHealth.units || []).length"><td colspan="8" class="empty">Tidak ada data kendaraan.</td></tr>
            </tbody>
          </table>
        </div>
      </div>

      <div class="card">
        <h3 style="padding:14px 18px 0;">🏅 Top 5 Driver (Nominal)</h3>
        <div class="table-wrap">
          <table class="tbl">
            <thead><tr><th>#</th><th>Driver</th><th>Nopol</th><th>Nominal</th><th>Transaksi</th></tr></thead>
            <tbody>
              <tr v-for="(t, i) in (d?.finance?.top_drivers || [])" :key="i">
                <td><b>{{ i + 1 }}</b></td>
                <td>{{ t.driver_name }}</td>
                <td>{{ t.nopol }}</td>
                <td>{{ fmt(t.total) }}</td>
                <td>{{ num(t.tx_count) }}</td>
              </tr>
              <tr v-if="!(d?.finance?.top_drivers || []).length"><td colspan="5" class="empty">Tidak ada data pada rentang tanggal ini.</td></tr>
            </tbody>
          </table>
        </div>
      </div>
    </template>
  </div>
</template>
