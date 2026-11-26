import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import RecruitmentPortalView from './RecruitmentPortalView.vue'
import RecruitmentTkdPanel from '../components/RecruitmentTkdPanel.vue'
import router from '../router/index'

const { apiMock } = vi.hoisted(() => ({ apiMock: vi.fn() }))
vi.mock('../api', () => ({ api: apiMock }))

const TOKEN = 'tok_sby_9f3a'
const NIK = '3573010101990001'
const SESSION = 'session-token'
const STEPS = ['CV', 'TRAINING', 'TKD', 'FIRSTWORK']
const LOOKUP_KNOWN = { status: 'success', known: true, can_continue: true, session_token: SESSION }
const LOOKUP_NEW = { status: 'success', known: false, can_continue: false, session_token: SESSION }
const SUMMARY = { status: 'success', data: {
  known: true, nama_masked: 'Budi S.', branch_code: 'SBY',
  branch_name: 'Surabaya', next_action: 'FIRSTWORK',
  stages: [
    { type: 'CV', status: 'SELESAI', can_start: true },
    { type: 'TRAINING', status: 'BELUM', can_start: true },
    { type: 'TKD', status: 'BELUM', can_start: true },
    { type: 'FIRSTWORK', status: 'BELUM', can_start: true },
  ],
} }

function card(w, step) {
  return w.find(`.rp-card[data-step="${step}"]`)
}

async function mountPortal(search = `?token=${TOKEN}`, lookup = LOOKUP_KNOWN, summary = SUMMARY) {
  window.history.replaceState({}, '', `/app/recruitment-portal${search}`)
  apiMock.mockImplementation((url) => {
    if (String(url).includes('/api/recruitment/lookup')) return Promise.resolve(lookup)
    if (String(url).includes('/api/recruitment/portal/summary')) return Promise.resolve(summary)
    return Promise.resolve({ status: 'success', data: {} })
  })
  const w = mount(RecruitmentPortalView)
  await flushPromises()
  return w
}

async function cek(w, nik = NIK) {
  await w.find('input[aria-label="NIK 16 digit"]').setValue(nik)
  await w.find('form.rp-check').trigger('submit')
  await flushPromises()
}

describe('RecruitmentPortalView — cek NIK sekali (Rilis C)', () => {
  beforeEach(() => { vi.clearAllMocks() })
  afterEach(() => { window.history.replaceState({}, '', '/app/recruitment-portal') })

  it('mendaftarkan rute publik /recruitment-portal', () => {
    const route = router.resolve('/recruitment-portal')
    expect(route.name).toBe('recruitment-portal')
    expect(route.meta.public).toBe(true)
  })

  it('hanya meminta NIK dan tidak menampilkan input tanggal lahir', async () => {
    const w = await mountPortal()
    expect(w.find('input[type="date"]').exists()).toBe(false)
    expect(w.find('#rp-nik').exists()).toBe(true)
    for (const step of STEPS) expect(card(w, step).exists()).toBe(true)
    expect(card(w, 'CV').attributes('data-locked')).toBe('false')
    for (const step of ['TRAINING', 'TKD', 'FIRSTWORK']) {
      expect(card(w, step).attributes('data-locked')).toBe('true')
    }
  })

  it('setelah cek memanggil lookup lalu summary dan menampilkan langkah berikutnya', async () => {
    const w = await mountPortal()
    await cek(w)
    expect(apiMock).toHaveBeenCalledWith('/api/recruitment/lookup', {
      params: { nik: NIK, token: TOKEN },
    })
    expect(apiMock).toHaveBeenCalledWith('/api/recruitment/portal/summary', {
      params: { token: SESSION },
    })
    expect(w.text()).toContain('Halo, Budi S.')
    expect(w.text()).toContain('Langkah berikutnya: FIRSTWORK')
    expect(card(w, 'CV').attributes('data-status')).toBe('SELESAI')
  })

  it('tautan form membawa token cabang dan token sesi', async () => {
    const w = await mountPortal()
    await cek(w)
    expect(card(w, 'CV').attributes('href')).toBe(`/app/cv-online-form?token=${TOKEN}&s=${SESSION}`)
    expect(card(w, 'FIRSTWORK').attributes('href')).toBe(`/app/first-work-form?token=${TOKEN}&s=${SESSION}`)
    expect(card(w, 'TRAINING').attributes('href')).toBe(`/app/training-form?token=${TOKEN}&s=${SESSION}`)
  })

  it('klik kartu TKD membuka panel dengan token sesi', async () => {
    const w = await mountPortal()
    await cek(w)
    await card(w, 'TKD').trigger('click')
    await flushPromises()
    const panel = w.findComponent(RecruitmentTkdPanel)
    expect(panel.exists()).toBe(true)
    expect(panel.props()).toMatchObject({ token: TOKEN, session: SESSION })
  })

  it('NIK baru menampilkan CTA CV dan mengunci tahap lain', async () => {
    const w = await mountPortal(`?token=${TOKEN}`, LOOKUP_NEW,
      { ...SUMMARY, data: { ...SUMMARY.data, known: false, next_action: 'CV',
        stages: SUMMARY.data.stages.map((s) => ({
          ...s, status: 'BELUM', can_start: s.type === 'CV' })) } })
    await cek(w)
    expect(w.text()).toContain('Mulai dari CV Online')
    expect(card(w, 'CV').attributes('data-locked')).toBe('false')
    expect(card(w, 'FIRSTWORK').attributes('data-locked')).toBe('true')
  })

  it('NIK bukan 16 digit tidak memanggil API', async () => {
    const w = await mountPortal()
    await cek(w, '12345')
    expect(w.text()).toContain('NIK wajib 16 digit angka.')
    expect(apiMock).not.toHaveBeenCalled()
  })

  it('tanpa token cabang menampilkan pesan dan tidak memanggil API', async () => {
    const w = await mountPortal('')
    await cek(w)
    expect(w.text()).toContain('Tautan portal cabang tidak valid')
    expect(apiMock).not.toHaveBeenCalled()
  })

  it('token juga diterima lewat parameter t', async () => {
    const w = await mountPortal('?t=tok_alt_1')
    await cek(w)
    expect(card(w, 'CV').attributes('href')).toContain('token=tok_alt_1')
  })

  it('gagal lookup menampilkan pesan error', async () => {
    const w = await mountPortal()
    apiMock.mockRejectedValueOnce(new Error('Terlalu banyak pengecekan. Coba lagi sebentar.'))
    await cek(w)
    expect(w.text()).toContain('Terlalu banyak pengecekan')
    expect(card(w, 'FIRSTWORK').attributes('data-locked')).toBe('true')
  })
})
