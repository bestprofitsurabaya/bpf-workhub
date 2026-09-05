import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import WaterView from './WaterView.vue'

const { apiMock } = vi.hoisted(() => ({ apiMock: vi.fn() }))
vi.mock('../api', () => ({ api: apiMock }))
vi.mock('../stores/auth', () => ({
  useAuthStore: () => ({ role: 'finance' }),
}))
vi.mock('../stores/stepup', () => ({
  useStepupStore: () => ({
    open: false, label: '', busy: false, err: '',
    require: (fn) => fn(),
    submit: vi.fn(),
    cancel: vi.fn(),
  }),
}))

const TYPES = [
  { id: 1, name: 'Gelas', brands: [{ id: 1, type_id: 1, brand: 'VIT' }] },
  { id: 2, name: 'Botol', brands: [{ id: 2, type_id: 2, brand: 'Le Minerale' }] },
  { id: 3, name: 'Galon', brands: [{ id: 3, type_id: 3, brand: 'AQUA' }] },
]
const PURCHASES = [
  { id: 1, display_id: 'WTR-20260812-0001', ob_name: 'BUDI', purchase_date: '2026-08-12', status: 'pending', created_at: '2026-08-12T09:30:00', items: [{ drink_type: 'Galon', brand: 'AQUA', satuan: 'galon', quantity: 3 }] },
  { id: 2, display_id: 'WTR-20260812-0002', ob_name: 'SITI', purchase_date: '2026-08-12', status: 'verified', created_at: '2026-08-12T10:00:00', items: [{ drink_type: 'Botol', brand: 'Le Minerale', satuan: 'dus', quantity: 2 }], remark: 'OK', verified_by: 'RINA' },
]

async function mountView() {
  apiMock.mockImplementation((path) => {
    if (path === '/api/water/brands') return Promise.resolve({ types: TYPES, brands: [] })
    if (path === '/api/water/purchases') return Promise.resolve(PURCHASES)
    if (path.startsWith('/api/water/purchases/')) return Promise.resolve(PURCHASES[0])
    return Promise.resolve({ status: 'success' })
  })
  const w = mount(WaterView)
  await flushPromises()
  return w
}

describe('WaterView', () => {
  beforeEach(() => { vi.clearAllMocks() })

  it('menampilkan daftar pengajuan dengan status', async () => {
    const w = await mountView()
    expect(w.text()).toContain('WTR-20260812-0001')
    expect(w.text()).toContain('WTR-20260812-0002')
    expect(w.text()).toContain('Menunggu Verifikasi')
    expect(w.text()).toContain('Terverifikasi')
  })

  it('finance melihat tombol verifikasi & tolak untuk pengajuan pending', async () => {
    const w = await mountView()
    const btns = w.findAll('button').map((b) => b.text())
    expect(btns).toContain('✅ Verifikasi')
    expect(btns).toContain('✖ Tolak')
    expect(btns).toContain('📄 PDF')
  })

  it('finance melihat master merk per tipe', async () => {
    const w = await mountView()
    expect(w.text()).toContain('Master Merk Air Minum')
    expect(w.text()).toContain('AQUA')
    expect(w.text()).toContain('Le Minerale')
  })

  it('detail menampilkan remark verifikasi (pengajuan terverifikasi)', async () => {
    apiMock.mockImplementation((path) => {
      if (path === '/api/water/brands') return Promise.resolve({ types: TYPES, brands: [] })
      if (path === '/api/water/purchases') return Promise.resolve(PURCHASES)
      if (path === '/api/water/purchases/2') return Promise.resolve(PURCHASES[1])
      return Promise.resolve(PURCHASES[0])
    })
    const w = mount(WaterView)
    await flushPromises()
    // Buka detail pengajuan TERVERIFIKASI (indeks 1) — punya remark
    const detailBtns = w.findAll('button').filter((b) => b.text() === '👁️ Detail')
    await detailBtns[1].trigger('click')
    await flushPromises()
    expect(w.text()).toContain('Remark')
    expect(w.text()).toContain('OK')
  })
})
