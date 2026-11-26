import { beforeEach, describe, expect, it, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { nextTick } from 'vue'
import CvOnlineFormView from './CvOnlineFormView.vue'

const NIK = '3573010101990001'
const META = {
  branch: 'SBY',
  branch_name: 'Surabaya',
  options: {
    user: ['EF 1'],
    domisili: ['JAWA TIMUR'],
    pendidikan: ['S1'],
    jenis_kelamin: ['Pria', 'Wanita'],
    lama: ['1 - 2 Tahun'],
  },
}

let fetchMock
let submittedBody

async function mountForm() {
  const wrapper = mount(CvOnlineFormView)
  await flushPromises()
  return wrapper
}

async function fillStepSumberDanUndangan(w) {
  const inputs = w.findAll('input.input')
  await inputs[0].setValue('Instagram')
  await inputs[1].setValue('Budi')
  await w.findAll('select')[0].setValue('EF 1')
  const areas = w.findAll('textarea')
  await areas[0].setValue('Ibu Siti, 081211112222')
  await areas[1].setValue('Bapak Amin, 081233334444')
  await w.find('form').trigger('submit')
  await flushPromises()
}

describe('CvOnlineFormView — NIK (Rilis A)', () => {
  beforeEach(() => {
    submittedBody = null
    window.scrollTo = vi.fn()
    try { localStorage.clear() } catch { /* abaikan */ }
    fetchMock = vi.fn((url, init) => {
      const path = String(url)
      if (path.includes('/api/cv-online/form-meta')) {
        return Promise.resolve({ ok: true, json: () => Promise.resolve(META) })
      }
      if (path.includes('/api/cv-online/public')) {
        submittedBody = init.body
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({
            status: 'success',
            registration_no: 'CV-SBY-260102-001',
            nama: 'Budi Santoso',
            submitted_at: '2026-11-24 10:00:00',
          }),
        })
      }
      return Promise.resolve({ ok: false, json: () => Promise.resolve({}) })
    })
    vi.stubGlobal('fetch', fetchMock)
  })

  it('menampilkan field NIK di langkah data pribadi dengan pesan error yang jelas', async () => {
    const w = await mountForm()
    await fillStepSumberDanUndangan(w)

    const nik = w.find('input[aria-label="NIK sesuai KTP"]')
    expect(nik.exists()).toBe(true)
    expect(nik.attributes('placeholder')).toBe('16 digit angka')

    await w.find('form').trigger('submit')
    await flushPromises()
    expect(w.find('.alert-error').exists()).toBe(true)
    expect(w.text()).toContain('NIK sesuai KTP wajib 16 digit angka.')
  })

  it('hanya menerima digit dan maksimal 16 karakter', async () => {
    const w = await mountForm()
    await fillStepSumberDanUndangan(w)

    const nik = w.find('input[aria-label="NIK sesuai KTP"]')
    await nik.setValue('a3 57b-301x01 0199 0001 9999')
    await nextTick()
    expect(nik.element.value).toBe(NIK)
    expect(w.text()).toContain('16/16 digit')
  })

  it('mengirim NIK 16 digit dalam payload submit', async () => {
    const w = await mountForm()
    await fillStepSumberDanUndangan(w)

    const nik = w.find('input[aria-label="NIK sesuai KTP"]')
    await nik.setValue('3573-0101-0199-0001')

    const personal = w.findAll('input.input')
    await personal[1].setValue('Budi Santoso')
    await personal[2].setValue('Surabaya')
    await personal[3].setValue('1995-01-19')
    const personalSelects = w.findAll('select')
    await personalSelects[0].setValue('Pria')
    await personalSelects[1].setValue('JAWA TIMUR')
    await w.find('textarea').setValue('Jl. Contoh No. 1, Surabaya')
    await w.find('input[type="tel"]').setValue('081234567890')
    await w.find('form').trigger('submit')
    await flushPromises()

    await w.findAll('select')[0].setValue('S1')
    await w.find('form').trigger('submit')
    await flushPromises()

    expect(w.text()).toContain('Ringkasan')
    expect(w.text()).toContain('357301••••0001')
    await w.find('input[type="checkbox"]').setValue(true)
    await w.find('form').trigger('submit')
    await flushPromises()

    expect(submittedBody).not.toBeNull()
    expect(submittedBody.get('nik')).toBe(NIK)
    expect(w.text()).toContain('Terima kasih')
  })

  it('teks persetujuan menyebut NIK sebagai data pribadi', async () => {
    const w = await mountForm()
    await fillStepSumberDanUndangan(w)
    expect(w.find('.cv-consent').text()).toContain('NIK')
  })

  it('dengan sesi portal: NIK dan tanggal lahir tidak diminta dan s dikirim', async () => {
    window.history.replaceState({}, '', '/app/cv-online-form?cabang=JKT&t=tok&s=ses-1')
    const metaUrl = []
    fetchMock = vi.fn((url, init) => {
      const path = String(url)
      if (path.includes('/api/cv-online/form-meta')) {
        metaUrl.push(path)
        return Promise.resolve({ ok: true, json: () => Promise.resolve({
          ...META, nik_masked: '****0001', nama: 'Budi Santoso' }) })
      }
      if (path.includes('/api/cv-online/public')) {
        submittedBody = init && init.body
        return Promise.resolve({ ok: true, json: () => Promise.resolve({
          status: 'success', registration_no: 'CV-SBY-260102-002' }) })
      }
      return Promise.resolve({ ok: false, json: () => Promise.resolve({}) })
    })
    vi.stubGlobal('fetch', fetchMock)

    const w = await mountForm()
    await flushPromises()
    expect(metaUrl[0]).toContain('s=ses-1')
    await fillStepSumberDanUndangan(w)
    expect(w.find('input[aria-label="NIK sesuai KTP"]').exists()).toBe(false)
    expect(w.find('input[type="date"]').exists()).toBe(false)
    expect(w.text()).toContain('****0001')
  })
})
