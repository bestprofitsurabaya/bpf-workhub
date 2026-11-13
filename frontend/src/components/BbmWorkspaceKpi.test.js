import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import BbmWorkspaceKpi from './BbmWorkspaceKpi.vue'

const { apiMock } = vi.hoisted(() => ({ apiMock: vi.fn() }))
vi.mock('../api', () => ({ api: apiMock }))

const SUMMARY = {
  period: { start: '2026-10-14', end: '2026-11-12' },
  claims: {
    masuk: { count: 9, amount: 1500000 },
    siap_cair: { count: 3, amount: 700000 },
    dibayar: { count: 4, amount: 1200000 },
    final: { count: 2, amount: 600000 },
    lpj_diajukan: { count: 1, amount: 100000 },
    lpj_sah: { count: 2, amount: 500000 },
    voucher_sah: { count: 1, amount: 260000 },
  },
  kasbon: {
    diajukan: { count: 7, amount: 1400000 },
    cair: { count: 3, amount: 900000 },
    selesai: { count: 2, amount: 600000 },
    outstanding: { count: 1, amount: 300000 },
  },
  realisasi: { lpj_sah: 500000, klaim_dibayar: 1200000, voucher_sah: 260000, total: 1960000 },
  meta: { basis_version: 'bbm-scope-2' },
}

describe('BbmWorkspaceKpi — KPI yang bisa diklik ke daftar baris', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    apiMock.mockResolvedValue(SUMMARY)
  })

  const mountView = () => mount(BbmWorkspaceKpi, {
    props: { scope: { start: '2026-10-14', end: '2026-11-12' } },
  })

  it('menampilkan lima KPI dari definisi tunggal (summary endpoint)', async () => {
    const w = mountView()
    await flushPromises()

    expect(apiMock).toHaveBeenCalledWith('/api/bbm/workspace/summary', {
      params: { start_date: '2026-10-14', end_date: '2026-11-12' },
    })
    expect(w.find('[data-testid="kpi-klaim_dibayar"]').text()).toContain('Rp 1.200.000')
    expect(w.find('[data-testid="kpi-lpj_sah"]').text()).toContain('Rp 500.000')
    expect(w.find('[data-testid="kpi-voucher_sah"]').text()).toContain('Rp 260.000')
    expect(w.find('[data-testid="kpi-kasbon_cair"]').text()).toContain('Rp 900.000')
    expect(w.find('[data-testid="kpi-outstanding"]').text()).toContain('Rp 300.000')
  })

  it('menampilkan jumlah baris sumber untuk tiap KPI', async () => {
    const w = mountView()
    await flushPromises()
    expect(w.find('[data-testid="kpi-klaim_dibayar"]').text()).toContain('4 baris')
    expect(w.find('[data-testid="kpi-outstanding"]').text()).toContain('1 baris')
  })

  it('klik KPI memancarkan tab + filter tujuan yang benar', async () => {
    const w = mountView()
    await flushPromises()

    await w.find('[data-testid="kpi-klaim_dibayar"]').trigger('click')
    await w.find('[data-testid="kpi-lpj_sah"]').trigger('click')
    await w.find('[data-testid="kpi-voucher_sah"]').trigger('click')
    await w.find('[data-testid="kpi-outstanding"]').trigger('click')

    const events = w.emitted('open')
    expect(events).toHaveLength(4)
    // Klaim dibayar → tab BBM, daftar riwayat, jenis CLAIM.
    expect(events[0][0]).toMatchObject({ tab: 'bbm', filters: { bbmTab: 'history', bbmType: 'CLAIM' } })
    // LPJ sah → tab BBM, jenis CASH_LPJ.
    expect(events[1][0]).toMatchObject({ tab: 'bbm', filters: { bbmType: 'CASH_LPJ' } })
    // Voucher rekanan → tab Voucher.
    expect(events[2][0]).toMatchObject({ tab: 'voucher' })
    // Dana di driver → tab Kasbon, filter dana di driver.
    expect(events[3][0]).toMatchObject({ tab: 'kasbon', filters: { kasbon: 'outstanding' } })
  })

  it('gagal memuat summary tidak merusak halaman', async () => {
    apiMock.mockRejectedValue(Object.assign(new Error('boom'), { data: { error: 'DB error' } }))
    const w = mountView()
    await flushPromises()
    expect(w.text()).toContain('DB error')
  })
})
