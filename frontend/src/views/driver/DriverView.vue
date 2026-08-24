<script setup>
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { io } from 'socket.io-client'
import { useAuthStore } from '../../stores/auth'
import { useDriverStore } from '../../stores/driverStore'
import DriverNotifBell from '../../components/DriverNotifBell.vue'
import BBMTab from './BBMTab.vue'
import TripTab from './TripTab.vue'
import KasbonTab from './KasbonTab.vue'
import RaporTab from './RaporTab.vue'
import OvertimeDriverTab from './OvertimeDriverTab.vue'

const auth = useAuthStore()
const store = useDriverStore()
const router = useRouter()

const brandIcon = '/static/icon-192.png'

const tab = ref(localStorage.getItem('driverTab') || 'bbm')
const dark = ref(localStorage.getItem('bpf_dark') === '1')
const toasts = ref([])

const TABS = [
  { key: 'bbm', label: 'BBM', icon: '⛽' },
  { key: 'kasbon', label: 'Kasbon', icon: '💰' },
  { key: 'trip', label: 'Trip', icon: '🗺️' },
  { key: 'overtime', label: 'OT', icon: '⏰' },
  { key: 'rapor', label: 'Rapor', icon: '📊' },
]

let socket = null
let syncTimer = null
let toastSeq = 0
let onOnline = null
let onOffline = null

const queueLabel = computed(() => {
  const t = store.queueTotal
  return t > 0 ? `${t} antrean` : ''
})

function toast(text, type = '') {
  const id = ++toastSeq
  toasts.value.push({ id, text, type })
  setTimeout(() => { toasts.value = toasts.value.filter((t) => t.id !== id) }, 4500)
}

function switchTab(key) {
  tab.value = key
  localStorage.setItem('driverTab', key)
  if (key === 'kasbon') store.loadDailyCode()
}

function toggleDark() {
  dark.value = !dark.value
  document.documentElement.classList.toggle('dark', dark.value)
  localStorage.setItem('bpf_dark', dark.value ? '1' : '0')
}

async function doLogout() {
  socket?.disconnect()
  await auth.logout()
  router.push({ name: 'login' })
}

function connectSocket() {
  try {
    socket = io({ reconnection: true, reconnectionAttempts: Infinity, reconnectionDelay: 1000, timeout: 10000 })
    socket.on('connect', () => {
      if (store.driverName) socket.emit('join_driver', { name: store.driverName })
    })
    socket.on('driver_notification', (d) => {
      if (!d || !d.driver_name) return
      if (store.driverName && d.driver_name.toUpperCase() !== store.driverName) return
      store.pushNotification(d)
      toast(`🔔 ${d.message || 'Notifikasi baru'}`)
    })
  } catch { socket = null }
}

async function init() {
  document.documentElement.classList.toggle('dark', dark.value)
  await store.loadProfile()
  if (store.profile) {
    await store.refreshQueue()
    store.loadDailyCode()
    store.loadNotifications()
    connectSocket()
    store.locate().catch(() => { /* GPS opsional */ })
  }
  // Sinkronisasi: saat online kembali + interval 30 detik
  onOnline = () => {
    store.online = true
    store.syncAll().then((n) => { if (n) toast(`✅ ${n} data offline terkirim`, 'success') })
  }
  onOffline = () => { store.online = false }
  window.addEventListener('online', onOnline)
  window.addEventListener('offline', onOffline)
  syncTimer = setInterval(() => {
    store.online = navigator.onLine
    if (store.online) store.syncAll()
  }, 30000)
}

onMounted(init)
onBeforeUnmount(() => {
  socket?.disconnect()
  clearInterval(syncTimer)
  if (onOnline) window.removeEventListener('online', onOnline)
  if (onOffline) window.removeEventListener('offline', onOffline)
})
</script>

<template>
  <div class="driver-app">
    <!-- Header -->
    <header class="d-header">
      <img :src="brandIcon" alt="BPF" class="d-logo" />
      <div class="grow" style="min-width:0;">
        <div class="d-name">{{ store.profile?.name || (auth.user?.full_name || 'Driver') }}</div>
        <div class="muted" style="font-size:10px;">{{ store.profile?.nopol || '' }} · {{ store.profile?.vehicle_type || '' }}</div>
      </div>
      <DriverNotifBell />
      <button class="btn-icon" :title="dark ? 'Mode terang' : 'Mode gelap'" @click="toggleDark">{{ dark ? '☀️' : '🌙' }}</button>
      <button class="btn-icon" title="Keluar" @click="doLogout">🚪</button>
    </header>

    <!-- Status bar -->
    <div class="d-status" :class="store.online ? 'on' : 'off'">
      <span>{{ store.online ? '🟢 Online' : '🟡 Offline — data tersimpan lokal' }}</span>
      <span v-if="queueLabel" class="d-queue">📦 {{ queueLabel }}</span>
      <div class="spacer"></div>
      <button class="btn btn-sm" :disabled="store.syncing || !store.online" @click="store.syncAll().then((n) => { if (n) toast(`✅ ${n} data offline terkirim`, 'success') })">
        {{ store.syncing ? '⏳ Sinkron…' : '🔄 Sinkron' }}
      </button>
    </div>

    <!-- Error profil -->
    <div v-if="store.profileErr" class="d-error">
      <p>⚠️ {{ store.profileErr }}</p>
      <button class="btn btn-primary" @click="doLogout">🚪 Keluar &amp; hubungi Admin</button>
    </div>

    <template v-else>
      <!-- Konten tab -->
      <main class="d-content">
        <BBMTab v-show="tab === 'bbm'" @toast="toast" />
        <KasbonTab v-show="tab === 'kasbon'" @toast="toast" @switch-tab="switchTab" />
        <TripTab v-show="tab === 'trip'" @toast="toast" />
        <OvertimeDriverTab v-show="tab === 'overtime'" />
        <RaporTab v-show="tab === 'rapor'" @toast="toast" />
      </main>

      <!-- Bottom nav -->
      <nav class="d-nav">
        <button v-for="t in TABS" :key="t.key" class="d-nav-item" :class="{ active: tab === t.key }" @click="switchTab(t.key)">
          <span class="d-nav-ico">{{ t.icon }}</span>
          <span class="d-nav-label">{{ t.label }}</span>
        </button>
      </nav>
    </template>

    <!-- Toasts -->
    <div class="d-toasts">
      <transition-group name="toast">
        <div v-for="t in toasts" :key="t.id" class="d-toast" :class="t.type">{{ t.text }}</div>
      </transition-group>
    </div>
  </div>
</template>

<style scoped>
.driver-app {
  min-height: 100vh; display: flex; flex-direction: column;
  background: var(--bg); max-width: 640px; margin: 0 auto;
}
.d-header {
  position: sticky; top: 0; z-index: 20; display: flex; align-items: center; gap: 10px;
  padding: 12px 14px; background: var(--surface); border-bottom: 1px solid var(--border);
}
.d-logo { width: 34px; height: 34px; border-radius: 9px; }
.d-name { font-weight: 800; font-size: 14px; }
.d-status {
  display: flex; align-items: center; gap: 10px; padding: 6px 14px; font-size: 11px;
  border-bottom: 1px solid var(--border); position: sticky; top: 59px; z-index: 19;
}
.d-status.on { background: var(--bg-3, #f0fdf4); color: #059669; }
.d-status.off { background: var(--bg-2, #fef3c7); color: #d97706; }
.d-queue { background: #dc2626; color: #fff; font-size: 10px; font-weight: 700; padding: 2px 8px; border-radius: 10px; }
.d-error { padding: 30px 20px; text-align: center; }
.d-content { flex: 1; padding: 12px 14px 90px; }
.d-nav {
  position: fixed; bottom: 0; left: 50%; transform: translateX(-50%); width: 100%; max-width: 640px;
  display: flex; background: var(--surface); border-top: 1px solid var(--border); z-index: 30;
}
.d-nav-item { flex: 1; display: flex; flex-direction: column; align-items: center; gap: 2px; padding: 8px 0 10px; background: none; border: none; cursor: pointer; opacity: .55; }
.d-nav-item.active { opacity: 1; color: var(--accent, #2563eb); }
.d-nav-ico { font-size: 18px; }
.d-nav-label { font-size: 10px; font-weight: 600; }
.d-toasts { position: fixed; bottom: 76px; left: 50%; transform: translateX(-50%); z-index: 200; display: flex; flex-direction: column; gap: 8px; width: min(92vw, 560px); align-items: center; pointer-events: none; }
.d-toast { background: var(--card, #1e293b); color: #fff; padding: 10px 16px; border-radius: 12px; font-size: 12px; font-weight: 600; box-shadow: 0 8px 24px rgba(15, 23, 42, .3); text-align: center; }
.d-toast.error { background: #dc2626; }
.d-toast.warning { background: #d97706; }
.d-toast.success { background: #059669; }
.toast-enter-active, .toast-leave-active { transition: all .3s ease; }
.toast-enter-from, .toast-leave-to { opacity: 0; transform: translateY(10px); }
</style>
