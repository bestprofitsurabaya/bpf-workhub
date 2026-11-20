import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import ExpensesView from './ExpensesView.vue'

const { apiMock, authMock } = vi.hoisted(() => ({
  apiMock: vi.fn(),
  authMock: { role: 'finance', user: { branch_code: 'SBY' } },
}))
vi.mock('../api', () => ({ api: apiMock }))
vi.mock('../stores/auth', () => ({ useAuthStore: () => authMock }))

const VEC = (v) => Array(12).fill(0).map((_, i) => (i === 1 ? v : 0))
const RECAP = {
  year: 2026,
  selected: 'ALL',
  categories: ['kasbon', 'lpj', 'voucher', 'klaim'],
  branches: [
    { code: 'SBY', name: 'Cabang Surabaya' },
    { code: 'BDG', name: 'Cabang Bandung' },
  ],
  display: { name: 'Semua Cabang', kasbon: VEC(200000), lpj: VEC(150000), voucher: VEC(50000), klaim: VEC(30000), total: VEC(230000) },
  per_branch: {
    SBY: { name: 'Cabang Surabaya', kasbon: VEC(100000), lpj: VEC(75000), voucher: VEC(25000), klaim: VEC(15000), total: VEC(115000) },
    BDG: { name: 'Cabang Bandung', kasbon: VEC(100000), lpj: VEC(75000), voucher: VEC(25000), klaim: VEC(15000), total: VEC(115000) },
  },
  totals: { kasbon: 200000, lpj: 150000, voucher: 50000, klaim: 30000 },
  grand_total: 230000,
  sisa_total: 50000,
  errors: {},
}

beforeEach(() => {
  vi.clearAllMocks()
  authMock.role = 'finance'
  apiMock.mockResolvedValue(RECAP)
})

async function mountView() {
  const w = mount(ExpensesView)
  await flushPromises()
  return w
}

describe('ExpensesView', () => {
  it('menampilkan jembatan kasbon → LPJ dan total realisasi', async () => {
    const w = await mountView()
    const txt = w.text()
    expect(txt).toContain('Realisasi Pengeluaran')
    expect(txt).toContain('Kasbon BBM Cair')
    expect(txt).toContain('Realisasi LPJ')
    expect(txt).toContain('Voucher BBM')
    expect(txt).toContain('Sisa Kasbon')
    expect(txt).not.toContain('Pembelian Barang')
    expect(txt).not.toContain('PO diterima')
    expect(txt).toContain('Total Realisasi')
    expect(txt).toContain('Rp 200.000')  // kasbon cair
    expect(txt).toContain('Rp 150.000')  // realisasi LPJ
    expect(txt).toContain('Rp 50.000')   // voucher rekanan
    expect(txt).toContain('Rp 30.000')   // klaim tunai
  })

  it('tabel bulanan mengikuti rentang bulan + baris total', async () => {
    const w = await mountView()
    const table = w.findAll('table').at(0)
    expect(table.find('thead').text()).not.toContain('Pembelian')
    const trs = table.findAll('tbody tr')
    // Default YTD: Jan–Nov (2026-11) → 11 baris + 1 total.
    expect(trs.length).toBe(12)
    expect(trs[11].text()).toContain('Total')
    expect(trs[1].text()).toContain('Rp 150.000')
  })

  it('scope semua cabang menampilkan ringkasan per cabang + porsi', async () => {
    authMock.role = 'admin'
    const w = await mountView()
    const txt = w.text()
    expect(txt).toContain('Per Cabang')
    expect(txt).toContain('SBY — Cabang Surabaya')
    expect(txt).toContain('BDG — Cabang Bandung')
    expect(txt).toContain('50.0%')
  })

  it('pilihan cabang default mengikuti sesi (admin=ALL, finance=branch_code)', async () => {
    authMock.role = 'admin'
    const w = mount(ExpensesView)
    await flushPromises()
    expect(apiMock.mock.calls[0][0]).toContain('branch=ALL')
    w.unmount()

    apiMock.mockClear()
    authMock.role = 'finance'
    authMock.user = { branch_code: 'BDG' }
    const w2 = mount(ExpensesView)
    await flushPromises()
    expect(apiMock.mock.calls[0][0]).toContain('branch=BDG')
    w2.unmount()
    authMock.user = { branch_code: 'SBY' }
  })

  it('kartu Dana di Driver membuka antrean kasbon', async () => {
    const w = await mountView()
    await w.find('[data-testid="open-kasbon-queue"]').trigger('click')
    expect(w.emitted('open-tab')).toEqual([[
      { tab: 'kasbon', filters: { kasbon: 'outstanding' }, label: 'Dana di Driver' },
    ]])
  })

  // v2.104.0: kartu KPI lain juga bisa diklik ke daftar baris sumber.
  it('kartu Kasbon Cair & Realisasi LPJ membuka daftar baris yang terfilter', async () => {
    const w = await mountView()
    await w.find('[data-testid="open-kasbon-cair"]').trigger('click')
    await w.find('[data-testid="open-lpj-sah"]').trigger('click')

    const ev = w.emitted('open-tab')
    expect(ev[0][0]).toMatchObject({ tab: 'kasbon', filters: { kasbon: 'cair' } })
    expect(ev[1][0]).toMatchObject({ tab: 'bbm', filters: { bbmTab: 'history', bbmType: 'CASH_LPJ' } })
    await w.find('[data-testid="open-klaim"]').trigger('click')
    expect(w.emitted('open-tab')[2][0]).toMatchObject({ tab: 'bbm', filters: { bbmTab: 'history', bbmType: 'CLAIM' } })
  })

  it('menampilkan penjelasan cara membaca & pengecualian', async () => {
    const w = await mountView()
    const txt = w.text()
    expect(txt).toContain('Cara membaca laporan ini')
    expect(txt).toContain('bukan pengeluaran final')
    expect(txt).toContain('Air minum dan overtime')
  })

  it('error server ditampilkan dengan tombol coba lagi', async () => {
    apiMock.mockRejectedValue({ message: 'boom' })
    const w = await mountView()
    expect(w.text()).toContain('boom')
    expect(w.findComponent({ name: 'ErrorState' }).exists()
      || w.text().includes('Coba lagi')
      || w.findAll('button').length > 0).toBe(true)
  })
})
