<script setup>
import { computed, nextTick, onMounted, onBeforeUnmount, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { api } from '../api'
import { useAuthStore } from '../stores/auth'
import { useRealtimeStore } from '../stores/realtime'
import { identity } from '../stores/identity'
import NotificationBell from '../components/NotificationBell.vue'
import ToastStack from '../components/ToastStack.vue'
import HelpCenter from '../components/HelpCenter.vue'
import OnboardingTour from '../components/OnboardingTour.vue'
import { onboardingSteps } from '../content/help.js'
import { enableUsabilityModeFromUrl, markFirstAction, markSessionStart } from '../utils/usability.js'

const auth = useAuthStore()
const rt = useRealtimeStore()
const route = useRoute()
const router = useRouter()

const open = ref(false)
const rtOn = ref(false)
const dark = ref(localStorage.getItem('bpf_dark') === '1')
const hc = ref(localStorage.getItem('bpf_hc') === '1')
const brandIcon = '/static/icon-192.png'

const IT_ROLES = ['it_sby', 'it_hu', 'it_jkt2', 'it_bdg', 'it_smg', 'it_mlg',
  'it_mdn', 'it_bjm', 'it_plm', 'it_lpg', 'admin']

// P1 UI/UX: menu dikelompokkan agar admin cabang (21 menu) tidak melihat
// satu daftar panjang tanpa konteks.
const MENU_GROUPS = [
  {
    label: 'Ringkasan',
    items: [
      { label: 'Dashboard', path: '/dashboard', icon: '📊', roles: ['admin'] },
      { label: 'Dashboard GA', path: '/ga', icon: '🧾', roles: ['ga', 'admin'], badge: 'ga_pending' },
      { label: 'Dashboard Finance', path: '/finance', icon: '💰', roles: ['finance', 'admin'], badge: 'finance_pending' },
      { label: 'Marketing Hub', path: '/marketing', icon: '📣', roles: ['marketing'] },
      { label: 'Chief Driver', path: '/chief-driver', icon: '🚛', roles: ['chief_driver', 'ga', 'admin'] },
    ],
  },
  {
    label: 'SDM & Armada',
    items: [
      // v2.78.0: akun user, profil driver, penugasan, dan kendaraan
      // dikelompokkan dalam satu tempat agar tidak tersebar di 3 menu.
      { label: 'User & Driver', path: '/users', icon: '👥', roles: ['admin'] },
      { label: 'Penugasan Driver', path: '/assignments', icon: '🚗', roles: ['ga', 'admin'], badge: 'assignments_pending' },
      { label: 'Kendaraan & Pengaturan', path: '/settings', icon: '🚙', roles: ['admin'] },
      { label: 'In-Out Karyawan', path: '/inout', icon: '🚪', roles: ['receptionist', 'admin'] },
    ],
  },
  {
    label: 'Operasional',
    items: [
      { label: 'Log Perjalanan', path: '/trips', icon: '🗺️', roles: ['ga', 'admin'] },
      { label: 'BBM, Kasbon & SPBU', path: '/cash', icon: '⛽', roles: ['ga', 'finance', 'admin'], badge: 'cash_pending', keywords: 'kasbon klaim bbm spbu otp subsiditepat' },
      { label: 'Air Minum', path: '/water', icon: '🚰', roles: ['ob', 'finance', 'admin'], badge: 'water_pending' },
      { label: 'Aset & Pemeliharaan', path: '/assets', icon: '🔧', roles: ['ga', 'admin'] },
      { label: 'Pengadaan (PO)', path: '/procurement', icon: '🛒', roles: ['ga', 'admin'] },
      { label: 'Overtime Saya', path: '/overtime-me', icon: '⏰', roles: ['ob', 'security'] },
      { label: 'Overtime', path: '/ga-hr', icon: '⏰', roles: ['ga_hr', 'admin'] },
    ],
  },
  {
    label: 'Persetujuan',
    items: [
      // wave-18A: finance tidak melihat ACC Atasan (tidak berguna untuk pengelolaan klaim BBM) — OB/Security/GA/HR saja
      { label: 'ACC Atasan', path: '/approvals', icon: '✅', roles: ['chief_driver', 'ga', 'ga_hr'], badge: 'approvals_pending' },
    ],
  },
  {
    // Rekrutmen: satu sumber data pelamar. Receptionist mengelola, Traineer
    // hanya membaca; verifikasi kehadiran calon karyawan ada di FirstWork.
    label: 'Rekrutmen & Trainee',
    items: [
      { label: 'Rekrutmen', path: '/receptionist', icon: '🪪', roles: ['receptionist', 'traineer', 'admin'], keywords: 'pelamar kerja recruitment rekrutmen' },
      // v2.80.0: form publik trainee + verifikasi (traineer, finance read-only, admin)
      { label: 'Absensi FirstWork', path: '/first-work', icon: '📝', roles: ['traineer', 'finance', 'ga_hr', 'admin'], badge: 'first_work_pending', keywords: 'absensi first work trainee verifikasi' },
    ],
  },
  {
    label: 'Laporan & Analisis',
    items: [
      { label: 'Rekap Klaim BBM', path: '/rekap', icon: '📋', roles: ['ga', 'finance', 'admin'] },
      { label: 'Realisasi Pengeluaran', path: '/expenses', icon: '📊', roles: ['finance', 'admin'] },
      { label: 'Analisis BBM & Armada', path: '/analytics', icon: '📈', roles: ['ga', 'finance', 'admin'] },
    ],
  },
  {
    label: 'Administrasi',
    items: [
      { label: 'Access Review', path: '/access-review', icon: '🛂', roles: ['admin'] },
      { label: 'Audit Log', path: '/logs', icon: '📝', roles: ['admin'] },
    ],
  },
  {
    label: 'Perkakas IT',
    items: [
      { label: 'Inventaris IT', path: '/it/inventory', icon: '📦', roles: IT_ROLES },
      { label: 'Scan Aset', path: '/it/scan', icon: '📷', roles: IT_ROLES },
      { label: 'News Scraper', path: '/it', icon: '📰', roles: IT_ROLES },
      { label: 'Transcoder', path: '/transcoder', icon: '🎬', roles: IT_ROLES },
      { label: 'PDF Kit', path: '/pdfkit', icon: '📄', roles: IT_ROLES },
    ],
  },
]

function canSee(m) {
  if (!m.roles.includes(auth.role)) return false
  // v2.37.0: Admin cabang (admin_<kode>) tidak melihat menu lintas cabang
  if (['/access-review', '/logs'].includes(m.path) && !auth.isHoAdmin) return false
  // v2.45.0: ACC urusan divisi terkait — admin tidak terlibat ACC apa pun
  if (m.path === '/approvals' && auth.role === 'admin') return false
  return true
}

const menuGroups = computed(() => MENU_GROUPS
  .map((g) => ({ label: g.label, items: g.items.filter(canSee) }))
  .filter((g) => g.items.length))
const items = computed(() => menuGroups.value.flatMap((g) => g.items))
function matchesPath(path) {
  return route.path === path || route.path.startsWith(`${path}/`)
}
const pageTitle = computed(() => route.meta?.title || (items.value.find((i) => matchesPath(i.path))?.label || 'Dashboard'))
const activeGroup = computed(() => menuGroups.value.find((g) => g.items.some((i) => matchesPath(i.path)))?.label || '')
const breadcrumb = computed(() => {
  if (route.path === '/') return []
  return activeGroup.value ? [activeGroup.value, pageTitle.value] : [pageTitle.value]
})

// ---- Badge angka antrean (P1) ----
const badges = ref({})
let badgeTimer = null
async function loadBadges() {
  try {
    const d = await api('/api/nav/badges')
    badges.value = d?.badges || {}
  } catch { /* badge bersifat opsional */ }
}
function scheduleBadges() {
  clearTimeout(badgeTimer)
  badgeTimer = setTimeout(loadBadges, 800)
}
function badgeFor(m) {
  const n = m.badge ? Number(badges.value[m.badge] || 0) : 0
  if (!n) return ''
  return n > 99 ? '99+' : String(n)
}

// ---- Pencarian menu (Ctrl/Cmd+K) ----
const searchOpen = ref(false)
const searchQ = ref('')
const searchIdx = ref(0)
const searchInput = ref(null)
const flatMenu = computed(() => menuGroups.value.flatMap((g) => g.items.map((m) => ({ ...m, group: g.label }))))
const searchResults = computed(() => {
  const q = searchQ.value.trim().toLowerCase()
  if (!q) return flatMenu.value
  return flatMenu.value.filter((m) => `${m.label} ${m.group} ${m.path} ${m.keywords || ''}`.toLowerCase().includes(q))
})
function openSearch() {
  searchOpen.value = true
  searchQ.value = ''
  searchIdx.value = 0
  nextTick(() => searchInput.value?.focus())
}
function closeSearch() {
  searchOpen.value = false
  searchQ.value = ''
}
function goSearch(m) {
  if (!m) return
  markFirstAction(`menu:${m.label || m.path}`)
  closeSearch()
  open.value = false
  router.push(m.path)
}
function moveSearch(delta) {
  const n = searchResults.value.length
  if (!n) return
  searchIdx.value = (searchIdx.value + delta + n) % n
}
function onSearchKey(e) {
  if (e.key === 'ArrowDown') { e.preventDefault(); moveSearch(1) }
  else if (e.key === 'ArrowUp') { e.preventDefault(); moveSearch(-1) }
  else if (e.key === 'Enter') { e.preventDefault(); goSearch(searchResults.value[searchIdx.value]) }
  else if (e.key === 'Escape') { e.preventDefault(); closeSearch() }
}
function isTyping(e) {
  const t = e.target
  return !!t && (t.tagName === 'INPUT' || t.tagName === 'TEXTAREA' || t.tagName === 'SELECT' || t.isContentEditable)
}

// ---- P4: bantuan, glosarium, onboarding ----
const helpOpen = ref(false)
const tourOpen = ref(false)
const tourSteps = ref([])
const onboardKey = computed(() => `bpf_onboarded:${auth.user?.user_name || ''}`)

function openHelp() {
  helpOpen.value = true
}
function startTour() {
  if (!auth.user) return
  helpOpen.value = false
  tourSteps.value = onboardingSteps(auth.role, auth.user, auth.isHoAdmin)
  tourOpen.value = true
}
function finishTour() {
  if (auth.user?.user_name) localStorage.setItem(onboardKey.value, '1')
  tourOpen.value = false
}
let tourTimer = null

function onGlobalKey(e) {
  if ((e.ctrlKey || e.metaKey) && String(e.key).toLowerCase() === 'k') {
    e.preventDefault()
    searchOpen.value ? closeSearch() : openSearch()
  } else if (e.key === 'Escape' && searchOpen.value) {
    closeSearch()
  } else if (e.key === '?' && !isTyping(e)) {
    e.preventDefault()
    openHelp()
  }
}
watch(searchQ, () => { searchIdx.value = 0 })
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

let badgeInterval = null
let unwatchBadges = []
onMounted(() => {
  enableUsabilityModeFromUrl(window.location.search)
  markSessionStart()
  document.documentElement.classList.toggle('dark', dark.value)
  document.documentElement.classList.toggle('hc', hc.value)
  connectRealtime()
  loadBadges()
  unwatchBadges = [
    watch(() => rt.items.length, scheduleBadges),
    watch(() => rt.receptionistSeq, scheduleBadges),
  ]
  badgeInterval = setInterval(() => {
    if (document.visibilityState === 'visible') loadBadges()
  }, 60000)
  tourTimer = setTimeout(() => {
    if (auth.user?.user_name && localStorage.getItem(onboardKey.value) !== '1') startTour()
  }, 700)
  document.addEventListener('keydown', onGlobalKey)
})
onBeforeUnmount(() => {
  unwatchRt?.(); rt.disconnect()
  unwatchBadges.forEach((fn) => fn())
  clearTimeout(badgeTimer)
  clearInterval(badgeInterval)
  clearTimeout(tourTimer)
  document.removeEventListener('keydown', onGlobalKey)
})
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
        <div v-for="g in menuGroups" :key="g.label" class="nav-group">
          <div class="nav-sec">{{ g.label }}</div>
          <router-link v-for="m in g.items" :key="m.path" :to="m.path" @click="open = false">
            <span class="ico">{{ m.icon }}</span>
            <span class="nav-label">{{ m.label }}</span>
            <span v-if="badgeFor(m)" class="menu-badge" :title="`${badgeFor(m)} menunggu tindakan`">{{ badgeFor(m) }}</span>
          </router-link>
        </div>
      </nav>

      <div class="user-card">
        <div class="avatar" :style="{ background: auth.meta?.color || '#2563eb' }">{{ initials }}</div>
        <div class="grow" style="min-width:0;">
          <div class="u-name">{{ auth.user?.full_name || auth.user?.user_name }}</div>
          <div class="u-role">
            <span class="role-chip" :style="{ background: auth.meta?.color }">{{ auth.meta?.icon }} {{ auth.meta?.label }}</span>
            <span v-if="auth.user?.branch_name" class="branch-chip">🏢 {{ auth.user.branch_name }}</span>
            <span v-if="auth.role === 'admin' && !auth.isHoAdmin" class="branch-chip" title="Admin cabang — terkunci ke cabang ini">🔒 Cabang</span>
          </div>
        </div>
        <router-link class="btn-icon" to="/profile" title="Profil Saya" aria-label="Profil Saya">👤</router-link>
        <button class="btn-icon" title="Keluar" aria-label="Keluar" @click="doLogout">🚪</button>
      </div>
    </aside>

    <div class="main">
      <header class="topbar">
        <button class="btn-icon burger" title="Menu" @click="open = !open">☰</button>
        <h1>{{ pageTitle }}</h1>
        <button class="search-trigger" title="Cari menu (Ctrl+K)" aria-label="Cari menu" @click="openSearch">
          <span aria-hidden="true">🔍</span>
          <span class="search-label">Cari menu</span>
          <kbd>Ctrl K</kbd>
        </button>
        <span class="muted topbar-date" style="font-size:11px;">{{ new Date().toLocaleDateString('id-ID', { weekday: 'long', day: 'numeric', month: 'long', year: 'numeric' }) }}</span>
        <div class="spacer"></div>
        <span class="rt-dot" :class="rtOn ? 'on' : 'off'" :title="rtOn ? 'Realtime terhubung' : 'Realtime terputus'">
          {{ rtOn ? '⚡ Realtime' : '🔴 Offline' }}
        </span>
        <button class="btn-icon" title="Bantuan & glosarium (?)" aria-label="Bantuan" @click="openHelp">❓</button>
        <NotificationBell />
        <button class="btn-icon" :title="hc ? 'Mode kontras normal' : 'Mode kontras tinggi'" :aria-label="hc ? 'Mode kontras normal' : 'Mode kontras tinggi'" @click="toggleHc">{{ hc ? '🌗' : '🔆' }}</button>
        <button class="btn-icon" :title="dark ? 'Mode terang' : 'Mode gelap'" :aria-label="dark ? 'Mode terang' : 'Mode gelap'" @click="toggleDark">{{ dark ? '☀️' : '🌙' }}</button>
      </header>

      <main class="content" id="konten" tabindex="-1">
        <nav v-if="breadcrumb.length" class="crumb" aria-label="Breadcrumb">
          <router-link to="/">Beranda</router-link>
          <template v-for="(c, i) in breadcrumb" :key="`${c}-${i}`">
            <span class="crumb-sep" aria-hidden="true">/</span>
            <span :class="{ 'crumb-cur': i === breadcrumb.length - 1 }" :aria-current="i === breadcrumb.length - 1 ? 'page' : undefined">{{ c }}</span>
          </template>
        </nav>
        <router-view />
      </main>
    </div>

    <div v-if="searchOpen" class="search-overlay" @click.self="closeSearch">
      <div class="search-box" role="dialog" aria-modal="true" aria-label="Cari menu">
        <div class="search-head">
          <span aria-hidden="true">🔍</span>
          <input ref="searchInput" v-model="searchQ" class="search-input" type="search"
                 placeholder="Cari menu… (mis. kasbon, air minum, pengaturan)"
                 aria-label="Kata kunci menu" @keydown="onSearchKey" />
          <button class="btn-icon" aria-label="Tutup pencarian" title="Tutup (Esc)" @click="closeSearch">✕</button>
        </div>
        <div class="search-list">
          <button v-for="(m, i) in searchResults" :key="m.path" type="button"
                  class="search-item" :class="{ active: i === searchIdx }"
                  @mouseenter="searchIdx = i" @click="goSearch(m)">
            <span class="ico" aria-hidden="true">{{ m.icon }}</span>
            <span class="grow" style="min-width:0;text-align:left;">
              <b>{{ m.label }}</b>
              <small>{{ m.group }}</small>
            </span>
            <span v-if="badgeFor(m)" class="menu-badge">{{ badgeFor(m) }}</span>
          </button>
          <div v-if="!searchResults.length" class="empty" style="padding:18px;">Menu tidak ditemukan.</div>
        </div>
        <div class="search-foot">↑↓ pilih · Enter buka · Esc tutup</div>
      </div>
    </div>
    <HelpCenter :open="helpOpen" :path="route.path" :role="auth.role" @close="helpOpen = false" @replay-tour="startTour" />
    <OnboardingTour :open="tourOpen" :steps="tourSteps" @close="finishTour" @done="finishTour" />
    <ToastStack />
  </div>
</template>

<style scoped>
.nav-group { margin-bottom: 4px; }
.nav-group .nav-sec { padding-top: 10px; }
.nav-label { flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.menu-badge {
  margin-left: auto; background: var(--danger); color: #fff;
  font-size: 10px; font-weight: 700; line-height: 1;
  border-radius: 20px; min-width: 18px; height: 18px;
  display: inline-flex; align-items: center; justify-content: center;
  padding: 0 5px; flex-shrink: 0;
}
.search-trigger {
  display: inline-flex; align-items: center; gap: 6px;
  background: var(--surface-2); border: 1px solid var(--border);
  color: var(--text-3); border-radius: 9px; padding: 6px 10px; font-size: 12px;
}
.search-trigger:hover { color: var(--text); border-color: var(--primary); }
.search-trigger kbd {
  font-family: inherit; font-size: 10px; border: 1px solid var(--border);
  background: var(--surface); border-radius: 5px; padding: 1px 5px;
}
.crumb {
  display: flex; align-items: center; gap: 6px;
  font-size: 11px; color: var(--text-3); margin-bottom: 12px;
}
.crumb a { color: var(--text-3); }
.crumb a:hover { color: var(--primary); }
.crumb-cur { color: var(--text-2); font-weight: 600; }
.search-overlay {
  position: fixed; inset: 0; z-index: 2500;
  background: rgba(15, 23, 42, .55);
  display: flex; justify-content: center; align-items: flex-start;
  padding: 12vh 14px 14px;
}
.search-box {
  width: 100%; max-width: 560px; background: var(--surface);
  border: 1px solid var(--border); border-radius: 14px;
  box-shadow: var(--shadow-lg); overflow: hidden;
}
.search-head {
  display: flex; align-items: center; gap: 10px;
  padding: 12px 14px; border-bottom: 1px solid var(--border);
}
.search-input {
  flex: 1; border: none; outline: none; background: transparent;
  color: var(--text); font-size: 14px;
}
.search-list { max-height: min(55vh, 420px); overflow-y: auto; padding: 6px; }
.search-item {
  display: flex; align-items: center; gap: 10px; width: 100%;
  border: none; background: transparent; color: var(--text-2);
  padding: 9px 10px; border-radius: 8px; font-size: 13px;
}
.search-item:hover, .search-item.active { background: var(--surface-2); color: var(--text); }
.search-item b { display: block; font-size: 12.5px; }
.search-item small { display: block; font-size: 10px; color: var(--text-3); }
.search-foot { padding: 8px 14px; border-top: 1px solid var(--border); font-size: 10px; color: var(--text-3); }
@media (max-width: 900px) {
  .topbar-date { display: none; }
  .search-label, .search-trigger kbd { display: none; }
}
@media (max-width: 640px) {
  .search-overlay { padding-top: 70px; }
}
</style>
