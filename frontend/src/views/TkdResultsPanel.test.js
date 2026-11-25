import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import TkdResultsPanel from './TkdResultsPanel.vue'

const { apiMock, authMock } = vi.hoisted(() => ({
  apiMock: vi.fn(), authMock: { role: 'traineer' },
}))
vi.mock('../api', () => ({ api: apiMock }))
vi.mock('../stores/auth', () => ({ useAuthStore: () => authMock }))

const ROWS = [{ id: 'TKD-1', case_id: 'RC-1', nama: 'Andi', nik_masked: '****0001',
  branch_code: 'SBY', attempt_no: 1, status: 'SELESAI', score: 60, passed: 0,
  started_at: '2026-11-24 10:00:00', submitted_at: '2026-11-24 10:20:00',
  score_source: 'AUTO' }]

const REVIEW = {
  attempt: { id: 'TKD-1', modal_tier: '30k', score: 60 },
  case: { nama: 'Andi', tkd_score: 60, tkd_score_source: 'AUTO' },
  items: [{ position: 1, snapshot: {
    prompt: 'Berapa 7 × 8?', type: 'MCQ',
    options: [{ id: 'a', text: '54' }, { id: 'b', text: '56' }],
    answer: { option: 'a' }, points: 2,
  }, answer: { option: 'b' }, is_correct: 0, points_awarded: 0 }],
  profile_text_answer: 'Saya teliti dan cepat',
  modal_tier: '30k', score: 60,
}

async function mountPanel() {
  apiMock.mockImplementation((path) => {
    if (path === '/api/recruitment/tkd/attempts') return Promise.resolve({ data: ROWS })
    if (path === '/api/recruitment/tkd/review/TKD-1') return Promise.resolve({ data: REVIEW })
    return Promise.resolve({ status: 'success' })
  })
  const w = mount(TkdResultsPanel)
  await flushPromises()
  return w
}

function scorePosts() {
  return apiMock.mock.calls.filter(([path]) => path === '/api/recruitment/tkd/score')
}

describe('TkdResultsPanel', () => {
  beforeEach(() => vi.clearAllMocks())

  it('menampilkan NIK termasker dan skor', async () => {
    const w = await mountPanel()
    expect(w.text()).toContain('****0001')
    expect(w.text()).toContain('60')
    expect(w.text()).not.toContain('3573010101990001')
  })

  it('detail menampilkan jawaban, kunci, dan poin', async () => {
    const w = await mountPanel()
    await w.find('button[data-review="TKD-1"]').trigger('click')
    await flushPromises()
    const cells = w.find('.tk-results-detail-table tbody tr').findAll('td')
    expect(w.text()).toContain('Poin')
    expect(cells[1].text()).toBe('Berapa 7 × 8?')
    expect(cells[2].text()).toBe('B — 56')
    expect(cells[3].text()).toBe('A — 54')
    expect(cells[5].text()).toBe('0')
    expect(w.find('[data-profile-answer]').text()).toBe('Saya teliti dan cepat')
    expect(w.text()).toContain('Tier modal: 30k')
  })

  it('koreksi mewajibkan alasan dan mengirim skor', async () => {
    const w = await mountPanel()
    await w.find('button[data-score="RC-1"]').trigger('click')
    await w.find('input[data-field="score"]').setValue('75')
    await w.find('button[data-action="save-score"]').trigger('click')
    expect(w.text()).toContain('Alasan wajib')
    expect(apiMock).not.toHaveBeenCalledWith('/api/recruitment/tkd/score',
      expect.objectContaining({ method: 'POST' }))

    await w.find('textarea[data-field="reason"]').setValue('Koreksi hasil')
    await w.find('button[data-action="save-score"]').trigger('click')
    await flushPromises()
    expect(apiMock).toHaveBeenCalledWith('/api/recruitment/tkd/score', {
      method: 'POST', body: { case_id: 'RC-1', score: 75, reason: 'Koreksi hasil' } })
  })

  it('koreksi tanpa attempt mencari kasus lewat NIK', async () => {
    const w = await mountPanel()
    await w.find('button[data-action="manual-search"]').trigger('click')
    await w.find('input[data-field="nik"]').setValue('3573010101990001')
    apiMock.mockResolvedValueOnce({ data: [{ case_id: 'RC-9', nama: 'Budi',
      nik_masked: '****0009', branch_code: 'SBY' }] })
    await w.find('button[data-action="do-search"]').trigger('click')
    await flushPromises()
    expect(apiMock).toHaveBeenCalledWith('/api/recruitment/cases',
      { params: { nik: '3573010101990001' } })
    expect(w.find('input[data-field="nik"]').element.value).toBe('')
    expect(w.text()).toContain('Budi')

    await w.find('button[data-pick-case="RC-9"]').trigger('click')
    await w.find('input[data-field="score"]').setValue('88')
    await w.find('textarea[data-field="reason"]').setValue('Koreksi Budi')
    await w.find('button[data-action="save-score"]').trigger('click')
    await flushPromises()
    expect(apiMock).toHaveBeenCalledWith('/api/recruitment/tkd/score', {
      method: 'POST', body: { case_id: 'RC-9', score: 88, reason: 'Koreksi Budi' } })
  })

  it('menerima skor desimal koma sebagai angka dan menolak 101 serta abc', async () => {
    const w = await mountPanel()
    await w.find('button[data-score="RC-1"]').trigger('click')
    const input = w.find('input[data-field="score"]')
    expect(input.attributes('type')).toBe('text')
    expect(input.attributes('inputmode')).toBe('decimal')
    await input.setValue('75,5')
    await w.find('textarea[data-field="reason"]').setValue('Koreksi desimal')
    await w.find('button[data-action="save-score"]').trigger('click')
    await flushPromises()
    expect(scorePosts()).toHaveLength(1)
    expect(scorePosts()[0][1]).toEqual({
      method: 'POST', body: { case_id: 'RC-1', score: 75.5, reason: 'Koreksi desimal' } })
    expect(typeof scorePosts()[0][1].body.score).toBe('number')

    await w.find('button[data-score="RC-1"]').trigger('click')
    for (const invalid of ['101', 'abc']) {
      await w.find('input[data-field="score"]').setValue(invalid)
      await w.find('textarea[data-field="reason"]').setValue('Alasan')
      await w.find('button[data-action="save-score"]').trigger('click')
      expect(scorePosts()).toHaveLength(1)
      expect(w.find('[data-score-errors]').text()).toContain('Skor harus antara 0 dan 100.')
    }
  })

  it('menyamarkan NIK penuh pada pesan error server', async () => {
    const w = await mountPanel()
    await w.find('button[data-score="RC-1"]').trigger('click')
    await w.find('input[data-field="score"]').setValue('80')
    await w.find('textarea[data-field="reason"]').setValue('Koreksi')
    apiMock.mockRejectedValueOnce(new Error('NIK 3573010101990001 ditolak server'))
    await w.find('button[data-action="save-score"]').trigger('click')
    await flushPromises()
    const text = w.find('[data-score-error]').text()
    expect(text).toContain('****0001')
    expect(text).not.toContain('3573010101990001')
  })

  it('menghapus pesan sukses saat filter diubah atau modal dibuka', async () => {
    const w = await mountPanel()

    async function saveScore(score) {
      await w.find('button[data-score="RC-1"]').trigger('click')
      await w.find('input[data-field="score"]').setValue(score)
      await w.find('textarea[data-field="reason"]').setValue('Koreksi ulang')
      await w.find('button[data-action="save-score"]').trigger('click')
      await flushPromises()
    }

    await saveScore('80')
    expect(w.find('[data-alert="success"]').exists()).toBe(true)
    await w.find('input[data-filter="q"]').setValue('Andi')
    await w.find('button[data-action="apply"]').trigger('click')
    await flushPromises()
    expect(w.find('[data-alert="success"]').exists()).toBe(false)

    await saveScore('81')
    expect(w.find('[data-alert="success"]').exists()).toBe(true)
    await w.find('button[data-action="manual-search"]').trigger('click')
    expect(w.find('[data-alert="success"]').exists()).toBe(false)
  })
})
