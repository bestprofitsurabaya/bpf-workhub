import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import TripTab from './TripTab.vue'
import { useDriverStore } from '../../stores/driverStore'

const { apiMock } = vi.hoisted(() => ({ apiMock: vi.fn() }))
vi.mock('../../api', () => ({ api: apiMock }))

const idb = vi.hoisted(() => ({
  addToQueue: vi.fn(() => Promise.resolve(1)),
  getAllFromQueue: vi.fn(() => Promise.resolve([])),
  deleteFromQueue: vi.fn(() => Promise.resolve()),
  updateQueueItem: vi.fn(() => Promise.resolve(null)),
  getAllQueueItems: vi.fn(() => Promise.resolve([])),
  countAllQueues: vi.fn(() => Promise.resolve({ fuel: 0, trip: 0, lpj: 0, overtime: 0, cash: 0 })),
  saveTripDraft: vi.fn(() => Promise.resolve()),
  loadTripDraft: vi.fn(() => Promise.resolve(null)),
  deleteTripDraft: vi.fn(() => Promise.resolve()),
}))
vi.mock('../../utils/idb', () => idb)

describe('TripTab', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    apiMock.mockResolvedValue([])
  })

  it('tombol Kirim Log Perjalanan benar-benar mengantrekan trip saat offline', async () => {
    const pinia = createPinia()
    setActivePinia(pinia)
    const store = useDriverStore()
    store.profile = { name: 'AHMAD', nopol: 'B 2628 SRP', last_odo_km: 81650 }
    store.online = false
    store.gps = {
      lat: -7.25, lon: 112.75, addr: 'Jl. Raya, Surabaya',
      detail: { kelurahan: 'Ketintang', kecamatan: 'Gayungan', kota: 'Surabaya', provinsi: 'Jawa Timur', kode_pos: '60231' },
      accuracy: 18, at: '2026-11-19T08:00:00.000Z',
    }

    const w = mount(TripTab, { global: { plugins: [pinia] } })
    await flushPromises()

    w.vm.jamBerangkat = '08:00'
    w.vm.rows[0].berangkat = 'Kantor'
    w.vm.rows[0].tujuan = 'Pelanggan'
    await flushPromises()

    const btn = w.findAll('button').find((b) => b.text().includes('Kirim Log Perjalanan'))
    expect(btn).toBeTruthy()
    expect(btn.attributes('type')).toBe('button')

    await btn.trigger('click')
    await flushPromises()

    expect(idb.addToQueue).toHaveBeenCalledTimes(1)
    const [queueName, item] = idb.addToQueue.mock.calls[0]
    expect(queueName).toBe('trip_queue')
    expect(item.data.driver_name).toBe('AHMAD')
    expect(item.data['lokasi_tujuan[]']).toEqual(['Pelanggan'])
    expect(item.data.gps_at).toBeTruthy()
    expect(item.data.gps_accuracy).toBe(18)
    expect(item.state).toBe('pending')
    expect(w.emitted('toast')?.[0]?.[0]).toContain('Offline')
  })
})
