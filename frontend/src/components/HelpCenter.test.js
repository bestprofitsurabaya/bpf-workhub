import { afterEach, describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import HelpCenter from './HelpCenter.vue'

afterEach(() => { localStorage.clear(); sessionStorage.clear() })

describe('HelpCenter', () => {
  it('menampilkan panduan sesuai halaman aktif', () => {
    const w = mount(HelpCenter, { props: { open: true, path: '/cash' } })
    expect(w.text()).toContain('Bantuan & Glosarium')
    expect(w.text()).toContain('Kasbon / BBM')
    expect(w.text()).toContain('Tab Kasbon')
    expect(w.text()).toContain('LPJ')
  })

  it('glosarium bisa dicari dan istilah terkait bisa diklik', async () => {
    const w = mount(HelpCenter, { props: { open: true, path: '/dashboard' } })
    await w.findAll('button').find((b) => b.text().includes('Glosarium')).trigger('click')
    const search = w.find('input[type="search"]')
    await search.setValue('odometer')
    expect(w.text()).toContain('ODO')
    expect(w.text()).toContain('Odometer')
    expect(w.text()).not.toContain('Air Minum')
  })

  it('menampilkan waktu aksi pertama saat mode uji kegunaan aktif', () => {
    localStorage.setItem('bpf_p5', '1')
    sessionStorage.setItem('bpf_p5_first_action', JSON.stringify({ label: 'buka antrean', ms: 12000 }))
    const w = mount(HelpCenter, { props: { open: true, path: '/dashboard' } })
    expect(w.text()).toContain('Mode uji kegunaan')
    expect(w.text()).toContain('buka antrean')
    expect(w.text()).toContain('12.0 dtk')
    expect(w.text()).toContain('di bawah target')
  })

  it('tombol tur lagi memancarkan replay-tour', async () => {
    const w = mount(HelpCenter, { props: { open: true, path: '/dashboard' } })
    await w.findAll('button').find((b) => b.text().includes('Tampilkan tur')).trigger('click')
    expect(w.emitted('replay-tour')).toHaveLength(1)
  })
})
