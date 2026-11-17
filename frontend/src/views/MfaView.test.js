import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import MfaView from './MfaView.vue'

const { apiMock, authMock, routerMock } = vi.hoisted(() => ({
  apiMock: vi.fn(),
  authMock: {
    ready: true,
    isAuthenticated: false,
    mfaPending: true,
    mfaMode: 'verify',
    mfaUsername: 'finance_smg',
    user: null,
    completeMfa: vi.fn((d) => {
      authMock.user = d?.user || null
      authMock.mfaPending = false
      return d
    }),
    logout: vi.fn(),
    bootstrap: vi.fn(() => Promise.resolve(false)),
  },
  routerMock: { push: vi.fn(), replace: vi.fn() },
}))

vi.mock('../api', () => ({ api: apiMock }))
vi.mock('../stores/auth', () => ({
  useAuthStore: () => authMock,
  ROLE_META: { finance: { home: '/finance' }, admin: { home: '/dashboard' } },
}))
vi.mock('../stores/identity', () => ({
  identity: { system_name: 'BPF WorkHub', company_name: 'PT Bestprofit Futures' },
}))
vi.mock('vue-router', () => ({ useRouter: () => routerMock }))

function resetAuth(mode = 'verify') {
  authMock.ready = true
  authMock.isAuthenticated = false
  authMock.mfaPending = true
  authMock.mfaMode = mode
  authMock.mfaUsername = 'finance_smg'
  authMock.user = null
}

describe('MfaView (login dua langkah)', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    resetAuth('verify')
  })

  it('menampilkan form kode 6 digit saat mode verifikasi', async () => {
    apiMock.mockResolvedValue({})
    const w = mount(MfaView)
    await flushPromises()
    expect(w.text()).toContain('Verifikasi Dua Langkah')
    expect(w.text()).toContain('finance_smg')
    const input = w.find('#mfa-code')
    expect(input.exists()).toBe(true)
    expect(input.attributes('maxlength')).toBe('6')
  })

  it('mengirim kode TOTP lalu menyelesaikan sesi dan redirect ke home role', async () => {
    apiMock.mockResolvedValue({
      status: 'success',
      user: { role: 'finance', user_name: 'finance_smg' },
      csrf_token: 'tok',
      home: '/finance',
    })
    const w = mount(MfaView)
    await flushPromises()
    const input = w.find('#mfa-code')
    await input.setValue('123456')
    await w.find('form').trigger('submit')
    await flushPromises()

    expect(apiMock).toHaveBeenCalledWith('/api/auth/mfa/verify', {
      method: 'POST',
      body: { code: '123456' },
    })
    expect(authMock.completeMfa).toHaveBeenCalled()
    expect(routerMock.push).toHaveBeenCalledWith('/finance')
  })

  it('menolak submit bila kode kurang dari 6 digit (tanpa memanggil API)', async () => {
    apiMock.mockResolvedValue({})
    const w = mount(MfaView)
    await flushPromises()
    await w.find('#mfa-code').setValue('123')
    await w.find('form').trigger('submit')
    await flushPromises()
    expect(apiMock).not.toHaveBeenCalledWith('/api/auth/mfa/verify', expect.anything())
    expect(w.text()).toContain('6 digit')
  })

  it('mode kode pemulihan mengirim recovery_code', async () => {
    apiMock.mockResolvedValue({
      status: 'success',
      user: { role: 'finance', user_name: 'finance_smg' },
      csrf_token: 'tok',
      recovery_used: true,
    })
    const w = mount(MfaView)
    await flushPromises()
    const toggle = w.findAll('button').find((b) => b.text().includes('Gunakan kode pemulihan'))
    expect(toggle).toBeTruthy()
    await toggle.trigger('click')
    await flushPromises()
    const input = w.find('#mfa-recovery')
    expect(input.exists()).toBe(true)
    await input.setValue('ABCDE-12345')
    await w.find('form').trigger('submit')
    await flushPromises()
    expect(apiMock).toHaveBeenCalledWith('/api/auth/mfa/verify', {
      method: 'POST',
      body: { recovery_code: 'ABCDE-12345' },
    })
    expect(routerMock.push).toHaveBeenCalledWith('/finance')
  })

  it('mode pendaftaran menampilkan QR + kunci manual, lalu kode pemulihan', async () => {
    resetAuth('enroll')
    apiMock.mockImplementation((path) => {
      if (path === '/api/auth/mfa/enroll/start') {
        return Promise.resolve({
          status: 'success',
          secret: 'JBSWY3DPEHPK3PXP',
          qr: 'data:image/svg+xml;base64,PHN2Zy8+',
          otpauth_uri: 'otpauth://totp/x',
        })
      }
      if (path === '/api/auth/mfa/enroll/confirm') {
        return Promise.resolve({
          status: 'success',
          user: { role: 'finance', user_name: 'finance_smg' },
          csrf_token: 'tok',
          recovery_codes: ['AAAAA-11111', 'BBBBB-22222'],
        })
      }
      return Promise.resolve({})
    })
    const w = mount(MfaView)
    await flushPromises()

    expect(apiMock).toHaveBeenCalledWith('/api/auth/mfa/enroll/start', { method: 'POST' })
    expect(w.text()).toContain('JBSWY3DPEHPK3PXP')
    expect(w.text()).toContain('Microsoft Authenticator')

    await w.find('#enroll-code').setValue('654321')
    await w.find('form').trigger('submit')
    await flushPromises()

    expect(apiMock).toHaveBeenCalledWith('/api/auth/mfa/enroll/confirm', {
      method: 'POST',
      body: { code: '654321' },
    })
    expect(w.text()).toContain('AAAAA-11111')
    expect(w.text()).toContain('BBBBB-22222')
    expect(w.text()).toContain('kode pemulihan')
  })

  it('tombol batal memanggil logout', async () => {
    apiMock.mockResolvedValue({})
    const w = mount(MfaView)
    await flushPromises()
    const cancel = w.findAll('button').find((b) => b.text().includes('login ulang'))
    expect(cancel).toBeTruthy()
    await cancel.trigger('click')
    expect(authMock.logout).toHaveBeenCalled()
  })
})
