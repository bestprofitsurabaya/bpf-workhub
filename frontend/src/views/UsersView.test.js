import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import UsersView from './UsersView.vue'
import { useAuthStore } from '../stores/auth'

const { apiMock } = vi.hoisted(() => ({ apiMock: vi.fn() }))
vi.mock('../api', () => ({ api: apiMock }))

const USERS = [
  { id: 1, username: 'ga1', full_name: 'GA Satu', role: 'ga', team_name: '', branch_code: '', is_active: true, last_login: null },
  { id: 2, username: 'fin1', full_name: 'FIN Satu', role: 'finance', team_name: '', branch_code: 'SBY', is_active: false, last_login: '2026-08-10' },
]

async function mountView() {
  const pinia = createPinia()
  setActivePinia(pinia)
  const auth = useAuthStore()
  auth.user = { role: 'admin', full_name: 'Administrator', user_name: 'admin' }
  apiMock.mockImplementation((path) => {
    if (path === '/api/users') return Promise.resolve(USERS)
    if (path === '/api/branches') return Promise.resolve({ branches: [{ code: 'SBY', name: 'Surabaya' }] })
    return Promise.resolve({ status: 'success', msg: 'saved' })
  })
  const w = mount(UsersView, {
    global: { plugins: [pinia] },
  })
  await flushPromises()
  return w
}

describe('UsersView', () => {
  beforeEach(() => { vi.clearAllMocks() })

  it('menampilkan daftar user dengan nama asli menonjol + username di bawahnya', async () => {
    const w = await mountView()
    const rows = w.findAll('tbody tr')
    // Nama orang tampil sebagai teks utama; username login tetap terlihat di sel yang sama
    expect(w.text()).toContain('GA Satu')
    expect(w.text()).toContain('ga1')
    expect(w.text()).toContain('FIN Satu')
    expect(w.text()).toContain('fin1')
    // teks nama tampil SEBELUM username dalam sel pertama baris (urutan visual)
    const firstCell = rows[0].find('td:nth-child(2)')
    const cellText = firstCell.text()
    expect(cellText.indexOf('GA Satu')).toBeLessThan(cellText.indexOf('ga1'))
    expect(w.text()).toContain('GA Officer')
    expect(w.text()).toContain('Nonaktif')
  })

  it('toggle aktif TIDAK mengirim field pin (PIN user dipertahankan)', async () => {
    const w = await mountView()
    const rows = w.findAll('tbody tr')
    const firstRow = rows[0]
    const toggleBtn = firstRow.findAll('button').find(b => b.text() === '🚫')
    expect(toggleBtn).toBeTruthy()
    await toggleBtn.trigger('click')
    await flushPromises()
    const call = apiMock.mock.calls.find((c) => c[0] === '/api/users/sync')
    expect(call).toBeTruthy()
    const body = call[1].body
    expect(body.is_active).toBe(false)
    expect('pin' in body).toBe(false)
  })

  it('hapus user TIDAK mengirim field pin dan menonaktifkan user', async () => {
    const w = await mountView()
    const rows = w.findAll('tbody tr')
    const firstRow = rows[0]
    const deleteBtn = firstRow.findAll('button').find(b => b.text() === '🗑')
    expect(deleteBtn).toBeTruthy()
    await deleteBtn.trigger('click')
    await flushPromises()
    const confirmBtn = w.findAll('button').find(b => b.text().includes('Nonaktifkan'))
    expect(confirmBtn).toBeTruthy()
    await confirmBtn.trigger('click')
    await flushPromises()
    const call = apiMock.mock.calls.find((c) => c[0] === '/api/users/sync')
    expect(call[1].body.is_active).toBe(false)
    expect('pin' in call[1].body).toBe(false)
  })

  it('edit user: username bisa diganti, simpan mengirim id & branch_code', async () => {
    const w = await mountView()
    const rows = w.findAll('tbody tr')
    const editBtn = rows[0].findAll('button').find(b => b.text() === '✏️')
    expect(editBtn).toBeTruthy()
    await editBtn.trigger('click')
    await flushPromises()

    // Username TIDAK disabled saat edit (admin boleh mengganti nama login)
    const usernameInput = w.findAll('input').find(i => i.attributes('placeholder')?.includes('huruf kecil'))
    expect(usernameInput).toBeTruthy()
    expect(usernameInput.attributes('disabled')).toBeUndefined()
    await usernameInput.setValue('ga1_baru')

    // Ganti cabang user
    const branchSelect = w.findAll('select').find(s => [...s.findAll('option')].some(o => o.text() === 'Pusat'))
    expect(branchSelect).toBeTruthy()
    await branchSelect.setValue('SBY')

    const saveBtn = w.findAll('button').find(b => b.text().includes('Simpan'))
    expect(saveBtn.attributes('disabled')).toBeUndefined()
    await saveBtn.trigger('click')
    await flushPromises()

    const call = apiMock.mock.calls.find((c) => c[0] === '/api/users/sync')
    expect(call).toBeTruthy()
    expect(call[1].body.id).toBe(1)
    expect(call[1].body.username).toBe('ga1_baru')
    expect(call[1].body.branch_code).toBe('SBY')
  })

  it('form tambah user: helper text menampilkan contoh pola username per role', async () => {
    const w = await mountView()
    const addBtn = w.findAll('button').find(b => b.text().includes('Tambah User'))
    await addBtn.trigger('click')
    await flushPromises()
    // Default role 'ga' (cabang fallback 'sby') → contoh ga_sby
    expect(w.text()).toContain('contoh: ga_sby')
    // Ganti role ke ob → contoh ob_sby + catatan nama bila >1 orang
    // (select role di MODAL = yang punya opsi role tapi bukan filter 'Semua Role')
    const roleSelect = w.findAll('select').find(s => {
      const opts = s.findAll('option').map(o => o.text())
      return opts.includes('🚰 OB') && !opts.some(t => t.includes('Semua Role'))
    })
    await roleSelect.setValue('ob')
    await flushPromises()
    expect(w.text()).toContain('contoh: ob_sby')
    expect(w.text()).toContain('ob_faisol_sby')
  })

  it('tambah user: simpan mengirim pin saat diisi', async () => {
    const w = await mountView()
    // Click "Tambah User" button
    const addBtn = w.findAll('button').find(b => b.text().includes('Tambah User'))
    expect(addBtn).toBeTruthy()
    await addBtn.trigger('click')
    await flushPromises()

    // The Modal component renders with v-if, so it should be in the DOM now.
    // Find all inputs with type text/number in the form
    const allInputs = w.findAll('input')
    // Debug: log all input types and placeholders
    allInputs.forEach((inp, i) => {
      console.log(`Input ${i}: type=${inp.attributes('type')}, placeholder=${inp.attributes('placeholder')}, disabled=${inp.attributes('disabled')}`)
    })

    // The first input in the modal should be username (placeholder: "huruf kecil, tanpa spasi")
    const usernameInput = allInputs.find(i => i.attributes('placeholder')?.includes('huruf kecil'))
    expect(usernameInput).toBeTruthy()
    await usernameInput.setValue('new_user')

    // The second input should be full_name
    const fullNameInput = allInputs.find(i => i.attributes('placeholder') === undefined && !i.attributes('disabled') && i.attributes('type') !== 'checkbox' && i.attributes('type') !== 'number' && i !== usernameInput)
    if (fullNameInput) {
      await fullNameInput.setValue('User Baru')
    }

    await flushPromises()

    // Click save button
    const saveBtn = w.findAll('button').find(b => b.text().includes('Simpan'))
    expect(saveBtn).toBeTruthy()
    expect(saveBtn.attributes('disabled')).toBeUndefined()
    await saveBtn.trigger('click')
    await flushPromises()

    const call = apiMock.mock.calls.find((c) => c[0] === '/api/users/sync')
    expect(call).toBeTruthy()
    expect(call[1].body.username).toBe('new_user')
    expect(call[1].body.pin).toBe('123456')
  })
})
