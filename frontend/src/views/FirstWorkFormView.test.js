import { beforeEach, describe, expect, it, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import FirstWorkFormView from './FirstWorkFormView.vue'

const NIK = '3578010101900001'
const DEMO = {
  tempat_lahir: 'Surabaya',
  tanggal_lahir: '1995-01-19',
  jenis_kelamin: 'Laki-laki',
  golongan_darah: 'O',
  kewarganegaraan: 'WNI',
  berlaku_hingga: '2030-01-19',
  pendidikan: 'SMA',
  alamat: 'Jl. Contoh No. 12',
  rt_rw: '03/04',
  kel_desa: 'Keputih',
  kecamatan: 'Sukolilo',
  agama: 'Islam',
  status_perkawinan: 'Belum Menikah',
  pekerjaan: 'Karyawan Swasta',
}

let submittedBody

async function mountForm() {
  const w = mount(FirstWorkFormView)
  await flushPromises()
  return w
}

function mockFetch() {
  return vi.fn((url, init) => {
    if (String(url).includes('/api/first-work/referrers')) {
      return Promise.resolve({
        ok: true,
        json: () => Promise.resolve({
          branch: 'SBY', branch_name: 'Surabaya',
          referrers: [{ id: 1, name: 'IFAH' }],
        }),
      })
    }
    if (String(url).includes('/api/first-work/public')) {
      submittedBody = init.body
      return Promise.resolve({
        ok: true,
        json: () => Promise.resolve({
          status: 'success', registration_no: 'FW-SBY-20261124-0001',
          nama: 'Hasil OCR KTP', submitted_at: '2026-11-24 10:00:00',
          fingerprint_no: 'EF_25001', bpf_no: 'EF_8001',
        }),
      })
    }
    return Promise.resolve({ ok: false, json: () => Promise.resolve({}) })
  })
}

async function goToStepTwo(w) {
  w.vm.setKtpFile(new File(['ktp'], 'ktp.jpg', { type: 'image/jpeg' }), false)
  Object.assign(w.vm.form, { nik: NIK, nama: 'Hasil OCR KTP', pendidikan: DEMO.pendidikan })
  await w.vm.goNext()
  await flushPromises()
}

async function goToSummary(w) {
  w.vm.form.referrer_id = '1'
  w.vm.form.no_hp = '081234567890'
  await w.vm.goNext()
  await flushPromises()
}

function fillIdentity(w) {
  return Promise.all([
    w.find('input[aria-label="Tempat Lahir"]').setValue(DEMO.tempat_lahir),
    w.find('input[aria-label="Tanggal Lahir"]').setValue(DEMO.tanggal_lahir),
    w.find('select[aria-label="Jenis Kelamin"]').setValue(DEMO.jenis_kelamin),
    w.find('select[aria-label="Golongan Darah"]').setValue(DEMO.golongan_darah),
    w.find('input[aria-label="Kewarganegaraan"]').setValue(DEMO.kewarganegaraan),
    w.find('input[aria-label="Berlaku Hingga"]').setValue(DEMO.berlaku_hingga),
  ])
}

function fillContact(w) {
  return Promise.all([
    w.find('textarea[aria-label="Alamat"]').setValue(DEMO.alamat),
    w.find('input[aria-label="RT/RW"]').setValue(DEMO.rt_rw),
    w.find('input[aria-label="Kel/Desa"]').setValue(DEMO.kel_desa),
    w.find('input[aria-label="Kecamatan"]').setValue(DEMO.kecamatan),
    w.find('select[aria-label="Agama"]').setValue(DEMO.agama),
    w.find('select[aria-label="Status Perkawinan"]').setValue(DEMO.status_perkawinan),
    w.find('input[aria-label="Pekerjaan"]').setValue(DEMO.pekerjaan),
  ])
}

describe('FirstWorkFormView — 13 field demografi (Rilis B Task 2)', () => {
  beforeEach(() => {
    submittedBody = null
    window.scrollTo = vi.fn()
    window.history.pushState({}, '', '/app/first-work-form?cabang=SBY&t=tok-SBY')
    try { localStorage.clear() } catch { /* abaikan */ }
    vi.stubGlobal('fetch', mockFetch())
  })

  it('langkah Identitas memuat field identitas KTP yang baru', async () => {
    const w = await mountForm()
    for (const label of ['Tempat Lahir', 'Tanggal Lahir', 'Jenis Kelamin',
      'Golongan Darah', 'Kewarganegaraan', 'Berlaku Hingga']) {
      const field = w.find(`[aria-label="${label}"]`)
      expect(field.exists(), label).toBe(true)
      expect(field.attributes('aria-label')).toBe(label)
    }
  })

  it('langkah Kontak & Referensi memuat field alamat & data kependudukan', async () => {
    const w = await mountForm()
    await goToStepTwo(w)
    for (const label of ['Alamat', 'RT/RW', 'Kel/Desa', 'Kecamatan',
      'Agama', 'Status Perkawinan', 'Pekerjaan']) {
      expect(w.find(`[aria-label="${label}"]`).exists(), label).toBe(true)
    }
  })

  it('mengirim ke-13 field dalam payload saat submit', async () => {
    const w = await mountForm()
    await fillIdentity(w)
    await goToStepTwo(w)
    await fillContact(w)
    await goToSummary(w)
    expect(w.vm.step).toBe(2)
    expect(w.text()).toContain('Surabaya')

    await w.find('input[type="checkbox"]').setValue(true)
    await w.find('form').trigger('submit')
    await flushPromises()

    expect(submittedBody).not.toBeNull()
    for (const [field, value] of Object.entries(DEMO)) {
      expect(submittedBody.get(field), field).toBe(value)
    }
    expect(w.text()).toContain('FW-SBY-20261124-0001')
  })

  it('field demografi tidak menimpa NIK & nama hasil OCR', async () => {
    const w = await mountForm()
    await fillIdentity(w)
    await goToStepTwo(w)
    await fillContact(w)
    expect(w.vm.form.nik).toBe(NIK)
    expect(w.vm.form.nama).toBe('Hasil OCR KTP')

    w.vm.goTo(0)
    await flushPromises()
    expect(w.find('input[aria-label="NIK sesuai KTP"]').element.value).toBe(NIK)
    expect(w.vm.form.tempat_lahir).toBe(DEMO.tempat_lahir)
    expect(w.vm.form.alamat).toBe(DEMO.alamat)
  })

  it('draf memulihkan field demografi', async () => {
    let w = await mountForm()
    await fillIdentity(w)
    await goToStepTwo(w)
    await fillContact(w)
    const draft = JSON.parse(localStorage.getItem('bpf_fw_draft_v1'))
    expect(draft.tempat_lahir).toBe(DEMO.tempat_lahir)
    expect(draft.alamat).toBe(DEMO.alamat)

    w.unmount()
    w = await mountForm()
    expect(w.vm.form.tempat_lahir).toBe(DEMO.tempat_lahir)
    expect(w.vm.form.tanggal_lahir).toBe(DEMO.tanggal_lahir)
    expect(w.vm.form.alamat).toBe(DEMO.alamat)
    expect(w.vm.form.nik).toBe(NIK)
  })
})
