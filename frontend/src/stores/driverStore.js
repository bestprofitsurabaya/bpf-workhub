import { defineStore } from 'pinia'
import { api } from '../api'
import { addToQueue, getAllFromQueue, deleteFromQueue, countAllQueues } from '../utils/idb'
import { locateWithAddress } from '../utils/gps'

function csrfHeader() {
  const csrf = localStorage.getItem('bpf_csrf') || sessionStorage.getItem('bpf_csrf')
  return csrf ? { 'X-CSRF-Token': csrf } : {}
}

/** Object (termasuk File & array multi-rute) → FormData untuk endpoint form klasik. */
export function toForm(data) {
  const fd = new FormData()
  for (const [k, v] of Object.entries(data || {})) {
    if (v === undefined || v === null) continue
    if (Array.isArray(v)) {
      for (const item of v) { if (item !== undefined && item !== null) fd.append(k, String(item)) }
      continue
    }
    if (v instanceof File || v instanceof Blob) fd.append(k, v, v.name || k)
    else fd.append(k, String(v))
  }
  return fd
}

/** POST multipart dengan header JSON/CSRF (endpoint klasik tetap menerima). */
async function postForm(path, fd) {
  const r = await fetch(path, {
    method: 'POST',
    body: fd,
    headers: { ...csrfHeader(), 'X-Requested-With': 'XMLHttpRequest', Accept: 'application/json' },
  })
  const j = await r.json().catch(() => null)
  return { ok: r.ok, status: r.status, data: j }
}

export const useDriverStore = defineStore('driver', {
  state: () => ({
    profile: null,
    profileErr: '',
    online: typeof navigator !== 'undefined' ? navigator.onLine : true,
    gps: { lat: null, lon: null, addr: '', spbu: '', locating: false },
    queue: { fuel: 0, trip: 0, lpj: 0 },
    syncing: false,
    lastSync: null,
    dailyCode: null,
    dailyMode: 'auto', // 'auto' | 'manual'
    notifications: [],
    unread: 0,
    // LPJ aktif: kasbon yang sedang diisi lewat form BBM
    activeLpj: null, // { cashId, display_id, total_amount, nopol, bbm_type }
  }),
  getters: {
    driverName: (s) => (s.profile?.name || '').toUpperCase(),
    queueTotal: (s) => s.queue.fuel + s.queue.trip + s.queue.lpj,
  },
  actions: {
    async loadProfile() {
      this.profileErr = ''
      try {
        const d = await api('/api/driver/me')
        if (d?.status === 'error') throw new Error(d.msg || 'Profil tidak ditemukan')
        this.profile = d
      } catch (e) {
        this.profileErr = e.message || 'Gagal memuat profil driver'
        this.profile = null
      }
    },

    async refreshQueue() {
      this.queue = await countAllQueues()
    },

    /** Simpan ke antrean offline lalu hitung ulang badge. */
    async enqueue(store, payload, cashId = null) {
      const item = { data: payload, timestamp: new Date().toISOString() }
      if (cashId) item.cashId = cashId
      await addToQueue(store, item)
      await this.refreshQueue()
    },

    /** Kirim semua antrean offline (3 jalur) ke server. */
    async syncAll() {
      if (!this.online || this.syncing) return 0
      this.syncing = true
      let sent = 0
      try {
        // 1) Laporan BBM offline → POST /driver
        const fuel = await getAllFromQueue('fuel_queue')
        for (const item of fuel) {
          try {
            const { ok, data } = await postForm('/driver', toForm(item.data))
            if (ok && data?.status === 'success') { await deleteFromQueue('fuel_queue', item.id); sent++ }
          } catch { /* retry nanti */ }
        }
        // 2) LPJ kasbon offline → POST /api/cash/submit-lpj/<cashId>
        const lpj = await getAllFromQueue('lpj_queue')
        for (const item of lpj) {
          if (!item.cashId) continue
          try {
            const { ok, data } = await postForm(`/api/cash/submit-lpj/${item.cashId}`, toForm(item.data))
            if (ok && data?.status === 'success') { await deleteFromQueue('lpj_queue', item.id); sent++ }
          } catch { /* retry nanti */ }
        }
        // 3) Log perjalanan offline → POST /submit-trip
        const trips = await getAllFromQueue('trip_queue')
        for (const item of trips) {
          try {
            const { ok, data } = await postForm('/submit-trip', toForm(item.data))
            if (ok && data?.status === 'success') { await deleteFromQueue('trip_queue', item.id); sent++ }
          } catch { /* retry nanti */ }
        }
        // 4) Overtime Driver offline → POST /api/overtime/driver/submit
        const overtimes = await getAllFromQueue('overtime_queue')
        for (const item of overtimes) {
          try {
            const { ok, data } = await api('/api/overtime/driver/submit', { method: 'POST', body: item.data })
            if (ok && data?.status === 'success') { await deleteFromQueue('overtime_queue', item.id); sent++ }
          } catch { /* retry nanti */ }
        }
        this.lastSync = new Date().toISOString()
      } finally {
        this.syncing = false
        await this.refreshQueue()
      }
      return sent
    },

    /** Lokasi GPS + alamat + SPBU terdekat (one-shot). */
    async locate() {
      if (this.gps.locating) return
      this.gps.locating = true
      try {
        const res = await locateWithAddress()
        this.gps = { ...this.gps, ...res, locating: false }
      } catch (e) {
        this.gps.locating = false
        throw e
      }
    },

    async loadDailyCode() {
      try {
        const d = await api('/api/cash/daily-code')
        this.dailyCode = d.code
        this.dailyMode = d.manual_mode ? 'manual' : 'auto'
      } catch { /* pakai nilai acak lama */ }
    },

    async loadNotifications() {
      if (!this.online) return
      try {
        const d = await api('/api/notifications', { params: { driver: this.driverName } })
        if (d?.error) return
        this.notifications = d.notifications || []
        this.unread = d.unread || 0
      } catch { /* abaikan */ }
    },

    async markNotifRead() {
      try {
        await api('/api/notifications/read', { method: 'POST', body: { driver: this.driverName } })
        this.unread = 0
        this.notifications = (this.notifications || []).map((n) => ({ ...n, is_read: 1 }))
      } catch { /* abaikan */ }
    },

    /** Notifikasi realtime masuk → unshift + toast. */
    pushNotification(n) {
      if (!n) return
      this.notifications.unshift({ ...n, is_read: 0, created_at: n.created_at || new Date().toISOString() })
      if (this.notifications.length > 30) this.notifications.pop()
      this.unread++
    },

    setActiveLpj(cash) {
      this.activeLpj = cash
    },
  },
})
