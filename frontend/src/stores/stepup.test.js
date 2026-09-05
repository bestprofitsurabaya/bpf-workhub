import { describe, it, expect, vi, beforeEach } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { flushPromises } from '@vue/test-utils'

const { apiMock } = vi.hoisted(() => ({ apiMock: vi.fn() }))
vi.mock('../api', () => ({ api: apiMock }))

import { useStepupStore } from './stepup'

const stepupError = (msg = 'Step-up diperlukan') => {
  const e = new Error(msg)
  e.status = 428
  e.data = { code: 'STEPUP_REQUIRED', msg }
  return e
}

describe('stepup store', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    setActivePinia(createPinia())
  })

  it('aksi sukses tanpa step-up: langsung selesai, modal tidak terbuka', async () => {
    const store = useStepupStore()
    apiMock.mockResolvedValueOnce({ status: 'success' })
    const r = await store.require(() => apiMock('/api/queue/payout/1', { method: 'POST' }))
    expect(r).toEqual({ status: 'success' })
    expect(store.open).toBe(false)
    expect(apiMock).toHaveBeenCalledWith('/api/queue/payout/1', { method: 'POST' })
  })

  it('428 STEPUP_REQUIRED: modal terbuka, aksi dijalankan ulang setelah PIN valid', async () => {
    const store = useStepupStore()
    const action = vi.fn()
    action
      .mockRejectedValueOnce(stepupError())
      .mockResolvedValueOnce({ status: 'success', msg: 'Dana dicairkan' })

    apiMock.mockResolvedValueOnce({ status: 'success', expires_in: 600 }) // /api/step-up

    const pending = store.require(action, 'mencairkan dana')
    await flushPromises() // biarkan 428 tertangkap & modal terbuka
    expect(store.open).toBe(true)
    expect(store.label).toBe('mencairkan dana')

    await store.submit('123456')
    const r = await pending

    expect(apiMock).toHaveBeenCalledWith('/api/step-up', { method: 'POST', body: { pin: '123456' } })
    expect(action).toHaveBeenCalledTimes(2) // gagal 428 → retry setelah PIN
    expect(r).toEqual({ status: 'success', msg: 'Dana dicairkan' })
    expect(store.open).toBe(false)
  })

  it('PIN salah: modal tetap terbuka dengan pesan error, tidak retry aksi', async () => {
    const store = useStepupStore()
    const action = vi.fn().mockRejectedValueOnce(stepupError())

    const badPin = new Error('PIN salah')
    badPin.status = 401
    apiMock.mockRejectedValueOnce(badPin)

    const pending = store.require(action, 'menyetujui')
    await flushPromises()
    await store.submit('000000')

    expect(store.open).toBe(true) // masih terbuka
    expect(store.err).toBe('PIN salah')
    expect(action).toHaveBeenCalledTimes(1) // belum di-retry
    await store.cancel()
    await pending // resolve undefined — tidak hang
  })

  it('retry aksi gagal lagi (mis. sudah diproses): error diteruskan ke pemanggil', async () => {
    const store = useStepupStore()
    const action = vi.fn()
    const raceErr = new Error('Transaksi sudah diproses.')
    raceErr.status = 409
    action.mockRejectedValueOnce(stepupError()).mockRejectedValueOnce(raceErr)
    apiMock.mockResolvedValueOnce({ status: 'success' })

    const pending = store.require(action, 'menyetujui klaim')
    await flushPromises()
    await store.submit('123456')
    await expect(pending).rejects.toThrow('Transaksi sudah diproses.')
    expect(store.open).toBe(false)
  })

  it('batal: modal tertutup dan pemanggil dilanjutkan tanpa error', async () => {
    const store = useStepupStore()
    const action = vi.fn().mockRejectedValueOnce(stepupError())
    const pending = store.require(action, 'menyetujui')
    await flushPromises()
    await store.cancel()
    expect(await pending).toBeUndefined()
    expect(store.open).toBe(false)
    expect(store._action).toBeNull()
  })

  it('error non-step-up (mis. 409/500) diteruskan apa adanya, modal tidak terbuka', async () => {
    const store = useStepupStore()
    const forbidden = new Error('Role tidak diizinkan')
    forbidden.status = 403
    const action = vi.fn().mockRejectedValueOnce(forbidden)
    await expect(store.require(action, 'x')).rejects.toThrow('Role tidak diizinkan')
    expect(store.open).toBe(false)
  })
})