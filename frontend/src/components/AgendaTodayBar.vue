<script setup>
// v2.123.0 — kartu Agenda ringkas di beranda/dashboard.
// Proporsional, informatif, dan bisa diklik untuk membuka kalender penuh.
// Pengingat hari H (opsional per agenda) dikirim sekali per hari lewat
// NotificationBell (realtime store) — tanpa job scheduler.
import { onMounted, ref } from 'vue'
import { api } from '../api'
import { useAuthStore } from '../stores/auth'
import { useRealtimeStore } from '../stores/realtime'

const auth = useAuthStore()
const rt = useRealtimeStore()
const todayItems = ref([])
const nextItem = ref(null)
const loaded = ref(false)
const failed = ref(false)

const DAY_MS = 86400000

function isoDate(d) {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
}

const today = new Date()
const todayIso = isoDate(today)
const todayLabel = today.toLocaleDateString('id-ID', {
  weekday: 'long', day: 'numeric', month: 'long',
})

function dateShort(iso) {
  const [y, m, d] = String(iso).split('-').map(Number)
  return new Date(y, m - 1, d).toLocaleDateString('id-ID', { day: 'numeric', month: 'short' })
}

function sortItems(list) {
  return [...list].sort((a, b) => Number(b.pinned) - Number(a.pinned)
    || String(a.title || '').localeCompare(String(b.title || '')))
}

// Pengingat hari H — hanya item yang ditandai `notify_on_day`.
// Sekali per item per hari per user (localStorage), agar tidak spam.
function fireReminders(list) {
  const flagged = list.filter((it) => it.notify_on_day)
  if (!flagged.length) return
  const key = `agenda_notify:${auth.user?.user_name || ''}:${todayIso}`
  let seen = {}
  try { seen = JSON.parse(localStorage.getItem(key) || '{}') } catch { seen = {} }
  const fresh = flagged.filter((it) => !seen[String(it.id)])
  if (!fresh.length) return
  const text = fresh.length === 1
    ? `📅 Agenda hari ini: ${fresh[0].title}`
    : `📅 ${fresh.length} agenda hari ini — buka Agenda untuk detail`
  rt.push(text, 'agenda_reminder', { ids: fresh.map((x) => x.id) })
  for (const it of fresh) seen[String(it.id)] = 1
  try { localStorage.setItem(key, JSON.stringify(seen)) } catch { /* mode privat */ }
}

onMounted(async () => {
  try {
    const [day, next] = await Promise.allSettled([
      api('/api/agenda/day', { params: { date: todayIso } }),
      api('/api/agenda/upcoming', { params: { days: 14 } }),
    ])
    if (day.status === 'fulfilled') {
      todayItems.value = sortItems(day.value?.items || [])
      fireReminders(todayItems.value)
    }
    if (next.status === 'fulfilled') {
      const horizon = new Date(today.getTime() + 14 * DAY_MS)
      const list = sortItems(next.value?.items || [])
        .filter((it) => it.date > todayIso && it.date <= isoDate(horizon))
      nextItem.value = list[0] || null
    }
    if (day.status === 'rejected' && next.status === 'rejected') failed.value = true
  } finally {
    loaded.value = true
  }
})
</script>

<template>
  <router-link v-if="loaded && !failed" class="agenda-card" to="/agenda" :title="`Buka Agenda ${todayLabel}`">
    <div class="ac-head">
      <span class="ac-ico" aria-hidden="true">📅</span>
      <div class="ac-heading">
        <b>Agenda</b>
        <small>{{ todayLabel }}</small>
      </div>
      <span class="ac-count" :class="{ zero: !todayItems.length }">{{ todayItems.length }}</span>
    </div>

    <div class="ac-body">
      <template v-if="todayItems.length">
        <div v-for="it in todayItems.slice(0, 2)" :key="it.id" class="ac-item">
          <span class="ac-dot" :class="'cat-' + it.category" aria-hidden="true"></span>
          <span class="ac-title">{{ it.pinned ? '📌 ' : '' }}{{ it.title }}</span>
          <span v-if="it.publish_mode === 'scheduled' && it.publish_at" class="ac-time">
            {{ String(it.publish_at).slice(11, 16) }}
          </span>
        </div>
        <div v-if="todayItems.length > 2" class="ac-more">+{{ todayItems.length - 2 }} agenda lagi</div>
      </template>
      <div v-else class="ac-empty">Tidak ada agenda hari ini.</div>
    </div>

    <div class="ac-foot">
      <span v-if="nextItem" class="ac-next">
        Berikutnya <b>{{ dateShort(nextItem.date) }}</b> · {{ nextItem.title }}
      </span>
      <span v-else class="ac-next muted">Tidak ada agenda mendatang.</span>
      <span class="ac-open">Buka kalender →</span>
    </div>
  </router-link>
</template>

<style scoped>
.agenda-card {
  display: block; text-decoration: none; color: inherit;
  border: 1px solid var(--border); border-radius: 12px;
  background: var(--surface); padding: 12px 14px; margin-bottom: 12px;
  max-width: 720px;
  box-shadow: 0 1px 2px rgba(16, 24, 40, .04);
  transition: border-color .15s, box-shadow .15s;
}
.agenda-card:hover, .agenda-card:focus-visible {
  border-color: #7c3aed; box-shadow: 0 4px 14px rgba(124, 58, 237, .12);
  outline: none;
}
.ac-head { display: flex; align-items: center; gap: 10px; }
.ac-ico { font-size: 18px; line-height: 1; }
.ac-heading { display: flex; flex-direction: column; line-height: 1.2; }
.ac-heading b { font-size: 13px; }
.ac-heading small { font-size: 10px; color: var(--text-3); text-transform: capitalize; }
.ac-count {
  margin-left: auto; background: #7c3aed; color: #fff; border-radius: 999px;
  min-width: 24px; text-align: center; font-weight: 700; font-size: 11px; padding: 2px 8px;
}
.ac-count.zero { background: var(--bg); color: var(--text-3); }
.ac-body { margin: 8px 0 6px; display: grid; gap: 4px; }
.ac-item { display: flex; align-items: center; gap: 7px; font-size: 12px; min-width: 0; }
.ac-dot { width: 8px; height: 8px; border-radius: 50%; background: #7c3aed; flex: none; }
.ac-dot.cat-rapat { background: #2563eb; }
.ac-dot.cat-libur { background: #059669; }
.ac-dot.cat-event { background: #d97706; }
.ac-dot.cat-pengumuman { background: #dc2626; }
.ac-title { min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.ac-time { margin-left: auto; font-size: 10px; color: var(--text-3); font-variant-numeric: tabular-nums; }
.ac-more { font-size: 10px; color: var(--text-3); padding-left: 15px; }
.ac-empty { font-size: 12px; color: var(--text-3); }
.ac-foot {
  display: flex; align-items: center; gap: 8px; flex-wrap: wrap;
  border-top: 1px dashed var(--border); padding-top: 7px; font-size: 10px; color: var(--text-3);
}
.ac-next { min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.ac-open { margin-left: auto; color: #7c3aed; font-weight: 600; }
@media (max-width: 640px) {
  .agenda-card { max-width: none; }
  .ac-foot { font-size: 10px; }
}
</style>
