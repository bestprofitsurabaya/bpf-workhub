import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import FinanceDashboard from './FinanceDashboard.vue'
import { useAuthStore } from '../../stores/auth'

const { apiMock } = vi.hoisted(() => ({ apiMock: vi.fn() }))
vi.mock('../../api', () => ({ api: apiMock }))

const BADGES = {
  bbm_verify_pending: 3,
  cash_pending: 2,
  finance_pending: 1,
  water_pending: 4,
}

const WATER_RECAP = {
  summary: { total: 12, pending: 4, verified: 7, rejected: 1, qty: 48 },
  queue: [{ id: 9, display_id: 'WTR-009', ob_name: 'BUDI', purchase_date: '2026-11-02T00:00:00', item_count: 2 }],
  per_ob: [{ ob_name: 'BUDI', total: 5, pending: 2, verified: 3, rejected: 0 }],
  per_type: [{ name: 'Galon', qty: 20, purchases: 6 }],
  per_brand: [{ name: 'AQUA', qty: 20, purchases: 6 }],
}

describe('FinanceDashboard', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  async function mountView(mountOpts = {}) {
    const pinia = createPinia()
    setActivePinia(pinia)
    const auth = useAuthStore(pinia)
    auth.user = { role: 'finance', user_name: 'finance_sby', full_name: 'Finance SBY', branch_name: 'Surabaya' }
    apiMock.mockResolvedValue({ badges: BADGES })
    const w = mount(FinanceDashboard, {
      global: {
        plugins: [pinia],
        stubs: { 'router-link': { props: ['to'], template: '<a :href="to"><slot /></a>' } },
      },
      ...mountOpts,
    })
    await flushPromises()
    return w
  }

  it('menyapa Finance sesuai cabang dari akun dan branch session', async () => {
    const w = await mountView()
    expect(w.find('[data-testid="finance-welcome"]').text()).toContain('Finance Surabaya')
    expect(w.find('[data-testid="finance-welcome"]').text()).toContain('kantor cabang Surabaya')
  })

  it('menampilkan ringkasan prioritas tanpa rincian operasional panjang', async () => {
    const w = await mountView()
    const priorities = w.find('[data-testid="finance-priorities"]')
    expect(priorities.text()).toContain('Klaim BBM siap dicairkan')
    expect(priorities.text()).toContain('3')
    expect(priorities.text()).toContain('Kasbon menunggu Finance')
    expect(priorities.text()).toContain('2')
    expect(priorities.text()).toContain('Klaim menunggu LPJ')
    expect(priorities.text()).toContain('Air minum menunggu')
    expect(w.find('[data-testid="water-workspace-link"]').attributes('href')).toBe('/water')
    expect(w.find('[data-testid="bbm-workspace-link"]').attributes('href')).toBe('/cash')
    expect(w.find('[data-testid="water-section-heading"]').exists()).toBe(false)
    expect(w.text()).not.toContain('Ringkasan per OB')
    expect(apiMock).toHaveBeenCalledOnce()
    expect(apiMock).toHaveBeenCalledWith('/api/nav/badges')
  })

  it('tab Air Minum memuat rekap dan antrean verifikasi secara lazy', async () => {
    const w = await mountView()
    expect(w.find('[data-testid="finance-tab-water"]').exists()).toBe(true)
    expect(w.find('[data-testid="water-section-heading"]').exists()).toBe(false)
    // Rekap belum diminta selama tab Ringkasan aktif.
    expect(apiMock).toHaveBeenCalledOnce()

    apiMock.mockResolvedValueOnce(WATER_RECAP)
    await w.find('[data-testid="finance-tab-water"]').trigger('click')
    await flushPromises()

    expect(w.find('[data-testid="finance-tab-water"]').attributes('aria-selected')).toBe('true')
    expect(w.find('[data-testid="water-section-heading"]').exists()).toBe(true)
    expect(w.text()).toContain('Antrean Verifikasi Air Minum')
    expect(w.text()).toContain('WTR-009')
    expect(apiMock).toHaveBeenCalledWith('/api/water/recap')
  })

  it('menampilkan keadaan gagal ringkasan, tetapi pintasan kerja tetap tersedia', async () => {
    apiMock.mockRejectedValueOnce(new Error('offline'))
    const w = await mountView()
    expect(w.text()).toContain('Ringkasan antrean belum dapat dimuat')
    expect(w.find('[data-testid="bbm-workspace-link"]').exists()).toBe(true)
    expect(w.find('[data-testid="water-workspace-link"]').exists()).toBe(true)
  })
})
