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

let pendingRows = [] // v2.73.0 — assignment yang belum dikonfirmasi (default kosong)
let pendingLpjRows = [] // kasbon berstatus FUNDS_WITH_DRIVER

function mockApi() {
  apiMock.mockImplementation((path, opts = {}) => {
    if (path === '/api/driver/me') return Promise.resolve({ name: 'RIVAN', nopol: 'L 1 AB', vehicle_type: 'AVANZA', bbm_type: 'PERTALITE', is_active: true })
    if (path === '/api/cash/daily-code') return Promise.resolve({ code: 300, manual_mode: false })
    if (path === '/api/voucher/config') return Promise.resolve({ value: 130000, partner: 'SPBU 54.601.01', daily_code: 700, nominal: 130700 })
    if (path === '/api/notifications') return Promise.resolve({ notifications: [], unread: 0 })
    if (path === '/api/cash/history') return Promise.resolve([])
    if (path === '/api/cash/pending-lpj') return Promise.resolve(pendingLpjRows)
    if (path === '/api/assignments/pending') return Promise.resolve(pendingRows)
    if (path === '/api/assignments/confirm') return Promise.resolve({ status: 'success', msg: 'Konfirmasi L 1 AB berhasil! ✅' })
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
  beforeEach(() => {
    vi.clearAllMocks(); pendingRows = []; pendingLpjRows = []
    localStorage.setItem('bpf_onboarded:rivan', '1')
    localStorage.setItem('driverTab', 'bbm')
  })
  afterEach(() => { vi.unstubAllGlobals() })

  it('menampilkan shell PWA driver dengan 5 tab navigasi', async () => {
    const w = await mountView()
    expect(w.text()).toContain('BBM')
    expect(w.text()).toContain('Kasbon')
    expect(w.text()).toContain('Trip')
    expect(w.text()).toContain('OT')
    expect(w.text()).toContain('Rapor')
    expect(w.text()).toContain('🟢 Online')
    w.unmount()
  })

  it('tombol bantuan membuka glosarium khusus driver', async () => {
    const w = await mountView()
    await w.find('button[title="Bantuan & glosarium"]').trigger('click')
    await flushPromises()
    expect(w.text()).toContain('Aplikasi Driver')
    await w.findAll('button').find((b) => b.text().includes('Glosarium')).trigger('click')
    expect(w.text()).toContain('LPJ')
    w.unmount()
  })

  it('memuat profil driver dari /api/driver/me dan menampilkan nama + nopol', async () => {
    const w = await mountView()
    expect(apiMock).toHaveBeenCalledWith('/api/driver/me')
    expect(w.text()).toContain('RIVAN')
    expect(w.text()).toContain('L 1 AB')
    w.unmount()
  })

  it('mode Voucher rekanan menampilkan nilai otomatis, SPBU mitra, nota, dan liter', async () => {
    const w = await mountView()
    await w.find('[data-testid="bbm-mode-voucher"]').trigger('click')
    await flushPromises()
    expect(w.find('[data-testid="voucher-partner"]').exists()).toBe(true)
    expect(w.find('[data-testid="voucher-nota"]').exists()).toBe(true)
    expect(w.find('[data-testid="voucher-liter"]').exists()).toBe(true)
    expect(w.find('[data-testid="voucher-nominal"]').element.value).toContain('130.700')
    expect(w.text()).toContain('Kirim Pemakaian Voucher')
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

describe('Visibilitas tab & alur LPJ', () => {
  beforeEach(() => {
    vi.clearAllMocks(); pendingRows = []; pendingLpjRows = []
    localStorage.setItem('bpf_onboarded:rivan', '1')
    localStorage.setItem('driverTab', 'bbm')
  })
  afterEach(() => { vi.unstubAllGlobals() })

  it('tab Kasbon tidak ikut tampil saat tab BBM aktif (root tunggal)', async () => {
    const w = await mountView()
    const kasbonPage = w.findAll('.tab-page').find((p) => p.text().includes('Ajukan Kasbon'))
    expect(kasbonPage).toBeTruthy()
    expect(kasbonPage.attributes('style') || '').toContain('display: none')
    w.unmount()
  })

  it('tombol Isi LPJ berpindah ke tab BBM', async () => {
    pendingLpjRows = [{ id: 4, display_id: 'C-9', total_amount: 150000, daily_code: 300, nopol: 'L 1 AB' }]
    const w = await mountView()
    const kasbonBtn = w.findAll('.d-nav-item').find((b) => b.text().includes('Kasbon'))
    await kasbonBtn.trigger('click')
    await flushPromises()
    const lpjBtn = w.findAll('button').find((b) => b.text().includes('Isi LPJ'))
    expect(lpjBtn).toBeTruthy()
    await lpjBtn.trigger('click')
    await flushPromises()
    const bbmPage = w.findAll('.tab-page').find((p) => p.text().includes('Jenis BBM'))
    expect(bbmPage.attributes('style') || '').not.toContain('display: none')
    expect(w.findAll('.tab-page').find((p) => p.text().includes('Ajukan Kasbon')).attributes('style')).toContain('display: none')
    w.unmount()
  })
})

describe('Konfirmasi serah terima kendaraan (v2.73.0)', () => {
  beforeEach(() => {
    vi.clearAllMocks(); pendingRows = []; pendingLpjRows = []
    localStorage.setItem('bpf_onboarded:rivan', '1')
    localStorage.setItem('driverTab', 'bbm')
  })
  afterEach(() => { vi.unstubAllGlobals() })

  it('banner serah terima tampil bila ada assignment yang belum dikonfirmasi', async () => {
    pendingRows = [{ id: 9, driver_name: 'RIVAN', nopol: 'L 1 AB', vehicle_type: 'AVANZA' }]
    const w = await mountView()
    await flushPromises()
    expect(w.text()).toContain('Serah Terima Kendaraan')
    expect(w.text()).toContain('Konfirmasi Serah Terima')
    w.unmount()
  })

  it('tanpa assignment pending banner tidak tampil', async () => {
    const w = await mountView()
    await flushPromises()
    expect(w.text()).not.toContain('Serah Terima Kendaraan')
    w.unmount()
  })

  it('tombol konfirmasi kirim POST /api/assignments/confirm hanya dengan nopol (identitas dari sesi)', async () => {
    pendingRows = [{ id: 9, driver_name: 'RIVAN', nopol: 'L 1 AB', vehicle_type: 'AVANZA' }]
    const w = await mountView()
    await flushPromises()
    const btn = w.findAll('button').find((b) => b.text().includes('Konfirmasi Serah Terima'))
    await btn.trigger('click')
    await flushPromises()
    expect(apiMock).toHaveBeenCalledWith('/api/assignments/confirm', { method: 'POST', body: { nopol: 'L 1 AB' } })
    // setelah sukses banner hilang
    expect(w.text()).not.toContain('Serah Terima Kendaraan')
    w.unmount()
  })
})
