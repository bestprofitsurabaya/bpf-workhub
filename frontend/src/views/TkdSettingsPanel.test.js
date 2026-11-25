import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import TkdSettingsPanel from './TkdSettingsPanel.vue'

const { apiMock, authMock } = vi.hoisted(() => ({
  apiMock: vi.fn(), authMock: { role: 'traineer' },
}))
vi.mock('../api', () => ({ api: apiMock }))
vi.mock('../stores/auth', () => ({ useAuthStore: () => authMock }))

const SETTINGS = { question_count: 20, duration_minutes: 25, pass_score: 70,
  max_attempts: 2, quota: { REGULASI: 7, PERUSAHAAN: 4, PRODUK: 6, HITUNG: 3 },
  shuffle_options: 1, active: 0,
  readiness: { ready: true, active_valued: 30, quota_ok: {}, tier_ok: {}, reasons: [] } }

async function mountPanel(role = 'traineer') {
  authMock.role = role
  apiMock.mockResolvedValue({ data: SETTINGS })
  const w = mount(TkdSettingsPanel)
  await flushPromises()
  return w
}

describe('TkdSettingsPanel', () => {
  beforeEach(() => vi.clearAllMocks())

  it('menampilkan angka dan kesiapan bank', async () => {
    const w = await mountPanel('admin')
    expect(w.text()).toContain('30')
    expect(w.find('input[data-field="max_attempts"]').element.disabled).toBe(true)
  })

  it('traineer tidak bisa menyimpan pengaturan', async () => {
    const w = await mountPanel('traineer')
    expect(w.find('button[data-action="save"]').element.disabled).toBe(true)
    expect(w.text()).toContain('Hanya admin')
  })

  it('admin menyimpan kuota dan status aktif', async () => {
    const w = await mountPanel('admin')
    await w.find('input[data-field="question_count"]').setValue('20')
    await w.find('button[data-action="save"]').trigger('click')
    await flushPromises()
    expect(apiMock).toHaveBeenCalledWith('/api/recruitment/tkd/settings', {
      method: 'PUT',
      body: expect.objectContaining({ question_count: 20, max_attempts: 2 }),
    })
  })
})
