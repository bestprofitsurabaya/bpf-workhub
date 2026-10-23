<script setup>
import { onMounted, ref, computed } from 'vue'
import { api } from '../../api'
import StatCard from '../../components/StatCard.vue'
import PageHeader from '../../components/PageHeader.vue'
import LoadingState from '../../components/LoadingState.vue'
import ErrorState from '../../components/ErrorState.vue'

const list = ref([])
const stats = ref(null)
const meta = ref({ uplines: [], users: [], statuses: [], user_options: [] })
const loading = ref(true)
const err = ref('')
const scopeUpline = ref('')

const f = ref({ date_from: '', date_to: '', upline: '', user: '', status: '', search: '' })

const STAGES = ['interview', 'training_1', 'training_2', 'training_3', 'training_4']
const STAGE_SHORT = { interview: 'I', training_1: 'H1', training_2: 'H2', training_3: 'H3', training_4: 'H4' }
const STATUS_BADGE = {
  interview: 'badge-blue', training_1: 'badge-cyan', training_2: 'badge-green',
  training_3: 'badge-purple', training_4: 'badge-orange', lulus: 'badge-green',
  resigned: 'badge-gray', rejected: 'badge-red',
}
const STATUS_LABELS = {
  interview: '📅 Interview', training_1: '📘 H1', training_2: '📗 H2',
  training_3: '📙 H3', training_4: '📕 H4', lulus: '🎓 Lulus',
  resigned: '🚪 Mengundurkan Diri', rejected: '✕ Ditolak',
}

async function load() {
  loading.value = true; err.value = ''
  try {
    const d = await api('/api/applicants', { params: { ...f.value } })
    list.value = d.data || []
    stats.value = d.stats || null
    scopeUpline.value = d.scope_upline || ''
  } catch (e) { err.value = e.message }
  finally { loading.value = false }
}

async function loadMeta() {
  try { meta.value = await api('/api/applicants/meta') } catch { meta.value = { uplines: [], users: [], statuses: [], user_options: [] } }
}

const badge = (s) => STATUS_BADGE[s] || 'badge-gray'
const attended = (a, stage) => !!(a.attendance && a.attendance[stage] && a.attendance[stage].attended_at)

const inTraining = computed(() =>
  (stats.value?.training_1 ?? 0) + (stats.value?.training_2 ?? 0) +
  (stats.value?.training_3 ?? 0) + (stats.value?.training_4 ?? 0))

onMounted(() => { load(); loadMeta() })
</script>

<template>
  <div>
    <PageHeader icon="🎯" title="Rekrutan Saya (Traineer)" subtitle="Pantau kehadiran orang yang Anda rekrut — interview & 4 hari training.">
      <span v-if="scopeUpline" class="badge badge-orange">Upline: {{ scopeUpline }}</span>
    </PageHeader>
    <div class="card card-pad" style="margin-bottom:16px;">
      <div class="row" style="flex-wrap:wrap;gap:10px;align-items:flex-end;margin-top:12px;">
        <div class="field" style="margin:0;"><label>Dari Tanggal</label>
          <input class="input" type="date" v-model="f.date_from" @change="load" /></div>
        <div class="field" style="margin:0;"><label>Sampai Tanggal</label>
          <input class="input" type="date" v-model="f.date_to" @change="load" /></div>
        <div class="field" style="margin:0;"><label>Upline</label>
          <select class="select" v-model="f.upline" @change="load" style="min-width:140px;">
            <option value="">Semua</option>
            <option v-for="u in meta.uplines" :key="u" :value="u">{{ u }}</option>
          </select></div>
        <div class="field" style="margin:0;"><label>User</label>
          <select class="select" v-model="f.user" @change="load" style="min-width:120px;">
            <option value="">Semua</option>
            <option v-for="u in meta.user_options" :key="u.id" :value="u.name">{{ u.name }}</option>
          </select></div>
        <div class="field" style="margin:0;"><label>Status</label>
          <select class="select" v-model="f.status" @change="load" style="min-width:140px;">
            <option value="">Semua status</option>
            <option v-for="s in meta.statuses" :key="s.value" :value="s.value">{{ s.label }}</option>
          </select></div>
        <div class="field" style="margin:0;flex:1;min-width:180px;"><label>🔍 Cari</label>
          <input class="input" v-model="f.search" placeholder="Nama / HP / posisi…" @keyup.enter="load" /></div>
        <button class="btn" @click="load">🔍 Cari</button>
        <button class="btn" @click="f = { date_from: '', date_to: '', upline: '', user: '', status: '', search: '' }; load()">✖ Reset</button>
      </div>
    </div>

    <div v-if="loading"><LoadingState :rows="5" label="Memuat rekrutan…" /></div>
    <div v-else-if="err"><ErrorState :message="err" @retry="load" /></div>
    <template v-else>
      <div class="stat-grid" style="margin-bottom:16px;">
        <StatCard icon="👥" label="Total Rekrutan" :value="stats?.total ?? list.length" color="#2563eb" />
        <StatCard icon="📅" label="Interview" :value="stats?.interview ?? 0" color="#d97706" />
        <StatCard icon="📘" label="Dalam Training" :value="inTraining" color="#7c3aed" />
        <StatCard icon="🎓" label="Lulus" :value="stats?.lulus ?? 0" color="#059669" />
        <StatCard icon="🚪" label="Mundur" :value="stats?.resigned ?? 0" color="#dc2626" />
      </div>

      <div class="card">
        <div class="table-wrap">
          <table class="tbl">
            <thead>
              <tr><th>Pelamar</th><th>Posisi</th><th>User</th><th>Interview</th><th>Kehadiran</th><th>Status</th></tr>
            </thead>
            <tbody>
              <tr v-for="a in list" :key="a.id">
                <td>
                  <b>{{ a.nama_lengkap }}</b>
                  <div class="muted" style="font-size:11px;">{{ a.display_id }} · {{ a.no_hp || '—' }}</div>
                  <div v-if="a.upline" class="muted" style="font-size:10px;color:#b45309;">⬆ {{ a.upline }}</div>
                </td>
                <td>{{ a.posisi || '—' }}</td>
                <td>{{ a.user_field || '—' }}</td>
                <td style="font-size:11px;">{{ (a.interview_at || '').slice(0, 16) }}</td>
                <td>
                  <div class="att-row">
                    <span v-for="s in STAGES" :key="s" class="att-chip" :class="attended(a, s) ? 'att-on' : ''"
                          :title="s + (attended(a, s) ? ' · ' + a.attendance[s].attended_at : ' — belum')">
                      {{ STAGE_SHORT[s] }}
                    </span>
                  </div>
                </td>
                <td><span class="badge" :class="badge(a.status)">{{ STATUS_LABELS[a.status] || a.status }}</span></td>
              </tr>
              <tr v-if="!list.length"><td colspan="6" class="empty">Belum ada rekrutan dengan filter ini.</td></tr>
            </tbody>
          </table>
        </div>
      </div>
    </template>
  </div>
</template>

<style scoped>
.att-row { display: flex; gap: 3px; }
.att-chip {
  min-width: 22px; height: 20px; padding: 0 4px; border-radius: 6px; font-size: 10px; font-weight: 700;
  display: inline-flex; align-items: center; justify-content: center;
  background: var(--bg); border: 1px solid var(--border); color: var(--text-3);
}
.att-chip.att-on { background: #059669; border-color: #059669; color: #fff; }
</style>
