import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import ApprovalsView from './ApprovalsView.vue'

const { apiMock } = vi.hoisted(() => ({ apiMock: vi.fn() }))
vi.mock('../api', () => ({ api: apiMock }))

const ITEMS = [
  {
    doc_type: 'cash', doc_ref: 5, display_id: 'CASH-SBY-20260906-0001',
    requested_by: 'Budi Driver', requester_role: 'driver', branch_code: 'SBY',
    chain: [{ approver: 'chief_driver', role: 'chief_driver' }, { approver: 'ga', role: 'ga' }],
    step: 1, status: 'pending', pending_at: 'chief_driver', created_at: '2026-09-06 08:00:00',
  },
  {
    doc_type: 'overtime_driver', doc_ref: 9, display_id: 'OTL-SBY-20260906-0002',
    requested_by: 'Budi Driver', requester_role: 'driver', branch_code: 'SBY',
    chain: [{ approver: 'ga_hr', role: 'ga_hr' }, { approver: 'admin', role: 'admin' }],
    step: 2, status: 'pending', pending_at: 'admin', created_at: '2026-09-06 07:30:00',
  },
]

async function mountView() {
  const w = mount(ApprovalsView)
  await flushPromises()
  return w
}

describe('ApprovalsView', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.stubGlobal('confirm', vi.fn(() => true))
    vi.stubGlobal('alert', vi.fn())
  })
  afterEach(() => vi.unstubAllGlobals())

  it('antrean kosong → pesan ramah tanpa tabel', async () => {
    apiMock.mockResolvedValue({ status: 'success', data: [] })
    const w = await mountView()
    expect(w.text()).toContain('Approval Berjenjang')
    expect(w.text()).toContain('Tidak ada pengajuan')
    expect(w.find('table').exists()).toBe(false)
  })

  it('menampilkan pengajuan pending + rantai ACC + langkah', async () => {
    apiMock.mockResolvedValue({ status: 'success', data: ITEMS })
    const w = await mountView()
    expect(w.text()).toContain('CASH-SBY-20260906-0001')
    expect(w.text()).toContain('OTL-SBY-20260906-0002')
    expect(w.text()).toContain('Budi Driver')
    // rantai ACC dirender (langkah 1 & 2)
    expect(w.text()).toContain('chief_driver →')
    expect(w.text()).toContain('2. ga')
    expect(w.text()).toContain('ga_hr →')
    expect(w.text()).toContain('2. admin')
  })

  it('ACC melalui modal memanggil endpoint keputusan', async () => {
    apiMock.mockImplementation((path, opts) => {
      if (path === '/api/approvals') return Promise.resolve({ status: 'success', data: ITEMS })
      if (String(path).endsWith('/decision')) {
        return Promise.resolve({ status: 'success', msg: 'ACC langkah 1' })
      }
      return Promise.resolve({})
    })
    const w = await mountView()
    await w.findAll('button').find((b) => b.text() === 'Keputusan').trigger('click')
    await flushPromises()
    expect(w.text()).toContain('Keputusan ACC')
    const accBtn = w.findAll('button').find((b) => b.text().includes('ACC') && !b.text().includes('Tolak'))
    await accBtn.trigger('click')
    await flushPromises()
    expect(apiMock).toHaveBeenCalledWith(
      '/api/approvals/cash/5/decision',
      expect.objectContaining({ method: 'POST', body: { decision: 'approved', note: '' } }),
    )
  })

  it('menolak tanpa alasan → alert, tidak memanggil endpoint', async () => {
    apiMock.mockResolvedValue({ status: 'success', data: ITEMS })
    const w = await mountView()
    await w.findAll('button').find((b) => b.text() === 'Keputusan').trigger('click')
    await flushPromises()
    const rejectBtn = w.findAll('button').find((b) => b.text().includes('Tolak'))
    await rejectBtn.trigger('click')
    await flushPromises()
    expect(vi.mocked(alert).mock.calls.some((c) => String(c[0]).includes('wajib'))).toBe(true)
    expect(apiMock).not.toHaveBeenCalledWith(
      expect.stringContaining('/decision'),
      expect.anything(),
    )
  })

  it('gagal memuat → pesan error', async () => {
    apiMock.mockRejectedValue(new Error('DB error'))
    const w = await mountView()
    expect(w.text()).toContain('DB error')
  })
})
