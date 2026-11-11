import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import ProfileView from './ProfileView.vue'

const { apiMock, authMock } = vi.hoisted(() => ({
  apiMock: vi.fn(),
  authMock: {
    role: 'finance',
    meta: { label: 'Finance', icon: '💰', color: '#059669' },
    user: { user_name: 'finance_smg', full_name: 'Finance Semarang', branch_name: 'Cabang Semarang' },
  },
}))
vi.mock('../api', () => ({ api: apiMock }))
vi.mock('../stores/auth', () => ({ useAuthStore: () => authMock }))

const PROFILE = {
  username: 'finance_smg', full_name: 'Finance Semarang', role: 'finance',
  branch_code: 'SMG', branch_name: 'Cabang Semarang', last_login: '2026-11-11 08:00:00',
}

function mountView() {
  apiMock.mockImplementation((path, opts) => {
    if (path === '/api/profile' && (!opts || opts.method === undefined || opts.method === 'GET')) {
      return Promise.resolve({ user: PROFILE })
    }
    if (path === '/api/profile') {
      return Promise.resolve({ status: 'success', msg: 'Tersimpan', user: { ...PROFILE, ...(opts.body.full_name ? { full_name: opts.body.full_name } : {}) } })
    }
    return Promise.resolve({})
  })
  return mount(ProfileView)
}

describe('ProfileView (Profil Saya)', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    authMock.user.full_name = 'Finance Semarang'
  })

  it('memuat profil sendiri dan menampilkan data akun', async () => {
    const w = mountView()
    await flushPromises()
    const txt = w.text()
    expect(apiMock).toHaveBeenCalledWith('/api/profile')
    expect(txt).toContain('finance_smg')
    expect(txt).toContain('Cabang Semarang')
    expect(txt).toContain('Finance')
    expect(w.find('input[placeholder="Nama lengkap"]').element.value).toBe('Finance Semarang')
  })

  it('menyimpan nama tampilan & memperbarui sesi', async () => {
    const w = mountView()
    await flushPromises()
    await w.find('input[placeholder="Nama lengkap"]').setValue('Rina Wati')
    await w.find('form').trigger('submit')
    await flushPromises()
    const call = apiMock.mock.calls.find((c) => c[1]?.method === 'PATCH')
    expect(call[1].body).toEqual({ full_name: 'Rina Wati' })
    expect(authMock.user.full_name).toBe('Rina Wati')
    expect(w.text()).toContain('Tersimpan')
  })

  it('menolak PIN baru yang tidak sama dengan ulangannya (tanpa memanggil API)', async () => {
    const w = mountView()
    await flushPromises()
    const inputs = w.findAll('input[type="password"]')
    await inputs[0].setValue('604128')
    await inputs[1].setValue('731845')
    await inputs[2].setValue('731846')
    await w.findAll('form')[1].trigger('submit')
    await flushPromises()
    expect(apiMock).not.toHaveBeenCalledWith('/api/profile', expect.objectContaining({ method: 'PATCH' }))
    expect(w.text()).toContain('Ulangi PIN baru tidak sama')
  })

  it('mengirim PIN lama & baru saat valid, lalu mengosongkan form', async () => {
    const w = mountView()
    await flushPromises()
    const inputs = w.findAll('input[type="password"]')
    await inputs[0].setValue('604128')
    await inputs[1].setValue('731845')
    await inputs[2].setValue('731845')
    await w.findAll('form')[1].trigger('submit')
    await flushPromises()
    const call = apiMock.mock.calls.find((c) => c[1]?.method === 'PATCH')
    expect(call[1].body).toEqual({ current_pin: '604128', new_pin: '731845' })
    expect(inputs[0].element.value).toBe('')
    expect(inputs[1].element.value).toBe('')
  })

  it('menampilkan pesan error dari server (mis. PIN lemah)', async () => {
    const w = mountView()
    await flushPromises()
    apiMock.mockImplementationOnce(() => Promise.reject(new Error('PIN terlalu lemah — gunakan PIN acak.')))
    const inputs = w.findAll('input[type="password"]')
    await inputs[0].setValue('604128')
    await inputs[1].setValue('123456')
    await inputs[2].setValue('123456')
    await w.findAll('form')[1].trigger('submit')
    await flushPromises()
    expect(w.text()).toContain('PIN terlalu lemah')
  })
})
