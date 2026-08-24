<script setup>
import { ref, watch } from 'vue'
import { useDriverStore } from '../../stores/driverStore'
import { api } from '../../api'
import { applyWatermark, fileToDataUrl } from '../../utils/watermark'

const store = useDriverStore()
const emit = defineEmits(['toast'])

const form = ref({
  tanggal: '', waktu_mulai: '', waktu_selesai: '', keterangan: '',
  no_kendaraan: '', broker: '', manager: '',
})
const error = ref('')
const loading = ref(false)
const done = ref(null)

// Foto
const fotoMulaiFile = ref(null)
const fotoSelesaiFile = ref(null)
const fotoMulaiPreview = ref(null)
const fotoSelesaiPreview = ref(null)

function today() {
  const d = new Date()
  const mm = String(d.getMonth() + 1).padStart(2, '0')
  const dd = String(d.getDate()).padStart(2, '0')
  return `${d.getFullYear()}-${mm}-${dd}`
}

// Pre-fill no_kendaraan dari profile
watch(() => store.profile, (p) => {
  if (p) form.value.no_kendaraan = p.nopol || form.value.no_kendaraan
}, { immediate: true })

/** GPS shared dari store (konsisten dengan BBMTab) */
async function gpsText() {
  if (store.gps.addr) return store.gps.addr
  if (store.gps.lat && store.gps.lon) return `${store.gps.lat.toFixed(5)}, ${store.gps.lon.toFixed(5)}`
  try { await store.locate(); return store.gps.addr || 'GPS tidak tersedia' }
  catch { return 'GPS tidak tersedia' }
}

async function handleFoto(event, type) {
  const file = event.target.files?.[0]
  if (!file) return
  const addr = await gpsText()
  const now = new Date().toLocaleString('id-ID', { dateStyle: 'medium', timeStyle: 'short' })
  const watermarked = await applyWatermark(file, addr, now)
  const blob = watermarked || file
  if (type === 'mulai') {
    fotoMulaiFile.value = blob
    fotoMulaiPreview.value = await fileToDataUrl(blob)
  } else {
    fotoSelesaiFile.value = blob
    fotoSelesaiPreview.value = await fileToDataUrl(blob)
  }
}

function blobToBase64(blob) {
  return new Promise((resolve) => {
    const r = new FileReader()
    r.onload = () => resolve(r.result)
    r.readAsDataURL(blob)
  })
}

async function submit() {
  error.value = ''
  if (!form.value.tanggal || !form.value.waktu_mulai) {
    error.value = 'Tanggal dan Waktu Mulai wajib diisi.'
    return
  }
  loading.value = true
  try {
    const payload = {
      ...form.value,
      nama: store.profile?.name || '',
      gps_lat: store.gps.lat ?? '',
      gps_lon: store.gps.lon ?? '',
      gps_address: store.gps.addr || '',
      gps_kelurahan: store.gps.detail?.kelurahan || '',
      gps_kecamatan: store.gps.detail?.kecamatan || '',
      gps_kota: store.gps.detail?.kota || '',
      gps_provinsi: store.gps.detail?.provinsi || '',
      gps_kode_pos: store.gps.detail?.kode_pos || '',
    }
    if (fotoMulaiFile.value) payload.foto_mulai = await blobToBase64(fotoMulaiFile.value)
    if (fotoSelesaiFile.value) payload.foto_selesai = await blobToBase64(fotoSelesaiFile.value)

    if (store.online) {
      const d = await api('/api/overtime/driver/submit', { method: 'POST', body: payload })
      done.value = { display_id: d.display_id, msg: d.msg }
      emit('toast', `✅ Overtime tercatat: ${d.display_id}`, 'success')
    } else {
      // Offline: simpan ke antrean
      await store.enqueue('overtime_queue', payload)
      done.value = { display_id: '-', msg: 'Offline — akan dikirim saat online' }
      emit('toast', '🟡 Offline — data disimpan lokal, akan dikirim otomatis', 'warning')
    }
  } catch (e) {
    error.value = e.message || 'Gagal mengirim.'
    emit('toast', '❌ ' + (e.message || 'Gagal mengirim overtime'), 'error')
  } finally {
    loading.value = false
  }
}

function reset() {
  done.value = null
  form.value = { tanggal: '', waktu_mulai: '', waktu_selesai: '', keterangan: '', no_kendaraan: store.profile?.nopol || '', broker: '', manager: '' }
  fotoMulaiFile.value = null
  fotoSelesaiFile.value = null
  fotoMulaiPreview.value = null
  fotoSelesaiPreview.value = null
  error.value = ''
}
</script>

<template>
  <div class="ot-card">
    <!-- GPS Box -->
    <div class="gps-box" :class="{ ok: store.gps.addr }">
      <div class="gps-title">
        <template v-if="store.gps.locating">🔍 Mencari lokasi…</template>
        <template v-else-if="store.gps.addr">📍 Lokasi Terdeteksi</template>
        <template v-else>⚠ GPS Belum Aktif</template>
      </div>
      <div class="gps-addr">{{ store.gps.addr || 'GPS akan otomatis aktif saat mengambil foto.' }}</div>
      <div v-if="store.gps.lat" class="gps-coord">📍 {{ store.gps.lat?.toFixed(5) }}, {{ store.gps.lon?.toFixed(5) }}</div>
      <button class="btn btn-sm" :disabled="store.gps.locating" style="margin-top:6px;" @click="store.locate()">📍 Aktifkan Lokasi</button>
    </div>

    <!-- SUCCESS -->
    <div v-if="done" class="ot-success">
      <div style="font-size:40px;">✅</div>
      <h3 style="margin:8px 0 4px;">Overtime Tercatat!</h3>
      <div class="info-box">
        <div><span>No.</span><b>{{ done.display_id }}</b></div>
        <div><span>Status</span><b>{{ done.msg }}</b></div>
      </div>
      <p style="font-size:11px;color:var(--text-3);margin-top:10px;">
        Simpan nomor di atas sebagai bukti. Data bisa dilihat oleh GA HR.
      </p>
      <button class="btn btn-primary" style="width:100%;margin-top:10px;" @click="reset">📝 Isi Lagi</button>
    </div>

    <!-- FORM -->
    <form v-else @submit.prevent="submit">
      <div v-if="error" class="alert alert-error" style="margin-bottom:10px;">{{ error }}</div>

      <div class="field">
        <label>Tanggal <span class="req">*</span></label>
        <input class="input" type="date" v-model="form.tanggal" :max="today()" required />
      </div>

      <div class="row" style="gap:8px;">
        <div class="field grow">
          <label>Waktu Mulai <span class="req">*</span></label>
          <input class="input" type="time" v-model="form.waktu_mulai" required />
        </div>
        <div class="field grow">
          <label>Waktu Selesai</label>
          <input class="input" type="time" v-model="form.waktu_selesai" />
        </div>
      </div>

      <div class="field">
        <label>No. Kendaraan</label>
        <input class="input" v-model="form.no_kendaraan" placeholder="cth: B 1234 XX" />
      </div>

      <div class="row" style="gap:8px;">
        <div class="field grow">
          <label>Broker</label>
          <input class="input" v-model="form.broker" placeholder="Nama broker" />
        </div>
        <div class="field grow">
          <label>Manager</label>
          <input class="input" v-model="form.manager" placeholder="Nama manager" />
        </div>
      </div>

      <div class="field">
        <label>Keterangan</label>
        <input class="input" v-model="form.keterangan" placeholder="cth: Lembur malam" />
      </div>

      <!-- FOTO -->
      <div class="foto-section">
        <label style="font-size:12px;font-weight:600;">📷 Foto Bukti Timestamp</label>
        <p style="font-size:10px;color:var(--text-3);margin:2px 0 8px;">Watermark otomatis (nama perusahaan + tanggal + GPS)</p>
        <div class="row" style="gap:8px;">
          <div class="foto-box">
            <label class="foto-input" :class="{ 'has-foto': fotoMulaiPreview }">
              <template v-if="fotoMulaiPreview">
                <img :src="fotoMulaiPreview" class="foto-thumb" />
                <span class="foto-badge">✅ Mulai</span>
              </template>
              <template v-else>
                <span style="font-size:24px;">📷</span>
                <span style="font-size:11px;font-weight:600;">Foto Mulai</span>
              </template>
            </label>
            <div class="foto-btns">
              <input type="file" accept="image/*" capture="environment" class="file-input-hidden" id="ot_cam_mulai" @change="handleFoto($event, 'mulai')" />
              <label class="btn btn-xs" for="ot_cam_mulai">📷 Kamera</label>
              <input type="file" accept="image/*" class="file-input-hidden" id="ot_gal_mulai" @change="handleFoto($event, 'mulai')" />
              <label class="btn btn-xs btn-outline" for="ot_gal_mulai">🖼️ Galeri</label>
            </div>
          </div>
          <div class="foto-box">
            <label class="foto-input" :class="{ 'has-foto': fotoSelesaiPreview }">
              <template v-if="fotoSelesaiPreview">
                <img :src="fotoSelesaiPreview" class="foto-thumb" />
                <span class="foto-badge">✅ Selesai</span>
              </template>
              <template v-else>
                <span style="font-size:24px;">📷</span>
                <span style="font-size:11px;font-weight:600;">Foto Selesai</span>
              </template>
            </label>
            <div class="foto-btns">
              <input type="file" accept="image/*" capture="environment" class="file-input-hidden" id="ot_cam_selesai" @change="handleFoto($event, 'selesai')" />
              <label class="btn btn-xs" for="ot_cam_selesai">📷 Kamera</label>
              <input type="file" accept="image/*" class="file-input-hidden" id="ot_gal_selesai" @change="handleFoto($event, 'selesai')" />
              <label class="btn btn-xs btn-outline" for="ot_gal_selesai">🖼️ Galeri</label>
            </div>
          </div>
        </div>
      </div>

      <button class="btn btn-primary" style="width:100%;margin-top:12px;padding:10px;" :disabled="loading">
        {{ loading ? '⏳ Mengirim…' : '📤 Kirim Overtime' }}
      </button>
    </form>
  </div>
</template>

<style scoped>
.gps-box { border: 1px dashed var(--border); border-radius: 10px; padding: 10px 12px; margin-bottom: 12px; background: var(--bg-2, #fef3c7); }
.gps-box.ok { background: var(--bg-3, #f0fdf4); border-color: #059669; }
.gps-title { font-size: 13px; font-weight: 700; }
.gps-addr { font-size: 11px; opacity: .8; margin-top: 2px; }
.gps-coord { font-size: 10px; opacity: .5; margin-top: 2px; font-family: monospace; }
.ot-card { padding: 0; }
.ot-success { text-align: center; padding: 16px 0; }
.info-box {
  margin-top: 10px; background: var(--bg); border: 1px solid var(--border);
  border-radius: 10px; padding: 10px; display: grid; gap: 6px; text-align: left;
}
.info-box span { font-size: 10px; color: var(--text-3); }
.info-box b { font-size: 13px; }
.foto-section { margin: 12px 0; }
.foto-box { flex: 1; min-width: 110px; }
.foto-input {
  display: flex; flex-direction: column; align-items: center; justify-content: center;
  min-height: 90px; border: 2px dashed var(--border); border-radius: 10px;
  cursor: pointer; transition: all .2s; overflow: hidden; position: relative;
}
.foto-input:hover { border-color: var(--primary, #7c3aed); }
.foto-input.has-foto { border-style: solid; border-color: #22c55e; }
.foto-thumb { width: 100%; height: 90px; object-fit: cover; border-radius: 8px; }
.foto-badge {
  position: absolute; bottom: 4px; left: 50%; transform: translateX(-50%);
  background: rgba(0,0,0,.6); color: #fff; font-size: 9px; font-weight: 600;
  padding: 2px 8px; border-radius: 16px; white-space: nowrap;
}
.foto-btns { display: flex; gap: 4px; margin-top: 4px; justify-content: center; }
.file-input-hidden { display: none; }
</style>
