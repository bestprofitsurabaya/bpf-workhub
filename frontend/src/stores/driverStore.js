import { defineStore } from 'pinia'
import { api, notifyUnauthorized } from '../api'
import {
  addToQueue, getAllFromQueue, deleteFromQueue, countAllQueues,
  updateQueueItem, getAllQueueItems,
} from '../utils/idb'
import { locateWithAddress, detailedLocation } from '../utils/gps'

/** UUID sekali pakai per percobaan submit — kunci idempotensi server. */
export function newSubmitId() {
  try {
    if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
      return crypto.randomUUID()
    }
  } catch { /* lanjut ke fallback */ }
  return 'id-' + Date.now().toString(36) + '-' + Math.random().toString(36).slice(2, 12)
}

/** Error jaringan (tanpa status HTTP) vs penolakan server (punya status). */
export function isNetworkError(err) {
  if (!err || err.status) return false
  return /koneksi|network|failed to fetch|load failed/i.test(err.message || '')
}

/* ------------------------------------------------------------------ *
 * Mesin sync v2 (v2.127.0)
 *
 * Kontrak:
 * - item antrean punya state: pending | failed (gagal permanen, perlu aksi)
 * - error jaringan/5xx/429 → tetap pending + nextAt (backoff + jitter)
 * - error validasi 4xx → failed (tidak diulang otomatis)
 * - 401/403 → sync berhenti, item tetap pending, sesi diminta login ulang
 * - idempotensi tetap di server (client_uuid) — retry tidak menggandakan
 * ------------------------------------------------------------------ */

export const QUEUE_ORDER = ['fuel_queue', 'lpj_queue', 'trip_queue', 'overtime_queue', 'cash_queue']
export const QUEUE_LABELS = {
  fuel_queue: 'BBM',
  lpj_queue: 'LPJ kasbon',
  trip_queue: 'Log trip',
  overtime_queue: 'Overtime',
  cash_queue: 'Kasbon',
}

const BACKOFF_BASE_MS = 30 * 1000
const BACKOFF_MAX_MS = 60 * 60 * 1000

/** Backoff eksponensial + jitter 80–120%, maksimum 1 jam. */
export function backoffDelay(attempts, rand = Math.random) {
  const n = Math.max(1, Number(attempts) || 1)
  const base = Math.min(BACKOFF_MAX_MS, BACKOFF_BASE_MS * (2 ** (n - 1)))
  const jitter = 0.8 + (Number(rand()) || 0) * 0.4
  return Math.round(Math.min(BACKOFF_MAX_MS, base * jitter))
}

/** Kelompokkan kegagalan: butuh login / boleh retry / gagal permanen. */
export function classifySyncError(status) {
  if (status === 401 || status === 403) return 'auth'
  if (!status) return 'retry'                       // jaringan mati / timeout
  if (status === 408 || status === 425 || status === 429) return 'retry'
  if (status >= 500) return 'retry'
  return 'failed'                                   // 4xx lain = ditolak server
}

/** Perkiraan ukuran payload untuk indikator kuota antrean (byte). */
export function estimateItemSize(data) {
  let bytes = 0
  for (const v of Object.values(data || {})) {
    if (v === undefined || v === null) continue
    if (typeof Blob !== 'undefined' && v instanceof Blob) bytes += v.size || 0
    else if (typeof v === 'string') bytes += v.length
    else bytes += 8
  }
  return bytes
}

function httpError(message, status, data) {
  const err = new Error(message || 'Gagal mengirim')
  if (status) err.status = status
  err.data = data
  return err
}

/** Kirim satu item sesuai jenis antreannya. Throw bila server menolak. */
async function sendQueueItem(store, item) {
  if (store === 'fuel_queue') {
    const r = await postForm('/driver', toForm(item.data))
    if (r.ok && r.data?.status === 'success') return r.data
    throw httpError(r.data?.msg || `HTTP ${r.status}`, r.ok ? 422 : r.status, r.data)
  }
  if (store === 'lpj_queue') {
    if (!item.cashId) throw httpError('LPJ tanpa ID kasbon', 422)
    const r = await postForm(`/api/cash/submit-lpj/${item.cashId}`, toForm(item.data))
    if (r.ok && r.data?.status === 'success') return r.data
    throw httpError(r.data?.msg || `HTTP ${r.status}`, r.ok ? 422 : r.status, r.data)
  }
  if (store === 'trip_queue') {
    const r = await postForm('/submit-trip', toForm(item.data))
    if (r.ok && r.data?.status === 'success') return r.data
    throw httpError(r.data?.msg || `HTTP ${r.status}`, r.ok ? 422 : r.status, r.data)
  }
  if (store === 'overtime_queue') {
    const d = await api('/api/overtime/driver/submit', { method: 'POST', body: item.data })
    if (d?.status === 'success') return d
    throw httpError(d?.msg || 'Overtime ditolak server', 422, d)
  }
  if (store === 'cash_queue') {
    const d = await api('/api/cash/request', { method: 'POST', body: item.data })
    if (d?.status === 'success') return d
    throw httpError(d?.msg || 'Kasbon ditolak server', 422, d)
  }
  throw httpError(`Antrean tidak dikenal: ${store}`, 422)
}

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
    gps: { lat: null, lon: null, addr: '', spbu: '', locating: false, detail: null },
    queue: { fuel: 0, trip: 0, lpj: 0, overtime: 0, cash: 0 },
    queueItems: [],
    queueBytes: 0,
    syncing: false,
    sync: {
      state: 'idle', // idle | syncing | offline | error | auth
      sent: 0,
      pending: 0,
      failed: 0,
      auth: false,
      lastError: '',
      at: null,
    },
    storagePersisted: false,
    storageUsage: 0,
    storageQuota: 0,
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
    queueTotal: (s) => Object.values(s.queue).reduce((a, b) => a + (Number(b) || 0), 0),
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
      try {
        const items = await getAllQueueItems()
        items.sort((a, b) => {
          const ta = Number(a.createdAt) || Date.parse(a.timestamp) || 0
          const tb = Number(b.createdAt) || Date.parse(b.timestamp) || 0
          return ta - tb
        })
        this.queueItems = items.map(({ data, ...meta }) => meta)
        this.queueBytes = items.reduce((n, it) => n + (Number(it.size) || 0), 0)
        const failed = items.filter((it) => it.state === 'failed').length
        this.sync.failed = failed
        this.sync.pending = items.length - failed
      } catch {
        this.queueItems = []
        this.queueBytes = 0
      }
    },

    /** Simpan ke antrean offline lalu hitung ulang badge. */
    async enqueue(store, payload, cashId = null) {
      const now = Date.now()
      const item = {
        data: payload,
        timestamp: new Date(now).toISOString(),
        createdAt: now,
        state: 'pending',
        attempts: 0,
        nextAt: 0,
        lastError: '',
        size: estimateItemSize(payload),
      }
      if (cashId) item.cashId = cashId
      const id = await addToQueue(store, item)
      await this.refreshQueue()
      return id
    },

    /** Minta browser tidak membuang IndexedDB (best-effort, iOS/Android). */
    async ensurePersistentStorage() {
      try {
        if (navigator.storage?.persist) {
          this.storagePersisted = await navigator.storage.persist()
        }
        if (navigator.storage?.estimate) {
          const est = await navigator.storage.estimate()
          this.storageUsage = est?.usage || 0
          this.storageQuota = est?.quota || 0
        }
      } catch { /* tidak didukung — abaikan */ }
    },

    /**
     * Kirim antrean offline.
     * @param {{force?: boolean}} opts force=true mengabaikan backoff/state failed
     *        (dipakai tombol "Coba lagi" per item).
     * @returns {Promise<number>} jumlah item yang berhasil terkirim.
     */
    async syncAll({ force = false } = {}) {
      if (this.syncing) return 0
      this.online = typeof navigator === 'undefined' ? true : navigator.onLine
      if (!this.online) {
        this.sync.state = 'offline'
        return 0
      }

      this.syncing = true
      this.sync.state = 'syncing'
      this.sync.auth = false
      this.sync.lastError = ''
      const summary = { sent: 0, pending: 0, failed: 0, auth: false }
      try {
        for (const storeName of QUEUE_ORDER) {
          let items = []
          try {
            items = await getAllFromQueue(storeName)
          } catch { continue } // IndexedDB rusak/terblokir — jangan hentikan jalur lain
          for (const item of items) {
            const state = item.state || 'pending'
            if (!force && state === 'failed') continue
            if (!force && item.nextAt && item.nextAt > Date.now()) continue
            try {
              await sendQueueItem(storeName, item)
              await deleteFromQueue(storeName, item.id)
              summary.sent++
            } catch (e) {
              const kind = classifySyncError(e?.status)
              const attempts = (Number(item.attempts) || 0) + 1
              const message = e?.message || 'Gagal mengirim'
              if (kind === 'auth') {
                // Sesi habis: hentikan seluruh sync, jangan buang data.
                summary.auth = true
                this.sync.auth = true
                this.sync.lastError = message
                await updateQueueItem(storeName, item.id, {
                  state: 'pending', attempts, lastError: message,
                })
                try { await notifyUnauthorized() } catch { /* api.js probe */ }
                break
              }
              if (kind === 'failed') {
                // Ditolak server (validasi) — jangan diulang tiap 30 detik.
                summary.failed++
                this.sync.lastError = message
                await updateQueueItem(storeName, item.id, {
                  state: 'failed', attempts, lastError: message, nextAt: 0,
                })
                continue
              }
              summary.pending++
              this.sync.lastError = message
              await updateQueueItem(storeName, item.id, {
                state: 'pending',
                attempts,
                lastError: message,
                nextAt: Date.now() + backoffDelay(attempts),
              })
            }
          }
          if (summary.auth) break
        }
        this.lastSync = new Date().toISOString()
        this.sync.at = this.lastSync
        this.sync.sent = summary.sent
      } finally {
        this.syncing = false
        this.sync.state = summary.auth ? 'auth' : (summary.failed ? 'error' : 'idle')
        await this.refreshQueue()
      }
      return summary.sent
    },

    /** Coba ulang satu item yang gagal (abaikan backoff). */
    async retryItem(store, id) {
      await updateQueueItem(store, id, {
        state: 'pending', attempts: 0, nextAt: 0, lastError: '',
      })
      await this.refreshQueue()
      return this.syncAll({ force: true })
    },

    /** Hapus satu item dari antrean (dipakai hanya setelah konfirmasi UI). */
    async dropItem(store, id) {
      await deleteFromQueue(store, id)
      await this.refreshQueue()
    },

    /** Lokasi GPS + alamat + SPBU terdekat + detail lokasi (one-shot). */
    async locate() {
      if (this.gps.locating) return
      this.gps.locating = true
      try {
        const res = await locateWithAddress()
        // Fetch detailed location (parallel)
        let detail = null
        try {
          detail = await detailedLocation(res.lat, res.lon)
        } catch { /* fallback */ }
        this.gps = { ...this.gps, ...res, detail, locating: false }
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
