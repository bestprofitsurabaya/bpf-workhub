import { describe, it, expect, vi, beforeEach } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'
import {
  useDriverStore, toForm, newSubmitId, isNetworkError,
  backoffDelay, classifySyncError, estimateItemSize,
} from './driverStore'

const { apiMock, notifyMock } = vi.hoisted(() => ({ apiMock: vi.fn(), notifyMock: vi.fn(() => Promise.resolve(false)) }))
vi.mock('../api', () => ({ api: apiMock, notifyUnauthorized: notifyMock }))

const idb = vi.hoisted(() => ({
  addToQueue: vi.fn(() => Promise.resolve(1)),
  getAllFromQueue: vi.fn(() => Promise.resolve([])),
  deleteFromQueue: vi.fn(() => Promise.resolve()),
  updateQueueItem: vi.fn(() => Promise.resolve(null)),
  getAllQueueItems: vi.fn(() => Promise.resolve([])),
  countAllQueues: vi.fn(() => Promise.resolve({ fuel: 0, trip: 0, lpj: 0, overtime: 0, cash: 0 })),
}))
vi.mock('../utils/idb', () => idb)

vi.mock('../utils/gps', () => ({
  locateWithAddress: vi.fn(() => Promise.resolve({ lat: -7.25, lon: 112.75, addr: 'Jl. Test, Surabaya', spbu: '' })),
}))

describe('driver store', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    setActivePinia(createPinia())
    idb.getAllFromQueue.mockImplementation(() => Promise.resolve([]))
    idb.getAllQueueItems.mockImplementation(() => Promise.resolve([]))
    idb.countAllQueues.mockResolvedValue({ fuel: 0, trip: 0, lpj: 0, overtime: 0, cash: 0 })
    idb.updateQueueItem.mockResolvedValue(null)
    notifyMock.mockResolvedValue(false)
    apiMock.mockImplementation((path) => {
      if (path === '/api/driver/me') return Promise.resolve({ name: 'RIVAN', nopol: 'L 1 AB', vehicle_type: 'AVANZA', bbm_type: 'PERTALITE', is_active: true })
      if (path === '/api/cash/daily-code') return Promise.resolve({ code: 300, manual_mode: false })
      if (path === '/api/notifications') return Promise.resolve({ notifications: [], unread: 0 })
      return Promise.resolve({})
    })
  })

  it('loadProfile memuat profil driver dan driverName uppercase', async () => {
    const s = useDriverStore()
    await s.loadProfile()
    expect(s.profile.name).toBe('RIVAN')
    expect(s.driverName).toBe('RIVAN')
  })

  it('enqueue menambah antrean dan memperbarui badge', async () => {
    const s = useDriverStore()
    await s.loadProfile()
    idb.countAllQueues.mockResolvedValueOnce({ fuel: 1, trip: 0, lpj: 0, overtime: 0, cash: 0 })
    await s.enqueue('fuel_queue', { driver_name: 'RIVAN', nominal: 100000 })
    expect(idb.addToQueue).toHaveBeenCalledWith('fuel_queue', expect.objectContaining({ data: expect.objectContaining({ driver_name: 'RIVAN' }) }))
    expect(s.queue.fuel).toBe(1)
    expect(s.queueTotal).toBe(1)
  })

  it('badge menghitung antrean overtime dan kasbon (v2.120.0)', async () => {
    const s = useDriverStore()
    idb.countAllQueues.mockResolvedValueOnce({ fuel: 0, trip: 0, lpj: 0, overtime: 2, cash: 1 })
    await s.refreshQueue()
    expect(s.queueTotal).toBe(3)
  })

  it('syncAll mengirim antrean fuel lalu menghapusnya', async () => {
    const s = useDriverStore()
    idb.getAllFromQueue.mockImplementation((store) => {
      if (store === 'fuel_queue') return Promise.resolve([{ id: 7, data: { driver_name: 'RIVAN', nominal: 50000 }, timestamp: 'x' }])
      return Promise.resolve([])
    })
    const fetchMock = vi.fn(() => Promise.resolve({ ok: true, json: () => Promise.resolve({ status: 'success' }) }))
    vi.stubGlobal('fetch', fetchMock)
    const n = await s.syncAll()
    expect(n).toBe(1)
    expect(fetchMock).toHaveBeenCalledWith('/driver', expect.objectContaining({ method: 'POST' }))
    expect(idb.deleteFromQueue).toHaveBeenCalledWith('fuel_queue', 7)
    vi.unstubAllGlobals()
  })

  it('syncAll menghapus antrean overtime setelah server sukses', async () => {
    const s = useDriverStore()
    idb.getAllFromQueue.mockImplementation((store) => {
      if (store === 'overtime_queue') return Promise.resolve([{ id: 11, data: { tanggal: '2026-11-12' }, timestamp: 'x' }])
      return Promise.resolve([])
    })
    apiMock.mockResolvedValueOnce({ status: 'success', display_id: 'OT-1' })
    const n = await s.syncAll()
    expect(n).toBe(1)
    expect(apiMock).toHaveBeenCalledWith('/api/overtime/driver/submit', expect.objectContaining({ method: 'POST' }))
    expect(idb.deleteFromQueue).toHaveBeenCalledWith('overtime_queue', 11)
  })

  it('syncAll mengirim antrean kasbon offline (v2.120.0)', async () => {
    const s = useDriverStore()
    idb.getAllFromQueue.mockImplementation((store) => {
      if (store === 'cash_queue') return Promise.resolve([{ id: 21, data: { base_amount: 50000, client_uuid: 'abc' }, timestamp: 'x' }])
      return Promise.resolve([])
    })
    apiMock.mockResolvedValueOnce({ status: 'success', msg: 'ok' })
    const n = await s.syncAll()
    expect(n).toBe(1)
    expect(apiMock).toHaveBeenCalledWith('/api/cash/request', expect.objectContaining({ method: 'POST' }))
    expect(idb.deleteFromQueue).toHaveBeenCalledWith('cash_queue', 21)
  })

  it('syncAll tetap mengirim saat navigator.onLine tertinggal false (probe server)', async () => {
    const s = useDriverStore()
    const original = Object.getOwnPropertyDescriptor(navigator, 'onLine')
    Object.defineProperty(navigator, 'onLine', { configurable: true, value: false })
    const fetchSpy = vi.spyOn(globalThis, 'fetch').mockImplementation((url) => Promise.resolve(
      url === '/api/health'
        ? { ok: true, status: 200 }
        : { ok: true, status: 200, json: () => Promise.resolve({ status: 'success' }) }
    ))
    idb.getAllFromQueue.mockImplementation((name) => Promise.resolve(
      name === 'fuel_queue'
        ? [{ id: 7, data: { nopol: 'L 1 AB', nominal: 1000 }, state: 'pending', attempts: 0 }]
        : []
    ))
    apiMock.mockResolvedValue({ status: 'success' })
    try {
      const n = await s.syncAll()
      expect(fetchSpy).toHaveBeenCalledWith('/api/health', expect.anything())
      expect(s.online).toBe(true)
      expect(n).toBe(1)
      expect(idb.deleteFromQueue).toHaveBeenCalledWith('fuel_queue', 7)
    } finally {
      fetchSpy.mockRestore()
      if (original) Object.defineProperty(navigator, 'onLine', original)
      else delete navigator.onLine
    }
  })

  it('newSubmitId menghasilkan kunci berbeda & isNetworkError membedakan HTTP', () => {
    expect(newSubmitId()).not.toBe(newSubmitId())
    const net = new Error('Koneksi ke server gagal. Periksa jaringan Anda.')
    expect(isNetworkError(net)).toBe(true)
    const http = new Error('Gagal')
    http.status = 400
    expect(isNetworkError(http)).toBe(false)
  })

  it('pushNotification menambah notifikasi & menaikkan unread', () => {
    const s = useDriverStore()
    s.pushNotification({ id: 1, message: 'Klaim disetujui GA', type: 'claim', action: 'approved' })
    expect(s.notifications.length).toBe(1)
    expect(s.unread).toBe(1)
  })

  it('locate mengisi koordinat & alamat GPS', async () => {
    const s = useDriverStore()
    await s.locate()
    expect(s.gps.lat).toBe(-7.25)
    expect(s.gps.addr).toContain('Surabaya')
  })

  it('toForm: array multi-rute menjadi beberapa entri FormData (fix bug rute tertimpa)', () => {
    const fd = toForm({
      driver_name: 'RIVAN',
      'lokasi_tujuan[]': ['Jl. A', 'Jl. B', 'Jl. C'],
      'km_tujuan[]': [1, 2, 3],
    })
    expect(fd.getAll('lokasi_tujuan[]')).toEqual(['Jl. A', 'Jl. B', 'Jl. C'])
    expect(fd.getAll('km_tujuan[]')).toEqual(['1', '2', '3'])
    expect(fd.get('driver_name')).toBe('RIVAN')
  })

  it('classifySyncError: auth, retry, dan failed dipisahkan', () => {
    expect(classifySyncError(401)).toBe('auth')
    expect(classifySyncError(403)).toBe('auth')
    expect(classifySyncError(undefined)).toBe('retry')
    expect(classifySyncError(408)).toBe('retry')
    expect(classifySyncError(429)).toBe('retry')
    expect(classifySyncError(503)).toBe('retry')
    expect(classifySyncError(400)).toBe('failed')
    expect(classifySyncError(422)).toBe('failed')
  })

  it('backoffDelay tumbuh eksponensial, berjitter, dan dibatasi 1 jam', () => {
    expect(backoffDelay(1, () => 0.5)).toBe(30000)
    expect(backoffDelay(2, () => 0.5)).toBe(60000)
    expect(backoffDelay(3, () => 0.5)).toBe(120000)
    expect(backoffDelay(1, () => 0)).toBe(24000)   // jitter -20%
    expect(backoffDelay(1, () => 1)).toBe(36000)   // jitter +20%
    expect(backoffDelay(50, () => 0.5)).toBe(3600000)
  })

  it('estimateItemSize menghitung string dan Blob', () => {
    expect(estimateItemSize({ a: '12345', b: null })).toBe(5)
    if (typeof Blob !== 'undefined') {
      expect(estimateItemSize({ a: '12345', b: new Blob(['abc']) })).toBe(8)
    }
  })

  it('syncAll menandai 4xx sebagai failed dan tidak menghapus item', async () => {
    const s = useDriverStore()
    idb.getAllFromQueue.mockImplementation((store) => {
      if (store === 'fuel_queue') {
        return Promise.resolve([{ id: 7, data: { driver_name: 'RIVAN' }, timestamp: 'x', state: 'pending', attempts: 0 }])
      }
      return Promise.resolve([])
    })
    const fetchMock = vi.fn(() => Promise.resolve({
      ok: false, status: 400,
      json: () => Promise.resolve({ status: 'error', msg: 'Nominal tidak valid' }),
    }))
    vi.stubGlobal('fetch', fetchMock)

    const n = await s.syncAll()

    expect(n).toBe(0)
    expect(idb.deleteFromQueue).not.toHaveBeenCalled()
    expect(idb.updateQueueItem).toHaveBeenCalledWith('fuel_queue', 7, expect.objectContaining({
      state: 'failed',
      lastError: 'Nominal tidak valid',
      nextAt: 0,
    }))
    expect(s.sync.failed).toBe(0) // refreshQueue mock tidak mengembalikan item
    vi.unstubAllGlobals()
  })

  it('syncAll menjadwalkan backoff pada 5xx tanpa menghapus item', async () => {
    const s = useDriverStore()
    idb.getAllFromQueue.mockImplementation((store) => {
      if (store === 'trip_queue') {
        return Promise.resolve([{ id: 9, data: { driver_name: 'RIVAN' }, timestamp: 'x', state: 'pending' }])
      }
      return Promise.resolve([])
    })
    const fetchMock = vi.fn(() => Promise.resolve({
      ok: false, status: 503,
      json: () => Promise.resolve({ status: 'error', msg: 'Server sibuk' }),
    }))
    vi.stubGlobal('fetch', fetchMock)

    const before = Date.now()
    await s.syncAll()

    const patch = idb.updateQueueItem.mock.calls[0][2]
    expect(patch.state).toBe('pending')
    expect(patch.attempts).toBe(1)
    expect(patch.nextAt).toBeGreaterThanOrEqual(before + 24000)
    expect(idb.deleteFromQueue).not.toHaveBeenCalled()
    vi.unstubAllGlobals()
  })

  it('syncAll berhenti dan meminta login pada 401', async () => {
    const s = useDriverStore()
    idb.getAllFromQueue.mockImplementation((store) => {
      if (store === 'fuel_queue') return Promise.resolve([{ id: 1, data: {}, timestamp: 'x', state: 'pending' }])
      if (store === 'trip_queue') return Promise.resolve([{ id: 2, data: {}, timestamp: 'x', state: 'pending' }])
      return Promise.resolve([])
    })
    const fetchMock = vi.fn(() => Promise.resolve({
      ok: false, status: 401,
      json: () => Promise.resolve({ status: 'error', msg: 'Sesi berakhir' }),
    }))
    vi.stubGlobal('fetch', fetchMock)

    const n = await s.syncAll()

    expect(n).toBe(0)
    expect(fetchMock).toHaveBeenCalledTimes(1) // tidak lanjut ke trip
    expect(s.sync.auth).toBe(true)
    expect(notifyMock).toHaveBeenCalled()
    expect(idb.updateQueueItem).toHaveBeenCalledWith('fuel_queue', 1, expect.objectContaining({ state: 'pending' }))
    expect(idb.deleteFromQueue).not.toHaveBeenCalled()
    vi.unstubAllGlobals()
  })

  it('syncAll melewati item failed sampai dipaksa', async () => {
    const s = useDriverStore()
    idb.getAllFromQueue.mockImplementation((store) => {
      if (store === 'fuel_queue') {
        return Promise.resolve([{ id: 3, data: {}, timestamp: 'x', state: 'failed', attempts: 2 }])
      }
      return Promise.resolve([])
    })
    const fetchMock = vi.fn(() => Promise.resolve({ ok: true, json: () => Promise.resolve({ status: 'success' }) }))
    vi.stubGlobal('fetch', fetchMock)

    expect(await s.syncAll()).toBe(0)
    expect(fetchMock).not.toHaveBeenCalled()

    expect(await s.syncAll({ force: true })).toBe(1)
    expect(fetchMock).toHaveBeenCalledTimes(1)
    vi.unstubAllGlobals()
  })

  it('syncAll melewati item yang nextAt-nya belum tiba', async () => {
    const s = useDriverStore()
    idb.getAllFromQueue.mockImplementation((store) => {
      if (store === 'fuel_queue') {
        return Promise.resolve([{ id: 4, data: {}, timestamp: 'x', state: 'pending', nextAt: Date.now() + 60000 }])
      }
      return Promise.resolve([])
    })
    const fetchMock = vi.fn(() => Promise.resolve({ ok: true, json: () => Promise.resolve({ status: 'success' }) }))
    vi.stubGlobal('fetch', fetchMock)

    expect(await s.syncAll()).toBe(0)
    expect(fetchMock).not.toHaveBeenCalled()
    expect(await s.syncAll({ force: true })).toBe(1)
    vi.unstubAllGlobals()
  })

  it('retryItem mereset state lalu mengirim paksa', async () => {
    const s = useDriverStore()
    idb.getAllFromQueue.mockImplementation((store) => {
      if (store === 'cash_queue') {
        return Promise.resolve([{ id: 21, data: {}, timestamp: 'x', state: 'failed' }])
      }
      return Promise.resolve([])
    })
    apiMock.mockResolvedValueOnce({ status: 'success', msg: 'ok' })

    const n = await s.retryItem('cash_queue', 21)

    expect(n).toBe(1)
    expect(idb.updateQueueItem).toHaveBeenCalledWith('cash_queue', 21, expect.objectContaining({
      state: 'pending', attempts: 0, nextAt: 0, lastError: '',
    }))
    expect(idb.deleteFromQueue).toHaveBeenCalledWith('cash_queue', 21)
  })

  it('enqueue menyimpan metadata state/attempts/size untuk mesin sync', async () => {
    const s = useDriverStore()
    await s.enqueue('trip_queue', { driver_name: 'RIVAN', catatan: 'x'.repeat(100) })
    const item = idb.addToQueue.mock.calls[0][1]
    expect(item.state).toBe('pending')
    expect(item.attempts).toBe(0)
    expect(item.nextAt).toBe(0)
    expect(item.size).toBeGreaterThan(100)
    expect(item.createdAt).toBeTypeOf('number')
  })
})
