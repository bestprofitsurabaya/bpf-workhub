<script setup>
import { ref, onMounted, onBeforeUnmount } from 'vue'
import { useDriverStore } from '../stores/driverStore'
import { getPushState, enablePush, disablePush } from '../utils/push'

const store = useDriverStore()
const open = ref(false)
// v2.128.0 — status notifikasi HP (Web Push)
const push = ref({ supported: false, subscribed: false, permission: 'default', ios: false, standalone: false })
const pushBusy = ref(false)
const pushMsg = ref('')

async function loadPush() {
  try { push.value = await getPushState() } catch { /* abaikan */ }
}

async function togglePush() {
  pushBusy.value = true
  pushMsg.value = ''
  try {
    if (push.value.subscribed) {
      await disablePush()
      pushMsg.value = '🔕 Notifikasi HP dimatikan di perangkat ini.'
    } else {
      await enablePush()
      pushMsg.value = '✅ Notifikasi HP aktif — tetap masuk walau app ditutup.'
    }
    await loadPush()
  } catch (e) {
    pushMsg.value = '⚠️ ' + (e?.message || 'Gagal mengatur notifikasi HP')
  } finally {
    pushBusy.value = false
  }
}

const ICONS = {
  claim: { approved: '✅', paid: '💸', archived: '📦', rejected: '⛔' },
  cash: { approved: '✅', paid: '💰', handover: '🤝', rejected: '⛔', cancelled: '↩️', completed: '🎉', lpj_rejected: '📋', reset: '🔄' },
  assignment: { assigned: '🚛', swapped: '🔄', released: '🚛' },
  appointment: { assigned: '📅', unassigned: '↩️', completed: '✅' },
}

function iconFor(n) { return (ICONS[n?.type] || {})[n?.action] || '🔔' }

function timeAgo(ts) {
  if (!ts) return ''
  const d = new Date(String(ts).replace(' ', 'T'))
  if (isNaN(d.getTime())) return ''
  const diff = (Date.now() - d.getTime()) / 1000
  if (diff < 60) return 'baru saja'
  if (diff < 3600) return Math.floor(diff / 60) + ' mnt lalu'
  if (diff < 86400) return Math.floor(diff / 3600) + ' jam lalu'
  return d.toLocaleDateString('id-ID')
}

function toggle() {
  open.value = !open.value
  if (open.value) {
    store.markNotifRead()
    store.loadNotifications()
    loadPush()
  }
}

function onDocKey(e) { if (e.key === 'Escape') open.value = false }
onMounted(() => document.addEventListener('keydown', onDocKey))
onBeforeUnmount(() => document.removeEventListener('keydown', onDocKey))
</script>

<template>
  <div class="notif-wrap">
    <button class="notif-bell" title="Notifikasi" aria-label="Notifikasi" aria-haspopup="dialog" :aria-expanded="open" @click="toggle">
      🔔<span v-if="store.unread" class="notif-badge">{{ store.unread > 99 ? '99+' : store.unread }}</span>
    </button>

    <div v-if="open" class="notif-backdrop" @click="open = false"></div>
    <!-- v-if wajib: sebelumnya panel dirender tanpa syarat sehingga jendela
         notifikasi SELALU menutupi layar dan tombol ✕ tidak berpengaruh. -->
    <div v-if="open" class="notif-panel" role="dialog" aria-modal="true" aria-label="Notifikasi driver">
      <div class="notif-head">
        <b>🔔 Notifikasi</b>
        <span class="notif-count">{{ store.notifications.length }} notifikasi</span>
        <button class="btn-icon" style="margin-left:auto;" aria-label="Tutup" title="Tutup (Esc)" @click="open = false">✕</button>
      </div>
      <div class="notif-list">
        <div v-for="n in store.notifications" :key="n.id" class="notif-item" :class="{ unread: !n.is_read }">
          <span class="notif-ico">{{ iconFor(n) }}</span>
          <div>
            <div class="notif-msg">{{ n.message }}</div>
            <div class="notif-time">{{ timeAgo(n.created_at) }}</div>
          </div>
        </div>
        <p v-if="!store.notifications.length" class="notif-empty">Belum ada notifikasi</p>
      </div>
      <div class="notif-push">
        <div v-if="!push.supported" class="notif-push-note">Browser ini belum mendukung notifikasi HP.</div>
        <template v-else>
          <div class="notif-push-row">
            <span>{{ push.subscribed ? '✅ Notifikasi HP aktif' : '🔕 Notifikasi HP belum aktif' }}</span>
            <button class="btn btn-sm btn-primary" :disabled="pushBusy" @click="togglePush">
              {{ pushBusy ? '⏳' : (push.subscribed ? 'Matikan' : 'Aktifkan') }}
            </button>
          </div>
          <p v-if="push.ios && !push.standalone" class="notif-push-note">
            Di iPhone: tambah dulu ke <b>Layar Utama</b> (Safari → Bagikan → Tambah ke Layar Utama), lalu buka dari ikon itu.
          </p>
          <p v-else-if="push.permission === 'denied'" class="notif-push-note">
            Izin notifikasi diblokir. Buka pengaturan situs di browser → Notifikasi → Izinkan.
          </p>
          <p v-if="pushMsg" class="notif-push-note">{{ pushMsg }}</p>
        </template>
      </div>
    </div>
  </div>
</template>

<style scoped>
.notif-wrap { position: relative; }
.notif-bell { position: relative; font-size: 17px; padding: 4px; background: none; border: none; cursor: pointer; }
.notif-badge {
  position: absolute; top: -4px; right: -8px; background: #dc2626; color: #fff; font-size: 9px; font-weight: 700;
  min-width: 16px; height: 16px; line-height: 16px; text-align: center; border-radius: 10px; padding: 0 3px;
}
.notif-backdrop { position: fixed; inset: 0; background: rgba(15, 23, 42, .45); z-index: 90; }
.notif-panel {
  position: fixed; top: 0; right: 0; bottom: 0; width: min(340px, 88vw); z-index: 91;
  background: var(--surface); border-left: 1px solid var(--border); display: flex; flex-direction: column;
  border-radius: 16px 0 0 16px; box-shadow: -6px 0 24px rgba(15, 23, 42, .18); animation: slideIn .25s ease;
}
@keyframes slideIn { from { transform: translateX(105%); } to { transform: translateX(0); } }
.notif-head { display: flex; align-items: center; gap: 8px; padding: 14px 16px; border-bottom: 1px solid var(--border); font-size: 13px; }
.notif-count { font-size: 10px; background: var(--bg-2, #eff6ff); color: var(--accent, #2563eb); padding: 2px 8px; border-radius: 10px; }
.notif-list { flex: 1; overflow-y: auto; padding: 8px 10px; }
.notif-item { display: flex; gap: 10px; padding: 10px; border-radius: 10px; margin-bottom: 6px; background: var(--bg-2, #f8fafc); border: 1px solid var(--border); }
.notif-item.unread { background: var(--bg-3, #eff6ff); border-color: var(--accent, #bfdbfe); }
.notif-ico { font-size: 18px; }
.notif-msg { font-size: 12px; line-height: 1.4; }
.notif-time { font-size: 10px; opacity: .6; margin-top: 2px; }
.notif-empty { text-align: center; opacity: .6; font-size: 12px; padding: 30px 10px; }
.notif-push { border-top: 1px solid var(--border); padding: 10px 14px 14px; background: var(--bg-2, #f8fafc); }
.notif-push-row { display: flex; align-items: center; justify-content: space-between; gap: 8px; font-size: 12px; }
.notif-push-note { font-size: 10px; line-height: 1.45; opacity: .75; margin: 6px 0 0; }
</style>
