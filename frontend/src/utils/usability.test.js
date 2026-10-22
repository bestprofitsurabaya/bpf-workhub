import { beforeEach, describe, expect, it, vi } from 'vitest'
import {
  firstAction, formatDuration, isUsabilityMode, markFirstAction,
  markSessionStart, resetUsabilitySession,
} from './usability.js'

describe('usability timing', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    vi.setSystemTime(new Date('2026-10-22T08:00:00Z'))
    localStorage.clear()
    sessionStorage.clear()
  })

  it('mencatat waktu aksi pertama hanya bila mode uji aktif', () => {
    markSessionStart({ force: true })
    expect(markFirstAction('buka antrean')).toBeNull()

    localStorage.setItem('bpf_p5', '1')
    expect(isUsabilityMode()).toBe(true)
    vi.advanceTimersByTime(12500)
    const rec = markFirstAction('buka antrean')
    expect(rec.label).toBe('buka antrean')
    expect(rec.ms).toBe(12500)
    expect(firstAction().ms).toBe(12500)

    vi.advanceTimersByTime(5000)
    expect(markFirstAction('aksi lain')).toBeNull()
    expect(firstAction().label).toBe('buka antrean')
  })

  it('reset memulai sesi baru dan format durasi ramah dibaca', () => {
    localStorage.setItem('bpf_p5', '1')
    markSessionStart({ force: true })
    vi.advanceTimersByTime(1000)
    markFirstAction('klik')
    expect(formatDuration(firstAction().ms)).toBe('1.0 dtk')

    resetUsabilitySession()
    expect(firstAction()).toBeNull()
    expect(formatDuration(21000)).toBe('21.0 dtk')
  })
})
