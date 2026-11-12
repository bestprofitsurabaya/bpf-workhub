<script setup>
import { computed, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'

const brandIcon = '/static/icon-192.png'
const PENDIDIKAN = ['SMA', 'SMK', 'MA', 'D3', 'D4', 'S1', 'S2', 'S3']
const DRAFT_KEY = 'bpf_fw_draft_v1'
const STEPS = ['Data Diri', 'Kontak & Referensi', 'Identitas']

// Cabang tujuan diambil dari link (?cabang=MLG). Server tetap memvalidasi
// terhadap master branches dan menolak nilai asing (jatuh ke SBY).
const linkParams = new URLSearchParams(window.location.search)
const linkBranch = (linkParams.get('cabang') || linkParams.get('branch') || '').trim().toUpperCase()
// v2.82.0: token form milik cabang. Tanpa token yang cocok, isian tidak bisa
// dikirim atas nama cabang tersebut (anti tukar/mix antar cabang).
const linkToken = (linkParams.get('t') || linkParams.get('token') || '').trim()
const branchLabel = ref('')
const resolvedBranch = ref(linkBranch)
// v2.86.0: status keabsahan tautan. 'loading' → 'ok' (tautan sah) atau
// 'invalid' (ditolak server) — tautan tidak sah dirender sebagai halaman
// penolakan penuh, TANPA form dan TANPA branding cabang mana pun.
const linkState = ref('loading')
const linkError = ref('')

// Kode provinsi pada 2 digit pertama NIK.
const PROVINSI = {
  11: 'Aceh', 12: 'Sumatera Utara', 13: 'Sumatera Barat', 14: 'Riau', 15: 'Jambi',
  16: 'Sumatera Selatan', 17: 'Bengkulu', 18: 'Lampung', 19: 'Bangka Belitung',
  21: 'Kepulauan Riau', 31: 'DKI Jakarta', 32: 'Jawa Barat', 33: 'Jawa Tengah',
  34: 'DI Yogyakarta', 35: 'Jawa Timur', 36: 'Banten', 51: 'Bali',
  52: 'Nusa Tenggara Barat', 53: 'Nusa Tenggara Timur', 61: 'Kalimantan Barat',
  62: 'Kalimantan Tengah', 63: 'Kalimantan Selatan', 64: 'Kalimantan Timur',
  65: 'Kalimantan Utara', 71: 'Sulawesi Utara', 72: 'Sulawesi Tengah',
  73: 'Sulawesi Selatan', 74: 'Sulawesi Tenggara', 75: 'Gorontalo',
  76: 'Sulawesi Barat', 81: 'Maluku', 82: 'Maluku Utara', 91: 'Papua',
  92: 'Papua Barat', 93: 'Papua Selatan', 94: 'Papua Tengah',
  95: 'Papua Pegunungan', 96: 'Papua Barat Daya',
}

const form = reactive({
  nik: '', nama: '', pendidikan: '',
  referrer_id: '', referensi_text: '', no_hp: '',
})
const referrers = ref([])
const metaLoading = ref(true)
const ktpFile = ref(null)
const ktpLabel = ref('')
const ktpPreview = ref('')
const error = ref('')
const submitting = ref(false)
// v2.85.0: persetujuan pemrosesan data pribadi (UU PDP) wajib sebelum kirim.
const consent = ref(false)
const done = ref(null)
const step = ref(0)
const restored = ref(false)
const nikCheck = reactive({ state: 'idle', exists: false })

const manualRef = computed(() => form.referrer_id === 'manual')
const pct = computed(() => Math.round(((step.value) / STEPS.length) * 100))

// --- NIK: baca jenis kelamin, tanggal lahir, dan provinsi ---
const nikInfo = computed(() => {
  if (form.nik.length !== 16) return null
  const province = PROVINSI[Number(form.nik.slice(0, 2))] || ''
  let dd = Number(form.nik.slice(6, 8))
  let mm = Number(form.nik.slice(8, 10))
  const yy = Number(form.nik.slice(10, 12))
  const female = mm > 40
  if (female) mm -= 40
  const year = yy > 26 ? 1900 + yy : 2000 + yy
  const date = new Date(year, mm - 1, dd)
  const validDate = dd >= 1 && dd <= 31 && mm >= 1 && mm <= 12
    && date.getDate() === dd && date.getMonth() === mm - 1
  if (!validDate) return { valid: false, province }
  const today = new Date()
  let age = today.getFullYear() - year
  if (today.getMonth() < mm - 1 || (today.getMonth() === mm - 1 && today.getDate() < dd)) age -= 1
  return {
    valid: true,
    female,
    gender: female ? 'Perempuan' : 'Laki-laki',
    birth: date.toLocaleDateString('id-ID', { day: '2-digit', month: 'long', year: 'numeric' }),
    province,
    age,
    warning: age < 15 || age > 70 ? `Usia terbaca ${age} tahun — pastikan NIK sesuai KTP.` : '',
  }
})

// --- HP: terima 08…, 8…, +62…, 62… dan tampilkan bentuk baku ---
function normalizeHp(value) {
  let digits = String(value || '').replace(/\D/g, '')
  if (digits.startsWith('62')) digits = '0' + digits.slice(2)
  else if (digits.startsWith('8')) digits = '0' + digits
  return digits
}
const hpInfo = computed(() => {
  const hp = normalizeHp(form.no_hp)
  return { hp, valid: /^08\d{8,12}$/.test(hp) }
})

function onNik(event) {
  form.nik = String(event.target.value || '').replace(/\D/g, '').slice(0, 16)
}
function onHpBlur() {
  if (form.no_hp) form.no_hp = normalizeHp(form.no_hp)
}
function onNamaBlur() {
  form.nama = String(form.nama || '').replace(/\s+/g, ' ').trim()
}

// --- Cek NIK duplikat langsung (debounce) ---
let checkTimer = null
function resetNikCheck() {
  nikCheck.state = 'idle'
  nikCheck.exists = false
}
watch(() => form.nik, (nik) => {
  clearTimeout(checkTimer)
  resetNikCheck()
  if (nik.length !== 16 || !nikInfo.value?.valid) return
  nikCheck.state = 'checking'
  checkTimer = setTimeout(async () => {
    try {
      const response = await fetch(`/api/first-work/check-nik?nik=${nik}`, {
        headers: { Accept: 'application/json' },
      })
      const data = await response.json()
      if (form.nik !== nik) return
      if (data?.status === 'error') { resetNikCheck(); return }
      nikCheck.exists = !!data.exists
      nikCheck.state = data.exists ? 'taken' : 'free'
    } catch {
      if (form.nik === nik) resetNikCheck()
    }
  }, 450)
})

// --- Draf otomatis supaya pengisian tidak hilang ---
function saveDraft() {
  try {
    localStorage.setItem(DRAFT_KEY, JSON.stringify({ ...form, step: step.value, saved_at: Date.now() }))
  } catch { /* localStorage penuh / private mode */ }
}
function clearDraft() {
  try { localStorage.removeItem(DRAFT_KEY) } catch { /* noop */ }
}
function restoreDraft() {
  try {
    const raw = localStorage.getItem(DRAFT_KEY)
    if (!raw) return
    const draft = JSON.parse(raw)
    const hasData = draft && (draft.nik || draft.nama || draft.no_hp || draft.pendidikan || draft.referensi_text)
    if (!hasData) return
    Object.assign(form, {
      nik: String(draft.nik || '').slice(0, 16),
      nama: draft.nama || '',
      pendidikan: draft.pendidikan || '',
      referrer_id: draft.referrer_id || '',
      referensi_text: draft.referensi_text || '',
      no_hp: draft.no_hp || '',
    })
    step.value = Math.min(Number(draft.step) || 0, STEPS.length - 1)
    restored.value = true
  } catch { /* draf rusak diabaikan */ }
}
watch(form, saveDraft, { deep: true })
watch(step, saveDraft)

async function loadReferrers() {
  try {
    const params = new URLSearchParams()
    if (linkBranch) params.set('cabang', linkBranch)
    if (linkToken) params.set('t', linkToken)
    const query = params.toString() ? `?${params.toString()}` : ''
    const response = await fetch('/api/first-work/referrers' + query, { headers: { Accept: 'application/json' } })
    const data = await response.json()
    if (!response.ok) {
      // v2.86.0: tautan ditolak server (token salah/kosong, cabang tak dikenal)
      // → halaman penolakan penuh, bukan form dengan branding default.
      linkState.value = 'invalid'
      linkError.value = data.error || 'Tautan form tidak valid untuk cabang ini.'
      referrers.value = []
      return
    }
    referrers.value = data.referrers || []
    branchLabel.value = data.branch_name || ''
    resolvedBranch.value = data.branch || linkBranch
    linkState.value = 'ok'
  } catch {
    // Koneksi gagal — tidak bisa memastikan tautan sah; jangan tampilkan form.
    linkState.value = 'invalid'
    linkError.value = 'Gagal memuat data cabang. Periksa koneksi internet lalu muat ulang halaman.'
    referrers.value = []
  } finally {
    metaLoading.value = false
  }
}

// Kompres foto KTP di perangkat: gambar diperkecil ke maks. 1600 px & JPEG 85%.
function compressImage(file) {
  return new Promise((resolve) => {
    if (!file.type.startsWith('image/')) { resolve(file); return }
    const url = URL.createObjectURL(file)
    const image = new Image()
    image.onload = () => {
      URL.revokeObjectURL(url)
      const maxSide = 1600
      const scale = Math.min(1, maxSide / Math.max(image.width, image.height))
      const canvas = document.createElement('canvas')
      canvas.width = Math.max(1, Math.round(image.width * scale))
      canvas.height = Math.max(1, Math.round(image.height * scale))
      canvas.getContext('2d').drawImage(image, 0, 0, canvas.width, canvas.height)
      canvas.toBlob((blob) => {
        if (!blob) { resolve(file); return }
        const name = file.name.replace(/\.[^.]+$/, '') + '.jpg'
        resolve(new File([blob], name, { type: 'image/jpeg' }))
      }, 'image/jpeg', 0.85)
    }
    image.onerror = () => { URL.revokeObjectURL(url); resolve(file) }
    image.src = url
  })
}

async function pickKtp(event) {
  error.value = ''
  const original = event.target.files?.[0]
  if (!original) return
  if (original.size > 12 * 1024 * 1024) {
    error.value = 'Ukuran file maksimal 12 MB.'
    event.target.value = ''
    return
  }
  const file = await compressImage(original)
  if (file.size > 5 * 1024 * 1024) {
    error.value = 'Ukuran file KTP masih melebihi 5 MB setelah dikompres.'
    event.target.value = ''
    return
  }
  ktpFile.value = file
  ktpLabel.value = `${file.name} · ${Math.max(1, Math.round(file.size / 1024))} KB`
  ktpPreview.value = file.type.startsWith('image/') ? URL.createObjectURL(file) : ''
}

function stepError(target) {
  if (target === 0) {
    if (form.nik.length !== 16) return 'NIK sesuai KTP wajib 16 digit angka.'
    if (!nikInfo.value?.valid) return 'Tanggal lahir pada NIK tidak valid. Periksa kembali 16 digit NIK.'
    if (nikCheck.exists) return 'NIK ini sudah pernah mendaftar. Hubungi Traineer bila perlu koreksi data.'
    if (form.nama.trim().length < 3) return 'Nama Lengkap sesuai KTP wajib diisi (min. 3 karakter).'
    return ''
  }
  if (target === 1) {
    if (!form.pendidikan.trim()) return 'Pendidikan Terakhir wajib diisi.'
    if (manualRef.value ? form.referensi_text.trim().length < 2 : !form.referrer_id) {
      return 'Referensi wajib dipilih atau diisi.'
    }
    if (!hpInfo.value.valid) return 'Nomor Handphone tidak valid. Contoh: 081234567890.'
    return ''
  }
  if (!ktpFile.value) return 'Upload Identitas (KTP) wajib dilampirkan.'
  if (!consent.value) {
    return 'Centang persetujuan pemrosesan data pribadi terlebih dahulu.'
  }
  return ''
}

function goNext() {
  const message = stepError(step.value)
  if (message) { error.value = message; return }
  error.value = ''
  step.value = Math.min(step.value + 1, STEPS.length - 1)
  window.scrollTo({ top: 0, behavior: 'smooth' })
}
function goBack() {
  error.value = ''
  step.value = Math.max(0, step.value - 1)
  window.scrollTo({ top: 0, behavior: 'smooth' })
}
function goTo(index) {
  if (index > step.value) { goNext(); return }
  error.value = ''
  step.value = index
}

async function submit() {
  if (linkState.value !== 'ok') {
    error.value = 'Tautan form tidak valid. Minta tautan resmi dari Traineer/Admin.'
    return
  }
  for (let i = 0; i < STEPS.length; i += 1) {
    const message = stepError(i)
    if (message) { step.value = i; error.value = message; return }
  }
  error.value = ''
  const payload = new FormData()
  payload.append('nik', form.nik)
  payload.append('nama', form.nama.trim())
  payload.append('pendidikan', form.pendidikan.trim())
  payload.append('no_hp', hpInfo.value.hp)
  if (manualRef.value) payload.append('referensi_text', form.referensi_text.trim())
  else payload.append('referrer_id', form.referrer_id)
  payload.append('branch', resolvedBranch.value)
  if (linkToken) payload.append('t', linkToken)
  payload.append('consent', '1')
  payload.append('ktp', ktpFile.value)

  const csrf = localStorage.getItem('bpf_csrf') || sessionStorage.getItem('bpf_csrf')
  submitting.value = true
  try {
    const response = await fetch('/api/first-work/public', {
      method: 'POST',
      body: payload,
      headers: csrf ? { 'X-CSRF-Token': csrf } : {},
    })
    const data = await response.json().catch(() => ({}))
    if (!response.ok || data.status !== 'success') {
      throw new Error(data.msg || 'Gagal mengirim. Coba lagi.')
    }
    done.value = data
    clearDraft()
    window.scrollTo({ top: 0, behavior: 'smooth' })
  } catch (e) {
    error.value = e.message || 'Gagal mengirim. Coba lagi.'
  } finally {
    submitting.value = false
  }
}

function reset() {
  Object.assign(form, {
    nik: '', nama: '', pendidikan: '',
    referrer_id: '', referensi_text: '', no_hp: '',
  })
  ktpFile.value = null
  ktpLabel.value = ''
  ktpPreview.value = ''
  done.value = null
  error.value = ''
  step.value = 0
  consent.value = false
  restored.value = false
  resetNikCheck()
  clearDraft()
}

function copyRegNo() {
  if (!done.value?.registration_no) return
  navigator.clipboard?.writeText(done.value.registration_no).catch(() => {})
}

function maskNik(nik) {
  const text = String(nik || '')
  return text.length === 16 ? `${text.slice(0, 6)}••••${text.slice(-4)}` : text
}

onMounted(() => {
  restoreDraft()
  loadReferrers()
})
onBeforeUnmount(() => clearTimeout(checkTimer))
</script>

<template>
  <div class="fw-page">
    <div class="fw-card">
      <div class="fw-brand">
        <img :src="brandIcon" alt="BPF" />
        <h1>Absensi FirstWork</h1>
        <!-- v2.86.0: tanpa fallback 'Surabaya' — nama cabang hanya tampil bila
             tautan terverifikasi server, dan disembunyikan saat tautan ditolak. -->
        <p v-if="linkState !== 'invalid'">PT Bestprofit Futures · {{ branchLabel || '…' }}</p>
      </div>

      <!-- v2.86.0: halaman penolakan penuh untuk tautan tidak sah —
           tanpa form, tanpa langkah, tanpa branding cabang. -->
      <div v-if="linkState === 'invalid'" class="fw-reject">
        <div class="fw-reject-ico">⛔</div>
        <h2>Tautan Form Tidak Valid</h2>
        <p class="fw-reject-msg">{{ linkError }}</p>
        <p class="fw-note">
          Gunakan tautan atau QR resmi dari Traineer/Admin cabang tujuan Anda.
          Setiap cabang memiliki tautan yang berbeda dan tidak dapat dipakai
          antar cabang.
        </p>
      </div>

      <template v-else>
      <div v-if="done" class="fw-success">
        <div class="fw-check">✅</div>
        <h2>Terima kasih, {{ done.nama }}!</h2>
        <div class="fw-info">
          <div><span>No. Registrasi</span><b>{{ done.registration_no }}</b></div>
          <div><span>Waktu Kirim</span><b>{{ done.submitted_at }}</b></div>
          <div><span>Status</span><b>Menunggu verifikasi Traineer</b></div>
        </div>
        <p class="fw-note">
          Simpan nomor registrasi di atas. Data Anda akan diverifikasi oleh Traineer
          sebelum diproses lebih lanjut.
        </p>
        <button class="btn fw-wide" @click="copyRegNo">📋 Salin No. Registrasi</button>
        <button class="btn btn-primary fw-wide" @click="reset">📝 Isi Data Lain</button>
      </div>

      <form v-else @submit.prevent="step === STEPS.length - 1 ? submit() : goNext()">
        <div v-if="restored" class="fw-restored">
          ↩️ Draf pengisian sebelumnya dipulihkan.
          <button type="button" class="fw-link" @click="reset(); restored = false">Mulai baru</button>
        </div>
        <div v-if="error" class="alert alert-error">{{ error }}</div>

        <div class="fw-steps">
          <button v-for="(label, i) in STEPS" :key="label" type="button" class="fw-step"
                  :class="{ active: step === i, done: step > i }" @click="goTo(i)">
            <span class="fw-step-no">{{ step > i ? '✓' : i + 1 }}</span>
            <span class="fw-step-label">{{ label }}</span>
          </button>
        </div>
        <div class="fw-progress"><div class="fw-progress-bar" :style="{ width: pct + '%' }" /></div>

        <!-- Langkah 1: data diri -->
        <template v-if="step === 0">
          <div class="fw-field">
            <label>NIK sesuai KTP <span class="req">*</span></label>
            <input class="input" :value="form.nik" inputmode="numeric" autocomplete="off"
                   maxlength="16" placeholder="16 digit angka" @input="onNik" />
            <small class="fw-hint">
              {{ form.nik.length }}/16 digit
              <template v-if="nikCheck.state === 'checking'"> · memeriksa…</template>
              <template v-else-if="nikCheck.state === 'free'"> · ✅ belum terdaftar</template>
              <template v-else-if="nikCheck.state === 'taken'"> · ⚠️ sudah terdaftar</template>
            </small>
          </div>

          <div v-if="nikCheck.exists" class="fw-callout fw-callout-red">
            NIK ini sudah pernah mendaftar. Hubungi Traineer untuk koreksi atau cek status
            pendaftaran Anda — tidak perlu mengisi ulang.
          </div>
          <div v-else-if="nikInfo" class="fw-callout" :class="nikInfo.valid ? '' : 'fw-callout-red'">
            <template v-if="nikInfo.valid">
              <div class="fw-derived">
                <span>👤 {{ nikInfo.gender }}</span>
                <span>🎂 {{ nikInfo.birth }}</span>
                <span v-if="nikInfo.province">📍 {{ nikInfo.province }}</span>
              </div>
              <small v-if="nikInfo.warning" class="fw-hint">{{ nikInfo.warning }}</small>
              <small v-else class="fw-hint">Dibaca otomatis dari NIK — cocokkan dengan KTP Anda.</small>
            </template>
            <template v-else>
              Tanggal lahir pada NIK tidak valid. Periksa kembali 16 digit NIK Anda.
            </template>
          </div>

          <div class="fw-field">
            <label>Nama Lengkap sesuai KTP <span class="req">*</span></label>
            <input class="input" v-model="form.nama" maxlength="150" autocomplete="name"
                   placeholder="cth: Ahmad Fauzi" @blur="onNamaBlur" />
            <small class="fw-hint">Tulis persis seperti di KTP, tanpa gelar.</small>
          </div>
        </template>

        <!-- Langkah 2: pendidikan, referensi, kontak -->
        <template v-else-if="step === 1">
          <div class="fw-field">
            <label>Pendidikan Terakhir <span class="req">*</span></label>
            <input class="input" v-model="form.pendidikan" list="fw-pendidikan"
                   maxlength="100" autocomplete="off"
                   placeholder="cth: S1 / SMK / S1 pendidikan keagamaan katolik" />
            <datalist id="fw-pendidikan">
              <option v-for="p in PENDIDIKAN" :key="p" :value="p" />
            </datalist>
            <small class="fw-hint">Boleh diisi bebas sesuai ijazah.</small>
          </div>

          <div class="fw-field">
            <label>Referensi <span class="req">*</span></label>
            <select class="select" v-model="form.referrer_id" :disabled="metaLoading">
              <option value="">— Pilih Pengundang / Pemberi Info —</option>
              <option v-for="ref in referrers" :key="ref.id" :value="String(ref.id)">{{ ref.name }}</option>
              <option value="manual">Lainnya / tidak ada di daftar…</option>
            </select>
            <input v-if="manualRef" class="input fw-gap" v-model="form.referensi_text"
                   maxlength="150" placeholder="Nama pengundang / pemberi informasi lowongan" />
            <small class="fw-hint">Nama orang yang mengundang atau memberi info lowongan.</small>
          </div>

          <div class="fw-field">
            <label>No. Handphone <span class="req">*</span></label>
            <input class="input" v-model="form.no_hp" type="tel" inputmode="tel"
                   maxlength="20" autocomplete="tel" placeholder="cth: 081234567890"
                   @blur="onHpBlur" />
            <small class="fw-hint">
              <template v-if="!form.no_hp">Boleh 08…, 8…, atau +62… (otomatis dibakukan).</template>
              <template v-else-if="hpInfo.valid">✅ Tersimpan sebagai {{ hpInfo.hp }}</template>
              <template v-else>⚠️ Nomor belum valid — perlu 10–14 digit dan diawali 08.</template>
            </small>
          </div>
        </template>

        <!-- Langkah 3: KTP + ringkasan -->
        <template v-else>
          <div class="fw-field">
            <label>Upload Identitas (KTP) <span class="req">*</span></label>
            <label class="fw-upload" :class="{ 'has-file': ktpFile }">
              <input type="file" accept="image/jpeg,image/png,application/pdf" capture="environment"
                     hidden @change="pickKtp" />
              <template v-if="ktpFile">
                <img v-if="ktpPreview" :src="ktpPreview" alt="Pratinjau KTP" class="fw-thumb" />
                <span class="fw-file">✅ {{ ktpLabel }}</span>
                <span class="fw-hint">Tap untuk ganti file</span>
              </template>
              <template v-else>
                <span class="fw-upload-ico">🪪</span>
                <span class="fw-file">Foto / Scan KTP</span>
                <span class="fw-hint">JPG, PNG, atau PDF · maks. 5 MB · foto dikompres otomatis</span>
              </template>
            </label>
          </div>

          <div class="fw-review">
            <h4>Ringkasan</h4>
            <div><span>Nama</span><b>{{ form.nama || '—' }}</b></div>
            <div><span>NIK</span><b>{{ maskNik(form.nik) }}</b></div>
            <div><span>Pendidikan</span><b>{{ form.pendidikan || '—' }}</b></div>
            <div><span>Referensi</span><b>{{ manualRef ? (form.referensi_text || '—') : (referrers.find(r => String(r.id) === form.referrer_id)?.name || '—') }}</b></div>
            <div><span>No. Handphone</span><b>{{ hpInfo.hp || '—' }}</b></div>
          </div>
        </template>

          <label class="fw-consent">
            <input type="checkbox" v-model="consent" />
            <span>Saya menyatakan data yang saya isi adalah benar dan saya
            <b>menyetujui penggunaan data pribadi saya</b> (NIK, nama, No. HP,
            foto KTP) oleh PT Bestprofit Futures untuk proses rekrutmen
            FirstWork ini.</span>
          </label>

          <div class="fw-nav">
            <button v-if="step > 0" type="button" class="btn" @click="goBack">← Kembali</button>
            <button v-if="step < STEPS.length - 1" type="submit" class="btn btn-primary fw-next">
              Lanjut →
            </button>
            <button v-else type="submit" class="btn btn-primary fw-next" :disabled="submitting || !consent">
              {{ submitting ? '⏳ Mengirim…' : '📤 Kirim Absensi' }}
            </button>
          </div>
          <p class="fw-note">
            Form ini terbuka untuk umum dan tidak memerlukan login. Data Anda hanya
            dipakai untuk proses rekrutmen PT Bestprofit Futures dan disesuai
            kebijakan retensi: foto KTP dihapus otomatis setelah proses selesai.
          </p>
      </form>
      </template>
    </div>
  </div>
</template>

<style scoped>
.fw-page {
  min-height: 100vh; display: flex; align-items: center; justify-content: center;
  padding: 20px 16px;
  background:
    radial-gradient(at 0% 0%, rgba(180, 83, 9, .10) 0px, transparent 50%),
    radial-gradient(at 100% 100%, rgba(37, 99, 235, .08) 0px, transparent 50%), var(--bg);
}
.fw-card {
  width: 100%; max-width: 460px; background: var(--surface); border: 1px solid var(--border);
  border-radius: var(--radius); padding: 26px 22px; box-shadow: var(--shadow-lg);
  animation: popIn .2s ease;
}
.fw-brand { text-align: center; margin-bottom: 18px; }
.fw-brand img { width: 54px; height: 54px; border-radius: 13px; box-shadow: 0 4px 14px rgba(180, 83, 9, .22); }
.fw-brand h1 { font-size: 18px; font-weight: 800; margin-top: 10px; }
.fw-brand p { font-size: 11px; color: var(--text-3); margin-top: 2px; }
.fw-field { margin-bottom: 14px; }
.fw-field > label { display: block; font-size: 12px; font-weight: 600; margin-bottom: 5px; }
.fw-hint { display: block; font-size: 10px; color: var(--text-3); margin-top: 4px; }
.fw-gap { margin-top: 8px; }
.req { color: var(--danger, #dc2626); }
.fw-wide { width: 100%; justify-content: center; padding: 11px; margin-top: 6px; }
.fw-note { margin-top: 14px; font-size: 11px; color: var(--text-3); text-align: center; line-height: 1.5; }
.fw-success { text-align: center; }
.fw-check { font-size: 44px; }
.fw-success h2 { font-size: 17px; margin-top: 6px; }
.fw-info {
  margin-top: 14px; background: var(--bg); border: 1px solid var(--border); border-radius: 12px;
  padding: 14px; text-align: left; display: grid; gap: 10px;
}
.fw-info span { display: block; font-size: 11px; color: var(--text-3); }
.fw-info b { font-size: 14px; }
.fw-upload {
  display: flex; flex-direction: column; align-items: center; justify-content: center;
  min-height: 118px; border: 2px dashed var(--border); border-radius: 12px;
  cursor: pointer; transition: all .2s; overflow: hidden; padding: 10px; text-align: center;
}
.fw-upload:hover { border-color: var(--primary, #7c3aed); background: rgba(124, 58, 237, .04); }
.fw-upload.has-file { border-style: solid; border-color: var(--success, #16a34a); }
.fw-upload-ico { font-size: 26px; margin-bottom: 4px; }
.fw-file { font-size: 12px; font-weight: 600; color: var(--text-2); word-break: break-word; }
.fw-thumb { width: 100%; max-height: 130px; object-fit: contain; border-radius: 8px; margin-bottom: 6px; }

.fw-steps { display: flex; gap: 6px; margin-bottom: 8px; }
.fw-step {
  flex: 1; display: flex; align-items: center; gap: 5px; padding: 6px 4px; border: 1px solid var(--border);
  background: var(--bg); border-radius: 9px; cursor: pointer; font-size: 10px; color: var(--text-3);
  min-width: 0;
}
.fw-step-no {
  width: 17px; height: 17px; border-radius: 50%; display: inline-flex; align-items: center;
  justify-content: center; font-weight: 700; background: var(--border); color: var(--text-2); flex: none;
}
.fw-step-label { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.fw-step.active { border-color: var(--primary, #7c3aed); color: var(--text); font-weight: 600; }
.fw-step.active .fw-step-no { background: var(--primary, #7c3aed); color: #fff; }
.fw-step.done .fw-step-no { background: var(--success, #16a34a); color: #fff; }
.fw-progress { height: 4px; background: var(--border); border-radius: 99px; overflow: hidden; margin-bottom: 16px; }
.fw-progress-bar { height: 100%; background: var(--primary, #7c3aed); transition: width .25s ease; }
.fw-callout {
  background: var(--bg); border: 1px solid var(--border); border-radius: 10px;
  padding: 10px 12px; margin-bottom: 14px; font-size: 11px; line-height: 1.5;
}
.fw-callout-red { border-color: #dc2626; background: rgba(220, 38, 38, .06); color: #b91c1c; }
.fw-derived { display: flex; flex-wrap: wrap; gap: 8px; font-size: 11px; font-weight: 600; }
.fw-restored {
  background: rgba(37, 99, 235, .08); border: 1px solid rgba(37, 99, 235, .3);
  border-radius: 9px; padding: 8px 10px; font-size: 11px; margin-bottom: 12px;
}
.fw-link { background: none; border: 0; padding: 0; color: #2563eb; font-size: 11px; cursor: pointer; text-decoration: underline; }
.fw-review { background: var(--bg); border: 1px solid var(--border); border-radius: 12px;
  padding: 12px 14px; display: grid; gap: 8px; margin-bottom: 12px;
}
.fw-review h4 { font-size: 11px; text-transform: uppercase; letter-spacing: .04em; color: var(--text-3); }
.fw-review span { display: block; font-size: 10px; color: var(--text-3); }
.fw-review b { font-size: 12px; }
/* v2.85.0: persetujuan pemrosesan data pribadi (UU PDP) */
.fw-consent { display: flex; gap: 10px; align-items: flex-start; cursor: pointer;
  background: var(--bg); border: 1px solid var(--border); border-radius: 10px;
  padding: 10px 12px; font-size: 11.5px; line-height: 1.5; margin-bottom: 4px; }
.fw-consent input { margin-top: 2px; flex: none; width: 16px; height: 16px; accent-color: var(--primary, #7c3aed); }
.fw-consent:has(input:checked) { border-color: var(--primary, #7c3aed); }
.fw-nav { display: flex; gap: 8px; margin-top: 6px; }
/* v2.86.0: halaman penolakan penuh tautan form tidak sah */
.fw-reject { text-align: center; padding: 28px 16px; display: grid; gap: 8px; justify-items: center; }
.fw-reject-ico { font-size: 34px; }
.fw-reject h2 { margin: 0; font-size: 16px; }
.fw-reject-msg { margin: 0; font-size: 12px; color: var(--text-3); line-height: 1.6; }
.fw-next { flex: 1; justify-content: center; }
</style>
