import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
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

async function mountView() {
  apiMock.mockResolvedValue(RECAP)
  const w = mount(FinanceDashboard)
  await flushPromises()
  return w
}

describe('FinanceDashboard', () => {
  beforeEach(() => vi.clearAllMocks())
  afterEach(() => vi.unstubAllGlobals())

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
    const inputs = w.findAll('input')
    await inputs[0].setValue('2026-08-01')
    await inputs[1].setValue('2026-08-31')
    await w.findAll('button').find((b) => b.text().includes('Terapkan')).trigger('click')
    await flushPromises()
    expect(apiMock).toHaveBeenCalledWith('/api/water/recap?from=2026-08-01&to=2026-08-31')
  })

  // p2: instrumen verifikasi klaim BBM (👁 Detail + Subsidi Tepat) & Berita Acara
  const BBM_QUEUE = [{ id: 7, display_id: 'BBM-007', driver_name: 'BUDI', nopol: 'L 2', nominal: 200000, status: 'verified_ga', ml_anomaly_flag: 0 }]
  const TX_DETAIL = { id: 7, display_id: 'BBM-007', driver_name: 'BUDI', nopol: 'L 2', nominal: 200000, liter: 30, odo_km: 5000, km_per_liter: 10, photos: [], created_at: '2026-01-02 09:00' }
  const TX_CROSS = { health_score: 80, flags: [], proof_signals: [], budget_usage_percent: 40, odo_diff: 20, recommendation: 'AMAN' }
  const SUBSIDY_MATCH = {
    verdict: 'match', liter: 30, nominal: 200000, linked: null,
    candidates: [{ id: 9, transaction_id: 'SPBU-0001', transaction_date: '2026-01-02 07:30', volume: 30, amount: 199000, dvol: 0, dnom: 1000, spbu_id: '34.001.03', city: 'SIDOARJO', verification: 'ORISINIL', verdict: 'match' }],
  }
  const ATTESTS = [{ id: 3, period_start: '2026-01-01', period_end: '2026-01-31', record_count: 12, generated_by: 'Finance SBY', generated_at: '2026-02-01 10:00:00' }]

  const financeImpl = (path, opts = {}) => {
    if (path === '/api/water/recap') return Promise.resolve(RECAP)
    if (path.startsWith('/api/queue')) return Promise.resolve(opts?.params?.tab === 'driver_confirm' ? [] : BBM_QUEUE)
    if (path === '/api/subsidy/attest') return Promise.resolve({ attestations: ATTESTS })
    if (path === '/api/transactions/detail/7') return Promise.resolve(TX_DETAIL)
    if (path.startsWith('/api/cross-check')) return Promise.resolve(TX_CROSS)
    if (path.startsWith('/api/subsidy/match')) return Promise.resolve(SUBSIDY_MATCH)
    return Promise.resolve(RECAP)
  }

  it('menampilkan Berita Acara Subsidi Tepat (periode, dibuat oleh, unduh PDF)', async () => {
    Object.defineProperty(window, 'location', { writable: true, value: { href: 'http://localhost/' } })
    const openSpy = vi.spyOn(window, 'open').mockReturnValue(null)
    apiMock.mockImplementation(financeImpl)
    const w = mount(FinanceDashboard)
    await flushPromises()
    expect(w.text()).toContain('Berita Acara Rekonsiliasi — Subsidi Tepat')
    expect(w.text()).toContain('2026-01-01 s/d 2026-01-31')
    expect(w.text()).toContain('Finance SBY')
    await w.findAll('button').find((b) => b.text().includes('PDF')).trigger('click')
    expect(openSpy).toHaveBeenCalledWith('/api/subsidy/attest/3/pdf', '_blank')
  })

  it('👁 Detail klaim BBM: instrumen render + kandidat bisa dijodohkan', async () => {
    apiMock.mockImplementation(financeImpl)
    const w = mount(FinanceDashboard)
    await flushPromises()
    const row = w.findAll('tbody tr').find((r) => r.text().includes('BBM-007'))
    await row.findAll('button').find((b) => b.text().includes('Detail')).trigger('click')
    await flushPromises()

    expect(apiMock).toHaveBeenCalledWith('/api/transactions/detail/7')
    expect(apiMock).toHaveBeenCalledWith('/api/subsidy/match/7')
    expect(w.text()).toContain('📋 Data Klaim')
    expect(w.text()).toContain('🩺 Cross-Check Otomatis')
    expect(w.text()).toContain('⛽ Subsidi Tepat')
    expect(w.text()).toContain('SPBU-0001')

    // Penjodohan: klik 🔗 Jodohkan → konfirmasi → POST /api/subsidy/link/7
    await w.findAll('button').find((b) => b.text() === '🔗 Jodohkan').trigger('click')
    await flushPromises()
    const yes = w.findAll('button').find((b) => b.text() === 'Jodohkan' && !b.text().includes('🔗'))
    await yes.trigger('click')
    await flushPromises()
    expect(apiMock).toHaveBeenCalledWith('/api/subsidy/link/7', {
      method: 'POST',
      body: { subsidy_transaction_id: 9 },
    })
  })
})
