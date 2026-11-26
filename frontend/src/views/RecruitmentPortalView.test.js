import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import RecruitmentPortalView from './RecruitmentPortalView.vue'
import RecruitmentTkdPanel from '../components/RecruitmentTkdPanel.vue'
import router from '../router/index'

const { apiMock } = vi.hoisted(() => ({ apiMock: vi.fn() }))
vi.mock('../api', () => ({ api: apiMock }))

const TOKEN = 'tok_sby_9f3a'
const NIK = '3573010101990001'
const DOB = '1999-01-01'
const STEPS = ['CV', 'TRAINING', 'TKD', 'FIRSTWORK']
const KNOWN = { status: 'success', known: true, can_continue: true }
const UNKNOWN = { status: 'success', known: false, can_continue: false }
const TKD_STATUS = { status: 'success', data: {
  state: 'BELUM', official_score: null, attempts_used: 0, max_attempts: 2,
  active_attempt: null, can_start: true, pass_score: 70,
  question_count: 20, duration_minutes: 25, bank_ready: true } }

function card(w, step) {
  return w.find(`.rp-card[data-step="${step}"]`)
}

async function mountPortal(search = `?token=${TOKEN}`, response = UNKNOWN) {
  window.history.replaceState({}, '', `/app/recruitment-portal${search}`)
  apiMock.mockImplementation(() => Promise.resolve(response))
  const w = mount(RecruitmentPortalView)
  await flushPromises()
  return w
}

async function cek(w, nik = NIK, dob = DOB) {
  await w.find('input[aria-label="NIK 16 digit"]').setValue(nik)
  await w.find('input[aria-label="Tanggal lahir"]').setValue(dob)
  await w.find('form.rp-check').trigger('submit')
  await flushPromises()
}

describe('RecruitmentPortalView — portal per cabang 4 kartu (Rilis A)', () => {
  beforeEach(() => { vi.clearAllMocks() })
  afterEach(() => {
    window.history.replaceState({}, '', '/app/recruitment-portal')
  })

  it('mendaftarkan rute publik /recruitment-portal', () => {
    const route = router.resolve('/recruitment-portal')
    expect(route.name).toBe('recruitment-portal')
    expect(route.meta.public).toBe(true)
  })

  it('sebelum lookup: hanya kartu CV aktif, tiga kartu lain terkunci dengan hint', async () => {
    const w = await mountPortal()

    for (const step of STEPS) expect(card(w, step).exists()).toBe(true)
    expect(card(w, 'CV').attributes('data-locked')).toBe('false')
    expect(card(w, 'CV').attributes('href')).toBe(`/app/cv-online-form?token=${TOKEN}`)

    for (const step of ['TRAINING', 'TKD', 'FIRSTWORK']) {
      expect(card(w, step).attributes('data-locked')).toBe('true')
      expect(card(w, step).text()).toContain('lengkapi CV Online dulu')
      expect(card(w, step).attributes('href')).toBeUndefined()
    }
    expect(apiMock).not.toHaveBeenCalled()
  })

  it('setelah known=true: keempat kartu aktif dan tautan memakai token cabang yang sama', async () => {
    const w = await mountPortal(`?token=${TOKEN}`, KNOWN)

    await cek(w)

    expect(apiMock).toHaveBeenCalledWith('/api/recruitment/lookup', {
      params: { nik: NIK, dob: DOB },
    })
    for (const step of STEPS) {
      expect(card(w, step).attributes('data-locked')).toBe('false')
    }
    expect(card(w, 'CV').attributes('href')).toBe(`/app/cv-online-form?token=${TOKEN}`)
    expect(card(w, 'FIRSTWORK').attributes('href')).toBe(`/app/first-work-form?token=${TOKEN}`)
    expect(card(w, 'TRAINING').attributes('href')).toBe(`/app/training-form?token=${TOKEN}`)
    expect(card(w, 'TRAINING').text()).not.toContain('Segera tersedia')
    expect(card(w, 'TKD').text()).toContain('Buka tes →')
    expect(w.text()).not.toContain('lengkapi CV Online dulu')
  })

  it('klik kartu TKD setelah dikenal membuka panel dan mengecek status TKD', async () => {
    const w = await mountPortal(`?token=${TOKEN}`, KNOWN)
    await cek(w)

    apiMock.mockResolvedValueOnce(TKD_STATUS)
    await card(w, 'TKD').trigger('click')
    await flushPromises()

    expect(card(w, 'TKD').element.tagName).toBe('BUTTON')
    expect(apiMock).toHaveBeenLastCalledWith('/api/recruitment/tkd/status', {
      method: 'POST', body: { nik: NIK, dob: DOB, token: TOKEN },
    })
    const panel = w.findComponent(RecruitmentTkdPanel)
    expect(panel.exists()).toBe(true)
    expect(panel.props()).toMatchObject({ token: TOKEN, nik: NIK, dob: DOB })
    expect(panel.text()).toContain('20 soal')
    expect(panel.text()).toContain('30.000')
  })

  it('known=false tidak membuka kartu selain CV', async () => {
    const w = await mountPortal()

    await cek(w)

    expect(card(w, 'CV').attributes('data-locked')).toBe('false')
    for (const step of ['TRAINING', 'TKD', 'FIRSTWORK']) {
      expect(card(w, step).attributes('data-locked')).toBe('true')
      expect(card(w, step).text()).toContain('lengkapi CV Online dulu')
    }
    expect(card(w, 'TKD').element.tagName).toBe('DIV')
    await card(w, 'TKD').trigger('click')
    expect(w.findComponent(RecruitmentTkdPanel).exists()).toBe(false)
  })

  it('NIK bukan 16 digit atau tanggal lahir invalid tidak memanggil lookup', async () => {
    const w = await mountPortal()

    await cek(w, '12345', DOB)
    expect(w.text()).toContain('NIK wajib 16 digit angka.')

    await cek(w, NIK, '31-01-1999')
    expect(w.text()).toContain('Tanggal lahir wajib berformat YYYY-MM-DD.')

    expect(apiMock).not.toHaveBeenCalled()
  })

  const LOOKUP_DONE = {
    status: 'success', known: true, can_continue: true,
    nama_masked: 'Bili D.', next_action: 'TRAINING',
    stages: [
      { type: 'CV', status: 'SELESAI', completed_at: '2026-11-25 19:28:30' },
      { type: 'TRAINING', status: 'BELUM', completed_at: null },
      { type: 'TKD', status: 'SELESAI', completed_at: '2026-11-25 19:24:47' },
      { type: 'FIRSTWORK', status: 'BELUM', completed_at: null },
    ],
  }

  it('kartu selesai menampilkan centang, waktu, redup, dan tidak bisa dibuka', async () => {
    const w = await mountPortal(`?token=${TOKEN}`, LOOKUP_DONE)
    await cek(w, '3509190102960003', '1996-02-01')
    const cv = card(w, 'CV')
    expect(cv.text()).toContain('✓ Selesai')
    expect(cv.text()).toContain('2026-11-25 19:28:30')
    expect(cv.text()).toContain('tidak perlu diulang')
    expect(cv.classes()).toContain('rp-card--done')
    expect(cv.element.tagName).toBe('DIV')
    expect(cv.attributes('href')).toBeUndefined()
    expect(card(w, 'TRAINING').classes()).not.toContain('rp-card--done')
    expect(card(w, 'TRAINING').attributes('href')).toBeTruthy()
  })

  it('langkah berikutnya tampil dari respons lookup', async () => {
    const w = await mountPortal(`?token=${TOKEN}`, LOOKUP_DONE)
    await cek(w, '3509190102960003', '1996-02-01')
    expect(w.text()).toContain('Langkah berikutnya: Training Absensi')
  })

  it('lookup hanya GET dan tidak menampilkan cabang/langkah/data pribadi dari respons', async () => {
    const bocor = {
      ...KNOWN,
      first_branch: 'CABANG_RAHASIA',
      branch_code: 'KODE_RAHASIA',
      step: 'LANGKAH_RAHASIA',
      nama: 'NAMA_RAHASIA',
      case_id: 'CASE_RAHASIA',
      nik: '9999999999999999',
    }
    const w = await mountPortal(`?token=${TOKEN}`, bocor)

    await cek(w)

    expect(apiMock).toHaveBeenCalledTimes(1)
    expect(apiMock.mock.calls[0][1]).toEqual({ params: { nik: NIK, dob: DOB } })
    const txt = w.text()
    for (const rahasia of ['CABANG_RAHASIA', 'KODE_RAHASIA', 'LANGKAH_RAHASIA',
      'NAMA_RAHASIA', 'CASE_RAHASIA', '9999999999999999']) {
      expect(txt).not.toContain(rahasia)
    }
  })

  it('cek ulang dengan NIK baru yang belum dikenal mengunci kembali kartu', async () => {
    const w = await mountPortal(`?token=${TOKEN}`, KNOWN)
    await cek(w)
    expect(card(w, 'FIRSTWORK').attributes('data-locked')).toBe('false')

    apiMock.mockImplementationOnce(() => Promise.resolve(UNKNOWN))
    await cek(w, '1111111111111111')

    expect(card(w, 'FIRSTWORK').attributes('data-locked')).toBe('true')
    expect(card(w, 'TRAINING').text()).toContain('lengkapi CV Online dulu')
  })

  it('token juga diterima lewat parameter t dan tetap diteruskan ke form', async () => {
    const w = await mountPortal('?t=tok_alt_1', KNOWN)

    expect(card(w, 'CV').attributes('href')).toBe('/app/cv-online-form?token=tok_alt_1')
    await cek(w)
    expect(card(w, 'FIRSTWORK').attributes('href')).toBe('/app/first-work-form?token=tok_alt_1')
  })

  it('gagal lookup menampilkan pesan error dan tidak membuka kartu', async () => {
    const w = await mountPortal()
    apiMock.mockRejectedValueOnce(new Error('Terlalu banyak pengecekan. Coba lagi sebentar.'))

    await cek(w)

    expect(w.text()).toContain('Terlalu banyak pengecekan')
    expect(card(w, 'FIRSTWORK').attributes('data-locked')).toBe('true')
  })
})
