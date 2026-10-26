import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import AssignmentsView from './AssignmentsView.vue'
import { useAuthStore } from '../stores/auth'

const { apiMock } = vi.hoisted(() => ({ apiMock: vi.fn() }))
vi.mock('../api', () => ({ api: apiMock }))

const activeRow = {
  id: 1, driver_name: 'BUDI', nopol: 'L 1 AB', vehicle_type: 'AVANZA',
  bbm_type: 'PERTALITE', is_current: 1, confirmed_by_driver: 0,
  driver_notes: 'kaca depan retak',
}
const swapRow = {
  id: 5, nopol: 'L 1 AB', old_driver: 'BUDI', new_driver: 'RIVAN',
  category: 'driver_request', reason: 'cuti panjang', ga_name: 'GA Surabaya',
  created_at: '2026-10-20 08:00:00',
}

function mockApi() {
  apiMock.mockImplementation((path, opts = {}) => {
    if (path === '/api/assignments/active') return Promise.resolve([activeRow])
    if (path === '/api/assignments/unassigned') return Promise.resolve([])
    if (path === '/api/drivers') return Promise.resolve([{ name: 'RIVAN', is_active: 1 }, { name: 'CUT', is_active: 0 }])
    if (path === '/api/assignments/swap-history') return Promise.resolve([swapRow])
    if (path === '/api/assignments/swap') return Promise.resolve({ status: 'success', msg: 'L 1 AB ditukar: BUDI → RIVAN' })
    if (path === '/api/assignment-remark') return Promise.resolve({ status: 'success' })
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

describe('AssignmentsView (v2.73.0 — swap, konfirmasi, remark)', () => {
  beforeEach(() => { vi.clearAllMocks() })
  afterEach(() => { vi.unstubAllGlobals() })

  it('tabel aktif menampilkan status serah terima ⏳ dan catatan GA', async () => {
    const w = await mountView()
    expect(w.text()).toContain('Belum dikonfirmasi')
    expect(w.text()).toContain('kaca depan retak')
    w.unmount()
  })

  it('tab Riwayat Tukar Driver menampilkan baris BUDI → RIVAN', async () => {
    const w = await mountView()
    const tabBtn = w.findAll('button').find((b) => b.text().includes('Riwayat Tukar Driver'))
    expect(tabBtn).toBeTruthy()
    await tabBtn.trigger('click')
    await flushPromises()
    expect(w.text()).toContain('RIVAN')
    expect(w.text()).toContain('Permintaan driver')
    expect(w.text()).toContain('cuti panjang')
    w.unmount()
  })

  it('modal tukar driver kirim payload lengkap termasuk ga_name dari sesi', async () => {
    const w = await mountView()
    const openBtn = w.findAll('button').find((b) => b.text().includes('Tukar Driver'))
    await openBtn.trigger('click')
    await flushPromises()
    expect(w.text()).toContain('Tukar Driver')
    // pilih kendaraan & driver di dalam modal (bukan form Assign di atasnya)
    const modal = w.find('.modal-overlay')
    const selects = modal.findAll('select')
    await selects[0].setValue('L 1 AB') // nopol dari daftar aktif
    await selects[1].setValue('RIVAN') // driver baru
    await modal.find('input[placeholder*="cuti"]').setValue('driver cuti')
    const submit = modal.findAll('button').find((b) => b.text().includes('✅ Tukar'))
    expect(submit).toBeTruthy()
    await submit.trigger('click')
    await flushPromises()
    const call = apiMock.mock.calls.find((c) => c[0] === '/api/assignments/swap')
    expect(call[1].body).toEqual({
      nopol: 'L 1 AB', new_driver: 'RIVAN',
      category: 'driver_request', reason: 'driver cuti', ga_name: 'GA Surabaya',
    })
    w.unmount()
  })

  it('modal catatan kirim remark ke /api/assignment-remark', async () => {
    const w = await mountView()
    const remarkBtn = w.findAll('button').find((b) => b.text().includes('Catatan'))
    await remarkBtn.trigger('click')
    await flushPromises()
    expect(w.text()).toContain('Catatan Kendaraan — L 1 AB')
    // prefilled catatan lama
    expect(w.find('textarea').element.value).toBe('kaca depan retak')
    await w.find('textarea').setValue('kaca depan retak — bengkel 2 Nov')
    const save = w.findAll('button').find((b) => b.text().includes('Simpan'))
    await save.trigger('click')
    await flushPromises()
    const call = apiMock.mock.calls.find((c) => c[0] === '/api/assignment-remark')
    expect(call[1].body.nopol).toBe('L 1 AB')
    expect(call[1].body.remark).toContain('bengkel 2 Nov')
    w.unmount()
  })
})
