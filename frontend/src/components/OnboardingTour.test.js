import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import OnboardingTour from './OnboardingTour.vue'

const STEPS = [
  { icon: '👋', title: 'Langkah satu', body: 'Penjelasan satu', points: ['Poin A'] },
  { icon: '⚡', title: 'Langkah dua', body: 'Penjelasan dua', points: ['Poin B'] },
]

describe('OnboardingTour', () => {
  it('berpindah langkah lalu memancarkan done di langkah terakhir', async () => {
    const w = mount(OnboardingTour, { props: { open: true, steps: STEPS } })
    expect(w.text()).toContain('Langkah satu')
    await w.findAll('button').find((b) => b.text().includes('Lanjut')).trigger('click')
    expect(w.text()).toContain('Langkah dua')
    await w.findAll('button').find((b) => b.text().includes('Mulai pakai')).trigger('click')
    expect(w.emitted('done')).toHaveLength(1)
  })

  it('tombol Lewati memancarkan close', async () => {
    const w = mount(OnboardingTour, { props: { open: true, steps: STEPS } })
    await w.findAll('button').find((b) => b.text() === 'Lewati').trigger('click')
    expect(w.emitted('close')).toHaveLength(1)
  })
})
