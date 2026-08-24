<script setup>
import { computed, onMounted, onBeforeUnmount, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useAuthStore, ROLE_META } from '../stores/auth'
import { useRealtimeStore } from '../stores/realtime'
import { identity } from '../stores/identity'
import NotificationBell from '../components/NotificationBell.vue'
import ToastStack from '../components/ToastStack.vue'

const auth = useAuthStore()
const rt = useRealtimeStore()
const route = useRoute()
const router = useRouter()

const open = ref(false)
const rtOn = ref(false)
const dark = ref(localStorage.getItem('bpf_dark') === '1')
const hc = ref(localStorage.getItem('bpf_hc') === '1')
const brandIcon = '/static/icon-192.png'

const MENU = [
  { label: 'Dashboard', path: '/dashboard', icon: '📊', roles: ['admin'] },
  { label: 'Dashboard GA', path: '/ga', icon: '🧾', roles: ['ga', 'admin'] },
  { label: 'Dashboard Finance', path: '/finance', icon: '💰', roles: ['finance', 'admin'] },
  { label: 'Log Perjalanan', path: '/trips', icon: '🗺️', roles: ['ga', 'finance', 'admin'] },
  { label: 'Assignments', path: '/assignments', icon: '🚗', roles: ['ga', 'admin'] },
  { label: 'Rekap', path: '/rekap', icon: '📋', roles: ['finance', 'admin'] },
  { label: 'Kasbon / BBM', path: '/cash', icon: '💵', roles: ['ga', 'finance', 'admin'] },
  { label: 'Analytics', path: '/analytics', icon: '📈', roles: ['ga', 'finance', 'admin'] },
  { label: 'Marketing Hub', path: '/marketing', icon: '📣', roles: ['marketing'] },
  { label: 'Chief Driver', path: '/chief-driver', icon: '🚛', roles: ['chief_driver', 'ga', 'admin'] },
  { label: 'Manajemen User', path: '/users', icon: '👥', roles: ['admin'] },
  { label: 'Pengaturan', path: '/settings', icon: '⚙️', roles: ['admin'] },
  { label: 'Audit Log', path: '/logs', icon: '📝', roles: ['admin'] },
  { label: 'Air Minum', path: '/water', icon: '🚰', roles: ['ob', 'finance', 'admin'] },
  { label: 'Pelamar Kerja', path: '/receptionist', icon: '🪪', roles: ['receptionist', 'admin'] },
  { label: 'Rekrutan Saya', path: '/traineer', icon: '🎯', roles: ['traineer'] },
  { label: 'Aset & Pemeliharaan', path: '/assets', icon: '🔧', roles: ['ga', 'admin'] },
  { label: 'Overtime', path: '/ga-hr', icon: '⏰', roles: ['ga_hr', 'admin'] },
  { label: 'News Scraper', path: '/it', icon: '📰', roles: ['it_sby', 'it_hu', 'it_jkt2', 'it_bdg', 'it_smg', 'it_mlg', 'it_mdn', 'it_bjm', 'it_plm', 'it_lpg', 'admin'] },

]

const items = computed(() => MENU.filter((m) => m.roles.includes(auth.role)))
const pageTitle = computed(() => route.meta?.title || (items.value.find((i) => route.path.startsWith(i.path))?.label || 'Dashboard'))
const initials = computed(() => (auth.user?.full_name || auth.user?.user_name || '?').slice(0, 2).toUpperCase())

function toggleDark() {
  dark.value = !dark.value
  document.documentElement.classList.toggle('dark', dark.value)
  localStorage.setItem('bpf_dark', dark.value ? '1' : '0')
}

function toggleHc() {
  hc.value = !hc.value
  document.documentElement.classList.toggle('hc', hc.value)
  localStorage.setItem('bpf_hc', hc.value ? '1' : '0')
}

async function doLogout() {
  await auth.logout()
  router.push({ name: 'login' })
}

function connectRealtime() {
  rt.connect(auth.role)
  watchRealtime()
}

let unwatchRt = null
function watchRealtime() {
  unwatchRt?.()
  unwatchRt = watch(
    () => rt.connected,
    (v) => { rtOn.value = v }
  )
}

onMounted(() => {
  document.documentElement.classList.toggle('dark', dark.value)
  document.documentElement.classList.toggle('hc', hc.value)
  connectRealtime()
})
onBeforeUnmount(() => { unwatchRt?.(); rt.disconnect() })
</script>

<template>
  <div class="app-shell">
    <a href="#konten" class="skip-link">Langsung ke konten</a>
    <div class="backdrop" :class="{ show: open }" @click="open = false"></div>

    <aside class="sidebar" :class="{ open }">
      <div class="brand">
        <img :src="brandIcon" alt="BPF" />
        <div>
          <b>{{ identity.system_name }}</b>
          <span>{{ identity.company_name }}</span>
        </div>
      </div>

      <nav class="side-nav" aria-label="Menu utama">
        <div class="nav-sec">Menu · {{ auth.meta?.label }}</div>
        <router-link v-for="m in items" :key="m.path" :to="m.path" @click="open = false">
          <span class="ico">{{ m.icon }}</span>{{ m.label }}
        </router-link>
      </nav>

      <div class="user-card">
        <div class="avatar" :style="{ background: auth.meta?.color || '#2563eb' }">{{ initials }}</div>
        <div class="grow" style="min-width:0;">
          <div class="u-name">{{ auth.user?.full_name || auth.user?.user_name }}</div>
          <div class="u-role">
            <span class="role-chip" :style="{ background: auth.meta?.color }">{{ auth.meta?.icon }} {{ auth.meta?.label }}</span>
            <span v-if="auth.user?.branch_name" class="branch-chip">🏢 {{ auth.user.branch_name }}</span>
          </div>
        </div>
        <button class="btn-icon" title="Keluar" aria-label="Keluar" @click="doLogout">🚪</button>
      </div>
    </aside>

    <div class="main">
      <header class="topbar">
        <button class="btn-icon burger" title="Menu" @click="open = !open">☰</button>
        <h1>{{ pageTitle }}</h1>
        <span class="muted" style="font-size:11px;">{{ new Date().toLocaleDateString('id-ID', { weekday: 'long', day: 'numeric', month: 'long', year: 'numeric' }) }}</span>
        <div class="spacer"></div>
        <span class="rt-dot" :class="rtOn ? 'on' : 'off'" :title="rtOn ? 'Realtime terhubung' : 'Realtime terputus'">
          {{ rtOn ? '⚡ Realtime' : '🔴 Offline' }}
        </span>
        <NotificationBell />
        <button class="btn-icon" :title="hc ? 'Mode kontras normal' : 'Mode kontras tinggi'" :aria-label="hc ? 'Mode kontras normal' : 'Mode kontras tinggi'" @click="toggleHc">{{ hc ? '🌗' : '🔆' }}</button>
        <button class="btn-icon" :title="dark ? 'Mode terang' : 'Mode gelap'" :aria-label="dark ? 'Mode terang' : 'Mode gelap'" @click="toggleDark">{{ dark ? '☀️' : '🌙' }}</button>
      </header>

      <main class="content" id="konten" tabindex="-1">
        <router-view />
      </main>
    </div>
    <ToastStack />
  </div>
</template>
