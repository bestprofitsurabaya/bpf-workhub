import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'

const { apiMock } = vi.hoisted(() => ({ apiMock: vi.fn() }))
vi.mock('../api', () => ({ api: apiMock }))

import { useStepupStore } from '../stores/stepup'
import { useAuthStore } from '../stores/auth'
import StepUpModal from './StepUpModal.vue'

describe('StepUpModal', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    setActivePinia(createPinia())
    const auth = useAuthStore()
    auth.user = { role: 'finance', user_name: 'finance_sby', full_name: 'Rina' }
  })

  const stepupError = () => {
    const e = new Error('Step-up diperlukan')
    e.status = 428
    e.data = { code: 'STEPUP_REQUIRED', msg: e.message }
    return e
  }

  // Buka modal lewat alur nyata (require → 428) supaya aksi tertunda tersimpan
  async function openModal(store, label = 'mencairkan dana klaim ini') {
    const action = vi.fn().mockRejectedValueOnce(stepupError())
    const pending = store.require(action, label)
    await flushPromises()
    const w = mount(StepUpModal)
    await flushPromises()
    return { w, action, pending }
  }

  it('tersembunyi saat modal tidak terbuka', () => {
    const w = mount(StepUpModal)
    expect(w.find('.modal-overlay').exists()).toBe(false)
  })

  it('menampilkan label aksi & user, lalu mengirim PIN ke /api/step-up', async () => {
    const store = useStepupStore()
    apiMock.mockResolvedValueOnce({ status: 'success', expires_in: 600 })
    const { w } = await openModal(store)

    expect(w.text()).toContain('mencairkan dana klaim ini')
    expect(w.text()).toContain('Finance Surabaya')

    await w.find('input[type="password"]').setValue('246810')
    await w.findAll('button').find((b) => b.text().includes('Verifikasi')).trigger('click')
    await flushPromises()

    expect(apiMock).toHaveBeenCalledWith('/api/step-up', { method: 'POST', body: { pin: '246810' } })
    expect(store.busy).toBe(false)
    expect(store.open).toBe(false)
  })

  it('PIN kosong: tombol nonaktif & Enter tidak mengirim apa pun', async () => {
    const store = useStepupStore()
    const { w } = await openModal(store)
    const submitBtn = w.findAll('button').find((b) => b.text().includes('Verifikasi'))
    expect(submitBtn.attributes('disabled')).toBeDefined() // PIN kosong → terkunci
    // Enter tetap memicu handler guard: PIN wajib diisi, tidak ada request
    await w.find('input[type="password"]').trigger('keyup.enter')
    await flushPromises()
    expect(w.text()).toContain('PIN wajib diisi')
    expect(apiMock).not.toHaveBeenCalled()
    expect(store.open).toBe(true)
  })

  it('PIN salah: menampilkan error server dan modal tetap terbuka', async () => {
    const store = useStepupStore()
    const badPin = new Error('PIN salah')
    badPin.status = 401
    apiMock.mockRejectedValueOnce(badPin)
    const { w } = await openModal(store)

    await w.find('input[type="password"]').setValue('000000')
    await w.findAll('button').find((b) => b.text().includes('Verifikasi')).trigger('click')
    await flushPromises()

    expect(w.text()).toContain('PIN salah')
    expect(store.open).toBe(true)
  })

  it('tombol Batal menutup modal', async () => {
    const store = useStepupStore()
    const { w, pending } = await openModal(store)
    await w.findAll('button').find((b) => b.text().includes('Batal')).trigger('click')
    await flushPromises()
    expect(store.open).toBe(false)
    await expect(pending).resolves.toBeUndefined()
  })
})