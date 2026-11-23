<script setup>
import { onMounted, ref, watch } from 'vue'
import { api } from '../../api'
import { useDriverStore } from '../../stores/driverStore'

const store = useDriverStore()
const emit = defineEmits(['toast'])

const keluhan = ref('')
const submitting = ref(false)
const history = ref([])
const lastSubmitted = ref('')

const driverName = () => store.driverDisplayName || store.driverName
const nopol = () => store.profile?.nopol || ''
const vehicleType = () => store.profile?.vehicle_type || ''
const kmKendaraan = () => Number(store.profile?.last_odo_km || store.profile?.initial_odo_km || 0)

async function loadHistory() {
  try {
    const d = await api('/api/driver/service')
    history.value = Array.isArray(d?.data) ? d.data : (Array.isArray(d) ? d : [])
  } catch {
    history.value = []
  }
}

async function submit() {
  const text = keluhan.value.trim()
  if (text.length < 5) {
    emit('toast', '⚠️ Catatan keluhan minimal 5 karakter', 'error')
    return
  }
  submitting.value = true
  try {
    const r = await api('/api/driver/service', {
      method: 'POST',
      body: {
        keluhan: text,
        nopol: nopol(),
        vehicle_type: vehicleType(),
        km_kendaraan: kmKendaraan(),
      },
    })
    emit('toast', `✅ ${r.msg || 'Catatan service terkirim ke GA'}`, 'success')
    lastSubmitted.value = r.display_id || ''
    keluhan.value = ''
    await loadHistory()
  } catch (e) {
    emit('toast', '❌ ' + (e.message || 'Gagal mengirim catatan service'), 'error')
  } finally {
    submitting.value = false
  }
}

watch(() => store.profile, () => { if (!nopol()) loadHistory() })
onMounted(loadHistory)
</script>

<template>
  <div class="tab-page">
    <h4 style="margin:0 0 6px;">🔧 Catatan Service Mobil</h4>
    <p class="muted" style="font-size:12px;margin:0 0 12px;">
      Sampaikan keluhan kondisi kendaraan. Catatan langsung masuk ke GA dan bisa dicetak sebagai dokumen resmi.
    </p>

    <form class="card card-pad" @submit.prevent="submit">
      <div class="svc-row"><span>Nama Driver</span><b>{{ driverName() }}</b></div>
      <div class="svc-row"><span>Nomor Polisi</span><b>{{ nopol() || '—' }}</b></div>
      <div class="svc-row"><span>Jenis Mobil</span><b>{{ vehicleType() || '—' }}</b></div>
      <div class="svc-row"><span>KM Kendaraan</span><b>{{ kmKendaraan().toLocaleString('id-ID') }} km</b></div>

      <label class="svc-label" for="svc-keluhan">Catatan Keluhan Kendaraan</label>
      <textarea id="svc-keluhan" v-model="keluhan" class="inp svc-area" rows="6"
                placeholder="Contoh: Rem depan berbunyi keras saat pengereman, AC kurang dingin, ban depan kanan cepat aus…"></textarea>
      <div class="muted" style="font-size:10px;text-align:right;">{{ keluhan.length }}/2000 karakter</div>

      <button class="btn btn-primary" style="width:100%;justify-content:center;margin-top:10px;"
              :disabled="submitting || !nopol()">
        {{ submitting ? '⏳ Mengirim…' : '📤 Kirim ke GA' }}
      </button>
      <p v-if="lastSubmitted" class="muted" style="font-size:11px;text-align:center;margin:8px 0 0;">
        Terakhir terkirim: <b>{{ lastSubmitted }}</b>
      </p>
    </form>

    <h4 style="margin:16px 0 8px;font-size:14px;">📋 Riwayat Catatan Saya</h4>
    <div v-if="!history.length" class="card card-pad muted" style="font-size:12px;">Belum ada catatan service.</div>
    <div v-for="h in history" :key="h.id" class="card card-pad svc-card">
      <div class="row" style="justify-content:space-between;gap:8px;">
        <b style="font-size:12px;">{{ h.display_id }}</b>
        <span class="badge" :class="h.status === 'REVIEWED' ? 'badge-green' : h.status === 'REJECTED' ? 'badge-red' : 'badge-amber'">
          {{ h.status }}
        </span>
      </div>
      <div class="muted" style="font-size:11px;margin:4px 0;">{{ h.nopol }} · {{ h.km_kendaraan }} km · {{ String(h.created_at || '').slice(0,16).replace('T',' ') }}</div>
      <div style="font-size:12px;">{{ h.keluhan }}</div>
      <div v-if="h.ga_note" class="muted" style="font-size:11px;margin-top:6px;">Catatan GA: {{ h.ga_note }}</div>
    </div>
  </div>
</template>

<style scoped>
.svc-row { display:flex; justify-content:space-between; gap:10px; padding:6px 0; border-bottom:1px dashed var(--border, #e2e8f0); font-size:12px; }
.svc-row span { color: var(--text-3, #64748b); }
.svc-label { display:block; font-size:12px; font-weight:700; margin:14px 0 6px; }
.svc-area { width:100%; resize:vertical; font:inherit; font-size:13px; }
.svc-card { margin-bottom:8px; font-size:12px; }
.badge { font-size:9px; padding:2px 7px; border-radius:8px; font-weight:700; }
.badge-amber { background:#fef3c7; color:#92400e; }
.badge-green { background:#d1fae5; color:#065f46; }
.badge-red { background:#fee2e2; color:#b91c1c; }
</style>
