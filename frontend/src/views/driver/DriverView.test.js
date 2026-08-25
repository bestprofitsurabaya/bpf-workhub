import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import DriverView from './DriverView.vue'
import { useAuthStore } from '../../stores/auth'

vi.mock('socket.io-client', () => ({
  io: vi.fn(() => ({ on: vi.fn(), emit: vi.fn(), disconnect: vi.fn() })),
}))

const { apiMock } = vi.hoisted(() => ({ apiMock: vi.fn() }))
vi.mock('../../api', () => ({ api: apiMock }))

const idb = vi.hoisted(() => ({
  countAllQueues: vi.fn(() => Promise.resolve({ fuel: 0, trip: 0, lpj: 0 })),
  saveTripDraft: vi.fn(() => Promise.resolve()),
  loadTripDraft: vi.fn(() => Promise.resolve(null)),
  deleteTripDraft: vi.fn(() => Promise.resolve()),
}))
vi.mock('../../utils/idb', () => idb)
vi.mock('../../utils/gps', () => ({
  locateWithAddress: vi.fn(() => Promise.resolve({ lat: -7.25, lon: 112.75, addr: 'Jl. Raya, Surabaya', spbu: '' })),
}))

function mockApi() {
  apiMock.mockImplementation((path) => {
    if (path === '/api/driver/me') return Promise.resolve({ name: 'RIVAN', nopol: 'L 1 AB', vehicle_type: 'AVANZA', bbm_type: 'PERTALITE', is_active: true })
    if (path === '/api/cash/daily-code') return Promise.resolve({ code: 300, manual_mode: false })
    if (path === '/api/notifications') return Promise.resolve({ notifications: [], unread: 0 })
    if (path === '/api/cash/history' || path === '/api/cash/pending-lpj') return Promise.resolve([])
    if (path.includes('/api/appointments/driver-today')) return Promise.resolve([])
    if (path.includes('/api/vehicle-allowed-bbm/')) return Promise.resolve([])
    return Promise.resolve({})
  })
}

async function mountView() {
  const pinia = createPinia()
  setActivePinia(pinia)
  const auth = useAuthStore()
  auth.user = { role: 'driver', full_name: 'Rivan', user_name: 'rivan' }
  mockApi()
  const w = mount(DriverView, { global: { plugins: [pinia] } })
  await flushPromises()
  await flushPromises()
  return w
}

describe('DriverView', () => {
  beforeEach(() => { vi.clearAllMocks() })
  afterEach(() => { vi.unstubAllGlobals() })

  it('menampilkan shell PWA driver dengan 4 tab navigasi', async () => {
    const w = await mountView()
    expect(w.text()).toContain('BBM')
    expect(w.text()).toContain('Kasbon')
    expect(w.text()).toContain('Trip')
    expect(w.text()).toContain('Rapor')
    expect(w.text()).toContain('🟢 Online')
    w.unmount()
  })

  it('memuat profil driver dari /api/driver/me dan menampilkan nama + nopol', async () => {
    const w = await mountView()
    expect(apiMock).toHaveBeenCalledWith('/api/driver/me')
    expect(w.text()).toContain('RIVAN')
    expect(w.text()).toContain('L 1 AB')
    w.unmount()
  })

  it('switch tab ke Kasbon menampilkan form pengajuan & tombol sinkron tetap ada', async () => {
    const w = await mountView()
    const kasbonBtn = w.findAll('.d-nav-item').find((b) => b.text().includes('Kasbon'))
    await kasbonBtn.trigger('click')
    await flushPromises()
    expect(w.text()).toContain('Ajukan Kasbon')
    expect(w.text()).toContain('Sinkron')
    w.unmount()
  })
})
