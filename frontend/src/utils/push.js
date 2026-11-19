/**
 * Web Push driver (v2.128.0).
 *
 * Notifikasi berjalan saat aplikasi TERTUTUP:
 * - Android Chrome: dukungan penuh.
 * - iPhone/iPad: Safari >= 16.4, hanya setelah PWA ditambahkan ke Layar Utama.
 *
 * Izin harus diminta dari aksi pengguna (klik tombol) — Safari iOS menolak
 * permintaan izin otomatis.
 */
import { api } from '../api'

export function pushSupported() {
  return typeof window !== 'undefined' &&
    'serviceWorker' in navigator &&
    'PushManager' in window &&
    'Notification' in window
}

export function isIOS() {
  if (typeof navigator === 'undefined') return false
  return /iPad|iPhone|iPod/.test(navigator.userAgent) ||
    (navigator.platform === 'MacIntel' && navigator.maxTouchPoints > 1)
}

export function isStandalone() {
  if (typeof window === 'undefined') return false
  return window.matchMedia?.('(display-mode: standalone)')?.matches === true ||
    navigator.standalone === true
}

/** Kunci VAPID base64url → Uint8Array (dipakai PushManager.subscribe). */
export function urlBase64ToUint8Array(base64String) {
  const padding = '='.repeat((4 - (String(base64String || '').length % 4)) % 4)
  const base64 = (String(base64String || '') + padding).replace(/-/g, '+').replace(/_/g, '/')
  const raw = atob(base64)
  const out = new Uint8Array(raw.length)
  for (let i = 0; i < raw.length; i++) out[i] = raw.charCodeAt(i)
  return out
}

export async function getPushState() {
  const base = {
    supported: pushSupported(),
    permission: typeof Notification !== 'undefined' ? Notification.permission : 'unsupported',
    subscribed: false,
    ios: isIOS(),
    standalone: isStandalone(),
  }
  if (!base.supported) return base
  try {
    const reg = await navigator.serviceWorker.getRegistration()
    const sub = reg ? await reg.pushManager.getSubscription() : null
    base.subscribed = !!sub
  } catch { /* tidak bisa dibaca — anggap belum aktif */ }
  return base
}

export async function enablePush() {
  if (!pushSupported()) {
    throw new Error('Perangkat/browser ini belum mendukung notifikasi push.')
  }
  if (isIOS() && !isStandalone()) {
    throw new Error('Di iPhone: tambahkan dulu ke Layar Utama (Safari → Bagikan → Tambah ke Layar Utama), lalu buka dari ikon tersebut.')
  }
  // Penting untuk iOS/Safari: minta izin SEBELUM await apa pun, karena
  // permintaan izin hanya diterima selama gestur pengguna masih aktif.
  let permission = Notification.permission
  if (permission !== 'granted') permission = await Notification.requestPermission()
  if (permission !== 'granted') {
    throw new Error('Izin notifikasi ditolak. Aktifkan izin notifikasi untuk situs ini di pengaturan browser.')
  }
  const cfg = await api('/api/push/public-key')
  if (!cfg?.enabled || !cfg.public_key) {
    throw new Error(cfg?.reason || 'Notifikasi HP belum diaktifkan di server.')
  }
  const reg = await navigator.serviceWorker.ready
  let sub = await reg.pushManager.getSubscription()
  if (!sub) {
    sub = await reg.pushManager.subscribe({
      userVisibleOnly: true,
      applicationServerKey: urlBase64ToUint8Array(cfg.public_key),
    })
  }
  const res = await api('/api/push/subscribe', {
    method: 'POST',
    body: { subscription: sub.toJSON() },
  })
  return res || { status: 'success' }
}

export async function disablePush() {
  const reg = await navigator.serviceWorker.getRegistration()
  const sub = reg ? await reg.pushManager.getSubscription() : null
  if (!sub) return { removed: 0, devices: 0 }
  const endpoint = sub.endpoint
  let res = null
  try {
    res = await api('/api/push/unsubscribe', { method: 'POST', body: { endpoint } })
  } catch { /* server tidak terjangkau — perangkat tetap berhenti berlangganan */ }
  try { await sub.unsubscribe() } catch { /* abaikan */ }
  return res || { removed: 1, devices: 0 }
}
