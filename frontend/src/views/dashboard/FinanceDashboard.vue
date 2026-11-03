<script setup>
import { computed, onMounted, ref } from 'vue'
import { api } from '../../api'
import { useAuthStore } from '../../stores/auth'
import StatCard from '../../components/StatCard.vue'
import PageHeader from '../../components/PageHeader.vue'
import { formatDate } from '../../utils/format.js'

// Dashboard Finance = menu bar dua tab: Ringkasan kerja + rekap Air Minum.
// Klaim BBM, kasbon, dan Data SPBU tetap satu tempat di /cash.
const auth = useAuthStore()
const loading = ref(true)
const badges = ref(null)
const activeTab = ref('ringkasan')

const waterFrom = ref('')
const waterTo = ref('')
const waterLoading = ref(false)
const waterError = ref('')
const water = ref(null)

const greeting = computed(() => {
  const hour = new Date().getHours()
  const salutation = hour < 11 ? 'pagi' : hour < 15 ? 'siang' : hour < 18 ? 'sore' : 'malam'
  return `Selamat ${salutation}, ${auth.meta?.label || auth.user?.full_name || 'Finance'}`
})
const branchName = computed(() => auth.user?.branch_name || 'kantor cabang')
const priorities = computed(() => [
  { icon: '⛽', label: 'Klaim BBM siap dicairkan', key: 'bbm_verify_pending', color: '#d97706', to: '/cash?tab=bbm' },
  { icon: '💵', label: 'Kasbon menunggu Finance', key: 'cash_pending', color: '#059669', to: '/cash?tab=kasbon' },
  { icon: '📋', label: 'Klaim menunggu LPJ', key: 'finance_pending', color: '#7c3aed', to: '/cash?tab=kasbon' },
  { icon: '🚰', label: 'Air minum menunggu', key: 'water_pending', color: '#0d9488', to: '/water' },
])

const fmtRp = (n) => 'Rp ' + (Number(n) || 0).toLocaleString('id-ID')
const fmtNum = (n) => (Number(n) || 0).toLocaleString('id-ID')
const fmtDate = (d) => (d ? formatDate(d) : '—')

function buildWaterQuery() {
  const q = new URLSearchParams()
  if (waterFrom.value) q.set('from', waterFrom.value)
  if (waterTo.value) q.set('to', waterTo.value)
  const s = q.toString()
  return s ? '?' + s : ''
}

async function loadBadges() {
  loading.value = true
  try {
    const data = await api('/api/nav/badges')
    badges.value = data?.badges || {}
  } catch {
    badges.value = null
  } finally {
    loading.value = false
  }
}

async function loadWater() {
  waterLoading.value = true
  waterError.value = ''
  try {
    water.value = await api('/api/water/recap' + buildWaterQuery())
  } catch (e) {
    waterError.value = e.message || 'Gagal memuat rekap air minum'
    water.value = null
  } finally {
    waterLoading.value = false
  }
}

function switchTab(tab) {
  activeTab.value = tab
  if (tab === 'water' && !water.value && !waterLoading.value) loadWater()
}

function exportCsv() {
  window.location.href = '/api/water/recap/export' + buildWaterQuery()
}

onMounted(loadBadges)
</script>

<template>
  <div class="page finance-dashboard">
    <PageHeader icon="💰" title="Dashboard Finance" :subtitle="`Ringkasan kerja · ${branchName}`" />

    <nav class="workspace-tabs" role="tablist" aria-label="Menu Dashboard Finance">
      <button type="button" role="tab" :aria-selected="activeTab === 'ringkasan'" :class="{ active: activeTab === 'ringkasan' }"
              data-testid="finance-tab-ringkasan" @click="switchTab('ringkasan')">
        <span class="workspace-tab-icon" aria-hidden="true">📊</span>
        <span class="workspace-tab-text">Ringkasan<small>Prioritas kerja hari ini</small></span>
      </button>
      <button type="button" role="tab" :aria-selected="activeTab === 'water'" :class="{ active: activeTab === 'water' }"
              data-testid="finance-tab-water" @click="switchTab('water')">
        <span class="workspace-tab-icon" aria-hidden="true">🚰</span>
        <span class="workspace-tab-text">Air Minum<small>Rekap &amp; antrean verifikasi</small></span>
        <span v-if="badges" class="workspace-tab-count">{{ badges.water_pending || 0 }}</span>
      </button>
    </nav>

    <!-- Tab 1 — ringkasan kerja: sapaan, prioritas, dan pintasan modul. -->
    <section v-if="activeTab === 'ringkasan'" class="workspace-section" aria-label="Ringkasan kerja Finance">
      <section class="welcome-card" data-testid="finance-welcome">
        <div>
          <p class="eyebrow">OVERVIEW KANTOR CABANG</p>
          <h2>{{ greeting }}</h2>
          <p class="muted">Berikut prioritas kerja kantor cabang {{ branchName }} hari ini.</p>
        </div>
      </section>

      <h2 class="section-title">Ringkasan prioritas</h2>
      <div v-if="loading" class="priority-grid" aria-label="Memuat ringkasan">
        <div v-for="item in priorities" :key="item.key" class="stat-card skeleton">Memuat…</div>
      </div>
      <div v-else-if="badges" class="priority-grid" data-testid="finance-priorities">
        <router-link v-for="item in priorities" :key="item.key" :to="item.to" class="priority-link"
                     :data-testid="'priority-' + item.key">
          <StatCard :icon="item.icon" :label="item.label"
                    :value="Number(badges[item.key] || 0).toLocaleString('id-ID')" :color="item.color" />
        </router-link>
      </div>
      <div v-else class="card card-pad muted" role="status">Ringkasan antrean belum dapat dimuat.</div>

      <div class="quick-grid">
        <router-link class="quick-card" to="/cash" data-testid="bbm-workspace-link">
          <span class="quick-icon" aria-hidden="true">⛽</span>
          <div class="grow">
            <b>BBM, Kasbon &amp; SPBU</b>
            <p>Klaim BBM, pencairan, kasbon/LPJ, Data SPBU, dan akses OTP.</p>
          </div>
          <span class="quick-arrow" aria-hidden="true">→</span>
        </router-link>
        <router-link class="quick-card" to="/water" data-testid="water-workspace-link">
          <span class="quick-icon" aria-hidden="true">🚰</span>
          <div class="grow">
            <b>Air Minum</b>
            <p>Verifikasi pengajuan OB dan kelola master merk.</p>
          </div>
          <span class="quick-arrow" aria-hidden="true">→</span>
        </router-link>
      </div>
    </section>

    <!-- Tab 2 — rekap air minum: filter, statistik, antrean, dan sebaran. -->
    <section v-else class="workspace-section" aria-label="Rekap Air Minum">
      <div v-if="waterLoading" class="card card-pad muted skeleton">Memuat rekap air minum…</div>
      <div v-else-if="waterError" class="card card-pad">
        <p class="alert alert-error" style="margin-bottom:10px;">{{ waterError }}</p>
        <button class="btn btn-primary" @click="loadWater">🔄 Coba lagi</button>
      </div>
      <template v-else-if="water">
        <div class="card card-pad" style="margin-bottom:16px;" data-testid="water-section-heading">
          <div class="workspace-toolbar">
            <div class="field">
              <label>Dari</label>
              <input v-model="waterFrom" type="date" class="input" />
            </div>
            <div class="field">
              <label>Sampai</label>
              <input v-model="waterTo" type="date" class="input" />
            </div>
            <button class="btn btn-primary" @click="loadWater">🔍 Terapkan</button>
            <button class="btn" @click="exportCsv" title="Unduh rekap air minum sebagai CSV">⬇️ Export CSV</button>
            <span class="muted" style="font-size:11px;margin-left:auto;">
              Rekap mengikuti rentang tanggal yang dipilih.
            </span>
          </div>
        </div>

        <div class="stat-grid" style="margin-bottom:16px;">
          <StatCard icon="📄" label="Total Pengajuan" :value="fmtNum(water.summary.total)" color="#2563eb" />
          <StatCard icon="⏳" label="Menunggu Verifikasi" :value="fmtNum(water.summary.pending)" color="#d97706" />
          <StatCard icon="✅" label="Terverifikasi" :value="fmtNum(water.summary.verified)" color="#059669" />
          <StatCard icon="✕" label="Ditolak" :value="fmtNum(water.summary.rejected)" color="#dc2626" />
          <StatCard icon="🚰" label="Total Kuantitas" :value="fmtNum(water.summary.qty)" color="#0d9488" />
        </div>

        <div class="row water-split" style="align-items:flex-start;margin-bottom:16px;">
          <div class="card card-pad grow">
            <h3 style="margin-top:0;">🛡 Antrean Verifikasi Air Minum</h3>
            <div class="table-wrap">
              <table class="table">
                <thead><tr><th>Nomor</th><th>OB</th><th>Tanggal</th><th>Item</th><th></th></tr></thead>
                <tbody>
                  <tr v-for="q in water.queue" :key="q.id">
                    <td>{{ q.display_id }}</td>
                    <td>{{ q.ob_name }}</td>
                    <td>{{ fmtDate(q.purchase_date) }}</td>
                    <td>{{ q.item_count }}</td>
                    <td><router-link class="btn btn-sm" to="/water">Verifikasi →</router-link></td>
                  </tr>
                  <tr v-if="!water.queue.length"><td colspan="5" class="muted">Tidak ada pengajuan menunggu verifikasi 🎉</td></tr>
                </tbody>
              </table>
            </div>
            <div class="muted" style="font-size:11px;margin-top:8px;">
              {{ water.summary.pending }} pengajuan menunggu — verifikasi di halaman <router-link to="/water">Air Minum</router-link>
            </div>
          </div>

          <div class="card card-pad water-ob">
            <h3 style="margin-top:0;">👥 Ringkasan per OB</h3>
            <div class="table-wrap">
              <table class="table">
                <thead><tr><th>OB</th><th>Total</th><th>⏳</th><th>✅</th><th>✕</th></tr></thead>
                <tbody>
                  <tr v-for="o in water.per_ob" :key="o.ob_name">
                    <td>{{ o.ob_name }}</td>
                    <td>{{ o.total }}</td>
                    <td class="muted">{{ o.pending }}</td>
                    <td class="muted">{{ o.verified }}</td>
                    <td class="muted">{{ o.rejected }}</td>
                  </tr>
                  <tr v-if="!water.per_ob.length"><td colspan="5" class="muted">Belum ada pengajuan</td></tr>
                </tbody>
              </table>
            </div>
          </div>
        </div>

        <div class="row water-split" style="align-items:flex-start;">
          <div class="card card-pad grow">
            <h3 style="margin-top:0;">🥤 Per Jenis</h3>
            <div v-for="t in water.per_type" :key="t.name" class="bar-row">
              <span class="bar-label">{{ t.name }} — {{ fmtNum(t.qty) }} unit ({{ t.purchases }} pengajuan)</span>
              <div class="bar-track"><div class="bar-fill" :style="{ width: Math.min(100, t.qty / Math.max(1, water.per_type[0].qty) * 100) + '%' }"></div></div>
            </div>
            <div v-if="!water.per_type.length" class="muted">Belum ada data</div>
          </div>
          <div class="card card-pad grow">
            <h3 style="margin-top:0;">🏷️ Per Merk</h3>
            <div v-for="b in water.per_brand" :key="b.name" class="bar-row">
              <span class="bar-label">{{ b.name }} — {{ fmtNum(b.qty) }} unit ({{ b.purchases }} pengajuan)</span>
              <div class="bar-track"><div class="bar-fill" style="background:#0d9488;" :style="{ width: Math.min(100, b.qty / Math.max(1, water.per_brand[0].qty) * 100) + '%' }"></div></div>
            </div>
            <div v-if="!water.per_brand.length" class="muted">Belum ada data</div>
          </div>
        </div>
      </template>
      <div v-else class="card card-pad muted">Gagal memuat data.</div>
    </section>
  </div>
</template>

<style scoped>
.finance-dashboard { display: grid; gap: 16px; }
.finance-dashboard .workspace-tabs { margin-bottom: 0; }
.welcome-card {
  padding: 22px 24px; border: 1px solid var(--border); border-radius: var(--radius);
  background:
    radial-gradient(120% 160% at 100% 0%, color-mix(in srgb, var(--primary) 9%, transparent), transparent 55%),
    var(--surface);
  box-shadow: var(--shadow);
}
.welcome-card h2 { margin: 0 0 6px; font-size: clamp(20px, 3vw, 26px); }
.welcome-card p { margin: 0; }
.welcome-card .eyebrow { margin-bottom: 7px; color: var(--primary); font-size: 10px; font-weight: 800; letter-spacing: .1em; }
.section-title { margin: 2px 0 -4px; font-size: 16px; }
.priority-grid { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 12px; }
.priority-link { display: block; color: inherit; text-decoration: none; height: 100%; }
.priority-link .stat-card { height: 100%; }
.quick-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 12px; }
.quick-card {
  display: flex; align-items: center; gap: 14px; padding: 16px 18px;
  background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius);
  box-shadow: var(--shadow); color: inherit; text-decoration: none;
  transition: transform .15s, box-shadow .15s, border-color .15s;
}
.quick-card:hover { transform: translateY(-2px); box-shadow: var(--shadow-lg); border-color: color-mix(in srgb, var(--primary) 35%, var(--border)); }
.quick-icon { font-size: 22px; width: 44px; height: 44px; display: inline-grid; place-items: center; border-radius: 12px; background: var(--primary-soft); flex-shrink: 0; }
.quick-card b { font-size: 14px; }
.quick-card p { margin: 3px 0 0; font-size: 12px; color: var(--text-3); }
.quick-arrow { color: var(--primary); font-weight: 800; }
.water-split { display: flex; gap: 16px; flex-wrap: wrap; }
.water-ob { min-width: 320px; }
.bar-row { margin-bottom: 8px; }
.bar-label { font-size: 12px; display: block; margin-bottom: 3px; }
.bar-track { height: 8px; background: var(--border); border-radius: 6px; overflow: hidden; }
.bar-fill { height: 100%; background: var(--primary); border-radius: 6px; transition: width .3s; }
.table { width: 100%; border-collapse: collapse; font-size: 13px; }
.table th, .table td { text-align: left; padding: 7px 8px; border-bottom: 1px solid var(--border); }
.table th { font-size: 11px; text-transform: uppercase; letter-spacing: .05em; color: var(--text-3); background: var(--surface-2); }
.table tbody tr:last-child td { border-bottom: none; }
@media (max-width: 900px) {
  .priority-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .quick-grid { grid-template-columns: 1fr; }
}
@media (max-width: 600px) {
  .welcome-card { padding: 18px; }
  .priority-grid { gap: 9px; }
  .water-ob { min-width: 100%; }
}
</style>
