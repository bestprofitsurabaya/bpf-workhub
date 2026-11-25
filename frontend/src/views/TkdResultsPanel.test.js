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

async function mountPanel() {
  apiMock.mockImplementation((path) => {
    if (path === '/api/recruitment/tkd/attempts') return Promise.resolve({ data: ROWS })
    if (path === '/api/recruitment/tkd/review/TKD-1') return Promise.resolve({ data: {
      attempt: { id: 'TKD-1', modal_tier: '30k', score: 60 },
      case: { nama: 'Andi', tkd_score: 60, tkd_score_source: 'AUTO' },
      items: [{ position: 1, snapshot: { prompt: 'P', answer: { option: 'a' }, points: 1 },
                answer: { option: 'b' }, is_correct: 0, points_awarded: 0 }] } })
    return Promise.resolve({ status: 'success' })
  })
  const w = mount(TkdResultsPanel)
  await flushPromises()
  return w
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
    expect(w.text()).toContain('Kunci')
    expect(w.text()).toContain('Poin')
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
    apiMock.mockResolvedValueOnce({ data: [{ case_id: 'RC-9', nama: 'Budi', nik_masked: '****0009' }] })
    await w.find('button[data-action="do-search"]').trigger('click')
    await flushPromises()
    expect(w.text()).toContain('Budi')
  })
})
