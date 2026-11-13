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
import HelpCenter from '../../components/HelpCenter.vue'
import OnboardingTour from '../../components/OnboardingTour.vue'
import FlowGuide from '../../components/FlowGuide.vue'
import { onboardingSteps } from '../../content/help.js'
import { api } from '../../api'

const auth = useAuthStore()
const store = useDriverStore()
const router = useRouter()

const brandIcon = '/static/icon-192.png'

const dark = ref(localStorage.getItem('bpf_dark') === '1')
const toasts = ref([])
const helpOpen = ref(false)
const tourOpen = ref(false)
const tourSteps = ref([])
const onboardKey = computed(() => `bpf_onboarded:${auth.user?.user_name || ''}`)
let tourTimer = null

function startTour() {
  helpOpen.value = false
  tourSteps.value = onboardingSteps('driver', auth.user)
  tourOpen.value = true
}
function finishTour() {
  if (auth.user?.user_name) localStorage.setItem(onboardKey.value, '1')
  tourOpen.value = false
}

const TABS = [
  { key: 'bbm', label: 'BBM', icon: '⛽', hint: 'Klaim BBM, voucher rekanan, dan LPJ kasbon' },
  { key: 'kasbon', label: 'Kasbon', icon: '💰', hint: 'Uang muka perjalanan & status LPJ' },
  { key: 'trip', label: 'Trip', icon: '🗺️', hint: 'Log perjalanan & hasil kunjungan' },
  { key: 'overtime', label: 'OT', icon: '⏰', hint: 'Pengajuan lembur' },
  { key: 'rapor', label: 'Rapor', icon: '📊', hint: 'Performa BBM kendaraan (km/L)' },
]
// Valuasi tab tersimpan: kunci lama/tak dikenal tidak boleh membuat layar kosong.
const storedTab = localStorage.getItem('driverTab')
const tab = ref(TABS.some((t) => t.key === storedTab) ? storedTab : 'bbm')
const kasbonRefresh = ref(0)

// v2.73.0 — konfirmasi serah terima kendaraan (confirmed_by_driver).
// Import identitas dari sesi di backend; body hanya kirim nopol.
const pendingTask = ref(null) // { nopol, vehicle_type, ... }
const confirming = ref(false)

async function loadPendingTask() {
  try {
    const rows = await api('/api/assignments/pending')
    if (!Array.isArray(rows)) return
    pendingTask.value = rows.find((r) => (r.driver_name || '').toUpperCase() === store.driverName) || null
  } catch { /* offline / error — banner skip */ }
}

async function confirmTask() {
  if (!pendingTask.value?.nopol) return
  confirming.value = true
  try {
    const r = await api('/api/assignments/confirm', { method: 'POST', body: { nopol: pendingTask.value.nopol } })
    if (r?.status === 'success') {
      toast(`✅ ${r.msg || 'Konfirmasi berhasil'}`, 'success')
      pendingTask.value = null
    } else {
      toast('❌ ' + (r?.msg || 'Konfirmasi gagal'), 'error')
      pendingTask.value = null
    }
  } catch (e) {
    const t = e.message || 'Konfirmasi gagal'
    toast('❌ ' + t, 'error')
    if (t.toLowerCase().includes('pending')) pendingTask.value = null
  } finally {
    confirming.value = false
  }
}

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
  if (key === 'kasbon') {
    kasbonRefresh.value++
    store.loadDailyCode()
  }
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
    loadPendingTask() // v2.73.0 — cek serah terima yang belum dikonfirmasi
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

onMounted(async () => {
  await init()
  tourTimer = setTimeout(() => {
    if (auth.user?.user_name && localStorage.getItem(onboardKey.value) !== '1') startTour()
  }, 700)
})
onBeforeUnmount(() => {
  socket?.disconnect()
  clearInterval(syncTimer)
  clearTimeout(tourTimer)
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
      <button class="btn-icon" title="Bantuan & glosarium" aria-label="Bantuan" @click="helpOpen = true">❓</button>
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
      <!-- Serah terima kendaraan: konfirmasi tugas baru (v2.73.0) -->
      <div v-if="pendingTask" class="d-handover" role="status">
        <div class="d-handover-text">
          <b>🚛 Serah Terima Kendaraan</b>
          <span class="muted" style="font-size:11px;">
            {{ pendingTask.nopol }} · {{ pendingTask.vehicle_type }} — pastikan kondisi kendaraan sudah dicek, lalu konfirmasi.
          </span>
        </div>
        <button class="btn btn-primary" :disabled="confirming" @click="confirmTask">
          {{ confirming ? '⏳ Menyimpan…' : '✅ Konfirmasi Serah Terima' }}
        </button>
      </div>

      <!-- Konten tab -->
      <main class="d-content">
        <FlowGuide audience="driver" />
        <BBMTab v-show="tab === 'bbm'" @toast="toast" />
        <KasbonTab v-show="tab === 'kasbon'" :refresh="kasbonRefresh" @toast="toast" @switch-tab="switchTab" />
        <TripTab v-show="tab === 'trip'" @toast="toast" />
        <OvertimeDriverTab v-show="tab === 'overtime'" @toast="toast" />
        <RaporTab v-show="tab === 'rapor'" @toast="toast" />
      </main>

      <!-- Bottom nav -->
      <nav class="d-nav">
        <button v-for="t in TABS" :key="t.key" class="d-nav-item" :class="{ active: tab === t.key }"
                :title="t.hint" :aria-label="t.label + ' — ' + t.hint" @click="switchTab(t.key)">
          <span class="d-nav-ico">{{ t.icon }}</span>
          <span class="d-nav-label">{{ t.label }}</span>
        </button>
      </nav>
    </template>

    <!-- Toasts -->
    <HelpCenter :open="helpOpen" path="/driver" :role="auth.role" @close="helpOpen = false" @replay-tour="startTour" />
    <OnboardingTour :open="tourOpen" :steps="tourSteps" @close="finishTour" @done="finishTour" />
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
.d-status.on { background: var(--bg-3, #f0fdf4); color: var(--success); }
.d-status.off { background: var(--bg-2, #fef3c7); color: var(--warning); }
.d-queue { background: var(--danger); color: #fff; font-size: 10px; font-weight: 700; padding: 2px 8px; border-radius: 10px; }
.d-error { padding: 30px 20px; text-align: center; }
.d-handover {
  display: flex; align-items: center; gap: 10px; flex-wrap: wrap;
  margin: 10px 14px 0; padding: 10px 12px; border-radius: 12px;
  background: #eff6ff; border: 1px solid #bfdbfe; color: #1e40af;
}
html.dark .driver-app .d-handover { background: rgba(37, 99, 235, .15); border-color: rgba(37, 99, 235, .4); }
.d-handover-text { display: flex; flex-direction: column; gap: 2px; flex: 1; min-width: 150px; }
.d-content { flex: 1; padding: 12px 14px 90px; }
.d-nav {
  position: fixed; bottom: 0; left: 50%; transform: translateX(-50%); width: 100%; max-width: 640px;
  display: flex; background: var(--surface); border-top: 1px solid var(--border); z-index: 30;
  /* iPhone: jarak aman dari home-indicator */
  padding-bottom: env(safe-area-inset-bottom, 0px);
}
.d-nav-item {
  flex: 1; display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 2px;
  min-height: 44px; padding: 8px 0 10px; background: none; border: none; cursor: pointer; opacity: .55;
  -webkit-tap-highlight-color: transparent;
}
.d-nav-item.active { opacity: 1; color: var(--primary); }
.d-nav-ico { font-size: 18px; display: flex; align-items: center; justify-content: center; width: 44px; height: 24px; border-radius: 12px; transition: background .2s; }
.d-nav-item.active .d-nav-ico { background: var(--primary-soft); }
.d-nav-label { font-size: 10px; font-weight: 600; }
.d-toasts { position: fixed; bottom: calc(76px + env(safe-area-inset-bottom, 0px)); left: 50%; transform: translateX(-50%); z-index: 200; display: flex; flex-direction: column; gap: 8px; width: min(92vw, 560px); align-items: center; pointer-events: none; }
.d-toast { background: var(--card, #1e293b); color: #fff; padding: 10px 16px; border-radius: 12px; font-size: 12px; font-weight: 600; box-shadow: 0 8px 24px rgba(15, 23, 42, .3); text-align: center; }
.d-toast.error { background: var(--danger); }
.d-toast.warning { background: var(--warning); }
.d-toast.success { background: var(--success); }
.toast-enter-active, .toast-leave-active { transition: all .3s ease; }
.toast-enter-from, .toast-leave-to { opacity: 0; transform: translateY(10px); }
</style>
