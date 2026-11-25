import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import TkdBankPanel from './TkdBankPanel.vue'

const { apiMock } = vi.hoisted(() => ({ apiMock: vi.fn() }))
vi.mock('../api', () => ({ api: apiMock }))

const QUESTIONS = [
  { id: 1, code: 'REG-01', category: 'REGULASI', type: 'MCQ',
    prompt: 'Pengawas PBK', options: [{ id: 'a', text: 'Bappebti' }],
    answer: { option: 'a' }, points: 1, modal_tier: null, active: 1 },
  { id: 2, code: 'HIT-30-01', category: 'HITUNG', type: 'NUMERIC',
    prompt: 'Laba Ibu Dian', options: [], answer: { value: 56400.3, tolerance: 1 },
    points: 1, modal_tier: '30k', active: 0 },
]

async function mountPanel() {
  apiMock.mockResolvedValue({ data: QUESTIONS })
  const w = mount(TkdBankPanel)
  await flushPromises()
  return w
}

describe('TkdBankPanel', () => {
  beforeEach(() => vi.clearAllMocks())

  it('memuat dan menampilkan soal beserta status', async () => {
    const w = await mountPanel()
    expect(apiMock).toHaveBeenCalledWith('/api/recruitment/tkd/questions', { params: {} })
    const text = w.text()
    expect(text).toContain('REG-01')
    expect(text).toContain('HIT-30-01')
    expect(text).toContain('Aktif')
  })

  it('filter kategori dikirim ke API', async () => {
    const w = await mountPanel()
    await w.find('select[data-filter="category"]').setValue('HITUNG')
    await w.find('button[data-action="apply"]').trigger('click')
    await flushPromises()
    expect(apiMock).toHaveBeenLastCalledWith('/api/recruitment/tkd/questions',
      { params: { category: 'HITUNG' } })
  })

  it('form tambah memvalidasi kunci MCQ sebelum POST', async () => {
    const w = await mountPanel()
    await w.find('button[data-action="new"]').trigger('click')
    await w.find('input[data-field="code"]').setValue('NEW-1')
    await w.find('select[data-field="category"]').setValue('PRODUK')
    await w.find('select[data-field="type"]').setValue('MCQ')
    await w.find('textarea[data-field="prompt"]').setValue('Pertanyaan')
    await w.find('input[data-field="option_a"]').setValue('A')
    await w.find('input[data-field="option_b"]').setValue('B')
    await w.find('button[data-action="save"]').trigger('click')
    expect(w.text()).toContain('Kunci jawaban wajib dipilih')
    expect(apiMock).not.toHaveBeenCalledWith('/api/recruitment/tkd/questions',
      expect.objectContaining({ method: 'POST' }))
  })

  it('toggle memanggil endpoint dan memuat ulang', async () => {
    const w = await mountPanel()
    apiMock.mockResolvedValueOnce({ status: 'success' })
    apiMock.mockResolvedValueOnce({ data: QUESTIONS })
    await w.find('button[data-toggle="1"]').trigger('click')
    await flushPromises()
    expect(apiMock).toHaveBeenCalledWith('/api/recruitment/tkd/questions/1/toggle', { method: 'POST' })
  })

  it('preview menampilkan kunci khusus staff', async () => {
    const w = await mountPanel()
    await w.find('button[data-preview="1"]').trigger('click')
    expect(w.text()).toContain('Kunci')
    expect(w.text()).toContain('Bappebti')
  })
})
