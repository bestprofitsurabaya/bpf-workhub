import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import PageHeader from './PageHeader.vue'

describe('PageHeader', () => {
  it('merender ikon, judul, subtitle', () => {
    const w = mount(PageHeader, { props: { icon: '💰', title: 'Dashboard Finance', subtitle: 'Rekap' } })
    expect(w.text()).toContain('💰')
    expect(w.text()).toContain('Dashboard Finance')
    expect(w.text()).toContain('Rekap')
    expect(w.find('.ph-title').exists()).toBe(true)
  })

  it('merender slot aksi', () => {
    const w = mount(PageHeader, {
      props: { title: 'Rekap' },
      slots: { default: '<button class="btn">Export CSV</button>' },
    })
    expect(w.text()).toContain('Export CSV')
  })

  it('tanpa icon tidak merender .ph-icon, tanpa subtitle tidak merender .ph-sub', () => {
    const w = mount(PageHeader, { props: { title: 'Judul' } })
    expect(w.find('.ph-icon').exists()).toBe(false)
    expect(w.find('.ph-sub').exists()).toBe(false)
  })
})
