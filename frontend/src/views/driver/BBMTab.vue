<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { useDriverStore, newSubmitId } from '../../stores/driverStore'
import { api } from '../../api'
import { applyWatermark, fileToDataUrl } from '../../utils/watermark'
import KasbonTab from './KasbonTab.vue'

const store = useDriverStore()
const emit = defineEmits(['toast', 'locate', 'switch-tab'])
const props = defineProps({ startView: { type: String, default: 'laporan' } })

// v2.130.0 — Kasbon menjadi sub-tab BBM (bukan tab tersendiri): kasbon hanya
// untuk BBM, dan setelah dana cair muncul kewajiban LPJ di alur yang sama.
const view = ref(props.startView === 'kasbon' ? 'kasbon' : 'laporan')
const pendingLpj = ref([])

// v2.131.0 — feedback km/L (dulu tab Rapor) muncul setelah submit BBM berhasil.
const feedback = ref(null)
// Riwayat 5 transaksi terakhir tampil ringkas di bawah kartu feedback.
const feedbackHistory = ref([])
const showFeedbackHistory = ref(true)

async function loadFeedbackHistory(nopolValue) {
  const n = String(nopolValue || '').trim()
  if (!n) { feedbackHistory.value = []; return }
  try {
    const d = await api('/api/driver/feedback-history', { params: { nopol: n } })
    const rows = Array.isArray(d?.data) ? d.data : []
    feedbackHistory.value = rows.slice(0, 5).map((r) => ({
      date: String(r.date || ''),
      km_per_liter: Number(r.km_per_liter) || 0,
      performa: r.performa || 'CUKUP',
    }))
    showFeedbackHistory.value = true
  } catch { feedbackHistory.value = [] }
}

async function loadFeedback(nopolValue) {
  const n = String(nopolValue || '').trim()
  if (!n) return
  try {
    const d = await api('/api/get-feedback/' + encodeURIComponent(n))
    feedback.value = d?.status === 'success'
      ? { performa: d.performa, avg: d.avg_km_per_liter, msg: d.msg, nopol: n }
      : null
  } catch { feedback.value = null }
  await loadFeedbackHistory(n)
}

async function loadPendingLpj() {
  try {
    const rows = await api('/api/cash/pending-lpj', { params: { driver: store.driverName } })
    pendingLpj.value = Array.isArray(rows) ? rows : []
  } catch { pendingLpj.value = [] }
}

function openLpj(c) {
  store.setActiveLpj({
    cashId: c.id,
    display_id: c.display_id,
    total_amount: Number(c.total_amount) || 0,
    nopol: c.nopol || '',
    bbm_type: c.bbm_type || 'PERTALITE',
  })
  view.value = 'laporan'
  emit('toast', `📋 ${c.display_id}: isi bukti LPJ di form BBM`, 'success')
}

function onKasbonSwitch(key) {
  if (key === 'bbm') view.value = 'laporan'
}

watch(view, (v) => {
  if (v !== 'kasbon') return
  loadPendingLpj()
  store.loadDailyCode() // kode unik kasbon bisa berubah per hari
})
watch(() => store.activeLpj, (lpj) => { if (lpj) view.value = 'laporan' })

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
const odoBaseline = computed(() =>
  Number(store.profile?.last_odo_km || store.profile?.initial_odo_km || 0))
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
// v2.120.0: satu UUID per percobaan submit, dipertahankan sampai sukses agar
// retry/enqueue dikenali server sebagai pengiriman yang sama (idempoten).
let submitUuid = null

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
  // Acuan ODO: transaksi terakhir; bila belum ada, KM awal kendaraan.
  if (!form.value.odo_km) form.value.odo_km = Number(p.last_odo_km || p.initial_odo_km || 0)
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
    bbm_type: '', price_per_liter: 10000, nominal: 0, jumlah_appointment: 0, spbu_type: 'rekanan',
    odo_km: Number(store.profile?.last_odo_km || store.profile?.initial_odo_km || 0),
    voucher_partner: '', nota_no: '', liter: 0,
  }
  photos.value = { foto_odo_sebelum: null, foto_nota_odo_sesudah: null, foto_struk: null, foto_struk_dispenser: null }
  previews.value = {}; wmState.value = {}; wmBlobs.value = {}
  loadAllowedBbm(store.profile?.bbm_type)
  store.setActiveLpj(null)
  submitUuid = null
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
    gps_at: store.gps.at || '',
    gps_accuracy: store.gps.accuracy ?? '',
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
  if (!submitUuid) submitUuid = newSubmitId()
  const payload = buildPayload()
  payload.client_uuid = submitUuid
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
        const fbNopol = form.value.nopol
        emit('toast', `✅ ${label} terkirim: ${j.transaction_id || j.msg}`, 'success')
        resetForm()
        await loadFeedback(fbNopol)
      } else {
        emit('toast', '❌ ' + (j?.msg || 'Gagal mengirim'), 'error')
      }
    } catch {
      // v2.120.0: koneksi putus di tengah submit → simpan ke antrean, jangan
      // buang bukti. UUID yang sama ikut terkirim saat sync (idempoten).
      try {
        const queued = { ...payload, ...files }
        const cashId = isLpj ? store.activeLpj?.cashId : null
        await store.enqueue(isLpj ? 'lpj_queue' : 'fuel_queue', queued, cashId)
        resetForm()
        emit('toast', '🟡 Koneksi terputus — data disimpan lokal, akan dikirim otomatis', 'warning')
      } catch {
        emit('toast', '❌ Error koneksi — data tidak terkirim', 'error')
      }
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
  loadPendingLpj()
  // Auto GPS saat pertama buka
  if (!store.gps.lat && !store.gps.locating) store.locate().catch(() => {})
})
</script>

<template>
  <div class="tab-page">
    <!-- v2.130.0 — BBM & Kasbon satu tab, dua sub-tampilan. -->
    <div class="bbm-subnav" role="tablist" aria-label="BBM dan Kasbon">
      <button type="button" role="tab" :aria-selected="view === 'laporan'"
              :class="{ active: view === 'laporan' }" @click="view = 'laporan'">
        ⛽ Laporan BBM
      </button>
      <button type="button" role="tab" :aria-selected="view === 'kasbon'"
              :class="{ active: view === 'kasbon' }" @click="view = 'kasbon'">
        💰 Kasbon &amp; LPJ
        <span v-if="pendingLpj.length" class="subnav-badge">{{ pendingLpj.length }}</span>
      </button>
    </div>

    <KasbonTab v-if="view === 'kasbon'" @toast="(m, t) => emit('toast', m, t)" @switch-tab="onKasbonSwitch" />

    <template v-else>
    <!-- Kewajiban LPJ: kasbon sudah cair tetapi belum dipertanggungjawabkan. -->
    <div v-if="pendingLpj.length && !store.activeLpj" class="lpj-due">
      <div>
        <b>📋 {{ pendingLpj.length }} kasbon cair belum di-LPJ</b>
        <div class="muted" style="font-size:11px;">
          Dana sudah di tangan Anda. Isi bukti pemakaian agar kasbon selesai.
        </div>
      </div>
      <button type="button" class="btn btn-sm btn-primary" @click="openLpj(pendingLpj[0])">
        📝 Isi LPJ sekarang
      </button>
    </div>

    <!-- Feedback km/L setelah submit BBM (menggantikan tab Rapor lama) -->
    <div v-if="feedback" class="feedback-card">
      <div class="row" style="justify-content:space-between;gap:8px;">
        <b style="font-size:13px;">📊 Feedback Pemakaian BBM · {{ feedback.nopol }}</b>
        <button type="button" class="btn-icon" aria-label="Tutup feedback" @click="feedback = null">✕</button>
      </div>
      <div class="row" style="align-items:center;gap:10px;margin-top:6px;">
        <span class="badge" :class="feedback.performa === 'BOROS' ? 'badge-red' : feedback.performa === 'CUKUP' ? 'badge-amber' : 'badge-green'">
          {{ feedback.performa }}
        </span>
        <b style="font-size:16px;">{{ feedback.avg }} KM/L</b>
      </div>
      <p class="muted" style="font-size:11px;margin:6px 0 0;">{{ feedback.msg }}</p>
    </div>

    <!-- Riwayat 5 feedback terakhir — lanjutan kartu feedback after-submit. -->
    <div v-if="feedbackHistory.length" class="feedback-card" data-testid="feedback-history">
      <div class="row" style="justify-content:space-between;gap:8px;">
        <b style="font-size:13px;">🕓 Riwayat Feedback · {{ feedback?.nopol || store.profile?.nopol }}</b>
        <button type="button" class="btn-icon"
                :aria-label="showFeedbackHistory ? 'Tutup riwayat feedback' : 'Buka riwayat feedback'"
                data-testid="feedback-history-toggle"
                @click="showFeedbackHistory = !showFeedbackHistory">
          {{ showFeedbackHistory ? '✕' : '▾' }}
        </button>
      </div>
      <template v-if="showFeedbackHistory">
        <div v-for="(h, i) in feedbackHistory" :key="i"
             class="row" style="justify-content:space-between;gap:8px;font-size:11px;margin-top:6px;">
          <span class="muted">{{ h.date }}</span>
          <span><b>{{ h.km_per_liter }}</b> KM/L</span>
          <span class="badge" :class="h.performa === 'BOROS' ? 'badge-red' : h.performa === 'CUKUP' ? 'badge-amber' : 'badge-green'">
            {{ h.performa }}
          </span>
        </div>
      </template>
    </div>

    <!-- Mode LPJ -->
    <div v-if="store.activeLpj" class="alert alert-info" style="margin-bottom:10px;">
      📋 Mengisi <b>LPJ {{ store.activeLpj.display_id }}</b> — bukti pemakaian kasbon. Nominal terkunci dari kasbon (termasuk kode unik) &amp; tidak bisa diubah.
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
        💸 Klaim BBM<small>Saya bayar dulu, minta ganti</small>
      </button>
      <button type="button" role="tab" :aria-selected="mode === 'voucher'" :class="{ active: mode === 'voucher' }"
              data-testid="bbm-mode-voucher" @click="mode = 'voucher'">
        🎟️ Voucher Rekanan<small>SPBU mitra menagih kantor</small>
      </button>
    </div>

    <p v-if="!store.activeLpj" class="mode-hint">
      <b>BBM</b> = laporan pemakaian. <b>Bukan kasbon</b> — kasbon adalah uang muka perjalanan.
      <button type="button" class="link-btn" @click="view = 'kasbon'">Butuh uang muka? Buka Kasbon →</button>
    </p>

    <form class="driver-form" @submit.prevent="submit">
      <div class="field"><label>Nama Driver</label>
        <input class="input" :value="store.driverDisplayName" disabled />
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
        <div class="muted" style="margin-top:2px;">Anda tidak membayar di kasir — kantor membayar SPBU mitra per periode.</div>
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
          <div v-if="odoBaseline" class="muted" style="font-size:10px;">
            Acuan {{ odoBaseline.toLocaleString('id-ID') }} km —
            {{ store.profile?.last_odo_km ? 'ODO terakhir' : 'KM awal kendaraan' }}
          </div>
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
        {{ saving ? '⏳ Mengirim…' : store.activeLpj ? '📤 Kirim LPJ (bukti kasbon)' : (mode === 'voucher' ? '📤 Kirim Pemakaian Voucher' : '📤 Kirim Laporan BBM') }}
      </button>
      <p class="muted" style="font-size:11px;text-align:center;margin-top:6px;">
        Foto otomatis diberi watermark (perusahaan + tanggal + lokasi GPS).
      </p>
    </form>
    </template>
  </div>
</template>

<style scoped>
/* v2.130.0 — sub-navigasi BBM: Laporan BBM | Kasbon & LPJ */
.bbm-subnav {
  display: flex; gap: 6px; margin-bottom: 12px; padding: 4px;
  background: var(--surface-2, #f1f5f9); border-radius: 12px;
}
.bbm-subnav button {
  flex: 1; display: flex; align-items: center; justify-content: center; gap: 6px;
  padding: 9px 10px; border: none; border-radius: 9px; background: none; color: inherit;
  font-weight: 700; font-size: 12px; cursor: pointer; min-height: 40px;
  -webkit-tap-highlight-color: transparent;
}
.bbm-subnav button.active { background: var(--surface, #fff); color: var(--primary, #2563eb); box-shadow: 0 1px 4px rgba(15, 23, 42, .12); }
.subnav-badge {
  background: var(--danger, #dc2626); color: #fff; font-size: 10px; font-weight: 800;
  min-width: 18px; height: 18px; padding: 0 5px; border-radius: 9px;
  display: inline-flex; align-items: center; justify-content: center;
}
/* Feedback km/L after-submit */
.feedback-card {
  padding: 10px 12px; margin-bottom: 12px; border-radius: 12px;
  background: var(--bg-3, #f0fdf4); border: 1px solid var(--success, #16a34a);
}
html.dark .feedback-card { background: rgba(22, 163, 74, .12); }
.badge { font-size:10px; padding:2px 8px; border-radius:8px; font-weight:800; }
.badge-amber { background:#fef3c7; color:#92400e; }
.badge-green { background:#d1fae5; color:#065f46; }
.badge-red { background:#fee2e2; color:#b91c1c; }

/* Kewajiban LPJ setelah kasbon cair */
.lpj-due {
  display: flex; align-items: center; gap: 10px; flex-wrap: wrap;
  padding: 10px 12px; margin-bottom: 12px; border-radius: 12px;
  background: #fffbeb; border: 1px solid #fde68a; color: #92400e;
}
html.dark .lpj-due { background: rgba(245, 158, 11, .15); border-color: rgba(245, 158, 11, .4); color: #fcd34d; }
.mode-switch { display: flex; gap: 8px; margin-bottom: 12px; }
.mode-switch button {
  flex: 1; display: flex; flex-direction: column; align-items: flex-start; gap: 2px;
  padding: 10px 12px; border: 1px solid var(--border); border-radius: 10px;
  background: var(--surface, #fff); color: inherit; cursor: pointer; text-align: left;
  font-weight: 700; font-size: 13px;
}
.mode-switch button small { font-weight: 400; font-size: 10px; opacity: .7; }
.mode-switch button.active { border-color: var(--primary, #2563eb); background: #eff6ff; }
.mode-hint { margin: -4px 0 10px; font-size: 11px; line-height: 1.45; opacity: .85; }
.link-btn { background: none; border: none; padding: 0; color: var(--primary, #2563eb); font: inherit; font-weight: 700; cursor: pointer; text-decoration: underline; }
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
