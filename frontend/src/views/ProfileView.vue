<script setup>
// v2.81.0 — Profil Saya: tiap user (semua role & cabang) mengganti nama
// tampilan dan PIN sendiri tanpa perlu Admin. Username/role/cabang tetap
// diatur Admin lewat Manajemen User.
import { onMounted, reactive, ref } from 'vue'
import { api } from '../api'
import { useAuthStore } from '../stores/auth'
import PageHeader from '../components/PageHeader.vue'

const auth = useAuthStore()
const loading = ref(true)
const savingName = ref(false)
const savingPin = ref(false)
const err = ref('')
const msg = ref('')
const profile = ref(null)

const nameForm = reactive({ full_name: '' })
const pinForm = reactive({ current_pin: '', new_pin: '', confirm_pin: '' })

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

onMounted(load)
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
    </template>
  </div>
</template>

<style scoped>
.profile-view { display: grid; gap: 14px; }
.profile-view h3 { margin: 0 0 8px; font-size: 14px; }
.pf-grid { display: grid; gap: 10px; grid-template-columns: repeat(auto-fit, minmax(160px, 1fr)); }
.pf-grid span { display: block; font-size: 10px; color: var(--text-3); text-transform: uppercase; letter-spacing: .03em; }
.pf-grid b { font-size: 13px; word-break: break-word; }
.pf-note { font-size: 11px; color: var(--text-3); margin: 0 0 10px; }
.pf-form { display: flex; flex-wrap: wrap; gap: 8px; align-items: flex-end; }
.pf-form .input { flex: 1 1 220px; }
.pf-pin { align-items: stretch; }
.pf-pin label { display: grid; gap: 4px; flex: 1 1 160px; font-size: 11px; color: var(--text-3); }
.pf-pin .btn { align-self: end; }
</style>
