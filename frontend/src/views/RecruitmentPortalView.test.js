import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import RecruitmentPortalView from './RecruitmentPortalView.vue'
import RecruitmentTkdPanel from '../components/RecruitmentTkdPanel.vue'
import router from '../router/index'

const { apiMock } = vi.hoisted(() => ({ apiMock: vi.fn() }))
vi.mock('../api', () => ({ api: apiMock }))

const TOKEN = 'tok_sby_9f3a'
const NIK = '3573010101990001'
const STEPS = ['CV', 'TRAINING', 'TKD', 'FIRSTWORK']
const KNOWN = { status: 'success', known: true, can_continue: true }
const UNKNOWN = { status: 'success', known: false, can_continue: false }
const TKD_STATUS = { status: 'success', data: {
  state: 'BELUM', official_score: null, attempts_used: 0, max_attempts: 2,
  active_attempt: null, can_start: true, pass_score: 70,
  question_count: 20, duration_minutes: 25, bank_ready: true } }

const INSTITUSI = {
  status: 'success', known: true, can_continue: true,
  nama_masked: 'Bili D.', next_action: 'TRAINING',
  stages: [
    { type: 'CV', status: 'SELESAI', completed_at: '2026-11-25 19:28:30' },
    { type: 'TRAINING', status: 'BELUM', completed_at: null },
    { type: 'TKD', status: 'BELUM', completed_at: null },
    { type: 'FIRSTWORK', status: 'BELUM', completed_at: null },
  ],
}

const HISTORY_ONE = {
  ...INSTITUSI,
  branch_history: {
    other_branch_count: 1,
    first_seen_at: '2026-10-12',
    branch_names: ['Cabang Malang'],
  },
}
const HISTORY_MANY = {
  ...INSTITUSI,
  branch_history: {
    other_branch_count: 3,
    first_seen_at: '2026-10-05',
    branch_names: ['Cabang Jakarta', 'Cabang Malang'],
  },
}

function card(w, step) {
  return w.find(`.rp-card[data-step="${step}"]`)
}

function main(w, step) {
  return card(w, step).find('.rp-card-main')
}

async function mountPortal(search = `?token=${TOKEN}`, response = UNKNOWN) {
  window.history.replaceState({}, '', `/app/recruitment-portal${search}`)
  apiMock.mockImplementation(() => Promise.resolve(response))
  const w = mount(RecruitmentPortalView)
  await flushPromises()
  return w
}

async function cek(w, nik = NIK) {
  await w.find('input[aria-label="NIK 16 digit"]').setValue(nik)
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
    expect(main(w, 'CV').attributes('href')).toBe(`/app/cv-online-form?token=${TOKEN}`)

    for (const step of ['TRAINING', 'TKD', 'FIRSTWORK']) {
      expect(card(w, step).attributes('data-locked')).toBe('true')
      expect(card(w, step).text()).toContain('Lengkapi CV Online terlebih dahulu.')
      expect(main(w, step).attributes('href')).toBeUndefined()
    }
    expect(apiMock).not.toHaveBeenCalled()
  })

  it('setelah known=true: keempat kartu aktif dan tautan memakai token cabang yang sama', async () => {
    const w = await mountPortal(`?token=${TOKEN}`, KNOWN)

    await cek(w)

    expect(apiMock).toHaveBeenCalledWith('/api/recruitment/lookup', {
      params: { nik: NIK, token: TOKEN },
    })
    for (const step of STEPS) {
      expect(card(w, step).attributes('data-locked')).toBe('false')
    }
    expect(main(w, 'CV').attributes('href')).toBe(`/app/cv-online-form?token=${TOKEN}`)
    expect(main(w, 'FIRSTWORK').attributes('href')).toBe(`/app/first-work-form?token=${TOKEN}`)
    expect(main(w, 'TRAINING').attributes('href')).toBe(`/app/training-form?token=${TOKEN}`)
    expect(card(w, 'TRAINING').text()).not.toContain('Segera tersedia')
    expect(card(w, 'TKD').text()).toContain('Buka →')
    expect(w.text()).not.toContain('Lengkapi CV Online terlebih dahulu.')
  })

  it('klik kartu TKD setelah dikenal membuka panel dan mengecek status TKD', async () => {
    const w = await mountPortal(`?token=${TOKEN}`, KNOWN)
    await cek(w)

    apiMock.mockResolvedValueOnce(TKD_STATUS)
    await main(w, 'TKD').trigger('click')
    await flushPromises()

    expect(main(w, 'TKD').element.tagName).toBe('BUTTON')
    expect(apiMock).toHaveBeenLastCalledWith('/api/recruitment/tkd/status', {
      method: 'POST', body: { nik: NIK, token: TOKEN },
    })
    const panel = w.findComponent(RecruitmentTkdPanel)
    expect(panel.exists()).toBe(true)
    expect(panel.props()).toMatchObject({ token: TOKEN, nik: NIK })
    expect(panel.text()).toContain('21 soal (20 dinilai)')
    expect(panel.text()).toContain('30.000')
  })

  it('known=false tidak membuka kartu selain CV', async () => {
    const w = await mountPortal()

    await cek(w)

    expect(card(w, 'CV').attributes('data-locked')).toBe('false')
    for (const step of ['TRAINING', 'TKD', 'FIRSTWORK']) {
      expect(card(w, step).attributes('data-locked')).toBe('true')
      expect(card(w, step).text()).toContain('Lengkapi CV Online terlebih dahulu.')
    }
    expect(main(w, 'TKD').element.tagName).toBe('DIV')
    await main(w, 'TKD').trigger('click')
    expect(w.findComponent(RecruitmentTkdPanel).exists()).toBe(false)
  })

  it('NIK bukan 16 digit tidak memanggil lookup dan isian tanggal lahir tidak ada', async () => {
    const w = await mountPortal()

    expect(w.find('input[aria-label="Tanggal lahir"]').exists()).toBe(false)

    await cek(w, '12345')
    expect(w.text()).toContain('NIK wajib 16 digit angka.')

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

  it('kartu selesai menampilkan centang, waktu, dan ringkasan ringkas', async () => {
    const w = await mountPortal(`?token=${TOKEN}`, LOOKUP_DONE)
    await cek(w, '3509190102960003')
    const cv = card(w, 'CV')
    expect(cv.find('.rp-status').text()).toBe('Selesai')
    expect(cv.find('.rp-node').text()).toBe('✓')
    expect(cv.text()).toContain('2026-11-25 19:28:30')
    expect(cv.text()).toContain('Data tersimpan pada')
    expect(cv.text()).toContain('Lihat keterangan')
    expect(cv.find('[data-expand]').attributes('open')).toBeUndefined()
    expect(cv.classes()).toContain('rp-card--done')
    expect(main(w, 'CV').element.tagName).toBe('DIV')
    expect(main(w, 'CV').attributes('href')).toBeUndefined()
    expect(card(w, 'TRAINING').classes()).not.toContain('rp-card--done')
    expect(main(w, 'TRAINING').attributes('href')).toBeTruthy()
  })

  it('langkah berikutnya tampil dari respons lookup', async () => {
    const w = await mountPortal(`?token=${TOKEN}`, LOOKUP_DONE)
    await cek(w, '3509190102960003')
    expect(w.text()).toContain('Langkah berikutnya: Training Absensi')
  })

  it('keterangan dibuka dan kartu selesai tetap tidak bisa dibuka', async () => {
    const w = await mountPortal(`?token=${TOKEN}`, LOOKUP_DONE)
    await cek(w, '3509190102960003')
    const cv = card(w, 'CV')
    expect(cv.find('[data-expand]').attributes('open')).toBeUndefined()
    await cv.find('[data-expand] summary').trigger('click')
    await flushPromises()
    expect(cv.find('[data-expand]').attributes('open')).toBe('')
    expect(cv.text()).toContain('Data diri dan pendidikan Anda tersimpan')
    expect(cv.text()).toContain('tidak perlu diulang')
    expect(main(w, 'CV').element.tagName).toBe('DIV')
    expect(main(w, 'CV').attributes('href')).toBeUndefined()
  })

  it('urutan kartu tetap CV, Training, TKD, FirstWork', async () => {
    const w = await mountPortal(`?token=${TOKEN}`, LOOKUP_DONE)
    await cek(w, '3509190102960003')
    expect(w.findAll('.rp-card').map((c) => c.attributes('data-step')))
      .toEqual(['CV', 'TRAINING', 'TKD', 'FIRSTWORK'])
  })

  it('lookup hanya GET dan tidak merender field mentah di luar ringkasan', async () => {
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
    expect(apiMock.mock.calls[0][1]).toEqual({
      params: { nik: NIK, token: TOKEN },
    })
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
    expect(card(w, 'TRAINING').text()).toContain('Lengkapi CV Online terlebih dahulu.')
  })

  it('token juga diterima lewat parameter t dan tetap diteruskan ke form', async () => {
    const w = await mountPortal('?t=tok_alt_1', KNOWN)

    expect(main(w, 'CV').attributes('href')).toBe('/app/cv-online-form?token=tok_alt_1')
    await cek(w)
    expect(main(w, 'FIRSTWORK').attributes('href')).toBe('/app/first-work-form?token=tok_alt_1')
  })

  it('gagal lookup menampilkan pesan error dan tidak membuka kartu', async () => {
    const w = await mountPortal()
    apiMock.mockRejectedValueOnce(new Error('Terlalu banyak pengecekan. Coba lagi sebentar.'))

    await cek(w)

    expect(w.text()).toContain('Terlalu banyak pengecekan')
    expect(card(w, 'FIRSTWORK').attributes('data-locked')).toBe('true')
  })
})

describe('RecruitmentPortalView — tampilan institusi (v2.135.8)', () => {
  beforeEach(() => { vi.clearAllMocks() })
  afterEach(() => {
    window.history.replaceState({}, '', '/app/recruitment-portal')
  })

  it('memakai logo resmi dan nama perusahaan di bilah merek', async () => {
    const w = await mountPortal()

    const bar = w.find('.rp-brandbar')
    expect(bar.exists()).toBe(true)
    expect(bar.find('img.rp-logo').attributes('src')).toBe('/static/bpf-logo.png')
    expect(bar.text()).toContain('PT Bestprofit Futures')
    expect(bar.text()).toContain('Portal Rekrutmen')
  })

  it('menampilkan penanda kepercayaan dan catatan privasi NIK', async () => {
    const w = await mountPortal()

    const trust = w.find('.rp-trust')
    expect(trust.exists()).toBe(true)
    expect(trust.text()).toContain('Data pribadi dilindungi')
    expect(trust.text()).toContain('Cukup NIK 16 digit')
    expect(w.find('.rp-privacy').text()).toContain('NIK lengkap tidak ditampilkan')
  })

  it('memakai daftar langkah vertikal, bukan grid kartu', async () => {
    const w = await mountPortal()
    const list = w.find('.rp-steps')
    expect(list.exists()).toBe(true)
    expect(list.findAll('.rp-card')).toHaveLength(4)
    expect(w.find('.rp-card').find('.rp-node').exists()).toBe(true)
  })

  it('menandai baris langkah berikutnya setelah NIK dikenal', async () => {
    const w = await mountPortal(`?token=${TOKEN}`, {
      status: 'success', known: true, can_continue: true,
      nama_masked: 'Bili D.', next_action: 'TRAINING',
      stages: [
        { type: 'CV', status: 'SELESAI', completed_at: '2026-11-25 19:28:30' },
        { type: 'TRAINING', status: 'BELUM', completed_at: null },
        { type: 'TKD', status: 'BELUM', completed_at: null },
        { type: 'FIRSTWORK', status: 'BELUM', completed_at: null },
      ],
    })
    await cek(w, '3509190102960003')

    expect(card(w, 'TRAINING').classes()).toContain('rp-card--next')
    expect(card(w, 'CV').classes()).not.toContain('rp-card--next')
    expect(card(w, 'CV').find('.rp-node').text()).toContain('✓')
  })

  it('badge satu kata, simpul centang, dan header progres dinamis', async () => {
    const w = await mountPortal(`?token=${TOKEN}`, INSTITUSI)
    await cek(w, '3509190102960003')

    expect(card(w, 'CV').find('.rp-status').text()).toBe('Selesai')
    expect(card(w, 'CV').find('.rp-node').text()).toBe('✓')
    expect(card(w, 'TRAINING').find('.rp-status').text()).toBe('Berikutnya')
    expect(card(w, 'TKD').find('.rp-status').text()).toBe('Belum')
    expect(w.find('.rp-steps-head').text()).toContain('1 dari 4 tahap selesai')
  })

  it('aksi dan kaki keterangan seragam untuk semua tahap aktif', async () => {
    const w = await mountPortal(`?token=${TOKEN}`, INSTITUSI)
    await cek(w, '3509190102960003')

    for (const step of ['TRAINING', 'TKD', 'FIRSTWORK']) {
      expect(card(w, step).text()).toContain('Buka →')
      expect(card(w, step).find('[data-expand]').exists()).toBe(true)
    }
    expect(main(w, 'CV').element.tagName).toBe('DIV')
  })

  it('info riwayat cabang lain tampil sebagai informasi dan tidak mengunci tahap', async () => {
    const w = await mountPortal(`?token=${TOKEN}`, HISTORY_ONE)
    await cek(w, '3509190102960003')

    const info = w.find('[data-history]')
    expect(info.exists()).toBe(true)
    expect(info.text()).toContain('Cabang Malang')
    expect(info.text()).toContain('12 Oktober 2026')
    expect(info.text()).toContain('tetap dapat melanjutkan')

    for (const step of STEPS) {
      expect(card(w, step).attributes('data-locked')).toBe('false')
    }
  })

  it('info beberapa cabang menyebut jumlah dan tanggal pertama', async () => {
    const w = await mountPortal(`?token=${TOKEN}`, HISTORY_MANY)
    await cek(w, '3509190102960003')

    const teks = w.find('[data-history]').text()
    expect(teks).toContain('3 cabang lain')
    expect(teks).toContain('Cabang Jakarta')
    expect(teks).toContain('Cabang Malang')
    expect(teks).toContain('1 cabang lain')
    expect(teks).toContain('5 Oktober 2026')
  })

  it('tanpa branch_history tidak ada info riwayat', async () => {
    const w = await mountPortal(`?token=${TOKEN}`, INSTITUSI)
    await cek(w, '3509190102960003')

    expect(w.find('[data-history]').exists()).toBe(false)
  })

  it('field mentah di branch_history tidak ikut dirender', async () => {
    const bocor = {
      ...HISTORY_ONE,
      branch_history: {
        ...HISTORY_ONE.branch_history,
        branch_codes: ['MLG'],
        nik: '9999999999999999',
        case_id: 'CASE_RAHASIA',
      },
    }
    const w = await mountPortal(`?token=${TOKEN}`, bocor)
    await cek(w, '3509190102960003')

    const teks = w.text()
    for (const rahasia of ['MLG', '9999999999999999', 'CASE_RAHASIA']) {
      expect(teks).not.toContain(rahasia)
    }
  })

  it('info riwayat hilang saat cek ulang NIK yang belum dikenal', async () => {
    const w = await mountPortal(`?token=${TOKEN}`, HISTORY_ONE)
    await cek(w, '3509190102960003')
    expect(w.find('[data-history]').exists()).toBe(true)

    apiMock.mockImplementationOnce(() => Promise.resolve(UNKNOWN))
    await cek(w, '1111111111111111')

    expect(w.find('[data-history]').exists()).toBe(false)
  })
})
