import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import OvertimeMeView from './OvertimeMeView.vue'

const { apiMock } = vi.hoisted(() => ({ apiMock: vi.fn() }))
vi.mock('../api', () => ({ api: apiMock }))
vi.mock('../stores/auth', () => ({
  useAuthStore: () => ({ role: 'security', user: { full_name: 'Budi Security', user_name: 'security_sby' } }),
}))
vi.mock('../utils/watermark', () => ({
  applyWatermark: vi.fn(), fileToDataUrl: vi.fn(),
}))
vi.mock('../utils/gps', () => ({
  getPosition: vi.fn(() => Promise.reject(new Error('no gps'))),
  detailedLocation: vi.fn(() => Promise.reject(new Error('no gps'))),
}))

const HISTORY = [
  { id: 1, display_id: 'OTL-A1', tanggal: '2026-09-12', waktu_mulai: '22:00', waktu_selesai: '23:00', keterangan: 'malam', submit_late: true, submit_deadline: '2026-09-13 23:00' },
  { id: 2, display_id: 'OTL-A2', tanggal: '2026-09-12', waktu_mulai: '08:00', waktu_selesai: '12:00', keterangan: 'siang', submit_late: false, submit_deadline: '2026-09-13 12:00' },
]

function apiRouter(overrides = {}) {
  return vi.fn(async (path, opts = {}) => {
    const url = path.split('?')[0]
    const table = {
      '/api/overtime/form-meta': { positions: ['OB', 'Security'], names: [], keterangan: [], submit_deadline_hours: 24 },
      '/api/overtime/mine': { data: HISTORY, total: HISTORY.length, submit_deadline_hours: 24 },
      ...overrides,
    }
    if (url in table) return table[url]
    throw new Error(`unmocked api path: ${path}`)
  })
}

async function mountView(overrides = {}) {
  apiMock.mockImplementation(apiRouter(overrides))
  const w = mount(OvertimeMeView)
  await flushPromises()
  return w
}

describe('OvertimeMeView — penanda terlambat-submit (v2.40.0)', () => {
  afterEach(() => vi.clearAllMocks())

  it('baris riwayat yang lewat batas diberi badge ⏳ Lewat batas + garis merah', async () => {
    const w = await mountView()
    const badgeRows = w.findAll('tr').filter(tr => tr.text().includes('⏳ Lewat batas'))
    expect(badgeRows.length).toBe(1)
    expect(badgeRows[0].text()).toContain('OTL-A1')
    // garis kiri merah pada baris terlambat
    expect(badgeRows[0].attributes('style')).toContain('#ef4444')
    // baris tepat waktu tanpa badge
    expect(w.text()).not.toContain('OTL-A2 ⏳')
  })

  it('ringkasan jumlah terlambat + batas jam dari form-meta', async () => {
    const w = await mountView()
    expect(w.text()).toContain('1 pengajuan lewat batas submit (24 jam setelah jam selesai OT)')
    // deadline diambil dari config
    const metaCalls = apiMock.mock.calls.filter(([p]) => p.startsWith('/api/overtime/form-meta'))
    expect(metaCalls.length).toBeGreaterThanOrEqual(1)
  })

  it('tanpa baris terlambat → tidak ada ringkasan', async () => {
    const w = await mountView({
      '/api/overtime/mine': { data: [HISTORY[1]], total: 1, submit_deadline_hours: 24 },
    })
    expect(w.text()).not.toContain('pengajuan lewat batas submit')
  })

  it('respons submit submit_late=true → kotak peringatan di panel sukses', async () => {
    const w = await mountView({
      '/api/overtime/me/submit': { status: 'success', display_id: 'OTL-X9', submit_late: true, msg: 'Overtime Security tercatat! No. OTL-X9' },
    })
    await w.find('input[type="date"]').setValue('2026-09-12')
    const times = w.findAll('input[type="time"]')
    await times[0].setValue('22:00')
    await times[1].setValue('23:00')
    await w.find('form').trigger('submit')
    await flushPromises()
    expect(w.text()).toContain('melewati batas 24 jam')
    expect(w.text()).toContain('diberi penanda khusus di sisi GA HR')
  })

  it('respons submit normal → tanpa kotak peringatan', async () => {
    const w = await mountView({
      '/api/overtime/me/submit': { status: 'success', display_id: 'OTL-X8', submit_late: false, msg: 'Overtime Security tercatat! No. OTL-X8' },
    })
    await w.find('input[type="date"]').setValue('2026-09-12')
    const times = w.findAll('input[type="time"]')
    await times[0].setValue('08:00')
    await times[1].setValue('12:00')
    await w.find('form').trigger('submit')
    await flushPromises()
    expect(w.text()).not.toContain('melewati batas 24 jam')
  })
})
