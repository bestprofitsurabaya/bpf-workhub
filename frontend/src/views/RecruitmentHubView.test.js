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
  RecruitmentPeopleView: true, TkdView: true, RecruitmentLinksView: true,
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

describe('RecruitmentHubView — tiga tab', () => {
  beforeEach(() => vi.clearAllMocks())

  it('admin melihat tepat tiga tab', async () => {
    const w = await mountAt('/recruitment?tab=pelamar', 'admin')
    const ids = w.findAll('[data-tab]').map((b) => b.attributes('data-tab'))
    expect(ids).toEqual(['pelamar', 'tkd', 'tautan'])
    const labels = w.findAll('[data-tab]').map((b) => b.text())
    expect(labels).toEqual(['Data Rekrutment', 'Soal TKD', 'Tautan Portal'])
  })

  it('receptionist melihat Pelamar dan Tautan', async () => {
    const w = await mountAt('/recruitment?tab=tkd', 'receptionist')
    const ids = w.findAll('[data-tab]').map((b) => b.attributes('data-tab'))
    expect(ids).toEqual(['pelamar', 'tautan'])
    expect(w.find('[data-tab="pelamar"]').attributes('data-active')).toBe('true')
  })

  it('finance hanya melihat Data Rekrutment', async () => {
    const w = await mountAt('/recruitment', 'finance')
    const ids = w.findAll('[data-tab]').map((b) => b.attributes('data-tab'))
    expect(ids).toEqual(['pelamar'])
  })

  it('query lama kasus/cv/firstwork dipetakan ke pelamar', async () => {
    for (const tab of ['kasus', 'cv', 'firstwork']) {
      const w = await mountAt(`/recruitment?tab=${tab}`, 'admin')
      expect(w.find('[data-tab="pelamar"]').attributes('data-active')).toBe('true')
    }
  })
})
