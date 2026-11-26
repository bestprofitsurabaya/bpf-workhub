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
    branch_code: 'SBY', stage: 'CV', status: 'AKTIF', last_event: 'CV_SUBMITTED',
    stages: { CV: 'SELESAI' } },
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
        if (String(url).includes('/timeline')) {
          return Promise.resolve({ data: [
            { id: 1, event_type: 'CV_SUBMITTED', event_at: '2026-11-25 09:00:00',
              branch_code: 'JKT', actor_role: 'public' }] })
        }
        return Promise.resolve({ data: {
          case: { nama: 'Budi Santoso', nik_masked: '****0001',
                  first_branch: 'SBY', status: 'AKTIF' },
          cv: { nama: 'Budi Santoso', tempat_lahir: 'Surabaya',
                tanggal_lahir: '1990-01-01', jenis_kelamin: 'Pria',
                no_hp: '081234567890', pendidikan_terakhir: 'S1',
                alamat: 'Jl. Contoh', domisili: 'JAWA TIMUR' },
          first_work: { registration_no: 'FW-SBY-1', branch_code: 'SBY',
                        submitted_at: '2026-11-26 10:00:00' },
          training: [{ id: 1, day: 1, attended_at: '2026-11-26 09:00:00' }],
          tkd: { score: 82, attempt_no: 1 },
          branches: [{ branch_code: 'SBY' }, { branch_code: 'JKT' }],
          steps: [{ step_type: 'CV', status: 'SELESAI' }],
          timeline: [], card_token: 'card' } })
      }
      return Promise.resolve({})
    })
  })

  it('menampilkan daftar orang dengan NIK termasker dan filter', async () => {
    const w = mount(RecruitmentPeopleView)
    await flushPromises()
    expect(w.findAll('tbody tr').length).toBe(2)
    expect(w.text()).toContain('****0001')
    expect(w.text()).toContain('SELESAI')
    expect(apiMock).toHaveBeenCalledWith('/api/recruitment/people', { params: {} })
    await w.find('input[aria-label="Cari nama atau NIK"]').setValue('Budi')
    await flushPromises()
    expect(apiMock.mock.calls.at(-1)[1].params.q).toBe('Budi')
  })

  it('membuka detail lengkap (CV, training, TKD, FirstWork) dan linimasa', async () => {
    const w = mount(RecruitmentPeopleView)
    await flushPromises()
    await w.find('tbody tr').trigger('click')
    await flushPromises()
    for (const section of ['Identitas & kasus', 'Riwayat cabang', 'CV Online',
      'Training H1/H2', 'TKD', 'FirstWork', 'Linimasa']) {
      expect(w.text()).toContain(section)
    }
    expect(w.text()).toContain('CV_SUBMITTED')
    expect(w.text()).toContain('081234567890')
    expect(w.text()).toContain('FW-SBY-1')
    expect(w.text()).toContain('82')
  })

  it('finance read-only tidak menampilkan aksi tulis', async () => {
    authMock.role = 'finance'
    const w = mount(RecruitmentPeopleView, { props: { view: 'firstwork' } })
    await flushPromises()
    await w.find('tbody tr').trigger('click')
    await flushPromises()
    expect(w.find('.rp-actions').exists()).toBe(false)
    expect(w.text()).toContain('FirstWork (akses finance)')
    expect(w.text()).not.toContain('CV Online')
    expect(apiMock.mock.calls[0][1].params.view).toBe('firstwork')
  })
})
