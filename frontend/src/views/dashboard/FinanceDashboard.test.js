import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { mount, flushPromises, config } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import FinanceDashboard from './FinanceDashboard.vue'

const { apiMock } = vi.hoisted(() => ({ apiMock: vi.fn() }))
vi.mock('../../api', () => ({ api: apiMock }))

const RECAP = {
  summary: { total: 4, pending: 1, verified: 2, rejected: 1, qty: 53 },
  per_ob: [
    { ob_name: 'OB 1', total: 2, pending: 1, verified: 1, rejected: 0, qty: 5 },
    { ob_name: 'OB 2', total: 1, pending: 0, verified: 0, rejected: 1, qty: 48 },
  ],
  per_type: [
    { name: 'Gelas', qty: 48, purchases: 1 },
    { name: 'Galon', qty: 3, purchases: 1 },
  ],
  per_brand: [
    { name: 'AQUA', qty: 3, purchases: 1 },
    { name: 'Le Minerale', qty: 2, purchases: 1 },
  ],
  queue: [{ id: 1, display_id: 'WTR-20260812-0001', ob_name: 'OB 1', purchase_date: '2026-08-12', item_count: 1 }],
  kasbon: { waiting_approve: { count: 2, nominal: 250000 }, waiting_lpj: { count: 1 } },
}

// old inline helper replaced by pinia-aware mountView() di atas

describe('FinanceDashboard', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    setActivePinia(createPinia())
    config.global.stubs = {
      'router-link': { props: ['to'], template: '<a :href="to"><slot /></a>' },
    }
  })
  afterEach(() => {
    config.global.stubs = {}
    vi.unstubAllGlobals()
  })

  async function mountView(mountOpts = {}) {
    const pinia = createPinia()
    setActivePinia(pinia)
    apiMock.mockResolvedValue(RECAP)
    const w = mount(FinanceDashboard, {
      global: {
        plugins: [pinia],
        stubs: { 'router-link': { template: '<a><slot /></a>' } },
      },
      ...mountOpts,
    })
    await flushPromises()
    return w
  }

  it('menampilkan kartu statistik rekap air minum', async () => {
    const w = await mountView()
    expect(w.text()).toContain('Total Pengajuan')
    expect(w.text()).toContain('Menunggu Verifikasi')
    expect(w.text()).toContain('Terverifikasi')
    expect(w.text()).toContain('4')
    expect(w.text()).toContain('53')
  })

  it('menampilkan antrean verifikasi & tabel per OB', async () => {
    const w = await mountView()
    expect(w.text()).toContain('WTR-20260812-0001')
    expect(w.text()).toContain('OB 1')
    expect(w.text()).toContain('OB 2')
    expect(w.text()).toContain('Verifikasi →')
  })

  it('menampilkan ringkasan kasbon menunggu Finance', async () => {
    const w = await mountView()
    expect(w.text()).toContain('Rp 250.000')
    expect(w.text()).toContain('2 pengajuan')
  })

  it('tombol Export CSV mengarah ke endpoint export', async () => {
    // jsdom tidak mendukung navigasi — stub location agar href bisa di-assign
    Object.defineProperty(window, 'location', {
      writable: true,
      value: { href: 'http://localhost/' },
    })
    const w = await mountView()
    await w.findAll('button').find((b) => b.text().includes('Export CSV')).trigger('click')
    expect(window.location.href).toBe('/api/water/recap/export')
  })

  it('filter tanggal diteruskan ke /api/water/recap', async () => {
    const w = await mountView()
    const inputs = w.findAll('input[type="date"]')
    await inputs[0].setValue('2026-08-01')
    await inputs[1].setValue('2026-08-31')
    await w.findAll('button').find((b) => b.text().includes('Terapkan')).trigger('click')
    await flushPromises()
    expect(apiMock).toHaveBeenCalledWith('/api/water/recap?from=2026-08-01&to=2026-08-31')
  })

  it('menampilkan pintasan ke halaman operasional BBM', async () => {
    const w = await mountView()
    const link = w.find('[data-testid="bbm-workspace-link"]')
    expect(link.exists()).toBe(true)
    expect(link.text()).toContain('BBM, Kasbon & Subsidi Tepat')
    expect(w.find('[data-testid="bbm-quick"]').exists()).toBe(false)
  })
})
