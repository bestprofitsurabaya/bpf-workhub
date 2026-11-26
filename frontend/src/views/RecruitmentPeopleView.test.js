import { beforeEach, describe, expect, it, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import RecruitmentPeopleView from './RecruitmentPeopleView.vue'

const { apiMock, authMock } = vi.hoisted(() => ({
  apiMock: vi.fn(), authMock: { role: 'ga_hr' },
}))
vi.mock('../api', () => ({ api: apiMock }))
vi.mock('../stores/auth', () => ({ useAuthStore: () => authMock }))

const PEOPLE = { data: [
  { case_id: 'RC-1', nama: 'Budi Santoso', nik_masked: '****0001',
    branch_code: 'SBY', stage: 'CV', status: 'AKTIF', last_event: 'CV_SUBMITTED' },
  { case_id: null, display_id: 'PLM-SBY-7', nama: 'Rina', nik_masked: '',
    branch_code: 'SBY', stage: 'interview', status: 'interview',
    last_event: '', link_status: 'unlinked' },
] }

describe('RecruitmentPeopleView', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    authMock.role = 'ga_hr'
    apiMock.mockImplementation((url) => {
      if (url === '/api/recruitment/people') return Promise.resolve(PEOPLE)
      if (String(url).includes('/timeline')) {
        return Promise.resolve({ data: [
          { id: 1, event_type: 'CV_SUBMITTED', event_at: '2026-11-25 09:00:00',
            branch_code: 'JKT', actor_role: 'public', actor_name: '' }] })
      }
      if (String(url).includes('/api/recruitment/people/')) {
        return Promise.resolve({ data: {
          case: { nama: 'Budi Santoso' }, cv: { nama: 'Budi Santoso' },
          first_work: { registration_no: '' }, timeline: [] } })
      }
      return Promise.resolve({})
    })
  })

  it('menampilkan daftar orang dengan NIK termasker dan filter', async () => {
    const w = mount(RecruitmentPeopleView)
    await flushPromises()
    expect(w.findAll('tbody tr').length).toBe(2)
    expect(w.text()).toContain('****0001')
    expect(apiMock).toHaveBeenCalledWith('/api/recruitment/people', { params: {} })
    await w.find('input[aria-label="Cari nama atau NIK"]').setValue('Budi')
    await flushPromises()
    expect(apiMock.mock.calls.at(-1)[1].params.q).toBe('Budi')
  })

  it('membuka detail dan linimasa saat baris diklik', async () => {
    const w = mount(RecruitmentPeopleView)
    await flushPromises()
    await w.find('tbody tr').trigger('click')
    await flushPromises()
    expect(w.text()).toContain('Linimasa')
    expect(w.text()).toContain('CV_SUBMITTED')
  })

  it('finance read-only tidak menampilkan aksi tulis', async () => {
    authMock.role = 'finance'
    const w = mount(RecruitmentPeopleView, { props: { view: 'firstwork' } })
    await flushPromises()
    expect(w.find('.rp-actions').exists()).toBe(false)
    expect(apiMock.mock.calls[0][1].params.view).toBe('firstwork')
  })
})
