import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import AssignmentsView from './AssignmentsView.vue'
import { useAuthStore } from '../stores/auth'

const { apiMock } = vi.hoisted(() => ({ apiMock: vi.fn() }))
vi.mock('../api', () => ({ api: apiMock }))

const pendingRow = {
  id: 11, request_code: 'SWR-20261123-0011', swap_type: 'exchange',
  requester_driver: 'BUDI', requester_nopol: 'L 1 AB',
  target_driver: 'RIVAN', target_nopol: 'L 2 CD',
  category: 'driver_request', reason: 'ban depan sudah aus',
  status: 'pending', created_at: '2026-11-23 08:00:00',
}
const moveRow = {
  id: 12, request_code: 'SWR-20261123-0012', swap_type: 'move',
  requester_driver: 'CUT', requester_nopol: 'L 3 EF',
  target_driver: null, target_nopol: 'L 9 ZZ',
  category: 'mutasi', reason: 'mutasi cabang',
  status: 'pending', created_at: '2026-11-23 09:00:00',
}

let decideImpl = null

function mockApi() {
  apiMock.mockImplementation((path, opts = {}) => {
    if (path === '/api/assignments/active') return Promise.resolve([])
    if (path === '/api/assignments/unassigned') return Promise.resolve([])
    if (path === '/api/drivers') return Promise.resolve([])
    if (path === '/api/assignments/swap-history') return Promise.resolve([])
    if (path === '/api/assignments/swap-requests') return Promise.resolve([pendingRow, moveRow])
    if (path.endsWith('/approve') || path.endsWith('/reject')) {
      if (decideImpl) return decideImpl(path, opts)
      return Promise.resolve({ status: 'success' })
    }
    return Promise.resolve({})
  })
}

async function mountView() {
  const pinia = createPinia()
  setActivePinia(pinia)
  const auth = useAuthStore()
  auth.user = { role: 'ga', full_name: 'GA Surabaya', user_name: 'ga_sby' }
  mockApi()
  const w = mount(AssignmentsView)
  await flushPromises()
  await flushPromises()
  return w
}

async function openTab(w) {
  const btn = w.findAll('button').find((b) => b.text().includes('Pengajuan'))
  expect(btn).toBeTruthy()
  await btn.trigger('click')
  await flushPromises()
}

describe('AssignmentsView — pengajuan driver (v2.132.0)', () => {
  beforeEach(() => { vi.clearAllMocks(); decideImpl = null })
  afterEach(() => { vi.unstubAllGlobals() })

  it('tab Pengajuan menampilkan badge jumlah dan kedua jenis pengajuan', async () => {
    const w = await mountView()
    const btn = w.findAll('button').find((b) => b.text().includes('Pengajuan'))
    expect(btn.text()).toContain('2')
    await openTab(w)
    expect(w.text()).toContain('SWR-20261123-0011')
    expect(w.text()).toContain('🔄 Tukar')
    expect(w.text()).toContain('➡️ Pindah')
    expect(w.text()).toContain('kosong')
    expect(w.text()).toContain('ban depan sudah aus')
    w.unmount()
  })

  it('Setujui mengirim acknowledge_supersede=false bila tidak ada konflik', async () => {
    const w = await mountView()
    await openTab(w)
    await w.findAll('button').filter((b) => b.text() === 'Setujui').at(0).trigger('click')
    const modal = w.find('[aria-label="Keputusan pengajuan"]')
    expect(modal.exists()).toBe(true)
    expect(modal.text()).toContain('Kedua kendaraan langsung bertukar')
    await modal.findAll('button').find((b) => b.text().includes('Setujui')).trigger('click')
    await flushPromises()
    const call = apiMock.mock.calls.find((c) => c[0] === '/api/assignments/swap-requests/11/approve')
    expect(call[1].body).toEqual({ acknowledge_supersede: false })
    w.unmount()
  })

  it('konflik serah terima memunculkan centang, lalu dikirim true', async () => {
    let first = true
    decideImpl = (path) => {
      if (first) {
        first = false
        const err = new Error('Ada serah terima sebelumnya yang belum selesai')
        err.status = 409
        err.data = { code: 'supersede_required', conflicts: [3] }
        return Promise.reject(err)
      }
      return Promise.resolve({ status: 'success' })
    }
    const w = await mountView()
    await openTab(w)
    await w.findAll('button').filter((b) => b.text() === 'Setujui').at(0).trigger('click')
    let modal = w.find('[aria-label="Keputusan pengajuan"]')
    await modal.findAll('button').find((b) => b.text().includes('Setujui')).trigger('click')
    await flushPromises()
    modal = w.find('[aria-label="Keputusan pengajuan"]')
    expect(modal.text()).toContain('belum selesai')
    const approveBtn = modal.findAll('button').find((b) => b.text().includes('Setujui'))
    expect(approveBtn.attributes('disabled')).toBeDefined()
    await modal.find('input[type="checkbox"]').setValue(true)
    await approveBtn.trigger('click')
    await flushPromises()
    const calls = apiMock.mock.calls.filter((c) => c[0].endsWith('/approve'))
    expect(calls).toHaveLength(2)
    expect(calls[1][1].body.acknowledge_supersede).toBe(true)
    w.unmount()
  })

  it('Tolak wajib catatan dan mengirim note', async () => {
    const w = await mountView()
    await openTab(w)
    await w.findAll('button').filter((b) => b.text() === 'Tolak').at(0).trigger('click')
    const modal = w.find('[aria-label="Keputusan pengajuan"]')
    const rejectBtn = modal.findAll('button').find((b) => b.text().includes('Tolak'))
    expect(rejectBtn.attributes('disabled')).toBeDefined()
    await modal.find('textarea').setValue('kendaraan masih dipakai shift malam')
    await rejectBtn.trigger('click')
    await flushPromises()
    const call = apiMock.mock.calls.find((c) => c[0] === '/api/assignments/swap-requests/11/reject')
    expect(call[1].body).toEqual({ note: 'kendaraan masih dipakai shift malam' })
    w.unmount()
  })
})
