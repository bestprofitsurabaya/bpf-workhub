import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import Pager from './Pager.vue'

describe('Pager (v2.129.0)', () => {
  it('menampilkan posisi halaman & total entri', () => {
    const w = mount(Pager, { props: { page: 2, pageCount: 5, total: 47, unit: 'pengajuan' } })
    expect(w.text()).toContain('Halaman 2 / 5')
    expect(w.text()).toContain('47 pengajuan')
  })

  it('menonaktifkan tombol di batas halaman', () => {
    const first = mount(Pager, { props: { page: 1, pageCount: 3, total: 30 } })
    expect(first.findAll('button')[0].attributes('disabled')).toBeDefined()
    expect(first.findAll('button')[1].attributes('disabled')).toBeUndefined()

    const last = mount(Pager, { props: { page: 3, pageCount: 3, total: 30 } })
    expect(last.findAll('button')[0].attributes('disabled')).toBeUndefined()
    expect(last.findAll('button')[1].attributes('disabled')).toBeDefined()
  })

  it('mengirim halaman berikutnya/sebelumnya', async () => {
    const w = mount(Pager, { props: { page: 2, pageCount: 4, total: 40 } })
    const [prev, next] = w.findAll('button')
    await next.trigger('click')
    await prev.trigger('click')
    expect(w.emitted('update:page')).toEqual([[3], [1]])
  })

  it('tidak dirender bila hanya satu halaman', () => {
    const w = mount(Pager, { props: { page: 1, pageCount: 1, total: 4 } })
    expect(w.find('.pager').exists()).toBe(false)
  })
})
