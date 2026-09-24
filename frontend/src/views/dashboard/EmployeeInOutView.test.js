import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import EmployeeInOutView from './EmployeeInOutView.vue'

// realtimeMock harus reaktif (Vue reactive) supaya watch() di komponen terpicu.
const { apiMock, realtimeMock } = await vi.hoisted(async () => {
  const { reactive } = await import('vue')
  return {
    apiMock: vi.fn(),
    realtimeMock: reactive({ receptionistSeq: 0 }),
  }
})
vi.mock('../../api', () => ({ api: apiMock }))
vi.mock('../../stores/stepup', () => ({
  useStepupStore: () => ({
    open: false, label: '', busy: false, err: '',
    require: (fn) => fn(),
    submit: vi.fn(),
    cancel: vi.fn(),
  }),
}))
vi.mock('../../stores/realtime', () => ({
  useRealtimeStore: () => realtimeMock,
}))

const LIST = [
  { id: 1, nama: 'BUDI', jabatan: 'OB', pergi: 1, waktu_pergi: '2026-09-23 08:15:00', datang: 0, waktu_datang: null, keterangan: 'survei', source: 'app', locked: true },
  { id: 2, nama: 'SITI', jabatan: 'STAFF', pergi: 1, waktu_pergi: '2026-09-23 09:00:00', datang: 1, waktu_datang: '2026-09-23 10:00:00', keterangan: 'antar dokumen', source: 'sheet', locked: false },
  { id: 3, nama: 'YOGA', jabatan: 'ADMIN', pergi: 0, waktu_pergi: null, datang: 0, waktu_datang: null, keterangan: 'Registrasi karyawan baru', source: 'registrasi', locked: true },
]
const PAYLOAD = {
  status: 'success', data: LIST, mode: 'hybrid', last_sync: 'x',
  roster: [{ nama: 'BUDI', jabatan: 'OB', di_luar: true }, { nama: 'SITI', jabatan: 'STAFF', di_luar: false }],
  stats: { total: 3, out_now: 1, pergi_today: 2, datang_today: 1, app_today: 1 },
}

function mockApi() {
  apiMock.mockImplementation((path, opts) => {
    if (path === '/api/receptionist/inout' && (!opts || !opts.method)) {
      return Promise.resolve(PAYLOAD)
    }
    if (path === '/api/receptionist/realtime-sync') return Promise.resolve({ synced: false })
    return Promise.resolve({ status: 'success', msg: 'ok' })
  })
}

async function mountView() {
  mockApi()
  const w = mount(EmployeeInOutView)
  await flushPromises()
  return w
}

describe('EmployeeInOutView', () => {
  beforeEach(() => { vi.clearAllMocks() })

  it('menampilkan daftar in-out dengan badge sumber & statistik', async () => {
    const w = await mountView()
    expect(w.text()).toContain('BUDI')
    expect(w.text()).toContain('SITI')
    expect(w.text()).toContain('YOGA')
    expect(w.text()).toContain('📱 App')
    expect(w.text()).toContain('🆕 Karyawan')
    expect(w.text()).toContain('📄 Sheet')
    expect(w.text()).toContain('Masih di Luar')
  })

  it('mode hybrid: tombol Keluar & Masuk tampil; mode sheet: tersembunyi + peringatan', async () => {
    const w = await mountView()
    expect(w.text()).toContain('📤 Keluar')
    expect(w.text()).toContain('📥 Masuk')

    apiMock.mockImplementation((path, opts) => {
      if (path === '/api/receptionist/inout' && (!opts || !opts.method)) {
        return Promise.resolve({ ...PAYLOAD, mode: 'sheet' })
      }
      return Promise.resolve({ synced: false })
    })
    const w2 = mount(EmployeeInOutView)
    await flushPromises()
    expect(w2.text()).not.toContain('📤 Keluar')
    expect(w2.text()).toContain('read-only')
  })

  it('catat keluar mengirim POST dengan arah keluar', async () => {
    const w = await mountView()
    await w.findAll('button').find((b) => b.text().includes('📤 Keluar')).trigger('click')
    await w.find('input[placeholder*="Ketik atau pilih"]').setValue('BUDI')
    await w.findAll('button').find((b) => b.text().includes('Catat Keluar')).trigger('click')
    await flushPromises()
    const post = apiMock.mock.calls.find((c) => c[0] === '/api/receptionist/inout' && c[1]?.method === 'POST')
    expect(post).toBeTruthy()
    expect(post[1].body).toEqual(expect.objectContaining({ nama: 'BUDI', arah: 'keluar' }))
  })

  it('roster chip: karyawan masih di luar default catat masuk', async () => {
    const w = await mountView()
    const chips = w.findAll('.roster-chip')
    await chips[0].trigger('click') // BUDI — di_luar: true
    await flushPromises()
    expect(w.text()).toContain('Catat Masuk (Kembali)')
  })

  it('hanya catatan app/registrasi yang punya tombol edit & hapus', async () => {
    const w = await mountView()
    const editBtns = w.findAll('button[title*="Edit catatan"]')
    const delBtns = w.findAll('button[title*="Hapus catatan"]')
    expect(editBtns.length).toBe(2) // BUDI (app) + YOGA (registrasi)
    expect(delBtns.length).toBe(2)
  })

  it('edit memanggil PATCH via stepup.require dengan body terisi', async () => {
    vi.stubGlobal('confirm', vi.fn(() => true))
    const w = await mountView()
    await w.findAll('button[title*="Edit catatan"]')[0].trigger('click')
    await flushPromises()
    expect(w.text()).toContain('Edit Catatan — BUDI')
    await w.findAll('button').find((b) => b.text().includes('💾 Simpan')).trigger('click')
    await flushPromises()
    const patch = apiMock.mock.calls.find((c) => c[0] === '/api/receptionist/inout/1' && c[1]?.method === 'PATCH')
    expect(patch).toBeTruthy()
    expect(patch[1].body).toEqual(expect.objectContaining({ nama: 'BUDI', pergi: 1 }))
    vi.unstubAllGlobals()
  })

  it('hapus memanggil DELETE dengan konfirmasi', async () => {
    vi.stubGlobal('confirm', vi.fn(() => true))
    const w = await mountView()
    await w.findAll('button[title*="Hapus catatan"]')[0].trigger('click')
    await flushPromises()
    expect(global.confirm).toHaveBeenCalled()
    expect(apiMock).toHaveBeenCalledWith('/api/receptionist/inout/1', { method: 'DELETE' })
    vi.unstubAllGlobals()
  })

  it('modal riwayat menarik events endpoint', async () => {
    mockApi()
    apiMock.mockImplementation((path, opts) => {
      if (String(path).includes('/events')) return Promise.resolve({ data: [{ id: 1, event_type: 'app_keluar', event_at: '2026-09-23 08:15:00', actor_name: 'R' }] })
      if (path === '/api/receptionist/inout' && (!opts || !opts.method)) return Promise.resolve(PAYLOAD)
      return Promise.resolve({ synced: false })
    })
    const w = mount(EmployeeInOutView)
    await flushPromises()
    await w.findAll('button[title*="Riwayat"]')[0].trigger('click')
    await flushPromises()
    expect(apiMock).toHaveBeenCalledWith('/api/receptionist/inout/1/events')
    expect(w.text()).toContain('Catat keluar')
  })

  it('realtime: receptionistSeq bertambah → load ulang otomatis', async () => {
    const w = await mountView()
    const callsBefore = apiMock.mock.calls.filter((c) => c[0] === '/api/receptionist/inout').length
    realtimeMock.receptionistSeq++
    await flushPromises()
    await flushPromises()
    const callsAfter = apiMock.mock.calls.filter((c) => c[0] === '/api/receptionist/inout').length
    expect(callsAfter).toBeGreaterThan(callsBefore)
  })

  it('buka halaman memicu realtime-sync (pull on-demand)', async () => {
    await mountView()
    expect(apiMock).toHaveBeenCalledWith('/api/receptionist/realtime-sync', { method: 'POST' })
  })
})
