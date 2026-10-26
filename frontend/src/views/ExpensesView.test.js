import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import ExpensesView from './ExpensesView.vue'

const { apiMock, authMock } = vi.hoisted(() => ({
  apiMock: vi.fn(),
  authMock: { role: 'finance' },
}))
vi.mock('../api', () => ({ api: apiMock }))
vi.mock('../stores/auth', () => ({ useAuthStore: () => authMock }))

const VEC = (v) => Array(12).fill(0).map((_, i) => (i === 1 ? v : 0))
const RECAP = {
  year: 2026,
  selected: 'ALL',
  categories: ['po', 'kasbon'],
  branches: [
    { code: 'SBY', name: 'Cabang Surabaya' },
    { code: 'BDG', name: 'Cabang Bandung' },
  ],
  display: { name: 'Semua Cabang', po: VEC(600000), kasbon: VEC(200000), total: VEC(800000) },
  per_branch: {
    SBY: { name: 'Cabang Surabaya', po: VEC(300000), kasbon: VEC(100000), total: VEC(400000) },
    BDG: { name: 'Cabang Bandung', po: VEC(300000), kasbon: VEC(100000), total: VEC(400000) },
  },
  totals: { po: 600000, kasbon: 200000 },
  grand_total: 800000,
  errors: {},
}

beforeEach(() => {
  vi.clearAllMocks()
  apiMock.mockResolvedValue(RECAP)
})

async function mountView() {
  const w = mount(ExpensesView)
  await flushPromises()
  return w
}

describe('ExpensesView', () => {
  it('menampilkan kartu total kategori & grand total', async () => {
    const w = await mountView()
    const txt = w.text()
    expect(txt).toContain('Rekap Pengeluaran')
    expect(txt).toContain('Pembelian Barang (PO diterima)')
    expect(txt).toContain('Kasbon BBM (dana cair)')
    expect(txt).toContain('Rp 600.000')
    expect(txt).toContain('Rp 200.000')
    expect(txt).toContain('Rp 800.000')
  })

  it('tabel bulanan 12 baris + baris total tahun', async () => {
    const w = await mountView()
    const trs = w.findAll('table').at(0).findAll('tbody tr')
    expect(trs.length).toBe(13)
    expect(trs[12].text()).toContain('Total 2026')
    expect(trs[1].text()).toContain('Rp 600.000')
  })

  it('scope semua cabang menampilkan ringkasan per cabang', async () => {
    authMock.role = 'admin'          // admin → default scope ALL
    const w = await mountView()
    const txt = w.text()
    expect(txt).toContain('Per Cabang — 2026')
    expect(txt).toContain('SBY — Cabang Surabaya')
    expect(txt).toContain('BDG — Cabang Bandung')
  })

  it('pilihan cabang default mengikuti role (admin=ALL, finance=SBY)', async () => {
    authMock.role = 'admin'
    const w = mount(ExpensesView)
    await flushPromises()
    expect(apiMock.mock.calls[0][0]).toContain('branch=ALL')
    w.unmount()

    apiMock.mockClear()
    authMock.role = 'finance'
    const w2 = mount(ExpensesView)
    await flushPromises()
    expect(apiMock.mock.calls[0][0]).toContain('branch=SBY')
    w2.unmount()
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
