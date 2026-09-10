<script setup>
import { ref, onMounted, computed } from 'vue'
import { api } from '../api'
import { useAuthStore } from '../stores/auth'
import { applyWatermark, fileToDataUrl } from '../utils/watermark'
import { getPosition, detailedLocation } from '../utils/gps'

/**
 * Form Overtime — user OB & Security (v2.39), dari dalam aplikasi (login).
 *
 * Kolom mengikuti sheet sumber overtime OB/Security (Apps Script contract):
 * Tanggal, Waktu Mulai, Waktu Selesai, Keterangan + foto bukti & GPS.
 * Identitas (Nama & Posisi) dikunci dari sesi login — tidak bisa dipilih.
 * Posisi otomatis: role ob → "OB", role security → "Security".
 */
const auth = useAuthStore()
const isSecurity = computed(() => auth.role === 'security')

const form = ref({ tanggal: '', waktu_mulai: '', waktu_selesai: '', keterangan: '' })
const error = ref('')
const loading = ref(false)
const done = ref(null) // { display_id, msg }

// Riwayat pribadi
const history = ref([])
const histLoading = ref(false)

// --- GPS (paritas form publik) ---
const gps = ref({ lat: '', lon: '', address: '', kelurahan: '', kecamatan: '', kota: '', provinsi: '', kode_pos: '' })
const gpsStatus = ref('')
const gpsLoading = ref(false)

// --- Foto bukti (watermark seperti form publik) ---
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

async function locate() {
  gpsLoading.value = true
  try {
    const pos = await getPosition()
    const d = await detailedLocation(pos.coords.latitude, pos.coords.longitude)
    gps.value = {
      lat: String(d.lat ?? ''), lon: String(d.lon ?? ''),
      address: d.full_address || '', kelurahan: d.kelurahan || '',
      kecamatan: d.kecamatan || '', kota: d.kota || '',
      provinsi: d.provinsi || '', kode_pos: d.kode_pos || '',
    }
    gpsStatus.value = '✅ ' + (d.full_address || `${d.lat}, ${d.lon}`)
  } catch {
    gpsStatus.value = '⚠️ GPS tidak tersedia — foto tetap diberi watermark tanggal & perusahaan'
  } finally {
    gpsLoading.value = false
  }
}

async function handleFoto(event, type) {
  const file = event.target.files?.[0]
  if (!file) return
  const gpsText = gps.value.lat && gps.value.lon
    ? `${Number(gps.value.lat).toFixed(5)}, ${Number(gps.value.lon).toFixed(5)}`
    : 'GPS tidak tersedia'
  const now = new Date().toLocaleString('id-ID', { dateStyle: 'medium', timeStyle: 'short' })
  try {
    const watermarked = await applyWatermark(file, gpsText, now)
    const blob = watermarked || file
    if (type === 'mulai') {
      fotoMulaiFile.value = blob
      fotoMulaiPreview.value = await fileToDataUrl(blob)
    } else {
      fotoSelesaiFile.value = blob
      fotoSelesaiPreview.value = await fileToDataUrl(blob)
    }
  } catch {
    if (type === 'mulai') { fotoMulaiFile.value = file; fotoMulaiPreview.value = await fileToDataUrl(file) }
    else { fotoSelesaiFile.value = file; fotoSelesaiPreview.value = await fileToDataUrl(file) }
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
      gps_lat: gps.value.lat, gps_lon: gps.value.lon, gps_address: gps.value.address,
      gps_kelurahan: gps.value.kelurahan, gps_kecamatan: gps.value.kecamatan,
      gps_kota: gps.value.kota, gps_provinsi: gps.value.provinsi, gps_kode_pos: gps.value.kode_pos,
    }
    if (fotoMulaiFile.value) payload.foto_mulai = await blobToBase64(fotoMulaiFile.value)
    if (fotoSelesaiFile.value) payload.foto_selesai = await blobToBase64(fotoSelesaiFile.value)
    const d = await api('/api/overtime/me/submit', { method: 'POST', body: payload })
    done.value = { display_id: d.display_id, msg: d.msg }
    loadHistory()
  } catch (e) {
    error.value = e.message || 'Gagal mengirim. Coba lagi.'
  } finally {
    loading.value = false
  }
}

function reset() {
  done.value = null
  form.value = { tanggal: '', waktu_mulai: '', waktu_selesai: '', keterangan: '' }
  fotoMulaiFile.value = null
  fotoSelesaiFile.value = null
  fotoMulaiPreview.value = null
  fotoSelesaiPreview.value = null
  error.value = ''
}

async function loadHistory() {
  histLoading.value = true
  try {
    const d = await api('/api/overtime/mine')
    history.value = d.data || []
  } catch { history.value = [] } finally { histLoading.value = false }
}

onMounted(() => {
  locate()
  loadHistory()
})
</script>

<template>
  <div class="page">
    <div class="card card-pad" style="margin-bottom:16px;">
      <h2 style="margin:0 0 2px;">⏰ Overtime {{ isSecurity ? 'Security' : 'OB' }}</h2>
      <div class="muted" style="font-size:12px;">
        Catat lembur Anda — Nama &amp; Posisi otomatis dari akun Anda ({{ auth.user?.full_name || auth.user?.user_name }}),
        sama seperti kolom di Google Sheet sumber data.
      </div>
    </div>

    <div class="ot-grid">
      <!-- FORM -->
      <div class="card card-pad">
        <div v-if="done" class="ot-success">
          <div style="font-size:40px;">✅</div>
          <h3 style="margin:8px 0 4px;">Overtime Tercatat!</h3>
          <div class="info-box">
            <div><span>No. Pengajuan</span><b>{{ done.display_id }}</b></div>
            <div><span>Status</span><b>{{ done.msg }}</b></div>
          </div>
          <p class="muted" style="font-size:11px;margin-top:10px;">
            Simpan nomor di atas sebagai bukti. Data bisa dilihat oleh GA HR.
          </p>
          <button class="btn btn-primary" style="width:100%;justify-content:center;margin-top:10px;" @click="reset">📝 Isi Overtime Lagi</button>
        </div>

        <form v-else @submit.prevent="submit">
          <div v-if="error" class="alert alert-error">{{ error }}</div>

          <div class="row" style="gap:10px;">
            <div class="field grow">
              <label>Nama (otomatis)</label>
              <input class="input" :value="auth.user?.full_name || auth.user?.user_name" disabled />
            </div>
            <div class="field" style="max-width:150px;">
              <label>Posisi (otomatis)</label>
              <input class="input" :value="isSecurity ? 'Security' : 'OB'" disabled />
            </div>
          </div>

          <div class="field">
            <label>Tanggal Overtime <span class="req">*</span></label>
            <input class="input" type="date" v-model="form.tanggal" :max="today()" required />
          </div>

          <div class="row" style="gap:10px;">
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
            <label>Keterangan</label>
            <input class="input" v-model="form.keterangan" placeholder="cth: OT malam / Keamanan kantor / Standby" />
          </div>

          <div class="foto-section">
            <label class="foto-label">📷 Foto Bukti Timestamp</label>
            <p class="muted" style="font-size:11px;margin:2px 0 10px;">Foto diberi watermark otomatis (perusahaan + tanggal + GPS)</p>
            <div class="row" style="gap:10px;">
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
                  </template>
                </label>
              </div>
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
                  </template>
                </label>
              </div>
            </div>
          </div>

          <div class="gps-box">
            <div class="row" style="justify-content:space-between;align-items:center;gap:8px;">
              <label class="foto-label">📍 Lokasi (GPS)</label>
              <button type="button" class="btn btn-xs" :disabled="gpsLoading" @click="locate">{{ gpsLoading ? '⏳ Deteksi…' : '🔄 Deteksi Ulang' }}</button>
            </div>
            <p style="font-size:11px;margin:4px 0 0;word-break:break-word;">{{ gpsStatus || 'Mendeteksi lokasi…' }}</p>
          </div>

          <button class="btn btn-primary" style="width:100%;justify-content:center;padding:11px;" :disabled="loading">
            {{ loading ? '⏳ Mengirim…' : '📤 Kirim Overtime' }}
          </button>
        </form>
      </div>

      <!-- RIWAYAT -->
      <div class="card card-pad">
        <h3 style="margin:0 0 10px;font-size:15px;">🕘 Riwayat Overtime Saya</h3>
        <div v-if="histLoading" class="muted" style="font-size:12px;">⏳ Memuat…</div>
        <div v-else-if="!history.length" class="muted" style="font-size:12px;">Belum ada data overtime.</div>
        <table v-else class="table">
          <thead>
            <tr>
              <th>No.</th>
              <th>Tanggal</th>
              <th>Waktu</th>
              <th>Keterangan</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="r in history" :key="r.id">
              <td style="font-size:11px;">{{ r.display_id }}</td>
              <td>{{ r.tanggal || '—' }}</td>
              <td>{{ [r.waktu_mulai || '—', r.waktu_selesai].filter(Boolean).join(' – ') }}</td>
              <td style="font-size:11px;">{{ r.keterangan || '—' }}</td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  </div>
</template>

<style scoped>
.ot-grid { display: grid; grid-template-columns: minmax(0, 1.2fr) minmax(0, 1fr); gap: 16px; align-items: start; }
@media (max-width: 900px) { .ot-grid { grid-template-columns: 1fr; } }
.ot-success { text-align: center; padding: 10px 0; }
.info-box {
  margin-top: 12px; background: var(--bg); border: 1px solid var(--border); border-radius: 12px;
  padding: 14px; text-align: left; display: grid; gap: 10px;
}
.info-box span { display: block; font-size: 11px; color: var(--text-3); }
.info-box b { font-size: 14px; }
.foto-section { margin: 14px 0; }
.gps-box { margin: 12px 0; padding: 10px 12px; border: 1px solid var(--border); border-radius: 10px; background: var(--bg); }
.btn-xs { padding: 3px 10px; font-size: 11px; }
.foto-label { font-size: 13px; font-weight: 600; }
.foto-box { flex: 1; min-width: 130px; }
.foto-input {
  display: flex; flex-direction: column; align-items: center; justify-content: center;
  min-height: 110px; border: 2px dashed var(--border); border-radius: 12px;
  cursor: pointer; transition: all .2s; overflow: hidden; position: relative;
}
.foto-input:hover { border-color: var(--primary, #7c3aed); background: rgba(124,58,237,.04); }
.foto-input.has-foto { border-style: solid; border-color: #22c55e; }
.foto-icon { font-size: 26px; margin-bottom: 4px; }
.foto-text { font-size: 12px; font-weight: 600; color: var(--text-2); }
.foto-thumb { width: 100%; height: 110px; object-fit: cover; border-radius: 10px; }
.foto-badge {
  position: absolute; bottom: 6px; left: 50%; transform: translateX(-50%);
  background: rgba(0,0,0,.6); color: #fff; font-size: 10px; font-weight: 600;
  padding: 2px 10px; border-radius: 20px; white-space: nowrap;
}
</style>
