import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import RecruitmentTkdPanel from './RecruitmentTkdPanel.vue'

const { apiMock } = vi.hoisted(() => ({ apiMock: vi.fn() }))
vi.mock('../api', () => ({ api: apiMock }))

const PROPS = { token: 'tok', nik: '3573010101990001', dob: '1999-01-01' }
const BELUM = { status: 'success', data: {
  state: 'BELUM', official_score: null, score_source: null, attempts_used: 0,
  max_attempts: 2, active_attempt: null, can_start: true, pass_score: 70,
  question_count: 20, duration_minutes: 25, bank_ready: true } }

async function mountPanel(status = BELUM) {
  apiMock.mockResolvedValueOnce(status)
  const w = mount(RecruitmentTkdPanel, { props: PROPS })
  await flushPromises()
  return w
}

describe('RecruitmentTkdPanel', () => {
  beforeEach(() => vi.clearAllMocks())
  afterEach(() => vi.useRealTimers())

  it('status BELUM menampilkan aturan dan pilihan modal', async () => {
    const w = await mountPanel()
    expect(apiMock).toHaveBeenCalledWith('/api/recruitment/tkd/status', {
      method: 'POST', body: { nik: PROPS.nik, dob: PROPS.dob, token: PROPS.token } })
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
      method: 'POST', body: { nik: PROPS.nik, dob: PROPS.dob, token: PROPS.token, modal_tier: '30k' } })
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
})
