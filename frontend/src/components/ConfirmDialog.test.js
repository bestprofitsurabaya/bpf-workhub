import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import { nextTick } from 'vue'
import ConfirmDialog from './ConfirmDialog.vue'

const btn = (w, text) => w.findAll('button').find((b) => b.text() === text)

describe('ConfirmDialog', () => {
  it('mengembalikan true saat dikonfirmasi dan false saat dibatalkan', async () => {
    const w = mount(ConfirmDialog)
    const ok = w.vm.open('Lanjutkan tindakan?')
    await nextTick()
    expect(w.text()).toContain('Lanjutkan tindakan?')
    await btn(w, 'Ya, lanjutkan').trigger('click')
    expect(await ok).toBe(true)

    const no = w.vm.open('Batalkan tindakan?')
    await nextTick()
    await btn(w, 'Batal').trigger('click')
    expect(await no).toBe(false)
  })

  it('input wajib diisi — modal tetap terbuka dan menampilkan pesan', async () => {
    const w = mount(ConfirmDialog)
    const answer = w.vm.open('Alasan penolakan?', { input: true, required: true })
    await nextTick()
    await btn(w, 'Ya, lanjutkan').trigger('click')
    expect(w.find('textarea').exists()).toBe(true)
    expect(w.text()).toContain('wajib diisi')

    await w.find('textarea').setValue('foto tidak terbaca')
    await btn(w, 'Ya, lanjutkan').trigger('click')
    expect(await answer).toBe('foto tidak terbaca')
  })
})
