<script setup>
import { ref } from 'vue'
import { useDriverStore } from '../../stores/driverStore'
import { api } from '../../api'
import { applyWatermark, fileToDataUrl } from '../../utils/watermark'

const store = useDriverStore()
const brandIcon = '/static/icon-192.png'

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

function getGpsText() {
  return new Promise((resolve) => {
    if (!navigator.geolocation) return resolve('GPS tidak tersedia')
    navigator.geolocation.getCurrentPosition(
      (pos) => resolve(`${pos.coords.latitude.toFixed(5)}, ${pos.coords.longitude.toFixed(5)}`),
      () => resolve('GPS tidak tersedia'),
      { timeout: 5000 }
    )
  })
}

async function handleFoto(event, type) {
  const file = event.target.files?.[0]
  if (!file) return
  const gpsText = await getGpsText()
  const now = new Date().toLocaleString('id-ID', { dateStyle: 'medium', timeStyle: 'short' })
  const watermarked = await applyWatermark(file, gpsText, now)
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
    }
    if (fotoMulaiFile.value) payload.foto_mulai = await blobToBase64(fotoMulaiFile.value)
    if (fotoSelesaiFile.value) payload.foto_selesai = await blobToBase64(fotoSelesaiFile.value)

    const d = await api('/api/overtime/driver/submit', { method: 'POST', body: payload })
    done.value = { display_id: d.display_id, msg: d.msg }
  } catch (e) {
    error.value = e.message || 'Gagal mengirim.'
  } finally {
    loading.value = false
  }
}

function reset() {
  done.value = null
  form.value = { tanggal: '', waktu_mulai: '', waktu_selesai: '', keterangan: '', no_kendaraan: '', broker: '', manager: '' }
  fotoMulaiFile.value = null
  fotoSelesaiFile.value = null
  fotoMulaiPreview.value = null
  fotoSelesaiPreview.value = null
  error.value = ''
}
</script>

<template>
  <div class="ot-card">
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
              <input type="file" accept="image/*" capture="environment" @change="handleFoto($event, 'mulai')" hidden />
              <template v-if="fotoMulaiPreview">
                <img :src="fotoMulaiPreview" class="foto-thumb" />
                <span class="foto-badge">✅ Mulai</span>
              </template>
              <template v-else>
                <span style="font-size:24px;">📷</span>
                <span style="font-size:11px;font-weight:600;">Foto Mulai</span>
              </template>
            </label>
          </div>
          <div class="foto-box">
            <label class="foto-input" :class="{ 'has-foto': fotoSelesaiPreview }">
              <input type="file" accept="image/*" capture="environment" @change="handleFoto($event, 'selesai')" hidden />
              <template v-if="fotoSelesaiPreview">
                <img :src="fotoSelesaiPreview" class="foto-thumb" />
                <span class="foto-badge">✅ Selesai</span>
              </template>
              <template v-else>
                <span style="font-size:24px;">📷</span>
                <span style="font-size:11px;font-weight:600;">Foto Selesai</span>
              </template>
            </label>
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
</style>
