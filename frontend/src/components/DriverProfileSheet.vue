<script setup>
import { computed, ref, watch } from 'vue'
import { api } from '../api'

const props = defineProps({
  modelValue: { type: Boolean, default: false },
})
const emit = defineEmits(['update:modelValue', 'changed'])

const ctx = ref(null)
const loading = ref(false)
const busy = ref(false)
const error = ref('')
const notice = ref('')
const draft = ref(null)
const handoverForm = ref({})

const CATEGORIES = [
  { value: 'driver_request', label: 'Permintaan driver' },
  { value: 'vehicle_issue', label: 'Masalah kendaraan' },
  { value: 'mutasi', label: 'Mutasi / rotasi' },
  { value: 'other', label: 'Lainnya' },
]

const STATUS = {
  pending: { label: '⏳ Menunggu GA', cls: '' },
  approved: { label: '✅ Disetujui — isi bukti', cls: 'badge-green' },
  completed: { label: '✔ Selesai', cls: 'badge-green' },
  rejected: { label: '✕ Ditolak', cls: 'badge-red' },
  cancelled: { label: '✕ Dibatalkan', cls: '' },
  superseded: { label: '↪ Ditutup', cls: '' },
}

const meName = computed(() => (ctx.value?.me?.driver || '').toUpperCase())
const freeVehicles = computed(() => ctx.value?.free_vehicles || [])
const partners = computed(() => ctx.value?.partners || [])
const requests = computed(() => ctx.value?.requests || [])

function statusLabel(status) {
  return (STATUS[status] || {}).label || status || '-'
}
function statusClass(status) {
  return (STATUS[status] || {}).cls || ''
}

function requestSide(row) {
  const requester = (row.requester_driver || '').toUpperCase()
  const target = (row.target_driver || '').toUpperCase()
  if (requester && requester === meName.value) return 'requester'
  if (target && target === meName.value) return 'target'
  return null
}

function receivedNopol(row) {
  const side = requestSide(row)
  if (side === 'requester') return row.target_nopol
  if (side === 'target') return row.requester_nopol
  return ''
}

function needsHandover(row) {
  if (row.status !== 'approved') return false
  const side = requestSide(row)
  return Boolean(side && !row[`${side}_photo`])
}

function hform(id) {
  if (!handoverForm.value[id]) {
    handoverForm.value[id] = { odometer: '', photo: null }
  }
  return handoverForm.value[id]
}

function handoverReady(id) {
  const f = handoverForm.value[id]
  return Boolean(f && String(f.odometer).trim() !== '' && f.photo)
}

function onPhoto(id, event) {
  const file = event?.target?.files?.[0] || null
  hform(id).photo = file
}

async function load() {
  loading.value = true
  error.value = ''
  try {
    ctx.value = await api('/api/assignments/swap-context')
  } catch (e) {
    error.value = e.message || 'Gagal memuat data kendaraan'
  } finally {
    loading.value = false
  }
}

function close() {
  draft.value = null
  emit('update:modelValue', false)
}

function pickFree(vehicle) {
  notice.value = ''
  draft.value = {
    swap_type: 'move',
    target_nopol: vehicle.nopol,
    target_driver: '',
    label: `Pindah ke ${vehicle.nopol} · ${vehicle.vehicle_type}`,
    category: 'driver_request',
    reason: '',
  }
}

function pickPartner(partner) {
  notice.value = ''
  draft.value = {
    swap_type: 'exchange',
    target_nopol: partner.nopol,
    target_driver: partner.driver_name,
    label: `Tukar dengan ${partner.driver_name} · ${partner.nopol}`,
    category: 'driver_request',
    reason: '',
  }
}

async function submitRequest() {
  if (!draft.value || draft.value.reason.trim().length < 10) return
  busy.value = true
  error.value = ''
  try {
    await api('/api/assignments/swap-requests', {
      method: 'POST',
      body: {
        swap_type: draft.value.swap_type,
        target_driver: draft.value.target_driver || undefined,
        target_nopol: draft.value.target_nopol,
        category: draft.value.category,
        reason: draft.value.reason.trim(),
      },
    })
    draft.value = null
    notice.value = 'Pengajuan terkirim — menunggu persetujuan GA.'
    await load()
    emit('changed')
  } catch (e) {
    error.value = e.message || 'Gagal mengirim pengajuan'
  } finally {
    busy.value = false
  }
}

async function cancelRequest(row) {
  busy.value = true
  error.value = ''
  try {
    await api(`/api/assignments/swap-requests/${row.id}/cancel`, { method: 'POST' })
    notice.value = 'Pengajuan dibatalkan.'
    await load()
    emit('changed')
  } catch (e) {
    error.value = e.message || 'Gagal membatalkan pengajuan'
  } finally {
    busy.value = false
  }
}

async function submitHandover(row) {
  const form = handoverForm.value[row.id]
  if (!form || !form.photo) return
  busy.value = true
  error.value = ''
  try {
    const body = new FormData()
    body.append('odometer', String(form.odometer).trim())
    body.append('photo', form.photo)
    const token = localStorage.getItem('bpf_csrf') || sessionStorage.getItem('bpf_csrf') || ''
    const resp = await fetch(`/api/assignments/swap-requests/${row.id}/handover`, {
      method: 'POST',
      headers: { 'X-CSRF-Token': token },
      body,
    })
    const data = await resp.json().catch(() => null)
    if (!resp.ok) throw new Error((data && data.msg) || `HTTP ${resp.status}`)
    delete handoverForm.value[row.id]
    notice.value = data?.status === 'completed'
      ? 'Serah terima selesai.'
      : 'Bukti terkirim — menunggu rekan Anda.'
    await load()
    emit('changed')
  } catch (e) {
    error.value = e.message || 'Gagal mengirim bukti serah terima'
  } finally {
    busy.value = false
  }
}

watch(() => props.modelValue, (open) => {
  if (open) load()
}, { immediate: true })
</script>

<template>
  <div v-if="modelValue" class="modal-overlay" role="dialog" aria-modal="true"
       aria-label="Profil & Kendaraan" @click.self="close" @keydown.esc="close">
    <section class="card card-pad ps-sheet">
      <header class="ps-head">
        <div>
          <h3>👤 Profil &amp; Kendaraan</h3>
          <p class="muted ps-sub">
            {{ meName || 'Driver' }} · Kendaraan saya:
            <b>{{ ctx?.me?.nopol || '—' }}</b>
            <span v-if="ctx?.me?.vehicle_type"> · {{ ctx.me.vehicle_type }}</span>
          </p>
        </div>
        <button class="btn-icon" type="button" aria-label="Tutup" @click="close">✕</button>
      </header>

      <div v-if="loading" class="ps-empty">Memuat data kendaraan…</div>
      <div v-else-if="error" class="alert alert-error ps-alert">{{ error }}</div>
      <template v-else>
        <div v-if="notice" class="alert alert-success ps-alert">{{ notice }}</div>

        <div v-if="!ctx?.me" class="ps-empty">
          Anda belum punya kendaraan aktif. Hubungi GA untuk penugasan pertama.
        </div>

        <template v-else>
          <h4 class="ps-title">Ganti Kendaraan</h4>

          <div class="ps-group">
            <div class="ps-group-head">Kendaraan kosong ({{ freeVehicles.length }})</div>
            <div v-if="!freeVehicles.length" class="ps-empty">Tidak ada kendaraan kosong.</div>
            <div v-for="v in freeVehicles" :key="v.nopol" class="ps-row">
              <span><b>{{ v.nopol }}</b> · {{ v.vehicle_type }}</span>
              <button class="btn btn-sm" :disabled="busy" @click="pickFree(v)">Ambil</button>
            </div>
          </div>

          <div class="ps-group">
            <div class="ps-group-head">Kendaraan dengan driver ({{ partners.length }})</div>
            <div v-if="!partners.length" class="ps-empty">
              Tidak ada rekan dengan kendaraan aktif.
            </div>
            <div v-for="p in partners" :key="p.driver_name" class="ps-row">
              <span><b>{{ p.driver_name }}</b> · {{ p.nopol }} · {{ p.vehicle_type }}</span>
              <button class="btn btn-sm" :disabled="busy" @click="pickPartner(p)">Tukar</button>
            </div>
          </div>
        </template>

        <h4 class="ps-title">Pengajuan saya</h4>
        <div v-if="!requests.length" class="ps-empty">Belum ada pengajuan.</div>
        <div v-for="r in requests" :key="r.id" class="ps-card" :data-request-id="r.id">
          <div class="ps-row">
            <b>{{ r.request_code || ('#' + r.id) }}</b>
            <span class="badge" :class="statusClass(r.status)">{{ statusLabel(r.status) }}</span>
          </div>
          <div class="ps-line">
            {{ r.swap_type === 'move' ? 'Pindah' : 'Tukar' }}:
            <b>{{ r.requester_nopol }}</b> → <b>{{ r.target_nopol }}</b>
            <span v-if="r.target_driver"> · {{ r.target_driver }}</span>
          </div>
          <div class="ps-line muted">{{ r.reason }}</div>
          <div v-if="r.ga_note" class="ps-line muted">Catatan GA: {{ r.ga_note }}</div>

          <div v-if="r.status === 'pending' && r.requester_driver === meName" class="ps-actions">
            <button class="btn btn-sm btn-danger" :disabled="busy" @click="cancelRequest(r)">
              Batalkan
            </button>
          </div>

          <div v-if="needsHandover(r)" class="ps-handover">
            <div class="ps-line"><b>Serah terima: {{ receivedNopol(r) }}</b></div>
            <p class="muted" style="font-size:11px;margin:0 0 6px;">
              Isi odometer dan unggah foto kendaraan yang Anda terima.
            </p>
            <input class="input" type="number" min="0" max="2000000"
                   :placeholder="'Odometer ' + receivedNopol(r) + ' (km)'"
                   v-model="hform(r.id).odometer" />
            <input class="input" type="file" accept="image/*,application/pdf"
                   style="margin-top:6px;" @change="onPhoto(r.id, $event)" />
            <button class="btn btn-sm btn-primary" style="margin-top:6px;"
                    :disabled="busy || !handoverReady(r.id)" @click="submitHandover(r)">
              📷 Kirim Bukti
            </button>
          </div>
        </div>
      </template>
    </section>

    <div v-if="draft" class="modal-overlay" role="dialog" aria-modal="true"
         aria-label="Ajukan ganti kendaraan" @click.self="draft = null">
      <div class="card card-pad ps-modal">
        <h3>{{ draft.swap_type === 'move' ? '➡️ Ambil Kendaraan' : '🔄 Tukar Kendaraan' }}</h3>
        <p class="muted ps-sub">{{ draft.label }}</p>
        <div class="field" style="margin-bottom:8px;">
          <label>Kategori</label>
          <select class="select" v-model="draft.category">
            <option v-for="c in CATEGORIES" :key="c.value" :value="c.value">{{ c.label }}</option>
          </select>
        </div>
        <div class="field" style="margin-bottom:10px;">
          <label>Alasan <span class="req">*</span></label>
          <textarea class="textarea" rows="3" v-model="draft.reason"
                    placeholder="minimal 10 karakter…"></textarea>
        </div>
        <div class="ps-actions">
          <button class="btn" @click="draft = null">Batal</button>
          <button class="btn btn-primary"
                  :disabled="busy || draft.reason.trim().length < 10"
                  @click="submitRequest">
            {{ busy ? '⏳ Mengirim…' : 'Ajukan' }}
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.ps-sheet {
  max-width: 520px;
  width: 94vw;
  max-height: 88vh;
  overflow-y: auto;
}
.ps-head { display: flex; align-items: flex-start; justify-content: space-between; gap: 10px; }
.ps-head h3 { margin: 0; }
.ps-sub { font-size: 11px; margin: 2px 0 10px; }
.ps-alert { margin: 0 0 10px; }
.ps-title { margin: 16px 0 6px; font-size: 13px; }
.ps-group { border: 1px solid var(--border); border-radius: 10px; padding: 8px 10px; margin-bottom: 10px; }
.ps-group-head { font-size: 11px; font-weight: 700; color: var(--muted, #64748b); margin-bottom: 4px; }
.ps-row { display: flex; align-items: center; justify-content: space-between; gap: 8px; padding: 3px 0; font-size: 12px; }
.ps-empty { font-size: 12px; color: var(--muted, #64748b); padding: 6px 0; }
.ps-card { border: 1px solid var(--border); border-radius: 10px; padding: 8px 10px; margin-bottom: 8px; font-size: 12px; }
.ps-line { margin: 2px 0; }
.ps-actions { display: flex; justify-content: flex-end; gap: 6px; margin-top: 6px; }
.ps-handover { margin-top: 8px; padding-top: 8px; border-top: 1px dashed var(--border); }
.ps-modal { max-width: 420px; width: 92vw; }
</style>
