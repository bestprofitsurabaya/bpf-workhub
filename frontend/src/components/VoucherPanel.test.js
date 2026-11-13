import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import VoucherPanel from './VoucherPanel.vue'
import { useAuthStore } from '../stores/auth'

const { apiMock } = vi.hoisted(() => ({ apiMock: vi.fn() }))
vi.mock('../api', () => ({ api: apiMock }))

const PENDING = {
  id: 1,
  display_id: 'BBM-SBY-20261113-0001',
  driver_name: 'BUDI',
  nopol: 'L 1234 AB',
  nominal: 130700,
  liter: 12.5,
  voucher_value: 130000,
  daily_code: 700,
  voucher_partner: 'SPBU 54.601.01',
  nota_no: 'INV-001',
  created_at: '2026-11-13T09:00:00',
  foto_odo_sebelum: 'odo.jpg',
  foto_nota_odo_sesudah: null,
  foto_struk: null,
}
const UNSETTLED = { ...PENDING, id: 2, display_id: 'BBM-SBY-20261113-0002' }

function mockApi() {
  apiMock.mockImplementation((path, opts = {}) => {
    if (path === '/api/voucher/summary') {
      return Promise.resolve({
        pending: { count: 1, amount: 130700 },
        open: { count: 1, amount: 130700 },
        settled: { count: 0, amount: 0 },
        config: { value: 130000, partner: 'SPBU 54.601.01' },
      })
    }
    if (path === '/api/voucher/pending') return Promise.resolve({ data: [PENDING] })
    if (path === '/api/voucher/unsettled') return Promise.resolve({ data: [UNSETTLED] })
    if (path === '/api/voucher/settlements') {
      if (opts.method === 'POST') return Promise.resolve({ status: 'success', msg: 'Tagihan dibuat' })
      return Promise.resolve([])
    }
    if (path === '/api/voucher/verify/1') return Promise.resolve({ status: 'success', msg: 'Voucher diverifikasi GA' })
    return Promise.resolve({})
  })
}

async function mountView(role = 'finance') {
  const pinia = createPinia()
  setActivePinia(pinia)
  const auth = useAuthStore()
  auth.user = { role, user_name: `${role}_sby`, full_name: `${role.toUpperCase()} SBY` }
  mockApi()
  const w = mount(VoucherPanel, { global: { plugins: [pinia] } })
  await flushPromises()
  await flushPromises()
  return w
}

describe('VoucherPanel — meja kerja voucher rekanan', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.stubGlobal('confirm', vi.fn(() => true))
  })

  it('menampilkan tiga angka: menunggu GA, belum ditagih, sudah ditagih', async () => {
    const w = await mountView()
    const txt = w.text()
    expect(txt).toContain('Menunggu verifikasi GA')
    expect(txt).toContain('Belum ditagih')
    expect(txt).toContain('Sudah masuk tagihan')
    expect(txt).toContain('Rp 130.700')
    expect(txt).toContain('Nilai cabang: Rp 130.000')
    w.unmount()
  })

  it('GA bisa memverifikasi voucher dari daftar pending', async () => {
    const w = await mountView('ga')
    const btn = w.findAll('button').find((b) => b.text().includes('Verifikasi'))
    expect(btn).toBeTruthy()
    await btn.trigger('click')
    await flushPromises()
    expect(apiMock).toHaveBeenCalledWith('/api/voucher/verify/1', { method: 'POST' })
    w.unmount()
  })

  it('finance membuat tagihan periode dari voucher terpilih', async () => {
    const w = await mountView('finance')
    const checks = w.findAll('input[type="checkbox"]')
    expect(checks.length).toBeGreaterThanOrEqual(2)
    await checks[1].setValue(true)

    const btn = w.findAll('button').find((b) => b.text().includes('Buat tagihan'))
    expect(btn.attributes('disabled')).toBeUndefined()
    await btn.trigger('click')
    await flushPromises()

    const post = apiMock.mock.calls.find(([p, o]) => p === '/api/voucher/settlements' && o?.method === 'POST')
    expect(post).toBeTruthy()
    expect(post[1].body.tx_ids).toEqual([2])
    w.unmount()
  })

  it('GA tidak melihat tombol buat tagihan (hanya finance/admin)', async () => {
    const w = await mountView('ga')
    expect(w.findAll('button').some((b) => b.text().includes('Buat tagihan'))).toBe(false)
    w.unmount()
  })
})
