<script setup>
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { io } from 'socket.io-client'
import { useAuthStore } from '../../stores/auth'
import { useDriverStore, QUEUE_LABELS } from '../../stores/driverStore'
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
const syncOpen = ref(false)

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
let onVisible = null
let onPageShow = null

const queueLabel = computed(() => {
  const t = store.queueTotal
  if (!t) return ''
  return store.sync.failed ? `${t} antrean · ${store.sync.failed} gagal` : `${t} antrean`
})
const queueSizeLabel = computed(() => formatBytes(store.queueBytes))
const syncStateLabel = computed(() => {
  if (!store.online) return 'Offline'
  if (store.syncing) return 'Sinkron…'
  if (store.sync.auth) return 'Perlu login'
  if (store.sync.failed) return 'Ada data gagal'
  return 'Online'
})

function formatBytes(n) {
  const v = Number(n) || 0
  if (v < 1024) return `${v} B`
  if (v < 1024 * 1024) return `${Math.round(v / 1024)} KB`
  return `${(v / (1024 * 1024)).toFixed(1)} MB`
}

function formatTime(value) {
  if (!value) return '—'
  const d = new Date(value)
  if (Number.isNaN(d.getTime())) return '—'
  return d.toLocaleString('id-ID', { dateStyle: 'short', timeStyle: 'short' })
}

function itemStateLabel(it) {
  if (it.state === 'failed') return 'Gagal'
  if (it.nextAt && it.nextAt > Date.now()) return 'Tunggu'
  return 'Menunggu'
}

async function runSync(force = false) {
  let n = 0
  try {
    n = await store.syncAll({ force })
  } catch {
    toast('⚠️ Sinkronisasi gagal — akan dicoba lagi', 'error')
    return 0
  }
  if (n > 0) toast(`✅ ${n} data offline terkirim`, 'success')
  else if (store.sync.auth) toast('🔒 Sesi berakhir — login untuk mengirim antrean', 'warning')
  else if (store.sync.failed) toast('⚠️ Ada data ditolak server — buka antrean', 'error')
  return n
}

async function retryItem(it) {
  const n = await store.retryItem(it.store, it.id)
  if (n > 0) toast('✅ Data terkirim', 'success')
  else if (store.sync.auth) toast('🔒 Sesi berakhir — login ulang', 'warning')
  else toast('⚠️ Masih gagal — periksa pesan error', 'error')
}

async function dropItem(it) {
  const label = QUEUE_LABELS[it.store] || it.store
  if (!window.confirm(`Hapus data ${label} dari antrean? Data yang belum terkirim akan hilang.`)) return
  await store.dropItem(it.store, it.id)
  toast('🗑️ Data antrean dihapus', 'warning')
}

function goLogin() {
  syncOpen.value = false
  doLogout()
}

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
    store.ensurePersistentStorage()
    store.loadDailyCode()
    store.loadNotifications()
    connectSocket()
    store.locate()
      .then(() => {
        if (store.gps.stale) {
          const jam = store.gps.at
            ? new Date(store.gps.at).toLocaleTimeString('id-ID', { hour: '2-digit', minute: '2-digit' })
            : ''
          toast(`📍 GPS belum aktif — memakai posisi terakhir${jam ? ` (${jam})` : ''}. Keluar ruangan lalu tekan "Isi Lokasi & Jam".`, 'warning')
        }
      })
      .catch(() => {
        toast('📍 GPS tidak aktif — izinkan akses lokasi, lalu tekan "Isi Lokasi & Jam"', 'warning')
      })
    loadPendingTask() // v2.73.0 — cek serah terima yang belum dikonfirmasi
    // v2.127.0 — sync juga saat halaman dibuka (bukan hanya saat event
    // online / timer 30 detik): antrean dari sesi sebelumnya langsung dicoba.
    store.syncAll()
      .then((n) => { if (n) toast(`✅ ${n} data offline terkirim`, 'success') })
      .catch(() => { /* dicoba lagi oleh timer/event online */ })
  }
  // Sinkronisasi: saat online kembali, app kembali terlihat (iOS/Android),
  // dan interval 30 detik selama halaman terlihat.
  onOnline = () => { store.online = true; runSync() }
  onOffline = () => { store.online = false }
  // v2.127.5 — pakai probe server, bukan hanya navigator.onLine yang bisa
  // tertinggal `false` setelah mode pesawat dimatikan.
  onVisible = () => {
    if (document.visibilityState !== 'visible') return
    runSync()
  }
  onPageShow = () => { runSync() }
  window.addEventListener('online', onOnline)
  window.addEventListener('offline', onOffline)
  document.addEventListener('visibilitychange', onVisible)
  window.addEventListener('pageshow', onPageShow)
  syncTimer = setInterval(() => {
    if (document.visibilityState !== 'visible') return
    runSync()
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
  if (onVisible) document.removeEventListener('visibilitychange', onVisible)
  if (onPageShow) window.removeEventListener('pageshow', onPageShow)
})
</script>

<template>
  <div class="driver-app">
    <!-- Header -->
    <header class="d-header">
      <img :src="brandIcon" alt="BPF" class="d-logo" />
      <div class="grow" style="min-width:0;">
        <div class="d-name">{{ store.driverDisplayName || (auth.user?.full_name || 'Driver') }}</div>
        <div class="muted" style="font-size:10px;">{{ store.profile?.nopol || '' }} · {{ store.profile?.vehicle_type || '' }}</div>
      </div>
      <button class="btn-icon" title="Bantuan & glosarium" aria-label="Bantuan" @click="helpOpen = true">❓</button>
      <DriverNotifBell />
      <button class="btn-icon" :title="dark ? 'Mode terang' : 'Mode gelap'" @click="toggleDark">{{ dark ? '☀️' : '🌙' }}</button>
      <button class="btn-icon" title="Keluar" @click="doLogout">🚪</button>
    </header>

    <!-- Status bar -->
    <div class="d-status" :class="store.online ? 'on' : 'off'">
      <span>{{ store.online ? '🟢' : '🟡' }} {{ syncStateLabel }}</span>
      <button v-if="queueLabel" type="button" class="d-queue" :aria-label="'Buka antrean: ' + queueLabel" @click="syncOpen = true">
        📦 {{ queueLabel }}
      </button>
      <div class="spacer"></div>
      <button class="btn btn-sm" :disabled="store.syncing || !store.online" @click="runSync()">
        {{ store.syncing ? '⏳ Sinkron…' : '🔄 Sinkron' }}
      </button>
    </div>

    <!-- Sesi habis di tengah sync: antrean tetap aman, minta login ulang -->
    <div v-if="store.sync.auth" class="d-auth" role="alert">
      <span>🔒 Sesi berakhir — {{ store.queueTotal }} data menunggu dikirim.</span>
      <button class="btn btn-sm btn-primary" @click="goLogin">Masuk</button>
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

    <!-- Panel antrean & status sinkronisasi -->
    <div v-if="syncOpen" class="d-sync-overlay" @click.self="syncOpen = false">
      <section class="d-sync-panel" role="dialog" aria-modal="true" aria-label="Antrean sinkronisasi">
        <header class="d-sync-head">
          <b>📦 Sinkronisasi</b>
          <button class="btn-icon" type="button" aria-label="Tutup" @click="syncOpen = false">✕</button>
        </header>
        <p class="d-sync-meta">
          {{ store.lastSync ? 'Terakhir: ' + formatTime(store.lastSync) : 'Belum pernah sinkron' }}
          · {{ store.sync.pending }} menunggu
          <span v-if="store.sync.failed"> · {{ store.sync.failed }} gagal</span>
          <span v-if="store.queueBytes"> · {{ queueSizeLabel }}</span>
        </p>
        <p v-if="store.sync.auth" class="d-sync-auth">
          Sesi berakhir. Login ulang agar {{ store.queueTotal }} data bisa dikirim.
        </p>
        <div v-if="!store.queueItems.length" class="d-sync-empty">
          ✅ Tidak ada data menunggu. Semua sudah terkirim.
        </div>
        <ul v-else class="d-sync-list">
          <li v-for="it in store.queueItems" :key="it.store + ':' + it.id" class="d-sync-item">
            <div class="d-sync-row">
              <b>{{ QUEUE_LABELS[it.store] || it.store }}</b>
              <span class="d-sync-time">{{ formatTime(it.timestamp) }}</span>
              <span class="d-sync-badge" :class="it.state === 'failed' ? 'bad' : 'wait'">
                {{ itemStateLabel(it) }}
              </span>
            </div>
            <div v-if="it.lastError" class="d-sync-err">{{ it.lastError }}</div>
            <div class="d-sync-actions">
              <button class="btn btn-sm" type="button" :disabled="store.syncing" @click="retryItem(it)">
                Coba lagi
              </button>
              <button class="btn btn-sm btn-danger" type="button" :disabled="store.syncing" @click="dropItem(it)">
                Hapus
              </button>
            </div>
          </li>
        </ul>
        <div class="d-sync-foot">
          <button class="btn btn-primary" type="button" :disabled="store.syncing || !store.online" @click="runSync(true)">
            {{ store.syncing ? '⏳ Mengirim…' : '🔄 Sinkron sekarang' }}
          </button>
        </div>
      </section>
    </div>

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
.d-queue { background: var(--danger); color: #fff; font-size: 10px; font-weight: 700; padding: 4px 8px; border-radius: 10px; border: none; cursor: pointer; }
.d-auth {
  display: flex; align-items: center; justify-content: space-between; gap: 10px;
  padding: 8px 14px; font-size: 11px; font-weight: 600;
  background: #fef2f2; color: #b91c1c; border-bottom: 1px solid #fecaca;
}
html.dark .d-auth { background: rgba(220, 38, 38, .15); border-color: rgba(220, 38, 38, .4); color: #fca5a5; }
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

/* Panel sinkronisasi (v2.127.0) */
.d-sync-overlay {
  position: fixed; inset: 0; z-index: 150; display: flex; align-items: flex-end; justify-content: center;
  background: rgba(15, 23, 42, .55);
}
.d-sync-panel {
  width: 100%; max-width: 640px; max-height: 82vh; overflow: auto;
  background: var(--surface); border-top: 1px solid var(--border);
  border-radius: 18px 18px 0 0; padding: 14px 14px calc(14px + env(safe-area-inset-bottom, 0px));
  box-shadow: 0 -12px 40px rgba(15, 23, 42, .35);
}
.d-sync-head { display: flex; align-items: center; justify-content: space-between; gap: 10px; }
.d-sync-meta { margin: 6px 0 10px; font-size: 11px; color: var(--text-3); }
.d-sync-auth {
  margin: 0 0 10px; padding: 8px 10px; border-radius: 10px; font-size: 11px;
  background: #fef2f2; color: #b91c1c; border: 1px solid #fecaca;
}
html.dark .d-sync-auth { background: rgba(220, 38, 38, .15); border-color: rgba(220, 38, 38, .4); color: #fca5a5; }
.d-sync-empty { padding: 22px 8px; text-align: center; font-size: 12px; color: var(--text-3); }
.d-sync-list { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: 8px; }
.d-sync-item { border: 1px solid var(--border); border-radius: 12px; padding: 9px 10px; background: var(--bg); }
.d-sync-row { display: flex; align-items: center; gap: 8px; font-size: 12px; }
.d-sync-time { font-size: 10px; color: var(--text-3); }
.d-sync-badge { margin-left: auto; font-size: 9px; font-weight: 700; padding: 2px 7px; border-radius: 8px; text-transform: uppercase; }
.d-sync-badge.wait { background: var(--bg-2, #fef3c7); color: var(--warning); }
.d-sync-badge.bad { background: #fee2e2; color: var(--danger); }
.d-sync-err { margin-top: 4px; font-size: 10px; color: var(--danger); line-height: 1.35; }
.d-sync-actions { display: flex; gap: 6px; margin-top: 7px; }
.d-sync-foot { position: sticky; bottom: 0; padding-top: 12px; background: var(--surface); }
.d-sync-foot .btn { width: 100%; justify-content: center; }
.d-toast { background: var(--card, #1e293b); color: #fff; padding: 10px 16px; border-radius: 12px; font-size: 12px; font-weight: 600; box-shadow: 0 8px 24px rgba(15, 23, 42, .3); text-align: center; }
.d-toast.error { background: var(--danger); }
.d-toast.warning { background: var(--warning); }
.d-toast.success { background: var(--success); }
.toast-enter-active, .toast-leave-active { transition: all .3s ease; }
.toast-enter-from, .toast-leave-to { opacity: 0; transform: translateY(10px); }
</style>
