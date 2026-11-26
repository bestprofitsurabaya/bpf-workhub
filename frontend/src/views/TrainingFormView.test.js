import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import TrainingFormView from './TrainingFormView.vue'
import router from '../router/index'

const { apiMock } = vi.hoisted(() => ({ apiMock: vi.fn() }))
vi.mock('../api', () => ({ api: apiMock }))

const TOKEN = 'tok_sby_9f3a'
const NIK = '3509190102960003'
const DOB = '1996-02-01'
const NAMA = 'Bili Darnanto Susilo'

const STATUS_DAY1_EMPTY = { status: 'success', data: {
  nama: NAMA, next_day: 1, days: { 1: null, 2: null } } }
const STATUS_DAY1_DONE = { status: 'success', data: {
  nama: NAMA, next_day: 2,
  days: { 1: { attended_at: '2026-11-25 09:12:00', link_status: 'linked' },
          2: null } } }
const SUBMIT_OK = { status: 'success', data: {
  day: 1, link_status: 'linked',
  days: { 1: { attended_at: '2026-11-25 09:12:00', link_status: 'linked' },
          2: null } } }

function mountForm() {
  window.history.replaceState({}, '', `/app/training-form?token=${TOKEN}`)
  return mount(TrainingFormView)
}

async function isiIdentitas(w, nik = NIK) {
  await w.find('input[aria-label="NIK 16 digit"]').setValue(nik)
  await w.find('form.rp-check').trigger('submit')
  await flushPromises()
}

describe('TrainingFormView — absensi training 2 hari', () => {
  beforeEach(() => { vi.clearAllMocks() })
  afterEach(() => {
    window.history.replaceState({}, '', '/app/recruitment-portal')
  })

  it('mendaftarkan rute publik /training-form', () => {
    const route = router.resolve('/training-form')
    expect(route.name).toBe('training-form')
    expect(route.meta.public).toBe(true)
  })

  it('menampilkan Hari 1 dan Hari 2, Hari 2 terkunci bila Hari 1 kosong', async () => {
    apiMock.mockResolvedValue(STATUS_DAY1_EMPTY)
    const w = mountForm()
    await isiIdentitas(w)

    const hari1 = w.find('input[type="radio"][value="1"]')
    const hari2 = w.find('input[type="radio"][value="2"]')
    expect(hari1.exists()).toBe(true)
    expect(hari2.exists()).toBe(true)
    expect(hari2.attributes('disabled')).toBeDefined()
    expect(w.text()).toContain('Hari 2 terbuka setelah Hari 1 tercatat')
  })

  it('Hari 2 bisa dipilih setelah Hari 1 tercatat', async () => {
    apiMock.mockResolvedValue(STATUS_DAY1_DONE)
    const w = mountForm()
    await isiIdentitas(w)

    const hari2 = w.find('input[type="radio"][value="2"]')
    expect(hari2.attributes('disabled')).toBeUndefined()
    expect(w.text()).toContain('Hari 1 sudah tercatat')
  })

  it('setelah simpan menampilkan konfirmasi dan status kedua hari', async () => {
    apiMock.mockResolvedValueOnce(STATUS_DAY1_EMPTY)
      .mockResolvedValueOnce(SUBMIT_OK)
    const w = mountForm()
    await isiIdentitas(w)
    await w.find('input[type="checkbox"]').setValue(true)
    await w.find('form.rp-submit').trigger('submit')
    await flushPromises()

    expect(w.text()).toContain('Absensi Hari 1 tercatat')
    expect(w.find('.rp-success').exists()).toBe(true)
    expect(apiMock).toHaveBeenLastCalledWith(
      '/api/recruitment/training/attendance',
      expect.objectContaining({ method: 'POST' }))
    const body = apiMock.mock.calls.at(-1)[1].body
    expect(body).toMatchObject({ token: TOKEN, nik: NIK, day: 1,
                                 consent: true })
  })

  it('menampilkan pesan ramah saat NIK/tanggal lahir tidak cocok', async () => {
    apiMock.mockRejectedValue(new Error(
      'Data peserta tidak ditemukan. Periksa NIK dan tanggal lahir.'))
    const w = mountForm()
    await isiIdentitas(w)

    expect(w.find('[role="alert"]').text()).toContain('Periksa NIK')
    expect(w.find('.rp-status').exists()).toBe(false)
  })

  it('dengan sesi portal: status dicek otomatis tanpa input NIK/DOB', async () => {
    window.history.replaceState({}, '', `/app/training-form?token=${TOKEN}&s=ses-1`)
    apiMock.mockResolvedValue(STATUS_DAY1_EMPTY)
    const w = mount(TrainingFormView)
    await flushPromises()

    expect(w.find('input[aria-label="NIK 16 digit"]').exists()).toBe(false)
    expect(w.find('input[type="date"]').exists()).toBe(false)
    expect(apiMock).toHaveBeenCalledWith('/api/recruitment/training/status', {
      params: { token: TOKEN, s: 'ses-1' },
    })
    expect(w.text()).toContain(NAMA)
  })
})
