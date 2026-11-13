import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import SettingsView from './SettingsView.vue'

const { apiMock } = vi.hoisted(() => ({ apiMock: vi.fn() }))
vi.mock('../api', () => ({ api: apiMock }))
// v2.37.0: SettingsView membaca auth store (Admin Pusat vs admin cabang)
vi.mock('../stores/auth', () => ({
  useAuthStore: () => ({ role: 'admin', isHoAdmin: true }),
}))

const DRIVERS = [{ name: 'RIVAN', nopol: 'L 1', vehicle_type: 'AVANZA', bbm_type: 'PERTALITE', is_active: true }]
const VEHICLES = [{ id: 1, vehicle_type: 'AVANZA', brand: 'Toyota', fuel_capacity: 45, is_active: true }]
const BBMS = [{ id: 1, name: 'PERTALITE', price_per_liter: 10000, is_active: true }]

// Status fitur edit/hapus air minum (v2.37.0) — diubah per test.
let waterEditEnabled = false

const confirmYes = async (w) => {
  const b = w.findAll('button').find((x) => x.text() === 'Ya, lanjutkan')
  expect(b).toBeTruthy()
  await b.trigger('click')
  await flushPromises()
}

async function mountView() {
  apiMock.mockImplementation((path) => {
    if (path === '/api/drivers') return Promise.resolve(DRIVERS)
    if (path === '/api/vehicles') return Promise.resolve(VEHICLES)
    if (path === '/api/bbm_types') return Promise.resolve(BBMS)
    if (path === '/api/water/edit-enabled') return Promise.resolve({ enabled: waterEditEnabled })
    return Promise.resolve({ status: 'success' })
  })
  const w = mount(SettingsView)
  await flushPromises()
  return w
}

describe('SettingsView', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.stubGlobal('confirm', vi.fn(() => true))
  })
  afterEach(() => { vi.unstubAllGlobals() })

  it('menampilkan tabel driver, kendaraan, dan tipe BBM', async () => {
    const w = await mountView()
    expect(w.text()).toContain('RIVAN')
    expect(w.text()).toContain('Toyota')
    expect(w.text()).toContain('PERTALITE')
    expect(w.text()).toContain('Aktif')
  })

  it('v2.78.0: tabel driver read-only — tidak ada tombol tambah/nonaktifkan/hapus', async () => {
    const w = await mountView()
    // Satu sumber pengelolaan driver = Manajemen User
    expect(w.text()).toContain('Kelola di Manajemen User')
    expect(w.findAll('button').some((b) => b.text().includes('Tambah Driver'))).toBe(false)
    expect(w.findAll('button').some((b) => b.text().includes('Nonaktifkan'))).toBe(false)
    expect(w.findAll('button').some((b) => b.text() === '🗑')).toBe(false)
    // Menampilkan status keterhubungan akun
    expect(w.text()).toContain('Tanpa akun')
  })

  it('reset PIN massal driver (konfirmasi) meminta PIN acak aman (tanpa 123456)', async () => {
    const w = await mountView()
    await w.findAll('button').find((b) => b.text().includes('PIN Driver')).trigger('click')
    await flushPromises()
    await confirmYes(w)
    expect(apiMock).toHaveBeenCalledWith('/api/drivers/pin-reset', {
      method: 'POST',
      body: {},
    })
  })

  it('modal tambah kendaraan: tipe kendaraan tidak duplikat (AVANZA hanya sekali)', async () => {
    const w = await mountView()
    await w.findAll('button').find((b) => b.text().includes('Tambah Kendaraan')).trigger('click')
    await flushPromises()
    const vehSelect = w.findAll('select').find((s) => s.findAll('option').some((o) => o.text() === 'AVANZA'))
    const opts = vehSelect.findAll('option').map((o) => o.text())
    expect(opts.filter((t) => t === 'AVANZA').length).toBe(1)
  })

  it('peta seksi tampil & berisi 10 seksi (9 + Voucher Rekanan v2.107.0)', async () => {
    const w = await mountView()
    const nav = w.find('.settings-nav')
    expect(nav.exists()).toBe(true)
    // 10 = 7 lama + Realtime Sheet (v2.42.0) + Deploy (v2.98.1) + Voucher (v2.107.0).
    expect(nav.findAll('.settings-nav-btn').length).toBe(10)
    // Seksi realtime receptionis (v2.42.0) ada di peta & panel
    expect(w.text()).toContain('Realtime Sheet Receptionist')
  })

  it('v2.37.0: toggle edit/hapus air minum — status nonaktif lalu PUT saat diaktifkan', async () => {
    waterEditEnabled = false
    const w = await mountView()
    const toggle = w.find('input[type=checkbox].slider-input, .water-toggle input[type=checkbox]')
      || w.findAll('input[type=checkbox]')[0]
    expect(toggle.exists()).toBe(true)
    expect(toggle.element.checked).toBe(false)
    await toggle.setValue(true)
    await flushPromises()
    await confirmYes(w)
    const put = apiMock.mock.calls.find((c) => c[0] === '/api/water/edit-enabled' && c[1]?.method === 'PUT')
    expect(put).toBeTruthy()
    expect(put[1].body).toEqual({ enabled: true })
  })
})
