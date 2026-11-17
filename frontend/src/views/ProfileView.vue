<script setup>
// v2.81.0 — Profil Saya: tiap user (semua role & cabang) mengganti nama
// tampilan dan PIN sendiri tanpa perlu Admin. Username/role/cabang tetap
// diatur Admin lewat Manajemen User.
import { onMounted, reactive, ref } from 'vue'
import { api } from '../api'
import { useAuthStore } from '../stores/auth'
import { useStepupStore } from '../stores/stepup'
import PageHeader from '../components/PageHeader.vue'
import Modal from '../components/Modal.vue'

const auth = useAuthStore()
const stepup = useStepupStore()
const loading = ref(true)
const savingName = ref(false)
const savingPin = ref(false)
const err = ref('')
const msg = ref('')
const profile = ref(null)

const nameForm = reactive({ full_name: '' })
const pinForm = reactive({ current_pin: '', new_pin: '', confirm_pin: '' })

// v2.112.0 — MFA TOTP self-service
const mfa = ref(null)
const mfaBusy = ref(false)
const mfaErr = ref('')
const mfaMsg = ref('')
const mfaModal = ref(null)   // { type: 'enable'|'disable'|'regen'|'codes', ... }
const mfaCopied = ref(false)

function fmtDT(value) {
  if (!value) return '—'
  const dt = new Date(String(value).replace(' ', 'T'))
  if (Number.isNaN(dt.getTime())) return String(value)
  return dt.toLocaleString('id-ID', {
    day: '2-digit', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit',
  })
}

function applyUser(user) {
  profile.value = user
  nameForm.full_name = user.full_name || ''
  if (auth.user) auth.user.full_name = user.full_name
}

async function load() {
  loading.value = true
  err.value = ''
  try {
    const data = await api('/api/profile')
    applyUser(data.user)
  } catch (e) {
    err.value = e.message || 'Gagal memuat profil.'
  } finally {
    loading.value = false
  }
}

async function saveName() {
  err.value = ''
  msg.value = ''
  const fullName = nameForm.full_name.trim().replace(/\s+/g, ' ')
  if (fullName.length < 2) {
    err.value = 'Nama minimal 2 karakter.'
    return
  }
  savingName.value = true
  try {
    const data = await api('/api/profile', { method: 'PATCH', body: { full_name: fullName } })
    applyUser(data.user)
    msg.value = data.msg || 'Nama tersimpan.'
  } catch (e) {
    err.value = e.message || 'Gagal menyimpan nama.'
  } finally {
    savingName.value = false
  }
}

async function savePin() {
  err.value = ''
  msg.value = ''
  const { current_pin: currentPin, new_pin: newPin, confirm_pin: confirmPin } = pinForm
  if (!currentPin.trim()) {
    err.value = 'Masukkan PIN saat ini.'
    return
  }
  if (!/^\d{6}$/.test(newPin)) {
    err.value = 'PIN baru harus 6 digit angka.'
    return
  }
  if (newPin !== confirmPin) {
    err.value = 'Ulangi PIN baru tidak sama.'
    return
  }
  if (newPin === currentPin.trim()) {
    err.value = 'PIN baru harus berbeda dari PIN saat ini.'
    return
  }
  savingPin.value = true
  try {
    const data = await api('/api/profile', {
      method: 'PATCH',
      body: { current_pin: currentPin.trim(), new_pin: newPin },
    })
    msg.value = data.msg || 'PIN berhasil diganti.'
    pinForm.current_pin = ''
    pinForm.new_pin = ''
    pinForm.confirm_pin = ''
  } catch (e) {
    err.value = e.message || 'Gagal mengganti PIN.'
  } finally {
    savingPin.value = false
  }
}

// ---------------------------------------------------------------------------
// MFA TOTP (v2.112.0)
// ---------------------------------------------------------------------------
async function loadMfa() {
  try {
    mfa.value = await api('/api/auth/mfa/status')
  } catch (e) {
    mfaErr.value = e.message || 'Gagal memuat status MFA.'
  }
}

function mfaDigits(value) {
  return String(value || '').replace(/\D/g, '').slice(0, 6)
}

function mfaCodeInput(e, target) {
  target.code = mfaDigits(e.target.value)
  e.target.value = target.code
}

async function openEnableMfa() {
  mfaErr.value = ''
  mfaMsg.value = ''
  mfaBusy.value = true
  try {
    const d = await stepup.require(
      () => api('/api/auth/mfa/setup/start', { method: 'POST' }),
      'Aktifkan MFA',
    )
    if (!d) return
    mfaModal.value = { type: 'enable', qr: d.qr, secret: d.secret, code: '', codes: [] }
  } catch (e) {
    mfaErr.value = e.message || 'Gagal memulai pendaftaran MFA.'
  } finally {
    mfaBusy.value = false
  }
}

async function confirmEnableMfa() {
  const code = mfaModal.value?.code || ''
  if (code.length !== 6) { mfaErr.value = 'Masukkan 6 digit kode dari aplikasi.'; return }
  mfaErr.value = ''
  mfaBusy.value = true
  try {
    const d = await stepup.require(
      () => api('/api/auth/mfa/setup/confirm', { method: 'POST', body: { code } }),
      'Aktifkan MFA',
    )
    if (!d) return
    mfaModal.value = { type: 'codes', codes: d.recovery_codes || [] }
    mfaMsg.value = 'MFA berhasil diaktifkan.'
    await loadMfa()
  } catch (e) {
    mfaErr.value = e.message || 'Kode salah atau pendaftaran gagal.'
    if (mfaModal.value) mfaModal.value.code = ''
  } finally {
    mfaBusy.value = false
  }
}

function openMfaAction(type) {
  mfaErr.value = ''
  mfaMsg.value = ''
  mfaModal.value = { type, code: '', codes: [] }
}

async function submitMfaAction() {
  const type = mfaModal.value?.type
  const code = mfaModal.value?.code || ''
  if (code.length !== 6) { mfaErr.value = 'Masukkan 6 digit kode dari aplikasi.'; return }
  mfaErr.value = ''
  mfaBusy.value = true
  try {
    if (type === 'disable') {
      const d = await stepup.require(
        () => api('/api/auth/mfa/disable', { method: 'POST', body: { code } }),
        'Nonaktifkan MFA',
      )
      if (!d) return
      mfaModal.value = null
      mfaMsg.value = d.msg || 'MFA dinonaktifkan.'
      await loadMfa()
    } else if (type === 'regen') {
      const d = await stepup.require(
        () => api('/api/auth/mfa/recovery/regenerate', { method: 'POST', body: { code } }),
        'Buat kode pemulihan baru',
      )
      if (!d) return
      mfaModal.value = { type: 'codes', codes: d.recovery_codes || [] }
      await loadMfa()
    }
  } catch (e) {
    mfaErr.value = e.message || 'Aksi MFA gagal.'
    if (mfaModal.value) mfaModal.value.code = ''
  } finally {
    mfaBusy.value = false
  }
}

async function copyRecoveryCodes() {
  const codes = mfaModal.value?.codes || []
  try {
    await navigator.clipboard.writeText(codes.join('\n'))
    mfaCopied.value = true
    setTimeout(() => { mfaCopied.value = false }, 2500)
  } catch {
    mfaErr.value = 'Tidak bisa menyalin otomatis. Salin manual.'
  }
}

function downloadRecoveryCodes() {
  const codes = mfaModal.value?.codes || []
  const text = [
    `Kode pemulihan MFA — ${profile.value?.username || ''}`,
    `Dibuat: ${new Date().toLocaleString('id-ID')}`,
    '',
    ...codes,
    '',
    'Setiap kode hanya bisa dipakai satu kali. Simpan di tempat aman.',
  ].join('\n')
  const blob = new Blob([text], { type: 'text/plain;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `kode-pemulihan-mfa-${profile.value?.username || 'akun'}.txt`
  a.click()
  URL.revokeObjectURL(url)
}

onMounted(() => {
  load()
  loadMfa()
})
</script>

<template>
  <div class="profile-view">
    <PageHeader icon="👤" title="Profil Saya"
                subtitle="Ganti nama tampilan dan PIN Anda sendiri — berlaku untuk semua cabang" />

    <div v-if="err" class="alert alert-error">{{ err }}</div>
    <div v-if="msg" class="alert alert-success">{{ msg }}</div>
    <div v-if="loading" class="card card-pad muted">⏳ Memuat profil…</div>

    <template v-else-if="profile">
      <div class="card card-pad">
        <h3>Data Akun</h3>
        <div class="pf-grid">
          <div><span>Username</span><b>{{ profile.username }}</b></div>
          <div><span>Peran</span><b>{{ auth.meta?.icon }} {{ auth.meta?.label || profile.role }}</b></div>
          <div><span>Cabang</span><b>{{ profile.branch_name || profile.branch_code || '—' }}</b></div>
          <div><span>Login Terakhir</span><b>{{ fmtDT(profile.last_login) }}</b></div>
        </div>
        <p class="pf-note">Username, peran, dan cabang hanya bisa diubah Admin.</p>
      </div>

      <div class="card card-pad">
        <h3>Nama Tampilan</h3>
        <p class="pf-note">Nama ini tampil di sidebar, dokumen/PDF, dan jejak audit.</p>
        <form class="pf-form" @submit.prevent="saveName">
          <input class="input" v-model="nameForm.full_name" maxlength="100" placeholder="Nama lengkap" />
          <button class="btn btn-primary" type="submit" :disabled="savingName">💾 Simpan Nama</button>
        </form>
      </div>

      <div class="card card-pad">
        <h3>Ganti PIN</h3>
        <p class="pf-note">
          PIN adalah tanda tangan digital Anda. Gunakan 6 digit yang tidak mudah ditebak
          (bukan 123456/angka berulang) dan jangan dibagikan ke siapa pun.
        </p>
        <form class="pf-form pf-pin" @submit.prevent="savePin">
          <label>
            PIN saat ini
            <input class="input" v-model="pinForm.current_pin" type="password" inputmode="numeric"
                   maxlength="6" autocomplete="current-password" placeholder="PIN lama" />
          </label>
          <label>
            PIN baru
            <input class="input" v-model="pinForm.new_pin" type="password" inputmode="numeric"
                   maxlength="6" autocomplete="new-password" placeholder="6 digit" />
          </label>
          <label>
            Ulangi PIN baru
            <input class="input" v-model="pinForm.confirm_pin" type="password" inputmode="numeric"
                   maxlength="6" autocomplete="new-password" placeholder="ulangi 6 digit" />
          </label>
          <button class="btn btn-primary" type="submit" :disabled="savingPin">🔑 Ganti PIN</button>
        </form>
      </div>

      <!-- v2.112.0 — MFA TOTP (self-service) -->
      <div class="card card-pad">
        <h3>Verifikasi Dua Langkah (MFA)</h3>
        <p class="pf-note">
          Lapisan keamanan tambahan saat login: selain PIN, Anda memasukkan kode 6 digit
          dari aplikasi authenticator (Microsoft Authenticator, Google Authenticator, dsb.).
        </p>
        <div v-if="mfaErr" class="alert alert-error">{{ mfaErr }}</div>
        <div v-if="mfaMsg" class="alert alert-success">{{ mfaMsg }}</div>
        <div v-if="!mfa" class="muted">⏳ Memuat status MFA…</div>
        <template v-else>
          <div class="pf-grid">
            <div><span>Status</span><b>{{ mfa.enabled ? '✅ Aktif' : '— Nonaktif' }}</b></div>
            <div><span>Kebijakan</span><b>{{ mfa.policy_label }}</b></div>
            <div><span>Kode Pemulihan</span><b>{{ mfa.recovery_left }} tersisa</b></div>
            <div><span>Terdaftar Sejak</span><b>{{ fmtDT(mfa.enrolled_at) }}</b></div>
          </div>

          <p v-if="mfa.required_for_me && !mfa.enabled" class="pf-warn">
            ⚠️ Role Anda diwajibkan MFA oleh Admin.
            <span v-if="mfa.grace_days_left > 0">
              Sisa masa tenggang {{ Math.ceil(mfa.grace_days_left) }} hari —
              segera aktifkan sebelum tenggang berakhir.
            </span>
            <span v-else>Pendaftaran akan diminta saat login berikutnya.</span>
          </p>

          <div class="pf-form" style="margin-top:10px">
            <button v-if="!mfa.enabled" class="btn btn-primary" type="button"
                    :disabled="mfaBusy" @click="openEnableMfa">
              🔐 Aktifkan MFA
            </button>
            <template v-else>
              <button class="btn" type="button" :disabled="mfaBusy" @click="openMfaAction('regen')">
                🔄 Kode pemulihan baru
              </button>
              <button class="btn btn-danger" type="button"
                      :disabled="mfaBusy || !mfa.can_disable" @click="openMfaAction('disable')">
                Matikan MFA
              </button>
            </template>
          </div>
          <p v-if="mfa.enabled && !mfa.can_disable" class="pf-note" style="margin-top:8px">
            MFA tidak dapat dimatikan sendiri karena diwajibkan untuk role Anda.
            Hubungi Admin bila perlu reset.
          </p>
        </template>
      </div>
    </template>

    <!-- Modal MFA -->
    <Modal v-if="mfaModal" :title="mfaModal.type === 'codes' ? 'Kode Pemulihan MFA'
      : mfaModal.type === 'enable' ? 'Aktifkan MFA'
      : mfaModal.type === 'disable' ? 'Matikan MFA' : 'Kode Pemulihan Baru'"
      @close="mfaModal = null">
      <div v-if="mfaErr" class="alert alert-error">{{ mfaErr }}</div>

      <!-- Pendaftaran -->
      <div v-if="mfaModal.type === 'enable'">
        <p class="pf-note">
          Buka <strong>Microsoft Authenticator</strong> → ketuk <strong>+</strong> →
          <strong>Akun lain</strong> → pindai QR di bawah. Bila kamera bermasalah,
          pilih <strong>Masukkan kode secara manual</strong>.
        </p>
        <div style="text-align:center">
          <img v-if="mfaModal.qr" :src="mfaModal.qr" alt="QR MFA"
               style="width:210px;height:210px;border:1px solid #e2e8f0;border-radius:12px;padding:6px" />
          <p v-else class="pf-warn">QR tidak tersedia — gunakan kunci manual.</p>
        </div>
        <details style="margin:8px 0">
          <summary style="cursor:pointer;font-size:12px;color:#2563eb">Kunci manual</summary>
          <code style="display:block;background:#f1f5f9;padding:8px;border-radius:8px;margin-top:6px;word-break:break-all">{{ mfaModal.secret }}</code>
        </details>
        <label class="pf-note" style="display:block;margin-top:8px">Kode 6 digit dari aplikasi</label>
        <input class="input" inputmode="numeric" maxlength="6" placeholder="000000"
               :value="mfaModal.code" @input="mfaCodeInput($event, mfaModal)"
               style="width:100%;text-align:center;font-size:20px;letter-spacing:6px" />
        <button class="btn btn-primary" type="button" style="width:100%;margin-top:10px"
                :disabled="mfaBusy || mfaModal.code.length !== 6" @click="confirmEnableMfa">
          {{ mfaBusy ? 'Menyimpan…' : 'Aktifkan MFA' }}
        </button>
      </div>

      <!-- Kode pemulihan -->
      <div v-else-if="mfaModal.type === 'codes'">
        <p class="pf-note">
          Simpan kode berikut di tempat aman. Kode hanya ditampilkan sekali dan
          masing-masing bisa dipakai satu kali bila ponsel hilang.
        </p>
        <div style="display:grid;grid-template-columns:repeat(2,1fr);gap:8px;margin:10px 0">
          <code v-for="c in mfaModal.codes" :key="c"
                style="background:#0f172a;color:#e2e8f0;padding:8px;border-radius:8px;text-align:center">{{ c }}</code>
        </div>
        <div class="pf-form">
          <button class="btn" type="button" @click="copyRecoveryCodes">
            {{ mfaCopied ? '✓ Tersalin' : '📋 Salin semua' }}
          </button>
          <button class="btn" type="button" @click="downloadRecoveryCodes">⬇️ Unduh .txt</button>
        </div>
      </div>

      <!-- Konfirmasi kode (matikan / kode baru) -->
      <div v-else>
        <p class="pf-note">
          Masukkan kode 6 digit dari aplikasi authenticator untuk memastikan
          tindakan ini benar-benar Anda.
        </p>
        <input class="input" inputmode="numeric" maxlength="6" placeholder="000000"
               :value="mfaModal.code" @input="mfaCodeInput($event, mfaModal)"
               style="width:100%;text-align:center;font-size:20px;letter-spacing:6px" />
        <button class="btn" :class="mfaModal.type === 'disable' ? 'btn-danger' : 'btn-primary'"
                type="button" style="width:100%;margin-top:10px"
                :disabled="mfaBusy || mfaModal.code.length !== 6" @click="submitMfaAction">
          {{ mfaBusy ? 'Memproses…' : (mfaModal.type === 'disable' ? 'Matikan MFA' : 'Buat Kode Baru') }}
        </button>
      </div>
    </Modal>
  </div>
</template>

<style scoped>
.profile-view { display: grid; gap: 14px; }
.profile-view h3 { margin: 0 0 8px; font-size: 14px; }
.pf-grid { display: grid; gap: 10px; grid-template-columns: repeat(auto-fit, minmax(160px, 1fr)); }
.pf-grid span { display: block; font-size: 10px; color: var(--text-3); text-transform: uppercase; letter-spacing: .03em; }
.pf-grid b { font-size: 13px; word-break: break-word; }
.pf-note { font-size: 11px; color: var(--text-3); margin: 0 0 10px; }
.pf-warn {
  font-size: 12px;
  color: #92400e;
  background: #fffbeb;
  border: 1px solid #fcd34d;
  border-radius: 8px;
  padding: 8px 10px;
  margin: 10px 0 0;
  line-height: 1.5;
}
.pf-form { display: flex; flex-wrap: wrap; gap: 8px; align-items: flex-end; }
.pf-form .input { flex: 1 1 220px; }
.pf-pin { align-items: stretch; }
.pf-pin label { display: grid; gap: 4px; flex: 1 1 160px; font-size: 11px; color: var(--text-3); }
.pf-pin .btn { align-self: end; }
</style>
