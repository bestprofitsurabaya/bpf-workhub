import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import AnalyticsView from './AnalyticsView.vue'

const { apiMock, ChartMock } = vi.hoisted(() => {
  const c = vi.fn()
  c.register = vi.fn()
  return { apiMock: vi.fn(), ChartMock: c }
})

vi.mock('chart.js', () => ({ Chart: ChartMock, registerables: [] }))
vi.mock('../api', () => ({ api: apiMock }))

const RESP = {
  finance: {
    total_month: 8232900, total_tx: 12, avg_per_day: 274430, avg_per_tx: 686075, days: 30,
    monthly_labels: ['2026-07', '2026-08'], monthly_amounts: [1000000, 7232900],
    top_drivers: [{ driver_name: 'RIVAN', nopol: 'L 1234 AB', total: 3000000, tx_count: 4 }],
  },
  ga: { total_drivers: 8, total_claims: 12, total_appt: 5, top_driver: 'RIVAN', freq_labels: ['RIVAN'], freq_values: [4] },
  cash: { total: 1, amount: 500000 },
  fleet: { best_vehicle: 'L 1 XYZ', worst_vehicle: 'L 2 ABC', avg_kml: 9.9, eff_labels: ['L 1 XYZ'], eff_values: [11.2] },
}

describe('AnalyticsView', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    apiMock.mockResolvedValue(RESP)
  })

  it('menampilkan kartu statistik finance, ga, cash & fleet dari response API', async () => {
    const w = mount(AnalyticsView)
    await flushPromises()
    await flushPromises()
    expect(w.text()).toContain('Total Nominal (Periode)')
    expect(w.text()).toContain('Rp 8.232.900')
    expect(w.text()).toContain('Klaim Terarsip')
    expect(w.text()).toContain('Driver Paling Sering Klaim')
    expect(w.text()).toContain('RIVAN')
    expect(w.text()).toContain('Kendaraan Paling Efisien')
    expect(w.text()).toContain('Kasbon BBM Cair')
    expect(w.text()).toContain('Rp 500.000')
    expect(w.text()).toContain('Rata-rata Efisiensi (km/L)')
  })

  it('menggambar 3 grafik Chart.js dari data API (line bulanan + bar frekuensi + bar efisiensi)', async () => {
    const w = mount(AnalyticsView)
    await flushPromises()
    await flushPromises()
    expect(apiMock).toHaveBeenCalledWith('/api/analytics/data', expect.objectContaining({ params: expect.any(Object) }))
    expect(ChartMock).toHaveBeenCalledTimes(3)
    const calls = ChartMock.mock.calls
    expect(calls[0][1].type).toBe('line')
    expect(calls[0][1].data.labels).toEqual(['2026-07', '2026-08'])
    expect(calls[1][1].type).toBe('bar')
    expect(calls[2][1].type).toBe('bar')
  })

  it('menampilkan tabel Top 5 driver', async () => {
    const w = mount(AnalyticsView)
    await flushPromises()
    await flushPromises()
    expect(w.text()).toContain('Top 5 Driver')
    expect(w.text()).toContain('L 1234 AB')
    expect(w.text()).toContain('Rp 3.000.000')
  })

  it('menampilkan pesan error saat API gagal', async () => {
    // Catatan: Chart tidak dibuat karena pada state error canvas tidak dirender
    // (branch v-else-if="err"), sehingga drawChart early-return sebelum new Chart().
    apiMock.mockRejectedValue(new Error('DB error'))
    const w = mount(AnalyticsView)
    await flushPromises()
    expect(w.text()).toContain('DB error')
    expect(ChartMock).not.toHaveBeenCalled()
  })
})
