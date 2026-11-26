import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import RecruitmentTkdPanel from './RecruitmentTkdPanel.vue'

const { apiMock } = vi.hoisted(() => ({ apiMock: vi.fn() }))
vi.mock('../api', () => ({ api: apiMock }))

const PROPS = { token: 'tok', session: 'session-token' }
const BELUM = { status: 'success', data: {
  state: 'BELUM', official_score: null, score_source: null, attempts_used: 0,
  max_attempts: 2, active_attempt: null, can_start: true, pass_score: 70,
  question_count: 20, duration_minutes: 25, bank_ready: true } }
const MCQ_ONE = [{ position: 1, type: 'MCQ', prompt: 'Pilih satu',
  options: [{ id: 'a', text: 'A' }, { id: 'b', text: 'B' }] }]

function examData(attemptId, questions, overrides = {}) {
  return { status: 'success', data: {
    attempt_id: attemptId, attempt_no: 1, modal_tier: '30k',
    expires_at: new Date(Date.now() + 1500000).toISOString(),
    remaining_seconds: 1500, duration_minutes: 25,
    questions, answers: {}, ...overrides } }
}

async function mountPanel(status = BELUM) {
  apiMock.mockResolvedValueOnce(status)
  const w = mount(RecruitmentTkdPanel, { props: PROPS })
  await flushPromises()
  return w
}

async function enterExam(w, attemptId, questions, overrides) {
  apiMock.mockResolvedValueOnce(examData(attemptId, questions, overrides))
  await w.find('[data-action="start"]').trigger('click')
  await flushPromises()
}

async function finishExam(result, refreshedStatus) {
  const w = await mountPanel()
  await enterExam(w, 'TKD-R', MCQ_ONE)
  apiMock.mockResolvedValueOnce({ status: 'success', data: result })
  if (refreshedStatus) apiMock.mockResolvedValueOnce({ status: 'success', data: refreshedStatus })
  await w.find('[data-action="submit"]').trigger('click')
  await flushPromises()
  await flushPromises()
  return w
}

function putCalls() {
  return apiMock.mock.calls.filter(([, opts]) => opts?.method === 'PUT')
}

describe('RecruitmentTkdPanel', () => {
  beforeEach(() => vi.clearAllMocks())
  afterEach(() => {
    vi.useRealTimers()
    apiMock.mockReset()
  })

  it('status BELUM menampilkan aturan dan pilihan modal', async () => {
    const w = await mountPanel()
    expect(apiMock).toHaveBeenCalledWith('/api/recruitment/tkd/status', {
      method: 'POST', body: { token: PROPS.token, s: PROPS.session } })
    const text = w.text()
    expect(text).toContain('20 soal')
    expect(text).toContain('25 menit')
    expect(text).toContain('lulus 70')
    expect(text).toContain('2 kesempatan')
    for (const tier of ['30.000', '50.000', '100.000']) expect(text).toContain(tier)
  })

  it('LULUS menampilkan skor resmi dan tidak menawarkan mulai', async () => {
    const w = await mountPanel({ status: 'success', data: {
      ...BELUM.data, state: 'LULUS', official_score: 86.67, can_start: false } })
    expect(w.text()).toContain('86,67')
    expect(w.text()).toContain('Lulus')
    expect(w.find('[data-action="start"]').exists()).toBe(false)
  })

  it('HABIS dan DIKECUALIKAN menampilkan pesan tanpa tombol mulai', async () => {
    const habis = await mountPanel({ status: 'success', data: {
      ...BELUM.data, state: 'HABIS', official_score: 60, can_start: false } })
    expect(habis.text()).toContain('Kesempatan habis')

    const exc = await mountPanel({ status: 'success', data: {
      ...BELUM.data, state: 'DIKECUALIKAN', can_start: false } })
    expect(exc.text()).toContain('Dikecualikan')
    expect(exc.find('[data-action="start"]').exists()).toBe(false)
  })

  it('mulai mengirim tier dan menampilkan soal tanpa kunci', async () => {
    const w = await mountPanel()
    apiMock.mockResolvedValueOnce({ status: 'success', data: {
      attempt_id: 'TKD-1', attempt_no: 1, modal_tier: '30k',
      expires_at: new Date(Date.now() + 1500000).toISOString(),
      remaining_seconds: 1500, duration_minutes: 25,
      questions: [{ position: 1, type: 'MCQ', category: 'REGULASI', prompt: 'Pertanyaan 1',
                    options: [{ id: 'a', text: 'A' }, { id: 'b', text: 'B' }] }],
      answers: {} } })
    await w.find('select[data-tier]').setValue('30k')
    await w.find('[data-action="start"]').trigger('click')
    await flushPromises()
    expect(apiMock).toHaveBeenLastCalledWith('/api/recruitment/tkd/start', {
      method: 'POST', body: { token: PROPS.token, s: PROPS.session, modal_tier: '30k' } })
    expect(w.text()).toContain('Pertanyaan 1')
    expect(w.text()).not.toContain('kunci')
  })

  it('memilih jawaban menyimpan otomatis dan submit menampilkan skor', async () => {
    vi.useFakeTimers()
    const w = await mountPanel()
    apiMock.mockResolvedValueOnce({ status: 'success', data: {
      attempt_id: 'TKD-1', attempt_no: 1, modal_tier: '30k',
      expires_at: new Date(Date.now() + 1500000).toISOString(), remaining_seconds: 1500,
      duration_minutes: 25,
      questions: [{ position: 1, type: 'MCQ', category: 'REGULASI', prompt: 'P',
                    options: [{ id: 'a', text: 'A' }, { id: 'b', text: 'B' }] }], answers: {} } })
    await w.find('[data-action="start"]').trigger('click')
    await flushPromises()
    apiMock.mockResolvedValueOnce({ status: 'success' })
    await w.find('input[value="b"]').setValue(true)
    vi.advanceTimersByTime(600)
    await flushPromises()
    expect(apiMock).toHaveBeenCalledWith('/api/recruitment/tkd/attempts/TKD-1/answers/1', {
      method: 'PUT', body: { answer: { option: 'b' } } })

    apiMock.mockResolvedValueOnce({ status: 'success', data: {
      attempt_id: 'TKD-1', score: 85, passed: true, official_score: 85,
      best_score: 85, attempts_used: 1, max_attempts: 2, state: 'LULUS' } })
    await w.find('[data-action="submit"]').trigger('click')
    await flushPromises()
    expect(w.text()).toContain('85')
    expect(w.text()).toContain('Lulus')
  })

  it('BERLANGSUNG menawarkan Lanjutkan dan memulihkan jawaban tersimpan', async () => {
    const expiry = new Date(Date.now() + 900000).toISOString()
    const w = await mountPanel({ status: 'success', data: {
      ...BELUM.data, state: 'BERLANGSUNG', can_start: false,
      active_attempt: { id: 'TKD-7', remaining_seconds: 900, expires_at: expiry } } })
    expect(w.find('[data-action="start"]').exists()).toBe(false)

    apiMock.mockResolvedValueOnce({ status: 'success', data: {
      attempt_id: 'TKD-7', expires_at: expiry, remaining_seconds: 900,
      questions: [{ position: 1, type: 'MCQ', prompt: 'Lanjut?',
                    options: [{ id: 'a', text: 'A' }, { id: 'b', text: 'B' }] }],
      answers: { '1': { option: 'b' } } } })
    await w.find('[data-action="resume"]').trigger('click')
    await flushPromises()

    expect(apiMock).toHaveBeenCalledWith('/api/recruitment/tkd/attempts/TKD-7', { method: 'GET' })
    expect(w.text()).toContain('Lanjut?')
    expect(w.find('input[value="b"]').element.checked).toBe(true)
  })

  it('memakai remaining_seconds, bukan expires_at tanpa zona waktu', async () => {
    vi.useFakeTimers()
    const w = await mountPanel({ status: 'success', data: {
      ...BELUM.data, state: 'BERLANGSUNG', can_start: false,
      active_attempt: { id: 'TKD-8', remaining_seconds: 900,
        expires_at: '2000-01-01T00:00:00' } } })

    expect(w.find('[data-timer]').text()).toBe('15:00')
    vi.advanceTimersByTime(2000)
    await flushPromises()
    expect(apiMock.mock.calls.some(([path]) => path.endsWith('/submit'))).toBe(false)
    w.unmount()
  })

  it('Escape menutup panel dan tidak mengaku sebagai modal', async () => {
    const w = await mountPanel()

    expect(w.find('.tkd-panel').attributes('aria-modal')).toBeUndefined()
    await w.find('.tkd-panel').trigger('keydown', { key: 'Escape' })
    await flushPromises()

    expect(w.emitted('close')).toBeTruthy()
    w.unmount()
  })

  it('start ditolak 409 menampilkan pesan server dan menyegarkan status', async () => {
    const w = await mountPanel()
    apiMock.mockRejectedValueOnce(Object.assign(new Error('Kesempatan habis.'), { status: 409 }))
    apiMock.mockResolvedValueOnce({ status: 'success', data: {
      ...BELUM.data, state: 'HABIS', can_start: false } })

    await w.find('[data-action="start"]').trigger('click')
    await flushPromises()

    expect(w.text()).toContain('Kesempatan habis.')
    expect(w.find('[data-action="start"]').exists()).toBe(false)
  })

  it('klik Selesai dua kali hanya mengirim submit sekali', async () => {
    const w = await mountPanel()
    apiMock.mockResolvedValueOnce({ status: 'success', data: {
      attempt_id: 'TKD-2', expires_at: new Date(Date.now() + 1500000).toISOString(),
      remaining_seconds: 1500, questions: [{ position: 1, type: 'MCQ', prompt: 'P',
        options: [{ id: 'a', text: 'A' }] }], answers: {} } })
    await w.find('[data-action="start"]').trigger('click')
    await flushPromises()

    const result = { status: 'success', data: { score: 90, passed: true,
      official_score: 90, attempts_used: 1, max_attempts: 2 } }
    apiMock.mockResolvedValueOnce(result)
    apiMock.mockResolvedValueOnce(result)
    const button = w.find('[data-action="submit"]')
    await button.trigger('click')
    await button.trigger('click')
    await flushPromises()

    expect(apiMock.mock.calls.filter(([path]) => path.endsWith('/submit'))).toHaveLength(1)
  })

  it('waktu habis mengumpulkan ujian otomatis', async () => {
    vi.useFakeTimers()
    const w = await mountPanel()
    apiMock.mockResolvedValueOnce({ status: 'success', data: {
      attempt_id: 'TKD-3', expires_at: new Date(Date.now() + 1500).toISOString(),
      remaining_seconds: 2, questions: [{ position: 1, type: 'NUMERIC', prompt: 'Angka' }],
      answers: {} } })
    await w.find('[data-action="start"]').trigger('click')
    await flushPromises()

    apiMock.mockResolvedValueOnce({ status: 'success', data: {
      score: 0, passed: false, official_score: 0, attempts_used: 1, max_attempts: 2 } })
    vi.advanceTimersByTime(3000)
    await flushPromises()

    expect(apiMock.mock.calls.some(([path]) => path.endsWith('/submit'))).toBe(true)
    expect(w.text()).toContain('Hasil ujian')
  })

  it('soal tidak membocorkan kunci atau penjelasan dari payload', async () => {
    const w = await mountPanel()
    apiMock.mockResolvedValueOnce({ status: 'success', data: {
      attempt_id: 'TKD-4', expires_at: new Date(Date.now() + 1500000).toISOString(),
      remaining_seconds: 1500,
      questions: [{ position: 1, type: 'MCQ', prompt: 'Aman?', correct: 'rahasia',
        points: 5, explanation: 'Kunci rahasia',
        options: [{ id: 'a', text: 'Ya', correct: true }, { id: 'b', text: 'Tidak' }] }],
      answers: {} } })
    await w.find('[data-action="start"]').trigger('click')
    await flushPromises()

    expect(w.text()).toContain('Aman?')
    expect(w.text()).not.toContain('rahasia')
    expect(w.text()).not.toContain('Kunci')
  })

  it('pindah soal dalam jendela debounce tetap menyimpan jawaban kedua posisi', async () => {
    vi.useFakeTimers()
    const w = await mountPanel()
    const questions = [
      { position: 1, type: 'MCQ', prompt: 'Satu',
        options: [{ id: 'a', text: 'A' }, { id: 'b', text: 'B' }] },
      { position: 2, type: 'MCQ', prompt: 'Dua',
        options: [{ id: 'a', text: 'A' }, { id: 'b', text: 'B' }] },
    ]
    await enterExam(w, 'TKD-8', questions)

    await w.find('input[value="b"]').setValue(true)
    await w.find('[data-action="next"]').trigger('click')
    await flushPromises()
    expect(w.text()).toContain('Soal 2 dari 2')

    await w.find('input[value="a"]').setValue(true)
    vi.advanceTimersByTime(600)
    await flushPromises()

    expect(putCalls()).toEqual([
      ['/api/recruitment/tkd/attempts/TKD-8/answers/1', {
        method: 'PUT', body: { answer: { option: 'b' } } }],
      ['/api/recruitment/tkd/attempts/TKD-8/answers/2', {
        method: 'PUT', body: { answer: { option: 'a' } } }],
    ])
  })

  it('tombol Sebelumnya dalam jendela debounce tetap menyimpan jawaban', async () => {
    vi.useFakeTimers()
    const w = await mountPanel()
    const questions = [
      { position: 1, type: 'MCQ', prompt: 'Satu', options: [{ id: 'a', text: 'A' }] },
      { position: 2, type: 'MCQ', prompt: 'Dua', options: [{ id: 'a', text: 'A' }] },
    ]
    await enterExam(w, 'TKD-9', questions)
    await w.find('[data-action="next"]').trigger('click')
    await flushPromises()
    await w.find('input[value="a"]').setValue(true)
    await w.find('[data-action="prev"]').trigger('click')
    await flushPromises()

    expect(putCalls()).toEqual([[
      '/api/recruitment/tkd/attempts/TKD-9/answers/2',
      { method: 'PUT', body: { answer: { option: 'a' } } },
    ]])
    expect(w.text()).toContain('Soal 1 dari 2')
  })

  it('Selesai menunggu PUT autosave selesai sebelum mengirim submit', async () => {
    vi.useFakeTimers()
    const w = await mountPanel()
    await enterExam(w, 'TKD-5', MCQ_ONE)
    let resolvePut
    apiMock.mockImplementationOnce(() => new Promise((resolve) => { resolvePut = resolve }))
    apiMock.mockResolvedValueOnce({ status: 'success', data: {
      score: 80, passed: true, official_score: 80,
      attempts_used: 1, max_attempts: 2, state: 'LULUS' } })

    await w.find('input[value="a"]').setValue(true)
    vi.advanceTimersByTime(600)
    await flushPromises()
    await w.find('[data-action="submit"]').trigger('click')
    await flushPromises()

    expect(apiMock.mock.calls.some(([path]) => path.endsWith('/submit'))).toBe(false)

    resolvePut({ status: 'success' })
    await flushPromises()
    await flushPromises()

    expect(apiMock.mock.calls.slice(0, 4).map(([path]) => path)).toEqual([
      '/api/recruitment/tkd/status',
      '/api/recruitment/tkd/start',
      '/api/recruitment/tkd/attempts/TKD-5/answers/1',
      '/api/recruitment/tkd/attempts/TKD-5/submit',
    ])
  })

  it('PUT gagal saat flush sebelum submit membatalkan submit dan menampilkan pesan server', async () => {
    vi.useFakeTimers()
    const w = await mountPanel()
    await enterExam(w, 'TKD-6', MCQ_ONE)
    apiMock.mockImplementation(() => Promise.reject(
      Object.assign(new Error('Jawaban ditolak server.'), { status: 500 })))

    await w.find('input[value="a"]').setValue(true)
    vi.advanceTimersByTime(600)
    await flushPromises()
    await w.find('[data-action="submit"]').trigger('click')
    await flushPromises()
    await flushPromises()

    expect(apiMock.mock.calls.some(([path]) => path.endsWith('/submit'))).toBe(false)
    expect(w.text()).toContain('Soal 1 dari 1')
    expect(w.text()).toContain('Jawaban ditolak server.')
  })

  it('hasil LULUS tidak menawarkan Coba lagi meski status lama mengizinkan', async () => {
    const w = await finishExam({ state: 'LULUS', score: 90, passed: true,
      official_score: 90, attempts_used: 1, max_attempts: 2,
      message: 'Selamat, Anda lulus TKD.' },
    { ...BELUM.data, state: 'LULUS', can_start: true })

    expect(w.find('[data-action="retry"]').exists()).toBe(false)
    expect(w.text()).toContain('Selamat, Anda lulus TKD.')
  })

  it('hasil HABIS tidak menawarkan Coba lagi meski status lama mengizinkan', async () => {
    const w = await finishExam({ state: 'HABIS', score: 50, passed: false,
      attempts_used: 2, max_attempts: 2, message: 'Kesempatan habis.' },
    { ...BELUM.data, state: 'HABIS', can_start: true })

    expect(w.find('[data-action="retry"]').exists()).toBe(false)
  })

  it('hasil BISA_COBA dengan sisa kesempatan menawarkan Coba lagi', async () => {
    const w = await finishExam({ state: 'BISA_COBA', score: 50, passed: false,
      attempts_used: 1, max_attempts: 2, message: 'Anda masih bisa mencoba lagi.' },
    { ...BELUM.data, state: 'BISA_COBA', can_start: false })

    expect(w.find('[data-action="retry"]').exists()).toBe(true)
    expect(w.text()).toContain('Anda masih bisa mencoba lagi.')
  })

  it('hasil BISA_COBA tanpa sisa kesempatan tidak menawarkan Coba lagi', async () => {
    const w = await finishExam({ state: 'BISA_COBA', score: 50, passed: false,
      attempts_used: 2, max_attempts: 2 },
    { ...BELUM.data, state: 'BISA_COBA', can_start: true })

    expect(w.find('[data-action="retry"]').exists()).toBe(false)
  })

  it('hasil BISA_COBA tanpa angka kesempatan tidak menawarkan Coba lagi', async () => {
    const w = await finishExam({ state: 'BISA_COBA', score: 50, passed: false },
      { ...BELUM.data, state: 'BISA_COBA', can_start: true })

    expect(w.find('[data-action="retry"]').exists()).toBe(false)
  })

  it('intro BERLANGSUNG menampilkan sisa waktu dari active_attempt', async () => {
    const w = await mountPanel({ status: 'success', data: {
      ...BELUM.data, state: 'BERLANGSUNG', can_start: false,
      active_attempt: { id: 'TKD-7', remaining_seconds: 900,
        expires_at: new Date(Date.now() + 900000).toISOString() } } })

    expect(w.text()).toContain('Sisa waktu:')
    expect(w.find('[data-timer]').text()).not.toBe('00:00')
    w.unmount()
  })

  it('Tutup dengan jawaban tertunda mengirim PUT sebelum emit close', async () => {
    vi.useFakeTimers()
    const w = await mountPanel()
    await enterExam(w, 'TKD-10', MCQ_ONE)
    let resolvePut
    apiMock.mockImplementationOnce(() => new Promise((resolve) => { resolvePut = resolve }))

    await w.find('input[value="a"]').setValue(true)
    await w.find('[data-action="close"]').trigger('click')
    await flushPromises()

    expect(putCalls()).toHaveLength(1)
    expect(w.emitted('close')).toBeUndefined()

    resolvePut({ status: 'success' })
    await flushPromises()
    await flushPromises()

    expect(w.emitted('close')).toHaveLength(1)
  })

  it('submit gagal saat waktu habis tidak mengulang submit otomatis', async () => {
    vi.useFakeTimers()
    const w = await mountPanel()
    await enterExam(w, 'TKD-12', MCQ_ONE, {
      expires_at: new Date(Date.now() + 1000).toISOString(),
      remaining_seconds: 1,
    })
    apiMock.mockRejectedValueOnce(new Error('Gagal mengumpulkan sementara.'))

    vi.advanceTimersByTime(1100)
    await flushPromises()
    expect(apiMock.mock.calls.filter(([path]) => path.endsWith('/submit'))).toHaveLength(1)
    expect(w.text()).toContain('Gagal mengumpulkan sementara.')

    vi.advanceTimersByTime(5000)
    await flushPromises()
    expect(apiMock.mock.calls.filter(([path]) => path.endsWith('/submit'))).toHaveLength(1)
    expect(w.find('[data-action="submit"]').exists()).toBe(true)
  })

  it('unmount dengan jawaban tertunda tetap mengirim PUT', async () => {
    vi.useFakeTimers()
    const w = await mountPanel()
    await enterExam(w, 'TKD-11', MCQ_ONE)
    apiMock.mockResolvedValueOnce({ status: 'success' })

    await w.find('input[value="b"]').setValue(true)
    w.unmount()
    await flushPromises()

    expect(putCalls()).toEqual([[
      '/api/recruitment/tkd/attempts/TKD-11/answers/1',
      { method: 'PUT', body: { answer: { option: 'b' } } },
    ]])
  })
})
