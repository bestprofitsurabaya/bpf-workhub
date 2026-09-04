<script setup>
import { ref } from 'vue'
import { api } from '../api'

const brandIcon = '/static/icon-192.png'
const form = ref({ nama_lengkap: '', pendidikan: '', no_hp: '', upline: '', user: '', posisi: '' })
const error = ref('')
const loading = ref(false)
const done = ref(null) // { display_id, interview_at }
const userOptions = ref([])

async function loadUserOptions() {
  try {
    const d = await api('/api/applicants/user-options')
    userOptions.value = d.options || []
  } catch {
    userOptions.value = []
  }
}

async function submit() {
  error.value = ''
  if (!form.value.nama_lengkap.trim() || !form.value.no_hp.trim() || !form.value.posisi.trim()) {
    error.value = 'Nama Lengkap, Nomor HP, dan Posisi yang Dilamar wajib diisi.'
    return
  }
  loading.value = true
  try {
    const d = await api('/api/applicants', { method: 'POST', body: form.value })
    done.value = { display_id: d.display_id, interview_at: d.interview_at }
  } catch (e) {
    error.value = e.message || 'Gagal mengirim. Coba lagi.'
  } finally {
    loading.value = false
  }
}

function reset() {
  done.value = null
  form.value = { nama_lengkap: '', pendidikan: '', no_hp: '', upline: '', user: '', posisi: '' }
  error.value = ''
}

loadUserOptions()
</script>

<template>
  <div class="apply-page">
    <div class="apply-card">
      <div class="apply-brand">
        <img :src="brandIcon" alt="BPF" />
        <h1>Formulir Pendaftaran Kerja</h1>
        <p>PT Bestprofit Futures · Jakarta</p>
        <p style="font-size:11px;color:#6b7280;margin:0;">Equity Tower, SCBD Lot 9, Jl. Jend. Sudirman Kav. 52-53, Jakarta Selatan</p>
      </div>

      <!-- SUCCESS -->
      <div v-if="done" class="apply-success">
        <div class="check-ico">✅</div>
        <h2>Pendaftaran Berhasil!</h2>
        <p class="muted" style="font-size:13px;">Data Anda sudah kami terima. Interview Anda tercatat otomatis:</p>
        <div class="info-box">
          <div><span>No. Registrasi</span><b>{{ done.display_id }}</b></div>
          <div><span>Tanggal &amp; Jam Interview</span><b>{{ done.interview_at }}</b></div>
        </div>
        <p class="muted" style="font-size:12px;margin-top:12px;">
          Mohon datang sesuai jadwal di atas dan sampaikan nomor registrasi kepada Receptionist.
          Jika Anda direkrut oleh UPLINE tertentu, sebutkan nama UPLINE saat verifikasi.
        </p>
        <button class="btn btn-primary" style="width:100%;justify-content:center;" @click="reset">📝 Daftar Lagi (Pelamar Lain)</button>
      </div>

      <!-- FORM -->
      <form v-else @submit.prevent="submit">
        <div v-if="error" class="alert alert-error">{{ error }}</div>
        <div class="field">
          <label>Nama Lengkap <span class="req">*</span></label>
          <input class="input" v-model="form.nama_lengkap" placeholder="Sesuai KTP" required autofocus />
        </div>
        <div class="field">
          <label>Pendidikan Terakhir</label>
          <input class="input" v-model="form.pendidikan" placeholder="cth: SMA / SMK / S1" />
        </div>
        <div class="field">
          <label>Nomor Telepon / HP <span class="req">*</span></label>
          <input class="input" v-model="form.no_hp" type="tel" placeholder="08xxxxxxxxxx" required />
        </div>
        <div class="field">
          <label>UPLINE</label>
          <input class="input" v-model="form.upline" placeholder="Nama orang yang merekrut Anda (jika ada)" />
        </div>
        <div class="field">
          <label>User</label>
          <select class="select" v-model="form.user">
            <option value="">— Pilih User (jika ada) —</option>
            <option v-for="u in userOptions" :key="u.id" :value="u.name">{{ u.name }}</option>
          </select>
        </div>
        <div class="field">
          <label>Posisi Yang Dilamar <span class="req">*</span></label>
          <input class="input" v-model="form.posisi" placeholder="cth: Marketing, Trader, Admin" required />
        </div>
        <button class="btn btn-primary" style="width:100%;justify-content:center;padding:11px;" :disabled="loading">
          {{ loading ? '⏳ Mengirim…' : '📤 Kirim Pendaftaran' }}
        </button>
        <div class="apply-note">
          ⏱️ Tanggal &amp; jam interview diambil otomatis dari waktu pengiriman formulir ini.
        </div>
      </form>
    </div>
  </div>
</template>

<style scoped>
.apply-page {
  min-height: 100vh; display: flex; align-items: center; justify-content: center; padding: 24px;
  background:
    radial-gradient(at 0% 0%, rgba(37, 99, 235, .08) 0px, transparent 50%),
    radial-gradient(at 100% 100%, rgba(5, 150, 105, .08) 0px, transparent 50%), var(--bg);
}
.apply-card {
  width: 100%; max-width: 460px; background: var(--surface); border: 1px solid var(--border);
  border-radius: 16px; padding: 30px 28px; box-shadow: var(--shadow-lg); animation: popIn .2s ease;
}
.apply-brand { text-align: center; margin-bottom: 18px; }
.apply-brand img { width: 54px; height: 54px; border-radius: 13px; box-shadow: 0 4px 14px rgba(37, 99, 235, .25); }
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
</style>
