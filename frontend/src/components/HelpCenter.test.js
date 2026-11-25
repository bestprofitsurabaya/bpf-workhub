import { afterEach, describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import HelpCenter from './HelpCenter.vue'
import { helpForPath } from '../content/help.js'

afterEach(() => { localStorage.clear(); sessionStorage.clear() })

describe('HelpCenter', () => {
  it('menampilkan panduan sesuai halaman aktif', () => {
    const w = mount(HelpCenter, { props: { open: true, path: '/cash' } })
    expect(w.text()).toContain('Bantuan & Glosarium')
    expect(w.text()).toContain('BBM, Kasbon & SPBU')
    expect(w.text()).toContain('Klaim BBM')
    expect(w.text()).toContain('LPJ')
  })

  it('panduan hub Rekrutmen mengikuti tab yang sedang dibuka', () => {
    const hub = mount(HelpCenter, { props: { open: true, path: '/recruitment' } })
    expect(hub.text()).toContain('🪪 Rekrutmen')
    expect(hub.text()).toContain('Pelamar')
    hub.unmount()

    const cv = mount(HelpCenter, { props: { open: true, path: '/recruitment', tab: 'cv' } })
    expect(cv.text()).toContain('Rekrutmen — CV Online')
    expect(cv.text()).toContain('Bagikan tautan/QR')
    cv.unmount()

    expect(helpForPath('/recruitment', 'tautan').title).toContain('Tautan')
    expect(helpForPath('/recruitment', 'rahasia').title).toBe('🪪 Rekrutmen')
    expect(helpForPath('/cash')).toBeTruthy()
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
