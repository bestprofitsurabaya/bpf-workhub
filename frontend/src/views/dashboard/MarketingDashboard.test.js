import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import MarketingDashboard from './MarketingDashboard.vue'

const { apiMock } = vi.hoisted(() => ({ apiMock: vi.fn() }))
vi.mock('../../api', () => ({ api: apiMock }))

const APPS = {
  data: [
    { id: 1, display_id: 'APP-1', nasabah_name: 'Nasabah A', marketing_member: 'M1', nasabah_phone: '0811', sesi: '1', area: 'Surabaya Barat', alamat: 'Jl. Darmo 10', notes: '', status: 'scheduled', visit_result: null },
  ],
  stats: { total: 1, sesi1: 1, sesi2: 0, completed: 0 },
}

async function mountView() {
  apiMock.mockImplementation((path) => {
    if (path === '/api/appointments') return Promise.resolve(APPS)
    return Promise.resolve({ status: 'success', msg: 'Tersimpan' })
  })
  const w = mount(MarketingDashboard)
  await flushPromises()
  return w
}

describe('MarketingDashboard', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.stubGlobal('confirm', vi.fn(() => true))
    vi.stubGlobal('prompt', vi.fn(() => 'Alasan uji'))
  })
  afterEach(() => { vi.unstubAllGlobals() })

  it('menampilkan form input + statistik + daftar appointment hari ini', async () => {
    const w = await mountView()
    expect(w.text()).toContain('Input Appointment Baru')
    expect(w.text()).toContain('Total Hari Ini')
    expect(w.text()).toContain('Sesi 1')
    expect(w.text()).toContain('Nasabah A')
    expect(w.text()).toContain('APP-1')
  })

  it('submit valid memanggil POST /api/appointments dengan array form', async () => {
    const w = await mountView()
    await w.find('input[placeholder="Nama nasabah"]').setValue('Nasabah Baru')
    await w.find('input[placeholder="Anggota tim yang memprospek"]').setValue('Yusie')
    await w.find('input[placeholder="Alamat calon nasabah"]').setValue('Jl. Darmo 10')
    await w.find('form').trigger('submit.prevent')
    await flushPromises()
    expect(apiMock).toHaveBeenCalledWith('/api/appointments', {
      method: 'POST',
      body: expect.arrayContaining([expect.objectContaining({ nasabah_name: 'Nasabah Baru', marketing_member: 'Yusie' })]),
    })
  })

  it('submit tanpa nama nasabah menampilkan peringatan dan tidak memanggil API', async () => {
    const w = await mountView()
    await w.find('form').trigger('submit.prevent')
    await flushPromises()
    expect(w.text()).toContain('wajib diisi')
    const posts = apiMock.mock.calls.filter((c) => c[0] === '/api/appointments' && c[1]?.method === 'POST')
    expect(posts.length).toBe(0)
  })

  it('klik ✏️ Edit membuka modal dan PATCH /api/appointments/<id> dengan data form', async () => {
    const w = await mountView()
    await w.findAll('button').find((b) => b.text().includes('✏️ Edit')).trigger('click')
    await flushPromises()
    expect(w.text()).toContain('Edit APP-1')
    // form modal = form ke-2 di dokumen (form pertama form input baru)
    await w.findAll('form')[1].trigger('submit.prevent')
    await flushPromises()
    expect(apiMock).toHaveBeenCalledWith('/api/appointments/1', {
      method: 'PATCH',
      body: expect.objectContaining({ nasabah_name: 'Nasabah A', marketing_member: 'M1' }),
    })
  })

  it('klik ✕ Batal membatalkan appointment dengan alasan via /cancel', async () => {
    const w = await mountView()
    await w.findAll('button').find((b) => b.text().includes('✕ Batal')).trigger('click')
    await flushPromises()
    expect(global.prompt).toHaveBeenCalled()
    expect(apiMock).toHaveBeenCalledWith('/api/appointments/1/cancel', { method: 'POST', body: { reason: 'Alasan uji' } })
  })

  it('tab ✅ Selesai memuat riwayat dari /api/appointments/history', async () => {
    apiMock.mockImplementation((path) => {
      if (path === '/api/appointments') return Promise.resolve(APPS)
      if (path === '/api/appointments/history') return Promise.resolve({
        data: [
          { id: 9, display_id: 'APP-9', nasabah_name: 'Nasabah Lama', marketing_member: 'M1', appointment_date: '2026-09-01', sesi: '1', area: 'Surabaya Barat', driver_name: 'Akhad', visit_result: 'ditemui' },
        ],
      })
      return Promise.resolve({ status: 'success', msg: 'Tersimpan' })
    })
    const w = mount(MarketingDashboard)
    await flushPromises()
    // riwayat dimuat saat mount (endpoint khusus marketing, bukan /completed)
    expect(apiMock).toHaveBeenCalledWith('/api/appointments/history', { params: { limit: 50 } })
    expect(apiMock).not.toHaveBeenCalledWith('/api/appointments/completed', expect.anything())
    // klik tab Selesai → baris riwayat tampil
    await w.findAll('button').find((b) => b.text().includes('Selesai')).trigger('click')
    await flushPromises()
    expect(w.text()).toContain('Nasabah Lama')
    expect(w.text()).toContain('APP-9')
  })
})
