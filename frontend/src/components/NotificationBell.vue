<script setup>
import { ref, onMounted, onBeforeUnmount } from 'vue'
import { useRealtimeStore } from '../stores/realtime'

const rt = useRealtimeStore()
const open = ref(false)

const ICON = { new_claim: '🚛', new_trip_report: '🗺️', appointment_update: '📅', water_purchase_new: '💧', overtime_new: '⏰', agenda_reminder: '📅' }
const TYPE_BADGE = {
  new_claim: 'badge-amber', new_trip_report: 'badge-blue', appointment_update: 'badge-purple', water_purchase_new: 'badge-cyan', overtime_new: 'badge-purple', agenda_reminder: 'badge-purple',
}

function toggle() {
  open.value = !open.value
  if (open.value) rt.markAllRead()
}

function onDocKey(e) { if (e.key === 'Escape') open.value = false }
onMounted(() => document.addEventListener('keydown', onDocKey))
onBeforeUnmount(() => document.removeEventListener('keydown', onDocKey))
</script>

<template>
  <div class="bell-wrap">
    <button class="btn-icon" title="Notifikasi realtime" aria-label="Notifikasi realtime" aria-haspopup="dialog" :aria-expanded="open" @click="toggle">
      🔔
      <span v-if="rt.unread" class="bell-badge">{{ rt.unread > 9 ? '9+' : rt.unread }}</span>
    </button>
    <div v-if="open" class="bell-panel" role="dialog" aria-label="Notifikasi realtime" @click.stop>
      <div class="bell-head row">
        <b>Notifikasi Realtime</b>
        <span class="muted" style="font-size:11px;">{{ rt.connected ? '⚡ terhubung' : '🔴 putus' }}</span>
      </div>
      <div v-if="!rt.items.length" class="empty" style="padding:16px;">Belum ada notifikasi.</div>
      <div v-for="it in rt.items" :key="it.id" class="bell-item">
        <span class="bell-ico">{{ ICON[it.type] || '🔔' }}</span>
        <div class="grow">
          <div style="font-size:12px;">{{ it.text }}</div>
          <div class="muted" style="font-size:10px;">{{ it.at }}</div>
        </div>
        <span class="badge" :class="TYPE_BADGE[it.type] || 'badge-gray'">{{ it.type.replace(/_/g, ' ') }}</span>
      </div>
    </div>
    <div v-if="open" class="bell-scrim" @click="open = false"></div>
  </div>
</template>

<style scoped>
.bell-wrap { position: relative; }
.bell-badge { position: absolute; top: -4px; right: -4px; background: #dc2626; color: #fff; font-size: 9px; font-weight: 700; border-radius: 10px; min-width: 16px; height: 16px; display: flex; align-items: center; justify-content: center; padding: 0 3px; }
.bell-panel { position: absolute; right: 0; top: 42px; width: 320px; max-height: 420px; overflow-y: auto; background: var(--surface); border: 1px solid var(--border); border-radius: 12px; box-shadow: 0 16px 40px rgba(2, 6, 23, .2); z-index: 1500; }
.bell-head { padding: 12px 14px; border-bottom: 1px solid var(--border, #e2e8f0); align-items: center; }
.bell-item { display: flex; gap: 10px; padding: 10px 14px; border-bottom: 1px solid var(--border, #e2e8f0); align-items: flex-start; }
.bell-item:last-child { border-bottom: none; }
.bell-ico { font-size: 16px; }
.bell-scrim { position: fixed; inset: 0; z-index: 1490; }
@media (max-width: 640px) { .bell-panel { position: fixed; left: 12px; right: 12px; top: 64px; width: auto; } }
</style>
