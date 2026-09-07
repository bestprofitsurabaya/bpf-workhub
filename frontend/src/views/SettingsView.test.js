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

  it('toggle driver memanggil endpoint activate/deactivate yang tepat', async () => {
    const w = await mountView()
    await w.findAll('button').find((b) => b.text().includes('Nonaktifkan')).trigger('click')
    await flushPromises()
    expect(apiMock).toHaveBeenCalledWith('/api/drivers/RIVAN/deactivate', { method: 'POST' })
  })

  it('modal tambah driver: simpan memanggil /api/drivers/sync dengan nama uppercase', async () => {
    const w = await mountView()
    await w.findAll('button').find((b) => b.text().includes('Tambah Driver')).trigger('click')
    await flushPromises()
    expect(w.text()).toContain('Tambah Driver')
    // Input nama driver ada di modal (placeholder 'mis. RIVAN') — jangan pakai
    // inputs[0] karena kartu TTD air minum (di atas) ikut punya input.
    const nameInput = w.findAll('input').find((i) => i.attributes('placeholder') === 'mis. RIVAN')
    await nameInput.setValue('budi')
    // Tombol modal simpan = '💾 Simpan' persis (bukan '💾 Simpan Nama TTD' dari kartu air minum)
    await w.findAll('button').find((b) => b.text().trim() === '💾 Simpan').trigger('click')
    await flushPromises()
    expect(apiMock).toHaveBeenCalledWith('/api/drivers/sync', {
      method: 'POST',
      body: expect.objectContaining({ driver_name: 'BUDI' }),
    })
  })

  it('hapus driver (dengan konfirmasi) memanggil /api/drivers/<nama>/delete', async () => {
    const w = await mountView()
    await w.findAll('button').find((b) => b.text() === '🗑').trigger('click')
    await flushPromises()
    expect(global.confirm).toHaveBeenCalled()
    expect(apiMock).toHaveBeenCalledWith('/api/drivers/RIVAN/delete', { method: 'POST' })
  })

  it('reset PIN massal driver (konfirmasi) memanggil /api/drivers/pin-reset dengan 123456', async () => {
    const w = await mountView()
    await w.findAll('button').find((b) => b.text().includes('PIN Driver')).trigger('click')
    await flushPromises()
    expect(global.confirm).toHaveBeenCalled()
    expect(apiMock).toHaveBeenCalledWith('/api/drivers/pin-reset', {
      method: 'POST',
      body: expect.objectContaining({ new_pin: '123456' }),
    })
  })

  it('tipe kendaraan pada modal tidak duplikat (AVANZA hanya sekali)', async () => {
    const w = await mountView()
    await w.findAll('button').find((b) => b.text().includes('Tambah Driver')).trigger('click')
    await flushPromises()
    // select pertama bisa jadi switcher cabang (v2.19.2) — pilih select yang
    // berisi opsi kendaraan (modal Tambah Driver)
    const vehSelect = w.findAll('select').find((s) => s.findAll('option').some((o) => o.text() === 'AVANZA'))
    const opts = vehSelect.findAll('option').map((o) => o.text())
    expect(opts.filter((t) => t === 'AVANZA').length).toBe(1)
  })

  it('v2.37.0: peta seksi tampil & berisi 6 seksi', async () => {
    const w = await mountView()
    const nav = w.find('.settings-nav')
    expect(nav.exists()).toBe(true)
    expect(nav.findAll('.settings-nav-btn').length).toBe(6)
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
    const put = apiMock.mock.calls.find((c) => c[0] === '/api/water/edit-enabled' && c[1]?.method === 'PUT')
    expect(put).toBeTruthy()
    expect(put[1].body).toEqual({ enabled: true })
  })
})
