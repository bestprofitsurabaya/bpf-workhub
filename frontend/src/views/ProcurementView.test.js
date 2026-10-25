import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import ProcurementView from './ProcurementView.vue'

const { apiMock, authMock } = vi.hoisted(() => ({
  apiMock: vi.fn(),
  authMock: { role: 'finance' },
}))
vi.mock('../api', () => ({ api: apiMock }))
vi.mock('../stores/auth', () => ({ useAuthStore: () => authMock }))
vi.mock('../stores/stepup', () => ({
  useStepupStore: () => ({
    open: false, label: '', busy: false, err: '',
    require: (fn) => fn(),
    submit: vi.fn(),
    cancel: vi.fn(),
  }),
}))

const SUPPLIERS = [
  { id: 1, name: 'PT Maju Bersama', category: 'ATK', contact_name: 'Budi', phone: '081234', address: 'Jl. A', is_active: 1 },
  { id: 2, name: 'CV Sumber Makmur', category: 'Perangkat IT', contact_name: '', phone: '', address: '', is_active: 0 },
]
const ORDERS = [
  { id: 1, display_id: 'PO-SBY-20261025-0001', supplier_name: 'PT Maju Bersama', order_date: '2026-10-25', status: 'open', created_by: 'ANDI', total_amount: 400000 },
  { id: 2, display_id: 'PO-SBY-20261025-0002', supplier_name: 'PT Maju Bersama', order_date: '2026-10-25', status: 'closed', created_by: 'RINA', total_amount: 150000 },
]
const ORDER_DETAIL = {
  ...ORDERS[0],
  notes: 'budget oktober',
  items: [
    { id: 10, po_id: 1, description: 'Tinta Printer', qty: 4, satuan: 'pcs', price: 100000, received: 0, outstanding: 4 },
  ],
  receipts: [],
}

async function mountView(role = 'finance') {
  authMock.role = role
  apiMock.mockImplementation((path) => {
    if (path === '/api/procurement/suppliers?all=1') return Promise.resolve({ suppliers: SUPPLIERS, open_pos: 1 })
    if (path === '/api/procurement/orders') return Promise.resolve({ orders: ORDERS, summary: { open: { count: 1, amount: 400000 }, partial: { count: 0, amount: 0 }, closed: { count: 1, amount: 150000 } }, filter: { status: 'all' } })
    if (/\/api\/procurement\/orders\/\d+$/.test(path)) return Promise.resolve(ORDER_DETAIL)
    return Promise.resolve({ status: 'success' })
  })
  const w = mount(ProcurementView)
  await flushPromises()
  return w
}

describe('ProcurementView', () => {
  beforeEach(() => { vi.clearAllMocks() })

  it('menampilkan daftar PO beserta status & nominal', async () => {
    const w = await mountView()
    const txt = w.text()
    expect(txt).toContain('PO-SBY-20261025-0001')
    expect(txt).toContain('PO-SBY-20261025-0002')
    expect(txt).toContain('Menunggu Barang')
    expect(txt).toContain('Selesai')
    expect(txt).toContain('Rp 400.000')
  })

  it('kartu statistik memuat jumlah & nilai per status', async () => {
    const w = await mountView()
    expect(w.text()).toContain('⏳ Menunggu Barang')
    expect(w.text()).toContain('📦 Diterima Sebagian')
    expect(w.text()).toContain('✅ Selesai')
  })

  it('detail PO menampilkan item, catatan, dan tombol penerimaan', async () => {
    const w = await mountView()
    const btn = w.findAll('button').find((b) => b.text().includes('👁️ Detail'))
    await btn.trigger('click')
    await flushPromises()
    const txt = w.text()
    expect(txt).toContain('Tinta Printer')
    expect(txt).toContain('budget oktober')
    expect(txt).toContain('Total: Rp 400.000')
    expect(txt).toContain('📦 Catat Penerimaan')
  })

  it('form PO baru menyediakan pilihan supplier aktif & item', async () => {
    const w = await mountView('finance')
    const btn = w.findAll('button').find((b) => b.text().includes('➕ PO Baru'))
    await btn.trigger('click')
    await flushPromises()
    const txt = w.text()
    expect(txt).toContain('Purchase Order Baru')
    expect(txt).toContain('Rincian Item')
    expect(txt).toContain('PT Maju Bersama')
  })

  it('tab supplier menampilkan master + status nonaktif', async () => {
    const w = await mountView()
    const btn = w.findAll('button').find((b) => b.text().includes('🏷️ Supplier'))
    await btn.trigger('click')
    await flushPromises()
    const txt = w.text()
    expect(txt).toContain('PT Maju Bersama')
    expect(txt).toContain('CV Sumber Makmur')
    expect(txt).toContain('Nonaktif')
  })

  it('ga (bukan finance) tidak melihat tombol kelola supplier', async () => {
    const w = await mountView('ga')
    const btn = w.findAll('button').find((b) => b.text().includes('🏷️ Supplier'))
    await btn.trigger('click')
    await flushPromises()
    expect(w.findAll('button').some((b) => b.text().includes('➕ Supplier'))).toBe(false)
  })
})
