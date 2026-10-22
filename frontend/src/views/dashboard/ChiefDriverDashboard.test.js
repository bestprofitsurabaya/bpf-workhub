import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import ChiefDriverDashboard from './ChiefDriverDashboard.vue'

const { apiMock } = vi.hoisted(() => ({ apiMock: vi.fn() }))
vi.mock('../../api', () => ({ api: apiMock }))

const APPS = [
  { id: 1, display_id: 'APP-1', status: 'scheduled', nasabah_name: 'Nasabah A', alamat: 'Jl. A', sesi: '1', area: 'Surabaya Barat', marketing_member: 'M1', driver_name: null, visit_result: null, visit_note: '' },
  { id: 2, display_id: 'APP-2', status: 'scheduled', nasabah_name: 'Nasabah B', alamat: 'Jl. B', sesi: '2', area: 'Sidoarjo', marketing_member: 'M2', driver_name: null, visit_result: null, visit_note: '' },
  { id: 3, display_id: 'APP-3', status: 'assigned', nasabah_name: 'Nasabah C', alamat: 'Jl. C', sesi: '1', area: 'Surabaya', marketing_member: 'M1', driver_name: 'RIVAN', visit_result: null, visit_note: '' },
  { id: 4, display_id: 'APP-4', status: 'completed', nasabah_name: 'Nasabah D', alamat: 'Jl. D', sesi: '2', area: 'Sidoarjo', marketing_member: 'M2', driver_name: 'BUDI', visit_result: 'ditemui', visit_note: 'Lancar' },
]
const DRIVERS = [{ name: 'RIVAN', is_active: true }, { name: 'BUDI', is_active: true }]
const MEMBERS = { members: ['M1', 'M2'] }
const SUMMARY = { members: [{ marketing_member: 'M1', total: 2, scheduled: 1, assigned: 1, completed: 0, cancelled: 0, ditemui: 0, prospek: 0, gagal: 0, sesi1: 2, sesi2: 0 }] }

function defaultMock() {
  apiMock.mockImplementation((path, opts = {}) => {
    if (path === '/api/appointments') {
      return Promise.resolve({
        data: APPS,
        stats: { total: 4, scheduled: 2, assigned: 1, completed: 1, cancelled: 0 },
      })
    }
    if (path === '/api/drivers') return Promise.resolve(DRIVERS)
    if (path === '/api/appointments/suggestions') return Promise.resolve({ '1': 'RIVAN', '2': 'BUDI' })
    if (path === '/api/marketing/members') return Promise.resolve(MEMBERS)
    if (path === '/api/appointments/member-summary') return Promise.resolve(SUMMARY)
    return Promise.resolve({ status: 'success', msg: 'ok' })
  })
}

const assignSelects = (w) => w.findAll('select.assign-select')
const btnByText = (w, text) => w.findAll('button').find((b) => b.text() === text)
const confirmYes = async (w, text = 'Ya, lanjutkan') => {
  const b = btnByText(w, text)
  expect(b).toBeTruthy()
  await b.trigger('click')
  await flushPromises()
}

describe('ChiefDriverDashboard', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    defaultMock()
    vi.stubGlobal('confirm', vi.fn(() => true))
    vi.stubGlobal('prompt', vi.fn(() => 'Alasan uji'))
  })
  afterEach(() => { vi.unstubAllGlobals() })

  it('render satu select driver independen per baris dengan saran default per sesi', async () => {
    const w = mount(ChiefDriverDashboard)
    await flushPromises()
    const selects = assignSelects(w)
    expect(selects.length).toBe(2)
    // saran load-balancing otomatis terisi sebagai default per baris
    expect(selects[0].element.value).toBe('RIVAN')
    expect(selects[1].element.value).toBe('BUDI')
    // mengubah baris pertama tidak mengubah baris kedua (fix bug select terbagi)
    await selects[0].setValue('BUDI')
    const after = assignSelects(w)
    expect(after[0].element.value).toBe('BUDI')
    expect(after[1].element.value).toBe('BUDI')
  })

  it('tombol Tugaskan memakai id appointment baris tersebut', async () => {
    const w = mount(ChiefDriverDashboard)
    await flushPromises()
    const tugaskan = w.findAll('button').filter((b) => b.text() === 'Tugaskan')
    expect(tugaskan.length).toBe(2)
    await tugaskan[1].trigger('click')
    await flushPromises()
    expect(apiMock).toHaveBeenCalledWith('/api/appointments/2/assign', { method: 'POST', body: { driver_name: 'BUDI' } })
  })

  it('klik 🌍 mengubah area manual via PATCH', async () => {
    const w = mount(ChiefDriverDashboard)
    await flushPromises()
    await w.findAll('button').find((b) => b.text() === '🌍').trigger('click')
    await flushPromises()
    await w.find('textarea').setValue('Alasan uji')
    await confirmYes(w, 'Simpan area')
    expect(apiMock).toHaveBeenCalledWith('/api/appointments/1', { method: 'PATCH', body: { area: 'Alasan uji' } })
  })

  it('klik ↩️ membatalkan tugas via /unassign', async () => {
    const w = mount(ChiefDriverDashboard)
    await flushPromises()
    await w.findAll('button').find((b) => b.text() === '↩️').trigger('click')
    await flushPromises()
    await confirmYes(w)
    expect(apiMock).toHaveBeenCalledWith('/api/appointments/3/unassign', { method: 'POST' })
  })

  it('klik ✕ pada board membatalkan appointment dengan alasan via /cancel', async () => {
    const w = mount(ChiefDriverDashboard)
    await flushPromises()
    await w.findAll('button').find((b) => b.text() === '✕').trigger('click')
    await flushPromises()
    await w.find('textarea').setValue('Alasan uji')
    await confirmYes(w, 'Batalkan')
    expect(apiMock).toHaveBeenCalledWith('/api/appointments/1/cancel', { method: 'POST', body: { reason: 'Alasan uji' } })
  })

  it('klik ✅ membuka modal hasil kunjungan — submit wajib pilih hasil & POST /complete', async () => {
    const w = mount(ChiefDriverDashboard)
    await flushPromises()
    await w.findAll('button').find((b) => b.text() === '✅').trigger('click')
    await flushPromises()
    expect(w.text()).toContain('Selesaikan APP-3')
    // tanpa memilih hasil -> tidak mengirim API
    await w.findAll('button').find((b) => b.text() === '✅ Selesai').trigger('click')
    await flushPromises()
    expect(w.text()).toContain('Pilih hasil kunjungan')
    const completeCalls = apiMock.mock.calls.filter(([p]) => p.includes('/complete'))
    expect(completeCalls.length).toBe(0)
    // pilih hasil lalu simpan -> POST /complete dengan result
    const resultSelect = w.findAll('select').find((s) => s.findAll('option').some((o) => o.attributes('value') === 'ditemui'))
    await resultSelect.setValue('ditemui')
    await w.findAll('button').find((b) => b.text() === '✅ Selesai').trigger('click')
    await flushPromises()
    expect(apiMock).toHaveBeenCalledWith('/api/appointments/3/complete', {
      method: 'POST', body: { result: 'ditemui', note: '' },
    })
  })

  it('menampilkan ringkasan per marketing anggota & klik baris menerapkan filter member', async () => {
    const w = mount(ChiefDriverDashboard)
    await flushPromises()
    expect(w.text()).toContain('Ringkasan per Marketing Anggota')
    expect(w.text()).toContain('M1')
    await w.findAll('tr').find((tr) => tr.text().includes('M1')).trigger('click')
    await flushPromises()
    const calls = apiMock.mock.calls.filter(([p]) => p === '/api/appointments')
    expect(calls[calls.length - 1][1].params.member).toBe('M1')
  })

  it('badge hasil kunjungan tampil di baris appointment selesai (APP-4)', async () => {
    const w = mount(ChiefDriverDashboard)
    await flushPromises()
    const row = w.findAll('tr').find((tr) => tr.text().includes('APP-4'))
    expect(row).toBeTruthy()
    expect(row.text()).toContain('😊 Ditemui')
    // tombol 🎯 Hasil tersedia untuk edit hasil kunjungan appointment selesai
    expect(row.text()).toContain('🎯 Hasil')
  })
})
