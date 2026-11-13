<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { useDriverStore } from '../../stores/driverStore'
import { api } from '../../api'
import { applyWatermark, fileToDataUrl } from '../../utils/watermark'

const store = useDriverStore()
const emit = defineEmits(['toast', 'locate'])

const form = ref({
  nopol: '', vehicle_type: 'AVANZA', bbm_type: '', price_per_liter: 10000,
  nominal: 0, odo_km: 0, jumlah_appointment: 0, spbu_type: 'rekanan',
  voucher_partner: '', nota_no: '', liter: 0,
})
// v2.107.0 — mode ketiga: voucher rekanan. Klaim = driver menalangi dulu;
// voucher = SPBU mitra memberi voucher + blanko, kantor bayar mitra per periode.
const mode = ref('claim') // 'claim' | 'voucher'
const voucherCfg = ref({ value: 0, partner: '', daily_code: 0, nominal: 0 })
const voucherNominal = computed(() => {
  if (!voucherCfg.value.value) return 0
  return Number(voucherCfg.value.value) + Number(voucherCfg.value.daily_code || 0)
})
const allowedBbm = ref([])
const liter = computed(() => {
  if (mode.value === 'voucher') return Number(form.value.liter) || 0
  return form.value.price_per_liter > 0 ? (form.value.nominal || 0) / form.value.price_per_liter : 0
})

const photos = ref({ foto_odo_sebelum: null, foto_nota_odo_sesudah: null, foto_struk: null, foto_struk_dispenser: null })
const previews = ref({})
const wmState = ref({})
const wmBlobs = ref({})
const saving = ref(false)
const submitting = computed(() => saving.value || store.syncing)

const PHOTO_FIELDS = [
  { key: 'foto_odo_sebelum', label: 'Foto ODO Sebelum', required: true },
  { key: 'foto_nota_odo_sesudah', label: 'Nota + ODO Sesudah', required: true },
  { key: 'foto_struk', label: 'Foto Struk', required: true },
  { key: 'foto_struk_dispenser', label: 'Foto Dispenser', required: true, onlyNonRekanan: true },
]

function applyProfile() {
  const p = store.profile
  if (!p) return
  form.value.nopol = p.nopol || form.value.nopol
  form.value.vehicle_type = p.vehicle_type || 'AVANZA'
  loadAllowedBbm(p.bbm_type)
}

async function loadVoucherConfig() {
  try {
    voucherCfg.value = await api('/api/voucher/config')
    if (!form.value.voucher_partner) form.value.voucher_partner = voucherCfg.value.partner || ''
  } catch {
    voucherCfg.value = { value: 0, partner: '', daily_code: 0, nominal: 0 }
  }
}

// Mode voucher: nominal dihitung server dari nilai cabang + kode harian.
// Klien hanya menampilkan pratinjau supaya driver tahu nilai yang dipakai.
watch(mode, (m) => {
  if (m === 'voucher') {
    form.value.spbu_type = 'rekanan'
    if (!voucherCfg.value.value) loadVoucherConfig()
  }
})

async function loadAllowedBbm(preferred) {
  try {
    const list = await api('/api/vehicle-allowed-bbm/' + encodeURIComponent(form.value.vehicle_type))
    allowedBbm.value = Array.isArray(list) ? list : []
    const pick = allowedBbm.value.find((b) => b.is_default)
      || allowedBbm.value.find((b) => b.bbm_type === preferred)
      || allowedBbm.value.find((b) => b.bbm_type === 'PERTALITE')
      || allowedBbm.value[0]
    if (pick) {
      form.value.bbm_type = pick.bbm_type
      form.value.price_per_liter = Number(pick.price_per_liter) || 10000
    }
  } catch {
    allowedBbm.value = []
    form.value.bbm_type = preferred || 'PERTALITE'
  }
}

watch(() => form.value.bbm_type, (b) => {
  const found = allowedBbm.value.find((x) => x.bbm_type === b)
  if (found) form.value.price_per_liter = Number(found.price_per_liter) || 10000
})

watch(() => store.profile, applyProfile, { immediate: true })

// Mode LPJ: kasbon aktif mengisi nominal/nopol/BBM dari data kasbon
watch(() => store.activeLpj, (lpj) => {
  if (lpj) {
    mode.value = 'claim'
    form.value.nominal = Number(lpj.total_amount) || 0
    form.value.nopol = lpj.nopol || form.value.nopol
    if (lpj.bbm_type) { form.value.bbm_type = lpj.bbm_type }
  }
})

async function gpsText() {
  if (store.gps.addr) return store.gps.addr
  if (store.gps.lat && store.gps.lon) return `${store.gps.lat.toFixed(5)}, ${store.gps.lon.toFixed(5)}`
  try { await store.locate(); return store.gps.addr || 'Lokasi tidak tersedia' }
  catch { return 'Lokasi tidak tersedia' }
}

async function onPhotoChange(field, e) {
  const f = e.target.files[0]
  if (!f) return
  if (!f.type.startsWith('image/')) { e.target.value = ''; emit('toast', '⚠️ Pilih file gambar', 'error'); return }
  photos.value[field] = f
  previews.value[field] = await fileToDataUrl(f)
  wmState.value[field] = 'processing'
  const addr = await gpsText()
  const coords = store.gps.lat ? `${store.gps.lat.toFixed(5)}, ${store.gps.lon.toFixed(5)}` : null
  const blob = await applyWatermark(f, addr, null, coords)
  wmBlobs.value[field] = blob
  wmState.value[field] = blob ? 'done' : 'error'
}

function removePhoto(field) {
  photos.value[field] = null; previews.value[field] = ''; wmBlobs.value[field] = null; wmState.value[field] = ''
}

function resetForm() {
  mode.value = 'claim'
  form.value = {
    nopol: store.profile?.nopol || '', vehicle_type: store.profile?.vehicle_type || 'AVANZA',
    bbm_type: '', price_per_liter: 10000, nominal: 0, odo_km: 0, jumlah_appointment: 0, spbu_type: 'rekanan',
    voucher_partner: '', nota_no: '', liter: 0,
  }
  photos.value = { foto_odo_sebelum: null, foto_nota_odo_sesudah: null, foto_struk: null, foto_struk_dispenser: null }
  previews.value = {}; wmState.value = {}; wmBlobs.value = {}
  loadAllowedBbm(store.profile?.bbm_type)
  store.setActiveLpj(null)
}

function buildPayload() {
  const isVoucher = mode.value === 'voucher'
  return {
    driver_name: store.driverName,
    // Voucher bukan jenis transaksi baru: tetap CLAIM, hanya label SPBU
    // rekanan + is_voucher yang membuat server mengisi kolom voucher.
    transaction_type: 'CLAIM',
    is_voucher: isVoucher ? '1' : '',
    nopol: form.value.nopol,
    vehicle_type: form.value.vehicle_type,
    bbm_type: form.value.bbm_type,
    nominal: isVoucher ? voucherNominal.value : (Number(form.value.nominal) || 0),
    price_per_liter: Number(form.value.price_per_liter) || 10000,
    odo_km: Number(form.value.odo_km) || 0,
    jumlah_appointment: Number(form.value.jumlah_appointment) || 0,
    spbu_type: isVoucher ? 'rekanan' : form.value.spbu_type,
    voucher_partner: isVoucher ? form.value.voucher_partner : '',
    nota_no: isVoucher ? form.value.nota_no : '',
    liter: isVoucher ? (Number(form.value.liter) || 0) : 0,
    gps_lat: store.gps.lat ?? '',
    gps_lon: store.gps.lon ?? '',
    gps_address: store.gps.addr || '',
    gps_kelurahan: store.gps.detail?.kelurahan || '',
    gps_kecamatan: store.gps.detail?.kecamatan || '',
    gps_kota: store.gps.detail?.kota || '',
    gps_provinsi: store.gps.detail?.provinsi || '',
    gps_kode_pos: store.gps.detail?.kode_pos || '',
  }
}

function requiredPhotos() {
  if (mode.value === 'voucher') {
    // Voucher rekanan selalu butuh bukti yang sama dengan klaim rekanan.
    return PHOTO_FIELDS.filter((f) => f.required && !f.onlyNonRekanan)
  }
  return PHOTO_FIELDS.filter((f) => f.required && (!f.onlyNonRekanan || form.value.spbu_type === 'non_rekanan'))
}

async function submit() {
  const isVoucher = mode.value === 'voucher'
  if (isVoucher) {
    if (!form.value.nopol || !(form.value.odo_km > 0) || !(form.value.liter > 0)
        || !form.value.voucher_partner || !form.value.nota_no) {
      emit('toast', '⚠️ Nopol, ODO, liter, SPBU mitra, dan nomor nota wajib diisi', 'error'); return
    }
    if (!(voucherNominal.value > 0)) {
      emit('toast', '⚠️ Nilai voucher cabang belum diatur — hubungi Finance/Admin', 'error'); return
    }
  } else if (!form.value.nopol || !(form.value.nominal > 0) || !(form.value.odo_km > 0)) {
    emit('toast', '⚠️ Nopol, nominal, dan ODO wajib diisi', 'error'); return
  }
  // Foto bertanda * wajib ada di klien: server sengaja menerima foto kosong
  // untuk jalur offline, jadi tanpa cek ini klaim bisa tersimpan tanpa bukti.
  const missingPhotos = requiredPhotos().filter((f) => !photos.value[f.key])
  if (missingPhotos.length) {
    emit('toast', '⚠️ Foto wajib belum lengkap: ' + missingPhotos.map((f) => f.label).join(', '), 'error')
    return
  }
  if (Object.values(wmState.value).includes('processing')) {
    emit('toast', '⏳ Tunggu watermark foto selesai diproses', 'warning')
    return
  }
  const isLpj = !!store.activeLpj
  const payload = buildPayload()
  const files = {}
  for (const f of PHOTO_FIELDS) {
    if (f.onlyNonRekanan && form.value.spbu_type !== 'non_rekanan') continue
    files[f.key] = wmBlobs.value[f.key] || photos.value[f.key] || null
  }

  if (store.online) {
    saving.value = true
    try {
      const fd = new FormData()
      for (const [k, v] of Object.entries(payload)) fd.append(k, String(v))
      for (const [k, v] of Object.entries(files)) {
        if (v) fd.append(k, v, v.name || k + '.jpg')
      }
      const endpoint = isLpj ? `/api/cash/submit-lpj/${store.activeLpj.cashId}` : '/driver'
      const csrf = localStorage.getItem('bpf_csrf') || sessionStorage.getItem('bpf_csrf')
      const r = await fetch(endpoint, {
        method: 'POST', body: fd,
        headers: { ...(csrf ? { 'X-CSRF-Token': csrf } : {}), 'X-Requested-With': 'XMLHttpRequest', Accept: 'application/json' },
      })
      const j = await r.json().catch(() => null)
      if (r.ok && j?.status === 'success') {
        const label = isLpj ? 'LPJ' : (isVoucher ? 'Voucher' : 'Klaim')
        emit('toast', `✅ ${label} terkirim: ${j.transaction_id || j.msg}`, 'success')
        resetForm()
      } else {
        emit('toast', '❌ ' + (j?.msg || 'Gagal mengirim'), 'error')
      }
    } catch {
      emit('toast', '❌ Error koneksi — data tidak terkirim', 'error')
    } finally { saving.value = false }
  } else {
    // Offline: simpan ke antrean (foto asli + data; watermark saat pengiriman ulang tidak ada — setia ke perilaku klasik)
    const queued = { ...payload, ...files }
    await store.enqueue(isLpj ? 'lpj_queue' : 'fuel_queue', queued, isLpj ? store.activeLpj.cashId : null)
    resetForm()
    emit('toast', '🟡 Offline — data disimpan lokal, akan dikirim otomatis', 'warning')
  }
}

onMounted(() => {
  if (store.profile) applyProfile()
  // Pratinjau nilai voucher cabang (dipakai saat mode Voucher dipilih).
  loadVoucherConfig()
  // Auto GPS saat pertama buka
  if (!store.gps.lat && !store.gps.locating) store.locate().catch(() => {})
})
</script>

<template>
  <div class="tab-page">
    <!-- Mode LPJ -->
    <div v-if="store.activeLpj" class="alert alert-info" style="margin-bottom:10px;">
      📋 Mengisi <b>LPJ {{ store.activeLpj.display_id }}</b> — nominal terkunci dari kasbon (termasuk kode unik) &amp; tidak bisa diubah.
    </div>

    <!-- GPS -->
    <div class="gps-box" :class="{ ok: store.gps.addr, err: store.gps.locating }">
      <div class="gps-title">
        <template v-if="store.gps.locating">🔍 Mencari lokasi…</template>
        <template v-else-if="store.gps.addr">📍 Lokasi Terdeteksi</template>
        <template v-else>⚠ GPS Belum Aktif</template>
      </div>
      <div class="gps-addr">{{ store.gps.addr || 'Mohon aktifkan lokasi atau tekan tombol di bawah.' }}</div>
      <div v-if="store.gps.lat" class="gps-coord">📍 {{ store.gps.lat?.toFixed(5) }}, {{ store.gps.lon?.toFixed(5) }}</div>
      <div v-if="store.gps.spbu" class="gps-spbu">⛽ {{ store.gps.spbu }}</div>
      <button class="btn btn-sm" :disabled="store.gps.locating" style="margin-top:6px;" @click="store.locate()">📍 Isi Lokasi &amp; Jam</button>
    </div>

    <!-- v2.107.0: mode Klaim vs Voucher rekanan -->
    <div v-if="!store.activeLpj" class="mode-switch" role="tablist" aria-label="Jenis laporan BBM">
      <button type="button" role="tab" :aria-selected="mode === 'claim'" :class="{ active: mode === 'claim' }"
              data-testid="bbm-mode-claim" @click="mode = 'claim'">
        💸 Klaim BBM<small>Driver bayar dulu, diganti kantor</small>
      </button>
      <button type="button" role="tab" :aria-selected="mode === 'voucher'" :class="{ active: mode === 'voucher' }"
              data-testid="bbm-mode-voucher" @click="mode = 'voucher'">
        🎟️ Voucher Rekanan<small>Voucher + blanko dari SPBU mitra</small>
      </button>
    </div>

    <form class="driver-form" @submit.prevent="submit">
      <div class="field"><label>Nama Driver</label>
        <input class="input" :value="store.driverName" disabled />
      </div>
      <div class="field"><label>Nopol</label>
        <input class="input" v-model="form.nopol" placeholder="cth: L 1413 CBI" />
      </div>
      <div class="field"><label>Tipe Kendaraan</label>
        <input class="input" v-model="form.vehicle_type" />
      </div>
      <div class="field"><label>Jenis BBM</label>
        <select class="select" v-model="form.bbm_type">
          <option v-for="b in allowedBbm" :key="b.bbm_type" :value="b.bbm_type">
            {{ b.bbm_type }} (Rp {{ Number(b.price_per_liter).toLocaleString('id-ID') }})
          </option>
          <option v-if="!allowedBbm.length" :value="form.bbm_type">{{ form.bbm_type }}</option>
        </select>
      </div>
      <div class="row">
        <div v-if="mode === 'claim'" class="field"><label>Nominal (Rp)</label>
          <input class="input" type="number" v-model.number="form.nominal" min="0" placeholder="0" :disabled="!!store.activeLpj" />
        </div>
        <div v-else class="field"><label>Nilai Voucher (otomatis)</label>
          <input class="input" :value="voucherNominal ? 'Rp ' + voucherNominal.toLocaleString('id-ID') : 'Belum diatur'"
                 disabled data-testid="voucher-nominal" />
        </div>
        <div class="field"><label>Harga/Liter</label>
          <input class="input" type="number" v-model.number="form.price_per_liter" min="0" />
        </div>
      </div>
      <div v-if="mode === 'voucher'" class="alert" style="padding:6px 10px;font-size:12px;background:#ecfdf5;">
        🎟️ Nilai voucher <b>Rp {{ Number(voucherCfg.value || 0).toLocaleString('id-ID') }}</b>
        + kode harian <b>{{ voucherCfg.daily_code || 0 }}</b> =
        <b>Rp {{ Number(voucherNominal || 0).toLocaleString('id-ID') }}</b>
        <span v-if="voucherCfg.partner" class="muted"> · Mitra: {{ voucherCfg.partner }}</span>
      </div>
      <div v-if="mode === 'voucher'" class="row">
        <div class="field"><label>SPBU Mitra</label>
          <input class="input" v-model="form.voucher_partner" placeholder="cth: SPBU 54.601.01" data-testid="voucher-partner" />
        </div>
        <div class="field"><label>Nomor Nota</label>
          <input class="input" v-model="form.nota_no" placeholder="nomor nota/struk" data-testid="voucher-nota" />
        </div>
      </div>
      <div class="alert" style="padding:6px 10px;font-size:12px;">⛽ Estimasi: <b>{{ liter.toFixed(2) }} L</b></div>

      <div class="row">
        <div class="field"><label>ODO (km)</label>
          <input class="input" type="number" v-model.number="form.odo_km" min="0" placeholder="0" />
        </div>
        <div v-if="mode === 'voucher'" class="field"><label>Liter (dari nota)</label>
          <input class="input" type="number" v-model.number="form.liter" min="0" step="0.01" placeholder="0"
                 data-testid="voucher-liter" />
        </div>
        <div v-else class="field"><label>Jumlah Appointment</label>
          <input class="input" type="number" v-model.number="form.jumlah_appointment" min="0" placeholder="0" />
        </div>
      </div>

      <div v-if="mode === 'claim'" class="field"><label>Tipe SPBU</label>
        <select class="select" v-model="form.spbu_type">
          <option value="rekanan">Rekanan</option>
          <option value="non_rekanan">Non-Rekanan (wajib foto dispenser)</option>
        </select>
      </div>

      <!-- Foto -->
      <div v-for="f in PHOTO_FIELDS" :key="f.key">
        <template v-if="!f.onlyNonRekanan || form.spbu_type === 'non_rekanan'">
          <label class="photo-label">{{ f.label }} <span v-if="f.required" class="req">*</span></label>
          <div class="photo-box">
            <img v-if="previews[f.key]" :src="previews[f.key]" class="photo-preview" alt="preview" />
            <div v-else class="photo-empty">📷</div>
            <div class="photo-actions">
              <input type="file" accept="image/*" class="file-input"
                     :id="'cam_' + f.key" capture="environment" @change="onPhotoChange(f.key, $event)" />
              <label class="btn btn-sm" :for="'cam_' + f.key">📷 Kamera</label>
              <input type="file" accept="image/*" class="file-input"
                     :id="'gal_' + f.key" @change="onPhotoChange(f.key, $event)" />
              <label class="btn btn-sm btn-outline" :for="'gal_' + f.key">🖼️ Galeri</label>
              <button v-if="photos[f.key]" type="button" class="btn btn-sm btn-danger" @click="removePhoto(f.key)">✕</button>
            </div>
            <div v-if="wmState[f.key]" class="wm-badge" :class="wmState[f.key]">
              {{ wmState[f.key] === 'processing' ? '⏳ Watermark…' : wmState[f.key] === 'done' ? '✅ Watermarked' : '⚠ Gagal' }}
            </div>
          </div>
        </template>
      </div>

      <button class="btn btn-primary" style="width:100%;justify-content:center;padding:12px;" :disabled="submitting">
        {{ saving ? '⏳ Mengirim…' : store.activeLpj ? '📤 Kirim LPJ Kasbon' : (mode === 'voucher' ? '📤 Kirim Pemakaian Voucher' : '📤 Kirim Laporan BBM') }}
      </button>
      <p class="muted" style="font-size:11px;text-align:center;margin-top:6px;">
        Foto otomatis diberi watermark (perusahaan + tanggal + lokasi GPS).
      </p>
    </form>
  </div>
</template>

<style scoped>
.mode-switch { display: flex; gap: 8px; margin-bottom: 12px; }
.mode-switch button {
  flex: 1; display: flex; flex-direction: column; align-items: flex-start; gap: 2px;
  padding: 10px 12px; border: 1px solid var(--border); border-radius: 10px;
  background: var(--surface, #fff); color: inherit; cursor: pointer; text-align: left;
  font-weight: 700; font-size: 13px;
}
.mode-switch button small { font-weight: 400; font-size: 10px; opacity: .7; }
.mode-switch button.active { border-color: var(--primary, #2563eb); background: #eff6ff; }
.gps-box {
  border: 1px dashed var(--border); border-radius: 10px; padding: 10px 12px; margin-bottom: 12px;
  background: var(--bg-2, #fef3c7);
}
.gps-box.ok { background: var(--bg-3, #f0fdf4); border-color: var(--success); }
.gps-title { font-size: 13px; font-weight: 700; }
.gps-addr { font-size: 11px; opacity: .8; margin-top: 2px; }
.gps-spbu { font-size: 11px; margin-top: 2px; }
.gps-coord { font-size: 10px; opacity: .5; margin-top: 2px; font-family: monospace; }
.photo-label { font-size: 12px; font-weight: 600; display: block; margin: 10px 0 4px; }
.photo-box { border: 1px dashed var(--border); border-radius: 10px; padding: 8px; display: flex; gap: 10px; align-items: center; }
.photo-preview { width: 64px; height: 64px; object-fit: cover; border-radius: 8px; }
.photo-empty { width: 64px; height: 64px; border-radius: 8px; background: var(--surface-2, #f1f5f9); display: flex; align-items: center; justify-content: center; font-size: 24px; }
.file-input { display: none; }
.wm-badge { font-size: 10px; padding: 2px 8px; border-radius: 10px; }
.wm-badge.processing { background: #fef3c7; color: var(--warning); }
.wm-badge.done { background: #d1fae5; color: var(--success); }
.wm-badge.error { background: #fee2e2; color: var(--danger); }
.btn-outline { background: transparent; border: 1px solid var(--border, #d1d5db); color: var(--text, #374151); }
.btn-outline:hover { background: var(--bg-2, #f1f5f9); }
</style>
