<script setup>
import { ref } from 'vue'
import { api } from '../api'
import { applyWatermark, fileToDataUrl } from '../utils/watermark'

const brandIcon = '/static/icon-192.png'
const form = ref({
  nama: '', posisi: '', tanggal: '', waktu_mulai: '', waktu_selesai: '', keterangan: '', email: '',
})
const error = ref('')
const loading = ref(false)
const done = ref(null) // { display_id, msg }
const names = ref([])
const keterangan = ref([])

// --- Foto ---
const fotoMulaiFile = ref(null)
const fotoSelesaiFile = ref(null)
const fotoMulaiPreview = ref(null)
const fotoSelesaiPreview = ref(null)

async function loadMeta() {
  try {
    const d = await api('/api/overtime/form-meta')
    names.value = d.names || []
    keterangan.value = d.keterangan || []
  } catch {
    names.value = []
    keterangan.value = []
  }
}

function today() {
  const d = new Date()
  const mm = String(d.getMonth() + 1).padStart(2, '0')
  const dd = String(d.getDate()).padStart(2, '0')
  return `${d.getFullYear()}-${mm}-${dd}`
}

/** Get GPS text from browser */
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

/** Handle foto selection: apply watermark + generate preview */
async function handleFoto(event, type) {
  const file = event.target.files?.[0]
  if (!file) return

  const gpsText = await getGpsText()
  const now = new Date().toLocaleString('id-ID', { dateStyle: 'medium', timeStyle: 'short' })

  // Apply watermark
  const watermarked = await applyWatermark(file, gpsText, now)
  const blob = watermarked || file

  // Store file for upload
  if (type === 'mulai') {
    fotoMulaiFile.value = blob
    fotoMulaiPreview.value = await fileToDataUrl(blob)
  } else {
    fotoSelesaiFile.value = blob
    fotoSelesaiPreview.value = await fileToDataUrl(blob)
  }
}

/** Convert blob to base64 */
function blobToBase64(blob) {
  return new Promise((resolve) => {
    const r = new FileReader()
    r.onload = () => resolve(r.result)
    r.readAsDataURL(blob)
  })
}

async function submit() {
  error.value = ''
  if (!form.value.nama.trim() || !form.value.posisi || !form.value.tanggal || !form.value.waktu_mulai) {
    error.value = 'Nama, Posisi, Tanggal, dan Waktu Mulai wajib diisi.'
    return
  }
  loading.value = true
  try {
    // Convert foto to base64
    const payload = { ...form.value }
    if (fotoMulaiFile.value) {
      payload.foto_mulai = await blobToBase64(fotoMulaiFile.value)
    }
    if (fotoSelesaiFile.value) {
      payload.foto_selesai = await blobToBase64(fotoSelesaiFile.value)
    }
    const d = await api('/api/overtime', { method: 'POST', body: payload })
    done.value = { display_id: d.display_id, msg: d.msg }
  } catch (e) {
    error.value = e.message || 'Gagal mengirim. Coba lagi.'
  } finally {
    loading.value = false
  }
}

function reset() {
  done.value = null
  form.value = { nama: '', posisi: '', tanggal: '', waktu_mulai: '', waktu_selesai: '', keterangan: '', email: '' }
  fotoMulaiFile.value = null
  fotoSelesaiFile.value = null
  fotoMulaiPreview.value = null
  fotoSelesaiPreview.value = null
  error.value = ''
}

loadMeta()
</script>

<template>
  <div class="apply-page">
    <div class="apply-card">
      <div class="apply-brand">
        <img :src="brandIcon" alt="BPF" />
        <h1>Form Overtime OB &amp; Security</h1>
        <p>PT Bestprofit Futures · Surabaya</p>
        <p style="font-size:11px;color:#6b7280;margin:0;">Graha Bukopin Lantai 11, Jl. Panglima Sudirman No. 10-18</p>
      </div>

      <!-- SUCCESS -->
      <div v-if="done" class="apply-success">
        <div class="check-ico">✅</div>
        <h2>Overtime Tercatat!</h2>
        <div class="info-box">
          <div><span>No. Pengajuan</span><b>{{ done.display_id }}</b></div>
          <div><span>Status</span><b>{{ done.msg }}</b></div>
        </div>
        <p class="muted" style="font-size:12px;margin-top:12px;">
          Data Anda sudah kami terima dan bisa dilihat oleh tim GA HR.
          Simpan nomor pengajuan di atas sebagai bukti.
        </p>
        <button class="btn btn-primary" style="width:100%;justify-content:center;" @click="reset">📝 Isi Overtime Lain</button>
      </div>

      <!-- FORM -->
      <form v-else @submit.prevent="submit">
        <div v-if="error" class="alert alert-error">{{ error }}</div>

        <div class="field">
          <label>Posisi <span class="req">*</span></label>
          <select class="select" v-model="form.posisi" required>
            <option value="">— Pilih Posisi —</option>
            <option value="OB">OB (Office Boy)</option>
            <option value="Security">Security</option>
          </select>
        </div>

        <div class="field">
          <label>Nama <span class="req">*</span></label>
          <select class="select" v-model="form.nama" required>
            <option value="">— Pilih Nama —</option>
            <option v-for="n in names" :key="n" :value="n">{{ n }}</option>
          </select>
        </div>

        <div class="field">
          <label>Tanggal Overtime <span class="req">*</span></label>
          <input class="input" type="date" v-model="form.tanggal" :max="today()" required />
        </div>

        <div class="row" style="gap:10px;align-items:flex-end;">
          <div class="field grow">
            <label>Waktu Mulai <span class="req">*</span></label>
            <input class="input" type="time" v-model="form.waktu_mulai" required />
          </div>
          <div class="field grow">
            <label>Waktu Selesai</label>
            <input class="input" type="time" v-model="form.waktu_selesai" />
          </div>
        </div>

        <!-- FOTO BUKTI -->
        <div class="foto-section">
          <label class="foto-label">📷 Foto Bukti Timestamp</label>
          <p class="muted" style="font-size:11px;margin:2px 0 10px;">Foto akan diberi watermark otomatis (nama perusahaan + tanggal + GPS)</p>

          <div class="row" style="gap:10px;">
            <!-- Foto Mulai -->
            <div class="foto-box">
              <label class="foto-input" :class="{ 'has-foto': fotoMulaiPreview }">
                <input type="file" accept="image/*" @change="handleFoto($event, 'mulai')" hidden />
                <template v-if="fotoMulaiPreview">
                  <img :src="fotoMulaiPreview" class="foto-thumb" />
                  <span class="foto-badge">✅ Mulai</span>
                </template>
                <template v-else>
                  <span class="foto-icon">📷</span>
                  <span class="foto-text">Foto Mulai</span>
                  <span class="foto-hint">Tap untuk ambil foto</span>
                </template>
              </label>
            </div>

            <!-- Foto Selesai -->
            <div class="foto-box">
              <label class="foto-input" :class="{ 'has-foto': fotoSelesaiPreview }">
                <input type="file" accept="image/*" @change="handleFoto($event, 'selesai')" hidden />
                <template v-if="fotoSelesaiPreview">
                  <img :src="fotoSelesaiPreview" class="foto-thumb" />
                  <span class="foto-badge">✅ Selesai</span>
                </template>
                <template v-else>
                  <span class="foto-icon">📷</span>
                  <span class="foto-text">Foto Selesai</span>
                  <span class="foto-hint">Tap untuk ambil foto</span>
                </template>
              </label>
            </div>
          </div>
        </div>

        <div class="field">
          <label>Keterangan</label>
          <input class="input" v-model="form.keterangan" list="ket-options" placeholder="cth: OT malam / Keamanan kantor / Standby" />
          <datalist id="ket-options">
            <option v-for="k in keterangan" :key="k" :value="k"></option>
          </datalist>
        </div>

        <div class="field">
          <label>Email (opsional)</label>
          <input class="input" v-model="form.email" type="email" placeholder="nama@email.com" />
        </div>

        <button class="btn btn-primary" style="width:100%;justify-content:center;padding:11px;" :disabled="loading">
          {{ loading ? '⏳ Mengirim…' : '📤 Kirim Overtime' }}
        </button>
        <div class="apply-note">
          ⏱️ Form ini terbuka untuk karyawan OB &amp; Security — tanpa perlu login.
        </div>
      </form>
    </div>
  </div>
</template>

<style scoped>
.apply-page {
  min-height: 100vh; display: flex; align-items: center; justify-content: center; padding: 24px;
  background:
    radial-gradient(at 0% 0%, rgba(126, 34, 206, .10) 0px, transparent 50%),
    radial-gradient(at 100% 100%, rgba(37, 99, 235, .08) 0px, transparent 50%), var(--bg);
}
.apply-card {
  width: 100%; max-width: 460px; background: var(--surface); border: 1px solid var(--border);
  border-radius: 16px; padding: 30px 28px; box-shadow: var(--shadow-lg); animation: popIn .2s ease;
}
.apply-brand { text-align: center; margin-bottom: 18px; }
.apply-brand img { width: 54px; height: 54px; border-radius: 13px; box-shadow: 0 4px 14px rgba(126, 34, 206, .25); }
.apply-brand h1 { font-size: 18px; font-weight: 800; margin-top: 10px; }
.apply-brand p { font-size: 11px; color: var(--text-3); margin-top: 2px; }
.apply-success { text-align: center; }
.check-ico { font-size: 44px; }
.apply-success h2 { font-size: 17px; margin-top: 6px; }
.info-box {
  margin-top: 14px; background: var(--bg); border: 1px solid var(--border); border-radius: 12px;
  padding: 14px; text-align: left; display: grid; gap: 10px;
}
.info-box span { display: block; font-size: 11px; color: var(--text-3); }
.info-box b { font-size: 14px; }
.apply-note { margin-top: 14px; font-size: 11px; color: var(--text-3); text-align: center; line-height: 1.5; }

/* Foto section */
.foto-section { margin: 16px 0; }
.foto-label { font-size: 13px; font-weight: 600; }
.foto-box { flex: 1; min-width: 130px; }
.foto-input {
  display: flex; flex-direction: column; align-items: center; justify-content: center;
  min-height: 120px; border: 2px dashed var(--border); border-radius: 12px;
  cursor: pointer; transition: all .2s; overflow: hidden; position: relative;
}
.foto-input:hover { border-color: var(--primary, #7c3aed); background: rgba(124,58,237,.04); }
.foto-input.has-foto { border-style: solid; border-color: #22c55e; }
.foto-icon { font-size: 28px; margin-bottom: 4px; }
.foto-text { font-size: 12px; font-weight: 600; color: var(--text-2); }
.foto-hint { font-size: 10px; color: var(--text-3); margin-top: 2px; }
.foto-thumb { width: 100%; height: 120px; object-fit: cover; border-radius: 10px; }
.foto-badge {
  position: absolute; bottom: 6px; left: 50%; transform: translateX(-50%);
  background: rgba(0,0,0,.6); color: #fff; font-size: 10px; font-weight: 600;
  padding: 2px 10px; border-radius: 20px; white-space: nowrap;
}
</style>
