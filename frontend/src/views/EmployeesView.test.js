import { beforeEach, describe, expect, it, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createRouter, createMemoryHistory } from 'vue-router'
import EmployeesView from './EmployeesView.vue'

const { apiMock, authMock } = vi.hoisted(() => ({
  apiMock: vi.fn(), authMock: { role: 'receptionist' },
}))
vi.mock('../api', () => ({ api: apiMock }))
vi.mock('../stores/auth', () => ({ useAuthStore: () => authMock }))

const EMPLOYEE = { id: 1, nama: 'Budi', nik_masked: '****0001', jabatan: 'Business Consultant',
                   branch_code: 'SBY', status: 'IN', needs_nik: 0 }

async function mountAt(path = '/employees') {
  authMock.role = 'receptionist'
  apiMock.mockImplementation((url) => {
    if (url === '/api/employees') return Promise.resolve({ data: [EMPLOYEE] })
    if (String(url).startsWith('/api/employees/1')) {
      return Promise.resolve({ data: { ...EMPLOYEE, employee_no: 'KRY-SBY-00001',
                                        events: [] } })
    }
    return Promise.resolve({ status: 'success' })
  })
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [{ path: '/employees', name: 'employees', component: EmployeesView }],
  })
  await router.push(path)
  await router.isReady()
  const w = mount(EmployeesView, { global: { plugins: [router] } })
  await flushPromises()
  return w
}

describe('EmployeesView', () => {
  beforeEach(() => { vi.clearAllMocks() })

  it('menampilkan status Di Kantor dan tombol Keluar', async () => {
    const w = await mountAt()
    expect(w.text()).toContain('Di Kantor')
    expect(w.text()).toContain('Keluar')
    expect(w.text()).toContain('****0001')
  })

  it('mengirim arah OUT saat tombol Keluar ditekan', async () => {
    const w = await mountAt()
    await w.find('[data-action="out"]').trigger('click')
    await flushPromises()
    expect(apiMock).toHaveBeenCalledWith('/api/employees/1/attendance', {
      method: 'POST', body: { direction: 'OUT', note: '' },
    })
  })

  it('arsip in-out bersifat read-only', async () => {
    const w = await mountAt('/employees?archive=1')
    expect(w.text()).toContain('Arsip In-Out lama')
    expect(w.find('[data-action="out"]').exists()).toBe(false)
  })
})
