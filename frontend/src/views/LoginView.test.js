import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import LoginView from './LoginView.vue'

const { authMock, pushMock } = vi.hoisted(() => ({
  authMock: { login: vi.fn(), user: null, isAuthenticated: false },
  pushMock: vi.fn(),
}))

vi.mock('../stores/auth', () => ({
  useAuthStore: () => authMock,
  ROLE_META: { admin: { home: '/dashboard' }, driver: { home: '/driver' } },
}))
vi.mock('../stores/identity', () => ({
  identity: {
    system_name: 'BPF WorkHub',
    company_name: 'PT BESTPROFIT FUTURES',
    // Nilai asli identitas: masih dipakai kop dokumen resmi (PDF).
    company_subtitle: 'Kantor Pusat | Jakarta',
  },
}))
vi.mock('vue-router', () => ({
  useRouter: () => ({ push: pushMock }),
  useRoute: () => ({ query: {} }),
}))

describe('LoginView — motto brand (v2.128.4)', () => {
  beforeEach(() => vi.clearAllMocks())

  it('menampilkan motto, bukan nama kota kantor pusat', () => {
    const w = mount(LoginView)
    expect(w.find('.brand-motto').text()).toBe('Satu Platform, Semua Operasional')
    // Teks lama tidak boleh muncul lagi di halaman login.
    expect(w.text()).not.toContain('Jakarta')
    expect(w.text()).not.toContain('Kantor Pusat')
    expect(w.find('.brand-city').exists()).toBe(false)
  })

  it('motto tampil bersama nama sistem & perusahaan', () => {
    const w = mount(LoginView)
    const text = w.text()
    expect(text).toContain('BPF WorkHub')
    expect(text).toContain('PT BESTPROFIT FUTURES')
    expect(text).toContain('Satu Platform, Semua Operasional')
  })

  it('login tetap mengirim username + PIN dan redirect ke home role', async () => {
    authMock.login.mockResolvedValue({
      status: 'success',
      user: { role: 'admin', user_name: 'admin' },
    })
    const w = mount(LoginView)
    await w.find('input[placeholder="Masukkan username"]').setValue('admin')
    await w.find('input[placeholder="••••••"]').setValue('123456')
    await w.find('form').trigger('submit')
    await flushPromises()

    expect(authMock.login).toHaveBeenCalledWith('admin', '123456')
    expect(pushMock).toHaveBeenCalledWith('/dashboard')
  })
})
