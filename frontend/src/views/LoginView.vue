<script setup>
import { ref } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { useAuthStore, ROLE_META } from '../stores/auth'
import { identity, companyCity } from '../stores/identity'

const auth = useAuthStore()
const router = useRouter()
const route = useRoute()

const brandIcon = '/static/icon-192.png'
const username = ref('')
const pin = ref('')
const showPin = ref(false)
const capsOn = ref(false)
const error = ref('')
const loading = ref(false)

function checkCaps(e) {
  capsOn.value = e.getModifierState && e.getModifierState('CapsLock')
}

async function submit() {
  error.value = ''
  if (!username.value.trim() || !pin.value) { error.value = 'Username dan PIN wajib diisi.'; return }
  loading.value = true
  try {
    const d = await auth.login(username.value.trim(), pin.value)
    const target = route.query.next && route.query.next.startsWith('/app/')
      ? route.query.next
      : (ROLE_META[d.user.role]?.home || '/dashboard')
    router.push(target)
  } catch (e) {
    error.value = e.message || 'Login gagal'
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <div class="login-page">
    <!-- Background decoration -->
    <div class="bg-orb bg-orb-1"></div>
    <div class="bg-orb bg-orb-2"></div>

    <div class="login-card">
      <!-- Brand -->
      <div class="login-brand">
        <div class="brand-icon-wrap">
          <img :src="brandIcon" alt="BPF" />
        </div>
        <h1>{{ identity.system_name }}</h1>
        <p class="brand-sub">{{ identity.company_name }}</p>
        <p class="brand-city">{{ companyCity() }}</p>
      </div>

      <!-- Error -->
      <div v-if="error" class="alert alert-error">
        <span>⚠️</span> {{ error }}
      </div>

      <!-- Form -->
      <form @submit.prevent="submit" class="login-form">
        <div class="field">
          <label>Username</label>
          <div class="input-icon-wrap">
            <span class="input-icon">👤</span>
            <input class="input input-icon-field" v-model="username" placeholder="Masukkan username" autocomplete="username" required autofocus />
          </div>
        </div>

        <div class="field">
          <label>PIN</label>
          <div class="input-icon-wrap">
            <span class="input-icon">🔑</span>
            <input class="input input-icon-field" v-model="pin" :type="showPin ? 'text' : 'password'" maxlength="6" inputmode="numeric"
                   placeholder="••••••" autocomplete="current-password" @keyup="checkCaps" required style="padding-right:44px;" />
            <button type="button" class="btn-icon pin-eye" :title="showPin ? 'Sembunyikan' : 'Lihat'"
                    :aria-label="showPin ? 'Sembunyikan PIN' : 'Lihat PIN'" @click="showPin = !showPin">
              {{ showPin ? '🙈' : '👁' }}
            </button>
          </div>
          <div v-if="capsOn" class="caps-hint" role="note">⚠️ Caps Lock aktif</div>
        </div>

        <button class="btn btn-primary login-btn" :disabled="loading">
          <span v-if="loading" class="btn-spinner"></span>
          <span v-else>🔐</span>
          {{ loading ? 'Memverifikasi...' : 'Masuk' }}
        </button>
      </form>

      <!-- Footer -->
      <div class="login-foot">
        <div class="foot-divider"></div>
        <p>Hak akses mengikuti peran yang diberikan Admin.</p>
        <p class="foot-secure">🔒 Sesuai ISO 27001 · Least Privilege</p>
      </div>
    </div>
  </div>
</template>

<style scoped>
.login-page {
  min-height: 100vh; display: flex; align-items: center; justify-content: center; padding: 20px;
  background: var(--bg); position: relative; overflow: hidden;
}

/* Background orbs */
.bg-orb { position: fixed; border-radius: 50%; filter: blur(80px); opacity: 0.5; pointer-events: none; }
.bg-orb-1 { width: 400px; height: 400px; top: -100px; left: -100px; background: rgba(37, 99, 235, 0.12); }
.bg-orb-2 { width: 350px; height: 350px; bottom: -80px; right: -80px; background: rgba(5, 150, 105, 0.10); }

.login-card {
  width: 100%; max-width: 380px; background: var(--surface); border: 1px solid var(--border);
  border-radius: 20px; padding: 36px 32px 28px; box-shadow: var(--shadow-lg);
  animation: popIn .25s ease; position: relative; z-index: 1;
}

/* Brand */
.login-brand { text-align: center; margin-bottom: 28px; }
.brand-icon-wrap {
  display: inline-flex; padding: 12px; background: linear-gradient(135deg, #2563eb 0%, #1d4ed8 100%);
  border-radius: 16px; box-shadow: 0 8px 24px rgba(37, 99, 235, 0.3);
}
.brand-icon-wrap img { width: 44px; height: 44px; border-radius: 10px; }
.login-brand h1 { font-size: 20px; font-weight: 800; margin-top: 14px; letter-spacing: -0.3px; }
.brand-sub { font-size: 12px; color: var(--text-2); margin-top: 4px; font-weight: 500; }
.brand-city { font-size: 11px; color: var(--text-3); margin-top: 2px; }

/* Form */
.login-form { display: flex; flex-direction: column; gap: 16px; }
.login-form label { font-size: 12px; font-weight: 600; color: var(--text-2); margin-bottom: 4px; display: block; }

.input-icon-wrap { position: relative; display: flex; align-items: center; }
.input-icon { position: absolute; left: 12px; font-size: 14px; pointer-events: none; z-index: 1; }
.input-icon-field { padding-left: 36px !important; width: 100%; }

.pin-eye {
  position: absolute; right: 4px; top: 50%; transform: translateY(-50%);
  width: 34px; height: 34px; border-radius: 8px; z-index: 2;
}

.login-btn {
  width: 100%; justify-content: center; padding: 12px; font-size: 15px; font-weight: 700;
  border-radius: 12px; margin-top: 4px; gap: 8px;
  background: linear-gradient(135deg, #2563eb 0%, #1d4ed8 100%);
  border: none; box-shadow: 0 4px 14px rgba(37, 99, 235, 0.3);
  transition: all 0.2s;
}
.login-btn:hover:not(:disabled) { transform: translateY(-1px); box-shadow: 0 6px 20px rgba(37, 99, 235, 0.4); }
.login-btn:active:not(:disabled) { transform: translateY(0); }
.login-btn:disabled { opacity: 0.7; cursor: not-allowed; }

.btn-spinner {
  width: 16px; height: 16px; border: 2px solid rgba(255,255,255,0.3); border-top-color: #fff;
  border-radius: 50%; animation: spin 0.6s linear infinite;
}
@keyframes spin { to { transform: rotate(360deg); } }

.caps-hint { font-size: 11px; color: var(--warning, #f59e0b); font-weight: 600; margin-top: 4px; }

/* Footer */
.login-foot { margin-top: 20px; text-align: center; }
.foot-divider { height: 1px; background: var(--border); margin-bottom: 14px; }
.login-foot p { font-size: 11px; color: var(--text-3); line-height: 1.5; margin: 0; }
.foot-secure { margin-top: 6px !important; font-weight: 600; font-size: 10px !important; letter-spacing: 0.5px; }

/* Alert */
.alert { display: flex; align-items: center; gap: 8px; padding: 10px 14px; border-radius: 10px; font-size: 13px; margin-bottom: 16px; }
.alert-error { background: #fef2f2; color: #991b1b; border: 1px solid #fecaca; }

/* Dark mode */
:global(.dark) .brand-icon-wrap { box-shadow: 0 8px 24px rgba(37, 99, 235, 0.2); }
:global(.dark) .alert-error { background: #450a0a; color: #fca5a5; border-color: #7f1d1d; }
</style>
