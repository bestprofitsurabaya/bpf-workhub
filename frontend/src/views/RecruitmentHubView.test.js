import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createRouter, createMemoryHistory } from 'vue-router'
import RecruitmentHubView from './RecruitmentHubView.vue'

const { apiMock, authMock } = vi.hoisted(() => ({
  apiMock: vi.fn(), authMock: { role: 'traineer', user: { branch_code: 'SBY' } },
}))
vi.mock('../api', () => ({ api: apiMock }))
vi.mock('../stores/auth', () => ({ useAuthStore: () => authMock }))

const STUBS = {
  ReceptionistView: true, RecruitmentCasesView: true, CvOnlineView: true,
  FirstWorkView: true, TkdView: true, RecruitmentLinksView: true,
}

async function mountAt(path, role = 'traineer', badges = {}) {
  authMock.role = role
  apiMock.mockResolvedValue({ badges })
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [{ path: '/recruitment', name: 'recruitment',
               component: RecruitmentHubView }],
  })
  await router.push(path)
  await router.isReady()
  const w = mount(RecruitmentHubView, {
    global: { plugins: [router], stubs: STUBS },
  })
  await flushPromises()
  return w
}

describe('RecruitmentHubView', () => {
  beforeEach(() => vi.clearAllMocks())

  it('traineer melihat enam tab dengan Tautan aktif sesuai query', async () => {
    const w = await mountAt('/recruitment?tab=tautan', 'traineer')
    const labels = w.findAll('[data-tab]').map((b) => b.text())
    expect(labels).toEqual(expect.arrayContaining(
      ['Pelamar', 'Kasus', 'CV Online', 'FirstWork', 'TKD', 'Tautan']))
    expect(w.find('[data-tab="tautan"]').attributes('data-active')).toBe('true')
  })

  it('receptionist hanya melihat Pelamar dan Tautan', async () => {
    const w = await mountAt('/recruitment?tab=tkd', 'receptionist')
    const ids = w.findAll('[data-tab]').map((b) => b.attributes('data-tab'))
    expect(ids).toEqual(['pelamar', 'tautan'])
    expect(w.find('[data-tab="pelamar"]').attributes('data-active')).toBe('true')
  })

  it('finance hanya melihat FirstWork', async () => {
    const w = await mountAt('/recruitment', 'finance')
    const ids = w.findAll('[data-tab]').map((b) => b.attributes('data-tab'))
    expect(ids).toEqual(['firstwork'])
  })

  it('badge antrean tampil di tab CV dan FirstWork', async () => {
    const w = await mountAt('/recruitment?tab=cv', 'admin',
      { cv_online_pending: 3, first_work_pending: 2 })
    expect(w.find('[data-tab="cv"]').text()).toContain('3')
    expect(w.find('[data-tab="firstwork"]').text()).toContain('2')
  })

  it('tab yang tidak dikenal jatuh ke tab pertama yang diizinkan', async () => {
    const w = await mountAt('/recruitment?tab=rahasia', 'finance')
    expect(w.find('[data-tab="firstwork"]').attributes('data-active')).toBe('true')
    expect(w.text()).toContain('🪪 Rekrutmen')
  })
})
