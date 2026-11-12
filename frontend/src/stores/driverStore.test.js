import { describe, it, expect, vi, beforeEach } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'
import { useDriverStore, toForm } from './driverStore'

const { apiMock } = vi.hoisted(() => ({ apiMock: vi.fn() }))
vi.mock('../api', () => ({ api: apiMock }))

const idb = vi.hoisted(() => ({
  addToQueue: vi.fn(() => Promise.resolve(1)),
  getAllFromQueue: vi.fn(() => Promise.resolve([])),
  deleteFromQueue: vi.fn(() => Promise.resolve()),
  countAllQueues: vi.fn(() => Promise.resolve({ fuel: 0, trip: 0, lpj: 0 })),
}))
vi.mock('../utils/idb', () => idb)

vi.mock('../utils/gps', () => ({
  locateWithAddress: vi.fn(() => Promise.resolve({ lat: -7.25, lon: 112.75, addr: 'Jl. Test, Surabaya', spbu: '' })),
}))

describe('driver store', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    setActivePinia(createPinia())
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
    idb.countAllQueues.mockResolvedValueOnce({ fuel: 1, trip: 0, lpj: 0 })
    await s.enqueue('fuel_queue', { driver_name: 'RIVAN', nominal: 100000 })
    expect(idb.addToQueue).toHaveBeenCalledWith('fuel_queue', expect.objectContaining({ data: expect.objectContaining({ driver_name: 'RIVAN' }) }))
    expect(s.queue.fuel).toBe(1)
    expect(s.queueTotal).toBe(1)
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
})
