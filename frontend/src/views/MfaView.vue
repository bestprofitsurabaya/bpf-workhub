<script setup>
// v2.112.0 — Langkah kedua login: verifikasi kode TOTP atau pendaftaran
// aplikasi authenticator (Microsoft Authenticator, Google Authenticator, dll).
// Halaman ini publik (belum punya sesi penuh), tetapi hanya bisa dipakai bila
// server menandai sesi sebagai `mfa_pending`.
import { computed, onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { api } from '../api'
import { useAuthStore, ROLE_META } from '../stores/auth'
import { identity } from '../stores/identity'

const auth = useAuthStore()
const router = useRouter()

const mode = ref(auth.mfaMode || 'verify')   // 'verify' | 'enroll'
const ready = ref(false)
const busy = ref(false)
const err = ref('')
const info = ref('')

const verifyForm = reactive({ code: '', recovery: '', useRecovery: false })
const enrollForm = reactive({ code: '' })
const enrollment = ref(null)      // { qr, secret, otpauth_uri, ... }
const recoveryCodes = ref([])
const enrolled = ref(false)
const showGuide = ref(false)
const brandIcon = '/static/icon-192.png'
const copied = ref(false)

const username = computed(() => auth.mfaUsername || '')
const homeTarget = computed(() => {
  const role = auth.user?.role
  return ROLE_META[role]?.home || '/dashboard'
})

function digitsOnly(value, max = 6) {
  return String(value || '').replace(/\D/g, '').slice(0, max)
}

function onCodeInput(e) {
  verifyForm.code = digitsOnly(e.target.value)
  e.target.value = verifyForm.code
}

function onEnrollInput(e) {
  enrollForm.code = digitsOnly(e.target.value)
  e.target.value = enrollForm.code
}

async function startEnroll() {
  busy.value = true
  err.value = ''
  try {
    const d = await api('/api/auth/mfa/enroll/start', { method: 'POST' })
    enrollment.value = d
    mode.value = 'enroll'
    showGuide.value = true
  } catch (e) {
    err.value = e.message || 'Gagal memulai pendaftaran MFA.'
  } finally {
    busy.value = false
  }
}

async function submitVerify() {
  err.value = ''
  if (verifyForm.useRecovery) {
    if (!verifyForm.recovery.trim()) { err.value = 'Masukkan kode pemulihan.'; return }
  } else if (verifyForm.code.length !== 6) {
    err.value = 'Masukkan 6 digit kode dari aplikasi authenticator.'
    return
  }
  const body = verifyForm.useRecovery
    ? { recovery_code: verifyForm.recovery.trim() }
    : { code: verifyForm.code }
  busy.value = true
  try {
    const d = await api('/api/auth/mfa/verify', { method: 'POST', body })
    auth.completeMfa(d)
    if (d.recovery_used) {
      info.value = 'Kode pemulihan dipakai. Segera buat kode pemulihan baru di Profil Saya.'
    }
    router.push(homeTarget.value)
  } catch (e) {
    err.value = e.message || 'Kode tidak valid.'
    verifyForm.code = ''
  } finally {
    busy.value = false
  }
}

async function submitEnroll() {
  err.value = ''
  if (!enrollForm.code) { err.value = 'Masukkan kode 6 digit yang tampil di aplikasi.'; return }
  busy.value = true
  try {
    const d = await api('/api/auth/mfa/enroll/confirm', {
      method: 'POST', body: { code: enrollForm.code },
    })
    auth.completeMfa(d)
    recoveryCodes.value = d.recovery_codes || []
    enrolled.value = true
    enrollment.value = null
  } catch (e) {
    err.value = e.message || 'Kode salah. Coba kode terbaru.'
    enrollForm.code = ''
  } finally {
    busy.value = false
  }
}

async function copyCodes() {
  try {
    await navigator.clipboard.writeText(recoveryCodes.value.join('\n'))
    copied.value = true
    setTimeout(() => { copied.value = false }, 2500)
  } catch {
    err.value = 'Tidak bisa menyalin otomatis. Salin manual kode di bawah.'
  }
}

function downloadCodes() {
  const text = [
    `Kode pemulihan MFA — ${identity.system_name}`,
    `Akun: ${username.value || auth.user?.user_name || '-'}`,
    `Dibuat: ${new Date().toLocaleString('id-ID')}`,
    '',
    ...recoveryCodes.value,
    '',
    'Simpan di tempat aman. Setiap kode hanya bisa dipakai satu kali.',
  ].join('\n')
  const blob = new Blob([text], { type: 'text/plain;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `kode-pemulihan-mfa-${username.value || 'akun'}.txt`
  a.click()
  URL.revokeObjectURL(url)
}

function copySecret() {
  const secret = enrollment.value?.secret
  if (!secret) return
  try {
    navigator.clipboard?.writeText(secret)
    info.value = 'Kunci manual disalin.'
    setTimeout(() => { info.value = '' }, 2500)
  } catch {
    err.value = 'Tidak bisa menyalin otomatis. Ketik manual kunci di atas.'
  }
}

function logout() {
  auth.logout()
}

onMounted(async () => {
  if (!auth.ready) await auth.bootstrap()
  if (auth.isAuthenticated) {
    router.replace(homeTarget.value)
    return
  }
  if (!auth.mfaPending) {
    router.replace({ name: 'login' })
    return
  }
  mode.value = auth.mfaMode || 'verify'
  ready.value = true
  if (mode.value === 'enroll') await startEnroll()
})
</script>

<template>
  <div class="mfa-page">
    <div class="bg-orb bg-orb-1"></div>
    <div class="bg-orb bg-orb-2"></div>

    <div class="mfa-card">
      <div class="mfa-brand">
        <div class="brand-icon-wrap">
          <img :src="brandIcon" alt="BPF" />
        </div>
        <h1>Verifikasi Dua Langkah</h1>
        <p class="brand-sub">{{ identity.system_name }} · {{ identity.company_name }}</p>
        <p v-if="username" class="brand-user">Akun: <strong>{{ username }}</strong></p>
      </div>

      <div v-if="err" class="alert alert-error"><span>⚠️</span> {{ err }}</div>
      <div v-if="info" class="alert alert-info"><span>ℹ️</span> {{ info }}</div>

      <div v-if="!ready" class="muted center">Memuat…</div>

      <!-- ================= HASIL PENDAFTARAN ================= -->
      <section v-else-if="enrolled" class="mfa-section">
        <h2>✅ MFA aktif</h2>
        <p class="muted">
          Simpan <strong>kode pemulihan</strong> berikut. Kode ini hanya ditampilkan
          sekali dan dipakai bila ponsel hilang atau aplikasi direset.
        </p>
        <div class="codes-grid">
          <code v-for="c in recoveryCodes" :key="c">{{ c }}</code>
        </div>
        <div class="row gap wrap">
          <button class="btn btn-ghost" type="button" @click="copyCodes">
            {{ copied ? '✓ Tersalin' : '📋 Salin semua' }}
          </button>
          <button class="btn btn-ghost" type="button" @click="downloadCodes">⬇️ Unduh .txt</button>
        </div>
        <button class="btn btn-primary btn-block" type="button" @click="router.push(homeTarget)">
          Masuk ke aplikasi
        </button>
      </section>

      <!-- ================= VERIFIKASI ================= -->
      <section v-else-if="mode === 'verify'" class="mfa-section">
        <p class="muted">
          Buka aplikasi authenticator di ponsel Anda, lalu masukkan
          <strong>kode 6 digit</strong> yang tampil.
        </p>

        <form v-if="!verifyForm.useRecovery" @submit.prevent="submitVerify">
          <label class="field-label" for="mfa-code">Kode verifikasi</label>
          <input
            id="mfa-code"
            class="code-input"
            inputmode="numeric"
            autocomplete="one-time-code"
            placeholder="000000"
            :value="verifyForm.code"
            @input="onCodeInput"
            maxlength="6"
            autofocus
          />
          <button class="btn btn-primary btn-block" type="submit" :disabled="busy || verifyForm.code.length !== 6">
            {{ busy ? 'Memeriksa…' : 'Verifikasi & Masuk' }}
          </button>
        </form>

        <form v-else @submit.prevent="submitVerify">
          <label class="field-label" for="mfa-recovery">Kode pemulihan</label>
          <input
            id="mfa-recovery"
            class="text-input"
            placeholder="XXXXX-XXXXX"
            v-model="verifyForm.recovery"
            autocomplete="one-time-code"
          />
          <button class="btn btn-primary btn-block" type="submit" :disabled="busy || !verifyForm.recovery.trim()">
            {{ busy ? 'Memeriksa…' : 'Gunakan kode pemulihan' }}
          </button>
        </form>

        <button class="link-btn" type="button" @click="verifyForm.useRecovery = !verifyForm.useRecovery">
          {{ verifyForm.useRecovery ? '← Kembali ke kode aplikasi' : 'Ponsel hilang? Gunakan kode pemulihan' }}
        </button>

        <p class="hint">
          Kode berganti setiap 30 detik. Pastikan jam ponsel disetel
          <strong>otomatis</strong>. Jika tetap gagal, hubungi Admin untuk reset MFA.
        </p>
      </section>

      <!-- ================= PENDAFTARAN ================= -->
      <section v-else class="mfa-section">
        <h2>Daftarkan aplikasi authenticator</h2>
        <p class="muted">
          Role Anda diwajibkan MFA oleh Admin. Pendaftaran hanya perlu dilakukan
          sekali (± 2 menit).
        </p>

        <div v-if="busy && !enrollment" class="muted center">Menyiapkan QR…</div>

        <template v-if="enrollment">
          <div class="qr-wrap">
            <img v-if="enrollment.qr" :src="enrollment.qr" alt="QR pendaftaran MFA" />
            <div v-else class="qr-fallback">
              Gambar QR tidak tersedia — gunakan kunci manual di bawah.
            </div>
          </div>

          <details class="manual-key">
            <summary>Kunci manual (bila kamera/QR bermasalah)</summary>
            <div class="key-row">
              <code>{{ enrollment.secret }}</code>
              <button class="btn btn-ghost btn-sm" type="button" @click="copySecret">
                Salin
              </button>
            </div>
            <p class="hint">
              Di Microsoft Authenticator pilih <strong>Akun lain</strong> →
              <strong>Masukkan kode secara manual</strong>, lalu ketik kunci di atas.
              Jenis akun: <em>Akun lain (Google, Facebook, dll.)</em>.
            </p>
          </details>

          <form @submit.prevent="submitEnroll">
            <label class="field-label" for="enroll-code">Masukkan kode 6 digit dari aplikasi</label>
            <input
              id="enroll-code"
              class="code-input"
              inputmode="numeric"
              autocomplete="one-time-code"
              placeholder="000000"
              :value="enrollForm.code"
              @input="onEnrollInput"
              maxlength="6"
            />
            <button class="btn btn-primary btn-block" type="submit" :disabled="busy || enrollForm.code.length !== 6">
              {{ busy ? 'Menyimpan…' : 'Aktifkan MFA' }}
            </button>
          </form>
        </template>

        <button class="link-btn" type="button" @click="startEnroll" :disabled="busy">
          Muat ulang QR
        </button>
      </section>

      <!-- ================= PANDUAN ================= -->
      <div class="guide">
        <button class="guide-toggle" type="button" @click="showGuide = !showGuide">
          <span>📱 Panduan Microsoft Authenticator</span>
          <span>{{ showGuide ? '▲' : '▼' }}</span>
        </button>
        <ol v-if="showGuide" class="guide-list">
          <li>Unduh <strong>Microsoft Authenticator</strong> dari Play Store / App Store.</li>
          <li>Buka aplikasi → ketuk <strong>+</strong> di kanan atas → pilih
            <strong>Akun lain</strong> (<em>Other account</em>).</li>
          <li>Arahkan kamera ke QR di halaman ini. Bila kamera tidak bisa,
            pilih <strong>Masukkan kode secara manual</strong> lalu ketik kunci manual.</li>
          <li>Aplikasi menampilkan kode 6 digit yang berganti tiap 30 detik.</li>
          <li>Ketik kode tersebut di kolom verifikasi, lalu tekan
            <strong>Verifikasi &amp; Masuk</strong>.</li>
        </ol>
        <p v-if="showGuide" class="hint">
          Tips: aktifkan <em>setel waktu otomatis</em> di ponsel. Jangan bagikan kode
          kepada siapa pun — staf IT/Admin tidak pernah meminta kode Anda.
        </p>
      </div>

      <button class="link-btn danger" type="button" @click="logout">
        Batal &amp; login ulang
      </button>
    </div>
  </div>
</template>

<style scoped>
.mfa-page {
  min-height: 100vh;
  display: grid;
  place-items: center;
  padding: 24px 16px;
  background: linear-gradient(140deg, #0f172a 0%, #1e293b 55%, #0f172a 100%);
  position: relative;
  overflow: hidden;
}
.bg-orb {
  position: absolute;
  border-radius: 50%;
  filter: blur(70px);
  opacity: .35;
  pointer-events: none;
}
.bg-orb-1 { width: 380px; height: 380px; background: #2563eb; top: -120px; left: -80px; }
.bg-orb-2 { width: 320px; height: 320px; background: #0d9488; bottom: -100px; right: -60px; }

.mfa-card {
  position: relative;
  width: min(460px, 100%);
  background: #fff;
  border-radius: 18px;
  padding: 26px 24px 22px;
  box-shadow: 0 24px 60px rgba(2, 6, 23, .45);
}
.mfa-brand { text-align: center; margin-bottom: 16px; }
.brand-icon-wrap { display: flex; justify-content: center; margin-bottom: 8px; }
.brand-icon-wrap img { width: 56px; height: 56px; border-radius: 14px; }
.mfa-brand h1 { font-size: 1.22rem; margin: 0 0 4px; color: #0f172a; }
.brand-sub { margin: 0; font-size: .8rem; color: #64748b; }
.brand-user { margin: 6px 0 0; font-size: .82rem; color: #334155; }

.mfa-section { margin-top: 8px; }
.mfa-section h2 { font-size: 1rem; margin: 0 0 6px; color: #0f172a; }
.muted { color: #64748b; font-size: .86rem; line-height: 1.5; }
.center { text-align: center; }

.field-label { display: block; font-size: .8rem; font-weight: 600; color: #334155; margin: 14px 0 6px; }
.code-input {
  width: 100%;
  font-size: 1.7rem;
  letter-spacing: .42em;
  text-align: center;
  font-variant-numeric: tabular-nums;
  padding: 12px 10px;
  border: 1.5px solid #cbd5e1;
  border-radius: 12px;
  outline: none;
}
.code-input:focus { border-color: #2563eb; box-shadow: 0 0 0 3px rgba(37, 99, 235, .15); }
.text-input {
  width: 100%;
  font-size: 1rem;
  padding: 11px 12px;
  border: 1.5px solid #cbd5e1;
  border-radius: 12px;
  outline: none;
  text-transform: uppercase;
}
.text-input:focus { border-color: #2563eb; box-shadow: 0 0 0 3px rgba(37, 99, 235, .15); }

.btn { border: none; border-radius: 11px; padding: 11px 14px; font-weight: 600; cursor: pointer; font-size: .9rem; }
.btn-primary { background: #2563eb; color: #fff; }
.btn-primary:hover:not(:disabled) { background: #1d4ed8; }
.btn-primary:disabled { opacity: .55; cursor: not-allowed; }
.btn-block { width: 100%; margin-top: 14px; }
.btn-ghost { background: #f1f5f9; color: #1e293b; }
.btn-sm { padding: 5px 10px; font-size: .78rem; }

.link-btn { background: none; border: none; color: #2563eb; cursor: pointer; font-size: .82rem; padding: 10px 0 0; display: block; }
.link-btn.danger { color: #b91c1c; }
.row { display: flex; align-items: center; }
.gap { gap: 8px; }
.wrap { flex-wrap: wrap; }

.qr-wrap { display: flex; justify-content: center; margin: 10px 0 6px; }
.qr-wrap img { width: 210px; height: 210px; border: 1px solid #e2e8f0; border-radius: 12px; padding: 6px; background: #fff; }
.qr-fallback { font-size: .8rem; color: #b45309; background: #fffbeb; border: 1px dashed #f59e0b; padding: 12px; border-radius: 10px; }

.manual-key { margin-top: 10px; font-size: .84rem; }
.manual-key summary { cursor: pointer; color: #2563eb; }
.key-row { display: flex; align-items: center; gap: 8px; margin-top: 8px; flex-wrap: wrap; }
.key-row code { background: #f1f5f9; padding: 6px 10px; border-radius: 8px; font-size: .82rem; word-break: break-all; }

.codes-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 8px;
  margin: 12px 0;
}
.codes-grid code {
  background: #0f172a;
  color: #e2e8f0;
  padding: 8px 10px;
  border-radius: 8px;
  text-align: center;
  font-size: .9rem;
  letter-spacing: .06em;
}

.alert { display: flex; gap: 8px; align-items: flex-start; padding: 10px 12px; border-radius: 10px; font-size: .84rem; margin-bottom: 10px; }
.alert-error { background: #fef2f2; color: #b91c1c; border: 1px solid #fecaca; }
.alert-info { background: #eff6ff; color: #1d4ed8; border: 1px solid #bfdbfe; }

.guide { margin-top: 18px; border-top: 1px solid #e2e8f0; padding-top: 10px; }
.guide-toggle {
  width: 100%;
  display: flex;
  justify-content: space-between;
  background: none;
  border: none;
  font-size: .84rem;
  font-weight: 600;
  color: #334155;
  cursor: pointer;
  padding: 4px 0;
}
.guide-list { margin: 8px 0 4px; padding-left: 20px; font-size: .82rem; color: #475569; line-height: 1.6; }
.hint { font-size: .76rem; color: #64748b; line-height: 1.5; margin-top: 10px; }
</style>
