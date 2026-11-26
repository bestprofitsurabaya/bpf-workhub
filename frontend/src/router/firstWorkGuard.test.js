import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import RecruitmentHubView from '../views/RecruitmentHubView.vue'

const { apiMock, authMock } = vi.hoisted(() => ({
  apiMock: vi.fn(),
  authMock: {
    ready: true, isAuthenticated: true, role: 'traineer', mfaPending: false,
    bootstrap: vi.fn(),
  },
}))
vi.mock('../api', () => ({ api: apiMock }))
vi.mock('../stores/auth', () => ({ useAuthStore: () => authMock, ROLE_META: {} }))

import router from './index'

const STUBS = {
  ReceptionistView: true, RecruitmentCasesView: true, CvOnlineView: true,
  FirstWorkView: true, TkdView: true, RecruitmentLinksView: true,
}

describe('guard /first-work', () => {
  beforeEach(() => {
    authMock.ready = true
    authMock.isAuthenticated = true
    authMock.role = 'traineer'
    authMock.mfaPending = false
  })

  it('user terautentikasi diarahkan ke tab FirstWork dengan query dibawa', async () => {
    await router.push('/403') // pastikan rute sebelumnya bukan /first-work
    await router.push('/first-work?branch=SBY')
    expect(router.currentRoute.value.fullPath).toBe('/recruitment?branch=SBY&tab=firstwork')
  })

  it('pendaftar tanpa login tetap masuk ke form publik', async () => {
    await router.push('/403') // pastikan rute sebelumnya bukan /first-work
    authMock.isAuthenticated = false
    await router.push('/first-work?branch=SBY')
    expect(router.currentRoute.value.name).toBe('first-work-form')
    expect(router.currentRoute.value.query.branch).toBe('SBY')
  })

  it('role di luar hub (/cv-online) ditolak oleh meta peran rute tujuan', async () => {
    await router.push('/403') // reset navigasi sebelumnya
    authMock.role = 'driver'
    await router.push('/cv-online')
    expect(router.currentRoute.value.name).toBe('forbidden')
    expect(router.currentRoute.value.path).toBe('/403')
  })

  it('finance membuka /cv-online dan mendarat di tab FirstWork di hub', async () => {
    await router.push('/403') // reset navigasi sebelumnya
    authMock.role = 'finance'
    apiMock.mockResolvedValue({ badges: {} })
    await router.push('/cv-online')
    expect(router.currentRoute.value.path).toBe('/recruitment')
    expect(router.currentRoute.value.name).toBe('recruitment')

    // Hub yang terpasang menormalkan ?tab=cv ke tab firstwork yang diizinkan finance.
    const w = mount(RecruitmentHubView, {
      global: { plugins: [router], stubs: STUBS },
    })
    await flushPromises()
    expect(router.currentRoute.value.query.tab).toBe('firstwork')
    expect(w.find('[data-tab="firstwork"]').attributes('data-active')).toBe('true')
    w.unmount()
  })
})
