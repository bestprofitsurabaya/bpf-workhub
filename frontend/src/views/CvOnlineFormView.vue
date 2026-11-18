<script setup>
import { computed, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'

const brandIcon = '/static/icon-192.png'
const DRAFT_KEY = 'bpf_cv_draft_v1'
const STEPS = ['Sumber & Undangan', 'Data Pribadi', 'Pendidikan & Pengalaman', 'Ringkasan']

const linkParams = new URLSearchParams(window.location.search)
const linkBranch = (linkParams.get('cabang') || linkParams.get('branch') || '').trim().toUpperCase()
const linkToken = (linkParams.get('t') || linkParams.get('token') || '').trim()

const branchLabel = ref('')
const resolvedBranch = ref(linkBranch)
const linkState = ref('loading')
const linkError = ref('')

const options = reactive({
  user: [],
  domisili: [],
  pendidikan: [],
  jenis_kelamin: ['Pria', 'Wanita'],
  lama: [],
})

const form = reactive({
  sumber_informasi: '',
  diundang_oleh: '',
  user_ef: '',
  kontak_serumah: '',
  kontak_tidak_serumah: '',
  nama: '',
  tempat_lahir: '',
  tanggal_lahir: '',
  jenis_kelamin: '',
  domisili: '',
  alamat: '',
  no_hp: '',
  pendidikan_terakhir: '',
  sekolah_menengah: '',
  perguruan_tinggi: '',
  pengalaman_status: '',
  pengalaman_lama: '',
  posisi_terakhir: '',
  pengalaman_1: '',
  pengalaman_2: '',
})

const consent = ref(false)
const error = ref('')
const submitting = ref(false)
const done = ref(null)
const step = ref(0)
const restored = ref(false)
let restoring = false

const pct = computed(() => Math.round((step.value / STEPS.length) * 100))
const today = new Date().toISOString().slice(0, 10)

const hpInfo = computed(() => {
  const digits = String(form.no_hp || '').replace(/\D/g, '')
  let hp = digits
  if (!hp) return { valid: false, hp: '' }
  if (hp.startsWith('62')) hp = '0' + hp.slice(2)
  else if (hp.startsWith('8')) hp = '0' + hp
  else if (hp.startsWith('05')) hp = '08' + hp.slice(2)
  return { valid: hp.length >= 10 && hp.length <= 15, hp }
})

const pengalamanLabel = computed(() => {
  if (form.pengalaman_status === 'sudah') return 'Sudah memiliki pengalaman kerja'
  if (form.pengalaman_status === 'belum') return 'Belum memiliki pengalaman kerja / Fresh Graduate'
  return '—'
})

function saveDraft() {
  if (restoring || linkState.value !== 'ok') return
  try {
    localStorage.setItem(DRAFT_KEY, JSON.stringify({ form, step: step.value }))
  } catch { /* localStorage penuh/diblokir — draf opsional */ }
}

function clearDraft() {
  try { localStorage.removeItem(DRAFT_KEY) } catch { /* abaikan */ }
}

function restoreDraft() {
  try {
    const raw = localStorage.getItem(DRAFT_KEY)
    if (!raw) return
    const saved = JSON.parse(raw)
    if (!saved || typeof saved !== 'object') return
    restoring = true
    Object.keys(form).forEach((key) => {
      if (saved.form && typeof saved.form[key] === 'string') form[key] = saved.form[key]
    })
    if (Number.isInteger(saved.step) && saved.step >= 0 && saved.step < STEPS.length) {
      step.value = saved.step
    }
    restored.value = true
  } catch { /* draf rusak — abaikan */ } finally {
    restoring = false
  }
}

async function loadMeta() {
  try {
    const params = new URLSearchParams()
    if (linkBranch) params.set('cabang', linkBranch)
    if (linkToken) params.set('t', linkToken)
    const query = params.toString() ? `?${params.toString()}` : ''
    const response = await fetch('/api/cv-online/form-meta' + query,
      { headers: { Accept: 'application/json' } })
    const data = await response.json().catch(() => ({}))
    if (!response.ok) {
      linkState.value = 'invalid'
      linkError.value = data.error || 'Tautan form tidak valid untuk cabang ini.'
      return
    }
    branchLabel.value = data.branch_name || ''
    resolvedBranch.value = data.branch || linkBranch
    Object.assign(options, data.options || {})
    linkState.value = 'ok'
  } catch {
    linkState.value = 'invalid'
    linkError.value = 'Gagal memuat data cabang. Periksa koneksi internet lalu muat ulang halaman.'
  }
}

function stepError(index) {
  if (index === 0) {
    if (!form.sumber_informasi.trim()) return 'Sumber Informasi wajib diisi.'
    if (!form.diundang_oleh.trim()) return 'Diundang Oleh wajib diisi.'
    if (!form.user_ef) return 'User (pengundang) wajib dipilih.'
    if (!form.kontak_serumah.trim()) return 'Kontak serumah wajib diisi.'
    if (!form.kontak_tidak_serumah.trim()) return 'Kontak tidak serumah wajib diisi.'
  }
  if (index === 1) {
    if (form.nama.trim().length < 3) return 'Nama Lengkap sesuai KTP wajib diisi (min. 3 karakter).'
    if (!form.tempat_lahir.trim()) return 'Tempat Lahir wajib diisi.'
    if (!form.tanggal_lahir) return 'Tanggal Lahir wajib diisi.'
    if (form.tanggal_lahir > today) return 'Tanggal Lahir tidak boleh di masa depan.'
    if (!form.jenis_kelamin) return 'Jenis Kelamin wajib dipilih.'
    if (!form.domisili) return 'Domisili wajib dipilih.'
    if (!form.alamat.trim()) return 'Alamat sesuai KTP wajib diisi.'
    if (!form.no_hp.trim()) return 'Nomor Handphone wajib diisi.'
    if (!hpInfo.value.valid) return 'Nomor Handphone belum valid — perlu 10–15 digit.'
  }
  if (index === 2) {
    if (!form.pendidikan_terakhir) return 'Pendidikan Terakhir wajib dipilih.'
    if (form.pengalaman_status === 'sudah' && !form.pengalaman_lama) {
      return 'Lama pengalaman bekerja wajib dipilih bila sudah memiliki pengalaman.'
    }
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
  step.value = Math.max(step.value - 1, 0)
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
  if (!consent.value) {
    error.value = 'Centang persetujuan syarat & ketentuan sebelum mengirim.'
    return
  }
  error.value = ''
  const payload = new FormData()
  Object.entries(form).forEach(([key, value]) => payload.append(key, String(value ?? '').trim()))
  payload.append('no_hp', hpInfo.value.hp || form.no_hp)
  payload.append('branch', resolvedBranch.value)
  if (linkToken) payload.append('t', linkToken)
  payload.append('consent', '1')

  submitting.value = true
  try {
    const response = await fetch('/api/cv-online/public', { method: 'POST', body: payload })
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
  Object.keys(form).forEach((key) => { form[key] = '' })
  done.value = null
  error.value = ''
  step.value = 0
  consent.value = false
  restored.value = false
  clearDraft()
}

function copyRegNo() {
  if (!done.value?.registration_no) return
  navigator.clipboard?.writeText(done.value.registration_no).catch(() => {})
}

watch(form, saveDraft, { deep: true })
watch(step, saveDraft)
onMounted(() => {
  restoreDraft()
  loadMeta()
})
onBeforeUnmount(() => { /* tidak ada timer/stream yang perlu dibersihkan */ })
</script>

<template>
  <div class="cv-page">
    <div class="cv-card">
      <div class="cv-brand">
        <img :src="brandIcon" alt="BPF" />
        <h1>Registrasi CV Online</h1>
        <p v-if="linkState !== 'invalid'">PT Bestprofit Futures · {{ branchLabel || '…' }}</p>
      </div>

      <div v-if="linkState === 'invalid'" class="cv-reject">
        <div class="cv-reject-ico">⛔</div>
        <h2>Tautan Form Tidak Valid</h2>
        <p class="cv-reject-msg">{{ linkError }}</p>
        <p class="cv-note">
          Gunakan tautan atau QR resmi dari Traineer/Admin cabang tujuan Anda.
          Setiap cabang memiliki tautan yang berbeda dan tidak dapat dipakai
          antar cabang.
        </p>
      </div>

      <div v-else-if="linkState === 'loading'" class="cv-empty">⏳ Memeriksa tautan…</div>

      <template v-else>
        <div v-if="done" class="cv-success">
          <div class="cv-check">🎉</div>
          <h2>Terima kasih, {{ done.nama }}!</h2>
          <p class="cv-lead">
            Registrasi CV Online Anda sudah kami terima.
          </p>

          <div class="cv-info">
            <div><span>No. Registrasi</span><b>{{ done.registration_no }}</b></div>
            <div><span>Waktu Kirim</span><b>{{ done.submitted_at }}</b></div>
            <div><span>Status</span><b>Menunggu pemeriksaan GA/HR</b></div>
          </div>

          <div class="cv-next-steps">
            <h3>Langkah selanjutnya</h3>
            <p>
              Peserta yang masuk kualifikasi akan diundang mengikuti
              <b>Tahapan Test Kemampuan Dasar Online</b> dan akan dihubungi oleh HRD.
            </p>
            <p>
              Silakan lakukan konfirmasi ke pengundang atau pemberi info lowongan.
              Komunikasi dapat dilakukan via WhatsApp —
              <b>screenshot informasi ini agar tidak hilang</b>.
            </p>
          </div>

          <p class="cv-note">
            Simpan nomor registrasi di atas. Bila ada kendala, hubungi
            Traineer{{ branchLabel ? ' cabang ' + branchLabel : '' }} — jangan
            mengisi form ini lagi.
          </p>
          <button class="btn cv-wide" @click="copyRegNo">📋 Salin No. Registrasi</button>
          <button class="btn btn-primary cv-wide" @click="reset">📝 Isi Data Lain</button>
        </div>

        <form v-else @submit.prevent="step === STEPS.length - 1 ? submit() : goNext()">
          <div v-if="restored" class="cv-restored">
            ↩️ Draf pengisian sebelumnya dipulihkan.
            <button type="button" class="cv-link" @click="reset(); restored = false">Mulai baru</button>
          </div>
          <div v-if="error" class="alert alert-error">{{ error }}</div>

          <div class="cv-steps">
            <button v-for="(label, i) in STEPS" :key="label" type="button" class="cv-step"
                    :class="{ active: step === i, done: step > i }" @click="goTo(i)">
              <span class="cv-step-no">{{ step > i ? '✓' : i + 1 }}</span>
              <span class="cv-step-label">{{ label }}</span>
            </button>
          </div>
          <div class="cv-progress"><div class="cv-progress-bar" :style="{ width: pct + '%' }" /></div>

          <!-- Langkah 1: sumber informasi & undangan -->
          <template v-if="step === 0">
            <div class="cv-field">
              <label>Sumber Informasi <span class="req">*</span></label>
              <input class="input" v-model="form.sumber_informasi" maxlength="150"
                     placeholder="cth: Instagram, teman, grup WhatsApp" />
            </div>

            <div class="cv-field">
              <label>Diundang Oleh <span class="req">*</span></label>
              <input class="input" v-model="form.diundang_oleh" maxlength="150"
                     placeholder="Nama pengundang / pemberi informasi lowongan" />
            </div>

            <div class="cv-field">
              <label>User (Pengundang) <span class="req">*</span></label>
              <select class="select" v-model="form.user_ef">
                <option value="">— Pilih User —</option>
                <option v-for="u in options.user" :key="u" :value="u">{{ u }}</option>
              </select>
              <small class="cv-hint">Pilih sesuai informasi nama pengundang / pemberi info lowongan.</small>
            </div>

            <div class="cv-field">
              <label>Kontak yang Bisa Dihubungi &amp; Serumah <span class="req">*</span></label>
              <textarea class="input" rows="3" v-model="form.kontak_serumah" maxlength="2000"
                        placeholder="Nama lengkap, No. telepon, pekerjaan, jabatan, alamat lengkap" />
              <small class="cv-hint">Contoh: Nama lengkap, No. telephone, Pekerjaan, Jabatan dan Alamat Lengkap.</small>
            </div>

            <div class="cv-field">
              <label>Kontak yang Bisa Dihubungi &amp; Tidak Serumah <span class="req">*</span></label>
              <textarea class="input" rows="3" v-model="form.kontak_tidak_serumah" maxlength="2000"
                        placeholder="Nama lengkap, No. telepon, pekerjaan, jabatan, alamat lengkap" />
              <small class="cv-hint">Contoh: Nama lengkap, No. telephone, Pekerjaan, Jabatan dan Alamat Lengkap.</small>
            </div>
          </template>

          <!-- Langkah 2: data pribadi -->
          <template v-else-if="step === 1">
            <div class="cv-field">
              <label>Nama Lengkap <span class="req">*</span></label>
              <input class="input" v-model="form.nama" maxlength="150" autocomplete="name"
                     placeholder="Isilah sesuai KTP" />
            </div>

            <div class="cv-field">
              <label>Tempat Lahir <span class="req">*</span></label>
              <input class="input" v-model="form.tempat_lahir" maxlength="100"
                     placeholder="Isilah sesuai KTP" />
            </div>

            <div class="cv-field">
              <label>Tanggal Lahir <span class="req">*</span></label>
              <input class="input" type="date" v-model="form.tanggal_lahir" :max="today" />
              <small class="cv-hint">Isilah sesuai KTP.</small>
            </div>

            <div class="cv-field">
              <label>Jenis Kelamin <span class="req">*</span></label>
              <select class="select" v-model="form.jenis_kelamin">
                <option value="">— Pilih —</option>
                <option v-for="g in options.jenis_kelamin" :key="g" :value="g">{{ g }}</option>
              </select>
            </div>

            <div class="cv-field">
              <label>Domisili <span class="req">*</span></label>
              <select class="select" v-model="form.domisili">
                <option value="">— Pilih domisili —</option>
                <option v-for="d in options.domisili" :key="d" :value="d">{{ d }}</option>
              </select>
              <small class="cv-hint">Sesuai tempat tinggal Anda saat ini.</small>
            </div>

            <div class="cv-field">
              <label>Alamat <span class="req">*</span></label>
              <textarea class="input" rows="3" v-model="form.alamat" maxlength="2000"
                        placeholder="Isilah sesuai KTP" />
            </div>

            <div class="cv-field">
              <label>No. Handphone <span class="req">*</span></label>
              <input class="input" v-model="form.no_hp" type="tel" inputmode="tel"
                     maxlength="20" autocomplete="tel" placeholder="cth: 081234567890" />
              <small class="cv-hint">
                <template v-if="!form.no_hp">Boleh 08…, 8…, atau +62… (otomatis dibakukan).</template>
                <template v-else-if="hpInfo.valid">✅ Tersimpan sebagai {{ hpInfo.hp }}</template>
                <template v-else>⚠️ Nomor belum valid — perlu 10–15 digit.</template>
              </small>
            </div>
          </template>

          <!-- Langkah 3: pendidikan & pengalaman -->
          <template v-else-if="step === 2">
            <div class="cv-field">
              <label>Pendidikan Terakhir <span class="req">*</span></label>
              <select class="select" v-model="form.pendidikan_terakhir">
                <option value="">— Pilih pendidikan terakhir —</option>
                <option v-for="p in options.pendidikan" :key="p" :value="p">{{ p }}</option>
              </select>
            </div>

            <div class="cv-field">
              <label>Sekolah Menengah Atas / Kejuruan</label>
              <input class="input" v-model="form.sekolah_menengah" maxlength="150"
                     placeholder="Nama sekolah" />
            </div>

            <div class="cv-field">
              <label>Perguruan Tinggi / Universitas</label>
              <input class="input" v-model="form.perguruan_tinggi" maxlength="150"
                     placeholder="Nama perguruan tinggi / universitas" />
            </div>

            <div class="cv-field">
              <label>Pengalaman Bekerja</label>
              <select class="select" v-model="form.pengalaman_status">
                <option value="">— Pilih salah satu —</option>
                <option value="sudah">Sudah memiliki pengalaman kerja</option>
                <option value="belum">Belum memiliki pengalaman kerja / Fresh Graduate</option>
              </select>
            </div>

            <div class="cv-field">
              <label>Lama Pengalaman Bekerja</label>
              <select class="select" v-model="form.pengalaman_lama">
                <option value="">— Pilih —</option>
                <option v-for="l in options.lama" :key="l" :value="l">{{ l }}</option>
              </select>
              <small class="cv-hint">Isi bila sudah memiliki pengalaman kerja.</small>
            </div>

            <div class="cv-field">
              <label>Posisi / Jabatan Terakhir</label>
              <input class="input" v-model="form.posisi_terakhir" maxlength="150"
                     placeholder="Jabatan / divisi pekerjaan terakhir" />
            </div>

            <div class="cv-field">
              <label>Pengalaman Kerja 1</label>
              <textarea class="input" rows="2" v-model="form.pengalaman_1" maxlength="2000"
                        placeholder="Perusahaan tempat Anda bekerja sebelumnya" />
            </div>

            <div class="cv-field">
              <label>Pengalaman Kerja 2</label>
              <textarea class="input" rows="2" v-model="form.pengalaman_2" maxlength="2000"
                        placeholder="Perusahaan tempat Anda bekerja sebelumnya" />
            </div>
          </template>

          <!-- Langkah 4: ringkasan + persetujuan -->
          <template v-else>
            <div class="cv-review">
              <h4>Ringkasan</h4>
              <div><span>Nama</span><b>{{ form.nama || '—' }}</b></div>
              <div><span>Tempat / Tanggal Lahir</span><b>{{ form.tempat_lahir || '—' }}<template v-if="form.tanggal_lahir">, {{ form.tanggal_lahir }}</template></b></div>
              <div><span>Jenis Kelamin</span><b>{{ form.jenis_kelamin || '—' }}</b></div>
              <div><span>Domisili</span><b>{{ form.domisili || '—' }}</b></div>
              <div><span>No. Handphone</span><b>{{ hpInfo.hp || '—' }}</b></div>
              <div><span>Pendidikan Terakhir</span><b>{{ form.pendidikan_terakhir || '—' }}</b></div>
              <div><span>Pengalaman</span><b>{{ pengalamanLabel }}</b></div>
              <div><span>Diundang Oleh</span><b>{{ form.diundang_oleh || '—' }}{{ form.user_ef ? ' · ' + form.user_ef : '' }}</b></div>
            </div>
          </template>

          <label class="cv-consent">
            <input type="checkbox" v-model="consent" />
            <span>Saya menyatakan data yang saya isi adalah benar dan saya
            <b>menyetujui syarat &amp; ketentuan serta penggunaan data pribadi saya</b>
            (nama, tempat/tanggal lahir, alamat, No. HP, pendidikan, dan pengalaman
            kerja) oleh PT Bestprofit Futures untuk proses rekrutmen ini.</span>
          </label>

          <div class="cv-nav">
            <button v-if="step > 0" type="button" class="btn" @click="goBack">← Kembali</button>
            <button v-if="step < STEPS.length - 1" type="submit" class="btn btn-primary cv-next">
              Lanjut →
            </button>
            <button v-else type="submit" class="btn btn-primary cv-next"
                    :disabled="submitting || !consent">
              {{ submitting ? '⏳ Mengirim…' : '📤 Kirim Registrasi' }}
            </button>
          </div>
          <p class="cv-note">
            Form ini terbuka untuk umum dan tidak memerlukan login. Data Anda hanya
            dipakai untuk proses rekrutmen PT Bestprofit Futures.
          </p>
        </form>
      </template>
    </div>
  </div>
</template>

<style scoped>
.cv-page {
  min-height: 100vh; display: flex; align-items: center; justify-content: center;
  padding: 20px 16px;
  background:
    radial-gradient(at 0% 0%, rgba(180, 83, 9, .10) 0px, transparent 50%),
    radial-gradient(at 100% 100%, rgba(37, 99, 235, .08) 0px, transparent 50%), var(--bg);
}
.cv-card {
  width: 100%; max-width: 460px; background: var(--surface); border: 1px solid var(--border);
  border-radius: var(--radius); padding: 26px 22px; box-shadow: var(--shadow-lg);
  animation: popIn .2s ease;
}
.cv-brand { text-align: center; margin-bottom: 18px; }
.cv-brand img { width: 54px; height: 54px; border-radius: 13px; box-shadow: 0 4px 14px rgba(180, 83, 9, .22); }
.cv-brand h1 { font-size: 18px; font-weight: 800; margin-top: 10px; }
.cv-brand p { font-size: 11px; color: var(--text-3); margin-top: 2px; }
.cv-field { margin-bottom: 14px; }
.cv-field > label { display: block; font-size: 12px; font-weight: 600; margin-bottom: 5px; }
.cv-hint { display: block; font-size: 10px; color: var(--text-3); margin-top: 4px; line-height: 1.5; }
.req { color: var(--danger, #dc2626); }
.cv-wide { width: 100%; justify-content: center; padding: 11px; margin-top: 6px; }
.cv-note { margin-top: 14px; font-size: 11px; color: var(--text-3); text-align: center; line-height: 1.5; }
.cv-empty { text-align: center; font-size: 12px; color: var(--text-3); padding: 20px 0; }
.cv-success { text-align: center; }
.cv-check { font-size: 44px; }
.cv-success h2 { font-size: 17px; margin-top: 6px; }
.cv-lead { margin: 8px 0 14px; font-size: 12.5px; line-height: 1.6; color: var(--text-2); }
.cv-info {
  margin-top: 14px; background: var(--bg); border: 1px solid var(--border); border-radius: 12px;
  padding: 14px; text-align: left; display: grid; gap: 10px;
}
.cv-info span { display: block; font-size: 11px; color: var(--text-3); }
.cv-info b { font-size: 14px; }
.cv-next-steps {
  text-align: left; border: 1px solid var(--border); border-radius: 12px;
  padding: 12px 14px; margin-top: 14px; background: var(--bg);
}
.cv-next-steps h3 { font-size: 12px; margin: 0 0 8px; }
.cv-next-steps p { margin: 0 0 8px; font-size: 11.5px; line-height: 1.6; color: var(--text-2); }
.cv-steps { display: flex; gap: 6px; margin-bottom: 8px; }
.cv-step {
  flex: 1; display: flex; align-items: center; gap: 5px; padding: 6px 4px; border: 1px solid var(--border);
  background: var(--bg); border-radius: 9px; cursor: pointer; font-size: 10px; color: var(--text-3);
  min-width: 0;
}
.cv-step-no {
  width: 17px; height: 17px; border-radius: 50%; display: inline-flex; align-items: center;
  justify-content: center; font-weight: 700; background: var(--border); color: var(--text-2); flex: none;
}
.cv-step-label { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.cv-step.active { border-color: var(--primary, #7c3aed); color: var(--text); font-weight: 600; }
.cv-step.active .cv-step-no { background: var(--primary, #7c3aed); color: #fff; }
.cv-step.done .cv-step-no { background: var(--success, #16a34a); color: #fff; }
.cv-progress { height: 4px; background: var(--border); border-radius: 99px; overflow: hidden; margin-bottom: 16px; }
.cv-progress-bar { height: 100%; background: var(--primary, #7c3aed); transition: width .25s ease; }
.cv-restored {
  background: rgba(37, 99, 235, .08); border: 1px solid rgba(37, 99, 235, .3);
  border-radius: 9px; padding: 8px 10px; font-size: 11px; margin-bottom: 12px;
}
.cv-link { background: none; border: 0; padding: 0; color: #2563eb; font-size: 11px; cursor: pointer; text-decoration: underline; }
.cv-review {
  background: var(--bg); border: 1px solid var(--border); border-radius: 12px;
  padding: 12px 14px; display: grid; gap: 8px; margin-bottom: 12px;
}
.cv-review h4 { font-size: 11px; text-transform: uppercase; letter-spacing: .04em; color: var(--text-3); }
.cv-review span { display: block; font-size: 10px; color: var(--text-3); }
.cv-review b { font-size: 12px; }
.cv-consent { display: flex; gap: 10px; align-items: flex-start; cursor: pointer;
  background: var(--bg); border: 1px solid var(--border); border-radius: 10px;
  padding: 10px 12px; font-size: 11.5px; line-height: 1.5; margin-bottom: 4px; }
.cv-consent input { margin-top: 2px; flex: none; width: 16px; height: 16px; accent-color: var(--primary, #7c3aed); }
.cv-consent:has(input:checked) { border-color: var(--primary, #7c3aed); }
.cv-nav { display: flex; gap: 8px; margin-top: 6px; }
.cv-next { flex: 1; justify-content: center; }
.cv-reject { text-align: center; padding: 28px 16px; display: grid; gap: 8px; justify-items: center; }
.cv-reject-ico { font-size: 34px; }
.cv-reject h2 { margin: 0; font-size: 16px; }
.cv-reject-msg { margin: 0; font-size: 12px; color: var(--text-3); line-height: 1.6; }
</style>
