import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import DriverProfileSheet from './DriverProfileSheet.vue'

const { apiMock } = vi.hoisted(() => ({ apiMock: vi.fn() }))
vi.mock('../api', () => ({ api: apiMock }))

const ME = { driver: 'RIVAN', nopol: 'L 1 AB', vehicle_type: 'AVANZA' }

function ctx(over = {}) {
  return {
    me: ME,
    free_vehicles: [{ nopol: 'L 9 ZZ', vehicle_type: 'AVANZA' }],
    partners: [{ driver_name: 'BUDI', nopol: 'L 2 CD', vehicle_type: 'INNOVA' }],
    requests: [],
    ...over,
  }
}

function mockApi(data) {
  apiMock.mockImplementation((path) => {
    if (path === '/api/assignments/swap-context') return Promise.resolve(data)
    return Promise.resolve({ status: 'success' })
  })
}

async function mountSheet(data) {
  mockApi(data)
  const w = mount(DriverProfileSheet, { props: { modelValue: true } })
  await flushPromises()
  await flushPromises()
  return w
}

describe('DriverProfileSheet', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    localStorage.clear()
    sessionStorage.clear()
  })
  afterEach(() => { vi.unstubAllGlobals() })

  it('menampilkan kendaraan kosong dan kendaraan ber-driver', async () => {
    const w = await mountSheet(ctx())
    expect(w.text()).toContain('Kendaraan saya')
    expect(w.text()).toContain('L 1 AB')
    expect(w.text()).toContain('Kendaraan kosong (1)')
    expect(w.text()).toContain('L 9 ZZ')
    expect(w.text()).toContain('Kendaraan dengan driver (1)')
    expect(w.text()).toContain('BUDI')
    expect(w.findAll('button').some((b) => b.text() === 'Ambil')).toBe(true)
    expect(w.findAll('button').some((b) => b.text() === 'Tukar')).toBe(true)
    w.unmount()
  })

  it('driver tanpa assignment melihat empty state, bukan layar kosong', async () => {
    const w = await mountSheet(ctx({ me: null, free_vehicles: [], partners: [] }))
    expect(w.text()).toContain('belum punya kendaraan aktif')
    expect(w.findAll('button').some((b) => b.text() === 'Ambil')).toBe(false)
    expect(w.text()).not.toContain('Kendaraan kosong (')
    w.unmount()
  })

  it('tombol Ambil mengirim pengajuan pindah (move)', async () => {
    const w = await mountSheet(ctx())
    await w.findAll('button').find((b) => b.text() === 'Ambil').trigger('click')
    expect(w.text()).toContain('Ambil Kendaraan')
    const submit = w.findAll('button').find((b) => b.text() === 'Ajukan')
    expect(submit.attributes('disabled')).toBeDefined()
    await w.find('textarea').setValue('butuh unit lebih besar')
    await submit.trigger('click')
    await flushPromises()
    const call = apiMock.mock.calls.find((c) => c[0] === '/api/assignments/swap-requests')
    expect(call[1].method).toBe('POST')
    expect(call[1].body.swap_type).toBe('move')
    expect(call[1].body.target_nopol).toBe('L 9 ZZ')
    expect(call[1].body.reason).toBe('butuh unit lebih besar')
    expect(call[1].body.target_driver).toBeUndefined()
    w.unmount()
  })

  it('tombol Tukar mengirim pengajuan exchange dengan rekan', async () => {
    const w = await mountSheet(ctx())
    await w.findAll('button').find((b) => b.text() === 'Tukar').trigger('click')
    const submit = w.findAll('button').find((b) => b.text() === 'Ajukan')
    await w.find('textarea').setValue('ban depan sudah aus')
    await submit.trigger('click')
    await flushPromises()
    const call = apiMock.mock.calls.find((c) => c[0] === '/api/assignments/swap-requests')
    expect(call[1].body.swap_type).toBe('exchange')
    expect(call[1].body.target_driver).toBe('BUDI')
    expect(call[1].body.target_nopol).toBe('L 2 CD')
    w.unmount()
  })

  it('pengajuan pending milik sendiri bisa dibatalkan', async () => {
    const w = await mountSheet(ctx({
      requests: [{
        id: 7, request_code: 'SWR-1', swap_type: 'move', status: 'pending',
        requester_driver: 'RIVAN', requester_nopol: 'L 1 AB',
        target_driver: null, target_nopol: 'L 9 ZZ', reason: 'butuh unit',
      }],
    }))
    await w.findAll('button').find((b) => b.text() === 'Batalkan').trigger('click')
    await flushPromises()
    const call = apiMock.mock.calls.find((c) => c[0] === '/api/assignments/swap-requests/7/cancel')
    expect(call[1].method).toBe('POST')
    w.unmount()
  })

  it('kirim bukti serah terima memakai FormData odometer + foto', async () => {
    localStorage.setItem('bpf_csrf', 'tok')
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true, json: () => Promise.resolve({ status: 'completed' }),
    })
    vi.stubGlobal('fetch', fetchMock)
    const w = await mountSheet(ctx({
      requests: [{
        id: 5, request_code: 'SWR-5', swap_type: 'exchange', status: 'approved',
        requester_driver: 'RIVAN', requester_nopol: 'L 1 AB',
        target_driver: 'BUDI', target_nopol: 'L 9 ZZ',
        requester_photo: null, target_photo: null, reason: 'tukar',
      }],
    }))
    expect(w.text()).toContain('Serah terima: L 9 ZZ')
    await w.find('input[type="number"]').setValue('48210')
    const file = new File(['x'], 'odo.jpg', { type: 'image/jpeg' })
    const fileInput = w.find('input[type="file"]')
    Object.defineProperty(fileInput.element, 'files', { value: [file] })
    await fileInput.trigger('change')
    await w.findAll('button').find((b) => b.text().includes('Kirim Bukti')).trigger('click')
    await flushPromises()
    expect(fetchMock).toHaveBeenCalledTimes(1)
    const [url, opts] = fetchMock.mock.calls[0]
    expect(url).toBe('/api/assignments/swap-requests/5/handover')
    expect(opts.method).toBe('POST')
    expect(opts.headers['X-CSRF-Token']).toBe('tok')
    expect(opts.body).toBeInstanceOf(FormData)
    expect(opts.body.get('odometer')).toBe('48210')
    expect(opts.body.get('photo').name).toBe('odo.jpg')
    w.unmount()
  })

  it('sisi yang sudah mengirim bukti tidak menampilkan form lagi', async () => {
    const w = await mountSheet(ctx({
      requests: [{
        id: 5, swap_type: 'exchange', status: 'approved',
        requester_driver: 'RIVAN', requester_nopol: 'L 1 AB',
        target_driver: 'BUDI', target_nopol: 'L 9 ZZ',
        requester_photo: 'SWAP_L_9_ZZ.jpg', target_photo: null, reason: 'tukar',
      }],
    }))
    expect(w.find('input[type="file"]').exists()).toBe(false)
    expect(w.text()).toContain('Disetujui')
    w.unmount()
  })
})
