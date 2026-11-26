<script setup>
import { computed, onMounted, ref, watchEffect } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { api } from '../api'
import { useAuthStore } from '../stores/auth'
import ReceptionistView from './dashboard/ReceptionistView.vue'
import RecruitmentCasesView from './RecruitmentCasesView.vue'
import CvOnlineView from './CvOnlineView.vue'
import FirstWorkView from './FirstWorkView.vue'
import TkdView from './TkdView.vue'
import RecruitmentLinksView from './RecruitmentLinksView.vue'

const auth = useAuthStore()
const route = useRoute()
const router = useRouter()

// Satu pintu masuk rekrutmen. Setiap tab mempertahankan batas peran lama
// (lihat router/index.js); tab yang tidak diizinkan tidak dirender sama sekali.
const TABS = [
  { id: 'pelamar', label: 'Pelamar', roles: ['receptionist', 'traineer', 'admin'], component: ReceptionistView },
  { id: 'kasus', label: 'Kasus', roles: ['traineer', 'ga_hr', 'admin'], component: RecruitmentCasesView },
  { id: 'cv', label: 'CV Online', roles: ['traineer', 'ga_hr', 'admin'], component: CvOnlineView, badge: 'cv_online_pending' },
  { id: 'firstwork', label: 'FirstWork', roles: ['traineer', 'finance', 'ga_hr', 'admin'], component: FirstWorkView, badge: 'first_work_pending' },
  { id: 'tkd', label: 'TKD', roles: ['traineer', 'ga_hr', 'admin'], component: TkdView },
  { id: 'tautan', label: 'Tautan', roles: ['receptionist', 'traineer', 'ga_hr', 'admin'], component: RecruitmentLinksView },
]

const availableTabs = computed(() => TABS.filter((t) => t.roles.includes(auth.role)))
const currentTab = computed(() => {
  const asked = String(route.query.tab || '')
  return availableTabs.value.some((t) => t.id === asked)
    ? asked
    : (availableTabs.value[0]?.id || '')
})
const activeComponent = computed(() =>
  availableTabs.value.find((t) => t.id === currentTab.value)?.component || null)

// Query adalah sumber tautan: bila ?tab= tidak ada/terlarang, normalisasi ke tab
// pertama yang diizinkan supaya URL selalu bisa dibagikan.
watchEffect(() => {
  if (route.query.tab !== currentTab.value) {
    router.replace({ query: { ...route.query, tab: currentTab.value } })
  }
})

const badges = ref({})
onMounted(async () => {
  try {
    const d = await api('/api/nav/badges')
    badges.value = d?.badges || {}
  } catch { /* badge bersifat opsional */ }
})
function badgeFor(tab) {
  if (!tab.badge) return ''
  const n = Number(badges.value[tab.badge] || 0)
  if (!n) return ''
  return n > 99 ? '99+' : String(n)
}
function selectTab(tab) {
  router.replace({ query: { ...route.query, tab: tab.id } })
}
</script>

<template>
  <div>
    <div class="card card-pad hub-header">
      <h2 class="hub-title">🪪 Rekrutmen</h2>
      <div class="muted hub-sub">
        Pelamar, kasus, CV Online, FirstWork, TKD, dan tautan form dalam satu halaman.
      </div>
    </div>

    <nav v-if="availableTabs.length" class="hub-tabs" aria-label="Tab Rekrutmen">
      <button v-for="t in availableTabs" :key="t.id" type="button"
              class="btn btn-sm hub-tab" :class="{ active: currentTab === t.id }"
              :data-tab="t.id" :data-active="currentTab === t.id ? 'true' : 'false'"
              :aria-current="currentTab === t.id ? 'page' : undefined"
              @click="selectTab(t)">
        {{ t.label }}
        <span v-if="badgeFor(t)" class="hub-badge" :title="`${badgeFor(t)} menunggu tindakan`">{{ badgeFor(t) }}</span>
      </button>
    </nav>
    <div v-else class="card card-pad">Tidak ada modul rekrutmen untuk peran ini.</div>

    <component :is="activeComponent" embedded />
  </div>
</template>

<style scoped>
.hub-header { margin-bottom: 12px; }
.hub-title { font-size: 17px; font-weight: 700; }
.hub-sub { font-size: 12px; margin-top: 4px; }
.hub-tabs {
  display: flex; gap: 6px; align-items: center;
  overflow-x: auto; -webkit-overflow-scrolling: touch;
  margin-bottom: 12px; padding-bottom: 4px;
}
.hub-tab { white-space: nowrap; flex-shrink: 0; }
.hub-tab.active { border-color: var(--primary); color: var(--primary); font-weight: 700; }
.hub-badge {
  display: inline-flex; align-items: center; justify-content: center;
  min-width: 18px; height: 18px; padding: 0 5px; margin-left: 4px;
  border-radius: 20px; background: var(--danger); color: #fff;
  font-size: 10px; font-weight: 700; line-height: 1;
}
</style>
