<script setup>
import { onMounted, ref, watch } from 'vue'
import { useDriverStore } from '../../stores/driverStore'
import { api } from '../../api'
import ConfirmDialog from '../../components/ConfirmDialog.vue'

const confirmRef = ref(null)
const ask = (message, opts) => confirmRef.value?.open(message, opts) ?? Promise.resolve(false)

const store = useDriverStore()
const emit = defineEmits(['toast', 'switchTab'])
// refresh naik setiap tab Kasbon dibuka (tab tetap ter-mount karena v-show).
const props = defineProps({ refresh: { type: Number, default: 0 } })

const baseAmount = ref(0)
const submitting = ref(false)
const history = ref([])
const pendingLpj = ref([])
const loading = ref(false)

const totalAmount = () => (Number(baseAmount.value) || 0) + (Number(store.dailyCode) || 0)

const STEPS = ['DRAFT', 'GA_APPROVED', 'FINANCE_APPROVED', 'FUNDS_WITH_DRIVER', 'LPJ_SUBMITTED', 'COMPLETED']
const STEP_ICON = { DRAFT: '📝', GA_APPROVED: '✅', FINANCE_APPROVED: '💰', FUNDS_WITH_DRIVER: '🤝', LPJ_SUBMITTED: '📋', COMPLETED: '🎉', REJECTED: '❌' }

async function loadData() {
  loading.value = true
  try {
    const [h, p] = await Promise.all([
      api('/api/cash/history', { params: { driver: store.driverName } }),
      api('/api/cash/pending-lpj', { params: { driver: store.driverName } }),
    ])
    history.value = Array.isArray(h) ? h : []
    pendingLpj.value = Array.isArray(p) ? p : []
  } catch {
    emit('toast', '❌ Gagal memuat data kasbon', 'error')
  } finally { loading.value = false }
}

async function submit() {
  const base = Number(baseAmount.value) || 0
  if (base <= 0) { emit('toast', '⚠️ Isi nominal dulu', 'error'); return }
  const total = totalAmount()
  if (!(await ask(`Ajukan dana sebesar Rp ${total.toLocaleString('id-ID')}?\n\nNominal ini sudah termasuk kode unik hari ini.`, { confirmText: 'Ya, lanjutkan' }))) return
  submitting.value = true
  try {
    const j = await api('/api/cash/request', {
      method: 'POST',
      body: {
        driver_name: store.driverName,
        nopol: store.profile?.nopol || '',
        vehicle_type: store.profile?.vehicle_type || 'AVANZA',
        bbm_type: store.profile?.bbm_type || 'PERTALITE',
        base_amount: base,
      },
    })
    if (j.status === 'success') {
      emit('toast', `✅ ${j.msg || 'Pengajuan berhasil'}`, 'success')
      baseAmount.value = 0
      loadData()
    } else {
      emit('toast', '❌ ' + (j.msg || 'Gagal'), 'error')
    }
  } catch (e) { emit('toast', '❌ ' + (e.message || 'Gagal'), 'error') }
  finally { submitting.value = false }
}

async function removeCash(id) {
  if (!(await ask('Hapus pengajuan ini?', { confirmText: 'Ya, lanjutkan', danger: true }))) return
  try {
    await api(`/api/cash/delete/${id}`, { method: 'POST' })
    emit('toast', '✅ Pengajuan dihapus', 'success')
    loadData()
  } catch (e) { emit('toast', '❌ ' + (e.message || 'Gagal'), 'error') }
}

function openLpj(c) {
  store.setActiveLpj({
    cashId: c.id,
    display_id: c.display_id,
    total_amount: Number(c.total_amount) || 0,
    nopol: c.nopol || '',
    bbm_type: c.bbm_type || 'PERTALITE',
  })
  emit('switchTab', 'bbm')
  emit('toast', `📋 Isi LPJ untuk ${c.display_id} di tab BBM`, 'success')
}

function progress(c) {
  if (c.status === 'COMPLETED') return 100
  if (c.status === 'REJECTED') return 0
  const idx = STEPS.indexOf(c.status)
  return idx < 0 ? 0 : Math.round((idx / (STEPS.length - 1)) * 100)
}

function barColor(c) {
  if (c.status === 'COMPLETED') return 'var(--success)'
  const p = progress(c)
  return p >= 60 ? 'var(--primary)' : p >= 30 ? 'var(--warning)' : '#94a3b8'
}

watch(() => props.refresh, () => loadData())
onMounted(loadData)
</script>

<template>
  <div class="tab-page">
    <div class="alert" style="display:flex;justify-content:space-between;align-items:center;margin-bottom:10px;">
      <span>
        <b>Kode Unik Hari Ini:</b> Rp {{ (store.dailyCode ?? 0).toLocaleString('id-ID') }}
      </span>
      <span class="muted" style="font-size:11px;">{{ store.dailyMode === 'manual' ? '🔒 Ditentukan Finance' : '🤖 Otomatis' }}</span>
    </div>

    <form class="driver-form" @submit.prevent="submit">
      <div class="field"><label>Driver</label><input class="input" :value="store.driverName" disabled /></div>
      <div class="field"><label>Nopol</label><input class="input" :value="store.profile?.nopol || ''" disabled /></div>
      <div class="field"><label>Nominal Dasar (Rp)</label>
        <input class="input" type="number" v-model.number="baseAmount" min="0" placeholder="0" />
      </div>
      <div class="alert" style="padding:6px 10px;font-size:12px;">💰 Total yang diajukan: <b>Rp {{ totalAmount().toLocaleString('id-ID') }}</b> <span class="muted">(termasuk kode unik)</span></div>
      <button class="btn btn-primary" style="width:100%;justify-content:center;padding:12px;" :disabled="submitting">
        {{ submitting ? '⏳ Mengirim…' : '💰 Ajukan Kasbon' }}
      </button>
    </form>

    <h4 style="margin:14px 0 6px;">📋 Perlu Isi LPJ ({{ pendingLpj.length }})</h4>
    <div v-if="loading" class="muted skeleton" style="font-size:12px;">⏳ Memuat…</div>
    <div v-else-if="!pendingLpj.length" class="muted" style="font-size:12px;">Tidak ada LPJ pending. 🎉</div>
    <div v-for="c in pendingLpj" :key="c.id" class="lpj-card">
      <strong>{{ c.display_id }}</strong> · Rp {{ Number(c.total_amount).toLocaleString('id-ID') }}
      <div class="muted" style="font-size:11px;">Kode: {{ c.daily_code }}</div>
      <button class="btn btn-sm btn-primary" style="margin-top:6px;" @click="openLpj(c)">📝 Isi LPJ</button>
    </div>

    <h4 style="margin:14px 0 6px;">🕐 Riwayat Pengajuan</h4>
    <div v-if="loading" class="muted skeleton" style="font-size:12px;">⏳ Memuat…</div>
    <div v-else-if="!history.length" class="muted" style="font-size:12px;">Belum ada pengajuan.</div>
    <div v-for="c in history.slice(0, 10)" :key="c.id" class="hist-card">
      <template v-if="c.status === 'REJECTED'">
        <div class="row">
          <b>{{ c.display_id }}</b>
          <span class="muted" style="font-size:11px;">Rp {{ Number(c.total_amount).toLocaleString('id-ID') }}</span>
          <div class="spacer"></div>
          <span class="badge badge-red">❌ Ditolak</span>
        </div>
        <div class="muted" style="font-size:11px;">{{ c.rejection_reason || '' }}</div>
      </template>
      <template v-else>
        <div class="row" style="margin-bottom:4px;">
          <b>{{ c.display_id }}</b>
          <span class="muted" style="font-size:11px;">Rp {{ Number(c.total_amount).toLocaleString('id-ID') }}</span>
          <div class="spacer"></div>
          <button v-if="c.status === 'DRAFT'" class="btn-icon" title="Hapus" @click="removeCash(c.id)">🗑</button>
        </div>
        <div class="bar"><div class="bar-fill" :style="{ width: progress(c) + '%', background: barColor(c) }"></div></div>
        <div class="row" style="justify-content:space-between;margin-top:3px;font-size:9px;opacity:.7;">
          <span v-for="s in STEPS" :key="s" :style="{ color: STEPS.indexOf(s) <= STEPS.indexOf(c.status) ? barColor(c) : undefined }">
            {{ STEP_ICON[s] }}
          </span>
        </div>
        <div class="muted" style="font-size:9px;text-align:center;margin-top:2px;">📝 Draft → ✅ GA → 💰 Finance → 🤝 Serah → 📋 LPJ → 🎉 Done</div>
      </template>
    </div>
    <ConfirmDialog ref="confirmRef" />
  </div>
</template>

<style scoped>
.lpj-card { background: var(--bg-2, #fef3c7); padding: 10px; border-radius: 8px; margin-bottom: 6px; border-left: 4px solid var(--warning); font-size: 12px; }
.hist-card { background: var(--surface); border: 1px solid var(--border); padding: 10px; border-radius: 8px; margin-bottom: 6px; font-size: 12px; }
.bar { background: var(--border, #e2e8f0); border-radius: 4px; height: 6px; overflow: hidden; }
.bar-fill { height: 100%; border-radius: 4px; transition: width .5s; }
</style>
