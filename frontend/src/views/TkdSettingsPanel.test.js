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

async function mountPanel(role = 'traineer', configureApi = () => {}) {
  authMock.role = role
  apiMock.mockResolvedValue({ data: SETTINGS })
  configureApi(apiMock)
  const w = mount(TkdSettingsPanel)
  await flushPromises()
  return w
}

function putCalls() {
  return apiMock.mock.calls.filter(([, options]) => options?.method === 'PUT')
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

  it('gagal memuat tidak mengirim PUT sampai GET berhasil saat muat ulang', async () => {
    const w = await mountPanel('admin', (api) =>
      api.mockRejectedValueOnce(new Error('Jaringan putus')))
    expect(w.find('[data-alert="error"]').text()).toContain('Jaringan putus')
    const save = w.find('button[data-action="save"]')
    expect(save.element.disabled).toBe(true)
    save.element.removeAttribute('disabled')
    await save.trigger('click')
    await flushPromises()
    expect(putCalls()).toHaveLength(0)

    const reload = w.find('button[data-action="reload"]')
    expect(reload.exists()).toBe(true)
    await reload.trigger('click')
    await flushPromises()
    expect(w.find('[data-alert="error"]').exists()).toBe(false)
    expect(w.find('button[data-action="save"]').element.disabled).toBe(false)
  })

  it('traineer tidak bisa menyimpan meski tombol dipaksa diklik', async () => {
    const w = await mountPanel('traineer')
    const save = w.find('button[data-action="save"]')
    expect(save.element.disabled).toBe(true)
    save.element.removeAttribute('disabled')
    await save.trigger('click')
    await flushPromises()
    expect(putCalls()).toHaveLength(0)
  })

  it('traineer tidak bisa mengubah field apa pun', async () => {
    const w = await mountPanel('traineer')
    const fields = w.findAll('input[data-field]')
    expect(fields.length).toBeGreaterThan(0)
    fields.forEach((field) => expect(field.element.disabled).toBe(true))
  })

  it('kuota desimal dan negatif dinormalisasi sebelum disimpan', async () => {
    const w = await mountPanel('admin')
    await w.find('input[data-quota="REGULASI"]').setValue('2.5')
    await w.find('input[data-quota="HITUNG"]').setValue('-3')
    await w.find('button[data-action="save"]').trigger('click')
    await flushPromises()
    expect(putCalls()).toHaveLength(1)
    const [url, options] = putCalls()[0]
    expect(url).toBe('/api/recruitment/tkd/settings')
    expect(options.body.quota.REGULASI).toBe(3)
    expect(options.body.quota.HITUNG).toBe(0)
    expect(Object.values(options.body.quota).every(Number.isInteger)).toBe(true)
  })

  it('penyebut kesiapan memakai jumlah soal dari server', async () => {
    const w = await mountPanel('admin')
    expect(w.find('[data-readiness]').text()).toContain('30/20')
    await w.find('input[data-field="question_count"]').setValue('99')
    await flushPromises()
    expect(w.find('[data-readiness]').text()).toContain('30/20')
  })

  it('kartu kesiapan tidak ditampilkan saat pengaturan masih dimuat', async () => {
    authMock.role = 'admin'
    apiMock.mockResolvedValue({ data: SETTINGS })
    const w = mount(TkdSettingsPanel)
    expect(w.find('[data-readiness]').exists()).toBe(false)
    await flushPromises()
    expect(w.find('[data-readiness]').exists()).toBe(true)
  })
})
