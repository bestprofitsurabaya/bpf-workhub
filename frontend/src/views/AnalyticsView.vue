<script setup>
import { nextTick, onBeforeUnmount, onMounted, ref } from 'vue'
import { Chart, registerables } from 'chart.js'
import { api } from '../api'
import LoadingState from '../components/LoadingState.vue'
import ErrorState from '../components/ErrorState.vue'
import PageHeader from '../components/PageHeader.vue'
import ReportMeta from '../components/ReportMeta.vue'

Chart.register(...registerables)

function localISO(d) {
  const mm = String(d.getMonth() + 1).padStart(2, '0')
  const dd = String(d.getDate()).padStart(2, '0')
  return `${d.getFullYear()}-${mm}-${dd}`
}

const today = localISO(new Date())
const start = ref(localISO(new Date(Date.now() - 29 * 864e5)))
const end = ref(today)
const d = ref(null)
const loading = ref(true)
const err = ref('')
const notice = ref('')
const generatedAt = ref('')
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
  try {
    vehicleHealth.value = await api('/api/vehicle-health', {
      params: { start_date: start.value, end_date: end.value },
    })
  } catch { vehicleHealth.value = null }
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
      plugins: {
        legend: { labels: { color: axis(), boxWidth: 12 } },
        tooltip: {
          callbacks: {
            label: (ctx) => `${ctx.dataset.label}: ${type === 'bar' && label.includes('km') ? ctx.parsed.y + ' km/L' : fmt(ctx.parsed.y)}`,
          },
        },
      },
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
  ch2 = drawChart(cFreq.value, 'bar', ga.freq_labels, ga.freq_values, '#8b5cf6', 'Jumlah klaim')
  ch3 = drawChart(cEff.value, 'bar', fl.eff_labels, fl.eff_values, '#059669', 'km/liter')
}

async function load() {
  loading.value = true; err.value = ''; notice.value = ''
  try {
    d.value = await api('/api/analytics/data', { params: { start_date: start.value, end_date: end.value } })
    generatedAt.value = new Date().toLocaleString('id-ID')
  } catch (e) { err.value = e.message }
  finally {
    loading.value = false
    nextTick(draw)
    loadVehicleHealth()
  }
}

function preset(key) {
  const now = new Date()
  if (key === '7') start.value = localISO(new Date(Date.now() - 6 * 864e5))
  else if (key === '30') start.value = localISO(new Date(Date.now() - 29 * 864e5))
  else if (key === 'month') start.value = localISO(new Date(now.getFullYear(), now.getMonth(), 1))
  else if (key === 'year') start.value = `${now.getFullYear()}-01-01`
  end.value = today
  load()
}

function csvCell(v) {
  const s = String(v ?? '')
  return /[",\n;]/.test(s) ? '"' + s.replace(/"/g, '""') + '"' : s
}

function exportCsv() {
  notice.value = ''
  if (!d.value) { notice.value = 'Belum ada data untuk diekspor.'; return }
  const fin = d.value.finance || {}
  const lines = [
    ['Analisis BBM & Armada', `${start.value} s/d ${end.value}`].map(csvCell).join(','),
    ['Ringkasan', '', ''].map(csvCell).join(','),
    ['Total Nominal', 'Jumlah Klaim', 'Rata-rata/Hari', 'Rata-rata/Klaim'].map(csvCell).join(','),
    [fin.total_month, fin.total_tx, fin.avg_per_day, fin.avg_per_tx].map(csvCell).join(','),
    [''],
    ['Top 5 Driver (Nominal)', 'Nopol', 'Nominal', 'Transaksi'].map(csvCell).join(','),
    ...(fin.top_drivers || []).map((t) => [t.driver_name, t.nopol, t.total, t.tx_count].map(csvCell).join(',')),
    [''],
    ['Kendaraan', 'km/L'].map(csvCell).join(','),
    ...((d.value.fleet?.eff_labels || []).map((nopol, i) => [nopol, d.value.fleet.eff_values?.[i] ?? 0].map(csvCell).join(','))),
    [''],
    ['Fleet Health', 'Nopol', 'Kendaraan', 'Driver', 'km/L', 'Transaksi', 'Nominal', 'Skor', 'Status'].map(csvCell).join(','),
    ...((vehicleHealth.value?.units || []).map((u) => [
      '', u.nopol, u.vehicle_type, u.current_driver || '', u.avg_kml || 0,
      u.total_tx, u.total_nominal, u.health_score, u.status,
    ].map(csvCell).join(','))),
  ]
  const blob = new Blob(['\ufeff' + lines.join('\n')], { type: 'text/csv;charset=utf-8;' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `analisis_bbm_${start.value}_${end.value}.csv`
  a.click()
  URL.revokeObjectURL(url)
}

onMounted(load)
onBeforeUnmount(() => { [ch1, ch2, ch3].forEach((c) => c && c.destroy()) })
</script>

<template>
  <div>
    <PageHeader icon="📈" title="Analisis BBM & Armada" subtitle="Tren biaya, frekuensi klaim, efisiensi kendaraan, dan kesehatan armada" />

    <ReportMeta
      title="Analisis BBM & Armada"
      question="Bagaimana pola biaya BBM, siapa yang paling sering mengklaim, kendaraan mana yang efisien, dan unit mana yang perlu perhatian?"
      :period="`${start} s/d ${end}`"
      scope="Cabang aktif sesuai sesi login"
      source="transactions (archived), drivers, vehicle_assignments, fuel_cash_requests"
      basis="Klaim archived; kasbon COMPLETED pada handover_at; armada mengikuti periode"
      exclusions="Klaim pending/rejected dan data demo tidak dihitung"
      :generated-at="generatedAt"
      :rows="num(d?.finance?.total_tx || 0) + ' klaim'"
    />

    <div class="card card-pad" style="margin-bottom:16px;">
      <div class="row" style="flex-wrap:wrap;gap:8px;">
        <div class="field" style="margin:0;"><label>Dari</label><input class="input" type="date" v-model="start" /></div>
        <div class="field" style="margin:0;"><label>Sampai</label><input class="input" type="date" v-model="end" /></div>
        <button class="btn btn-primary" @click="load" style="margin-top:18px;">📈 Tampilkan</button>
        <div class="spacer"></div>
        <button class="btn" @click="exportCsv" style="margin-top:18px;">⬇️ CSV</button>
      </div>
      <div class="row" style="gap:6px;margin-top:10px;flex-wrap:wrap;">
        <span class="muted" style="font-size:11px;align-self:center;">Cepat:</span>
        <button class="btn btn-sm" @click="preset('7')">7 hari</button>
        <button class="btn btn-sm" @click="preset('30')">30 hari</button>
        <button class="btn btn-sm" @click="preset('month')">Bulan ini</button>
        <button class="btn btn-sm" @click="preset('year')">Tahun ini</button>
      </div>
    </div>

    <div v-if="notice" class="alert" style="margin-bottom:12px;">ℹ️ {{ notice }}</div>

    <div v-if="loading"><LoadingState :rows="4" label="Memuat analitik…" /></div>
    <div v-else-if="err"><ErrorState :message="err" @retry="load" /></div>
    <template v-else>
      <!-- Finance -->
      <div class="stat-grid" style="margin-bottom:16px;">
        <div class="stat-card"><div class="s-icon" style="background:#2563eb1a;">💵</div><div class="s-value" style="color:#2563eb;">{{ fmt(d?.finance?.total_month) }}</div><div class="s-label">Total Nominal (Periode)</div><div class="s-bar" style="background:#2563eb;"></div></div>
        <div class="stat-card"><div class="s-icon" style="background:#0596691a;">🧾</div><div class="s-value" style="color:#059669;">{{ num(d?.finance?.total_tx) }}</div><div class="s-label">Klaim Terarsip</div><div class="s-bar" style="background:#059669;"></div></div>
        <div class="stat-card"><div class="s-icon" style="background:#d977061a;">📅</div><div class="s-value" style="color:#d97706;">{{ fmt(d?.finance?.avg_per_day) }}</div><div class="s-label">Rata-rata / Hari ({{ d?.finance?.days || 30 }} hari)</div><div class="s-bar" style="background:#d97706;"></div></div>
        <div class="stat-card"><div class="s-icon" style="background:#8b5cf61a;">🎯</div><div class="s-value" style="color:#8b5cf6;">{{ fmt(d?.finance?.avg_per_tx) }}</div><div class="s-label">Rata-rata / Klaim</div><div class="s-bar" style="background:#8b5cf6;"></div></div>
      </div>

      <!-- GA + Cash + Fleet -->
      <div class="stat-grid" style="margin-bottom:16px;">
        <div class="stat-card"><div class="s-icon" style="background:#0ea5e91a;">👥</div><div class="s-value" style="color:#0ea5e9;">{{ num(d?.ga?.total_drivers) }}</div><div class="s-label">Driver Aktif (master)</div><div class="s-bar" style="background:#0ea5e9;"></div></div>
        <div class="stat-card"><div class="s-icon" style="background:#f973161a;">🏆</div><div class="s-value" style="color:#f97316;font-size:14px;">{{ d?.ga?.top_driver || '—' }}</div><div class="s-label">Driver Paling Sering Klaim</div><div class="s-bar" style="background:#f97316;"></div></div>
        <div class="stat-card"><div class="s-icon" style="background:#84cc161a;">📅</div><div class="s-value" style="color:#65a30d;">{{ num(d?.ga?.total_appt) }}</div><div class="s-label">Total Appointment</div><div class="s-bar" style="background:#65a30d;"></div></div>
        <div class="stat-card"><div class="s-icon" style="background:#10b9811a;">💳</div><div class="s-value" style="color:#10b981;">{{ fmt(d?.cash?.amount) }}</div><div class="s-label">Kasbon BBM Cair ({{ num(d?.cash?.total) }} pengajuan)</div><div class="s-bar" style="background:#10b981;"></div></div>
        <div class="stat-card"><div class="s-icon" style="background:#ec48991a;">🚀</div><div class="s-value" style="color:#ec4899;font-size:14px;">{{ d?.fleet?.best_vehicle || '—' }}</div><div class="s-label">Kendaraan Paling Efisien</div><div class="s-bar" style="background:#ec4899;"></div></div>
        <div class="stat-card"><div class="s-icon" style="background:#64748b1a;">⛽</div><div class="s-value" style="color:#64748b;">{{ d?.fleet?.avg_kml || 0 }}</div><div class="s-label">Rata-rata Efisiensi (km/L)</div><div class="s-bar" style="background:#64748b;"></div></div>
      </div>

      <div class="card card-pad" style="margin-bottom:16px;">
        <h3 style="margin:0 0 4px;">📈 Tren Nominal per Bulan</h3>
        <p class="muted" style="font-size:11px;margin:0 0 12px;">Hanya klaim berstatus archived pada periode terpilih.</p>
        <div style="height:240px;"><canvas ref="cMonthly"></canvas></div>
      </div>

      <div class="stat-grid" style="margin-bottom:16px;">
        <div class="card card-pad">
          <h3 style="margin:0 0 4px;">📊 Frekuensi Klaim per Driver (Top 5)</h3>
          <p class="muted" style="font-size:11px;margin:0 0 12px;">Diurutkan berdasarkan jumlah klaim, bukan nominal.</p>
          <div style="height:220px;"><canvas ref="cFreq"></canvas></div>
        </div>
        <div class="card card-pad">
          <h3 style="margin:0 0 4px;">⛽ Efisiensi per Kendaraan (periode)</h3>
          <p class="muted" style="font-size:11px;margin:0 0 12px;">Rata-rata km/L klaim archived pada periode terpilih.</p>
          <div style="height:220px;"><canvas ref="cEff"></canvas></div>
        </div>
      </div>

      <!-- Fleet Health -->
      <div v-if="vehicleHealth" class="card card-pad" style="margin-bottom:16px;">
        <div class="row" style="align-items:center;gap:12px;margin-bottom:8px;flex-wrap:wrap;">
          <h3 style="margin:0;">🚗 Fleet Health (periode)</h3>
          <span class="muted" style="font-size:12px;">Skor 0–100: 60% efisiensi + 20% kebaruan aktivitas + 20% volume</span>
          <div class="spacer"></div>
          <span class="badge badge-blue">{{ vehicleHealth.total_units_with_data ?? vehicleHealth.total_active_units }} unit dengan data</span>
          <span class="badge" :class="vehicleHealth.avg_fleet_health >= 70 ? 'badge-green' : vehicleHealth.avg_fleet_health >= 40 ? 'badge-amber' : 'badge-red'">Avg: {{ vehicleHealth.avg_fleet_health }}/100</span>
        </div>
        <p class="muted" style="font-size:11px;margin:0 0 10px;">km/L kosong dianggap 10. “Unit dengan data” = nopol yang punya klaim archived pada periode, bukan seluruh armada terdaftar.</p>
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
              <tr v-if="!(vehicleHealth.units || []).length"><td colspan="8" class="empty">Tidak ada klaim archived pada periode ini.</td></tr>
            </tbody>
          </table>
        </div>
      </div>
      <div v-else-if="vehicleHealthLoading" class="card card-pad muted" style="margin-bottom:16px;font-size:12px;">⏳ Memuat fleet health…</div>

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
