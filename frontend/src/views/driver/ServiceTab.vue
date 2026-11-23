<script setup>
import { onMounted, ref, watch } from 'vue'
import { api } from '../../api'
import { useDriverStore } from '../../stores/driverStore'

const store = useDriverStore()
const emit = defineEmits(['toast'])

const kmInput = ref('')
const items = ref([''])
const submitting = ref(false)
const history = ref([])
const lastSubmitted = ref('')

const driverName = () => store.driverDisplayName || store.driverName
const nopol = () => store.profile?.nopol || ''
const vehicleType = () => store.profile?.vehicle_type || ''
const suggestedKm = () => Number(store.profile?.last_odo_km || store.profile?.initial_odo_km || 0)

function prefillKm() {
  if (!kmInput.value && suggestedKm()) kmInput.value = String(suggestedKm())
}

function addItem() {
  if (items.value.length >= 10) {
    emit('toast', '⚠️ Maksimal 10 poin keluhan', 'warning')
    return
  }
  items.value.push('')
}

function removeItem(index) {
  if (items.value.length === 1) {
    items.value[index] = ''
    return
  }
  items.value.splice(index, 1)
}

function buildKeluhan() {
  const rows = items.value.map((s) => String(s || '').trim()).filter(Boolean)
  return rows.map((s, i) => `${i + 1}. ${s}`).join('\n')
}

async function loadHistory() {
  try {
    const d = await api('/api/driver/service')
    history.value = Array.isArray(d?.data) ? d.data : (Array.isArray(d) ? d : [])
  } catch {
    history.value = []
  }
}

async function submit() {
  const keluhan = buildKeluhan()
  if (!String(kmInput.value).trim() || Number(kmInput.value) <= 0) {
    emit('toast', '⚠️ KM kendaraan wajib diisi manual dengan angka', 'error')
    return
  }
  if (!keluhan) {
    emit('toast', '⚠️ Minimal satu keluhan wajib diisi', 'error')
    return
  }
  if (keluhan.length > 2000) {
    emit('toast', '⚠️ Total catatan maksimal 2000 karakter', 'error')
    return
  }
  submitting.value = true
  try {
    const r = await api('/api/driver/service', {
      method: 'POST',
      body: {
        keluhan,
        keluhan_items: items.value.map((s) => String(s || '').trim()).filter(Boolean),
        km_kendaraan: Number(kmInput.value),
        nopol: nopol(),
        vehicle_type: vehicleType(),
      },
    })
    emit('toast', `✅ ${r.msg || 'Catatan service terkirim ke GA'}`, 'success')
    lastSubmitted.value = r.display_id || ''
    items.value = ['']
    await loadHistory()
  } catch (e) {
    emit('toast', '❌ ' + (e.message || 'Gagal mengirim catatan service'), 'error')
  } finally {
    submitting.value = false
  }
}

watch(() => store.profile, prefillKm, { immediate: true })
onMounted(() => { prefillKm(); loadHistory() })
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

      <label class="svc-label" for="svc-km">KM Kendaraan <span class="muted">(isi manual sesuai ODO saat ini)</span></label>
      <input id="svc-km" v-model="kmInput" class="inp" type="number" min="1" inputmode="numeric"
             placeholder="Contoh: 78179" />
      <div v-if="suggestedKm()" class="muted" style="font-size:10px;margin-top:4px;">
        ODO terakhir di profil: {{ suggestedKm().toLocaleString('id-ID') }} km — periksa lagi sebelum mengirim.
      </div>

      <label class="svc-label">Catatan Keluhan Kendaraan</label>
      <div v-for="(item, index) in items" :key="index" class="svc-item">
        <span class="svc-num">{{ index + 1 }}</span>
        <textarea v-model="items[index]" class="inp svc-area" rows="2"
                  :placeholder="index === 0 ? 'Contoh: Rem depan berbunyi keras saat pengereman' : 'Tambah keluhan lain…'"></textarea>
        <button type="button" class="btn-icon svc-remove" :aria-label="'Hapus poin ' + (index + 1)"
                @click="removeItem(index)">✕</button>
      </div>
      <div class="row" style="justify-content:space-between;align-items:center;margin-top:6px;">
        <button type="button" class="btn btn-sm" @click="addItem">＋ Tambah Keluhan</button>
        <span class="muted" style="font-size:10px;">{{ items.filter(i => String(i || '').trim()).length }} poin · {{ buildKeluhan().length }}/2000</span>
      </div>

      <button class="btn btn-primary" style="width:100%;justify-content:center;margin-top:12px;"
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
      <div style="font-size:12px;white-space:pre-wrap;">{{ h.keluhan }}</div>
      <div v-if="h.ga_note" class="muted" style="font-size:11px;margin-top:6px;">Catatan GA: {{ h.ga_note }}</div>
    </div>
  </div>
</template>

<style scoped>
.svc-row { display:flex; justify-content:space-between; gap:10px; padding:6px 0; border-bottom:1px dashed var(--border, #e2e8f0); font-size:12px; }
.svc-row span { color: var(--text-3, #64748b); }
.svc-label { display:block; font-size:12px; font-weight:700; margin:14px 0 6px; }
.svc-area { width:100%; resize:vertical; font:inherit; font-size:13px; }
.svc-item { display:flex; align-items:flex-start; gap:8px; margin-bottom:8px; }
.svc-num {
  flex:0 0 24px; height:24px; margin-top:2px; border-radius:50%;
  background:var(--primary-soft, #dbeafe); color:var(--primary, #2563eb);
  display:flex; align-items:center; justify-content:center; font-size:12px; font-weight:800;
}
.svc-remove { flex:0 0 30px; height:30px; margin-top:2px; color:var(--danger, #dc2626); }
.svc-card { margin-bottom:8px; font-size:12px; }
.badge { font-size:9px; padding:2px 7px; border-radius:8px; font-weight:700; }
.badge-amber { background:#fef3c7; color:#92400e; }
.badge-green { background:#d1fae5; color:#065f46; }
.badge-red { background:#fee2e2; color:#b91c1c; }
</style>
