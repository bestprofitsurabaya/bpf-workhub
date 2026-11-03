import { describe, it, expect } from 'vitest'
import { formatDate, formatDateTime } from './format.js'

describe('format tanggal', () => {
  it('menormalkan RFC/GMT dari sheet tanpa menggeser jam lokal', () => {
    expect(formatDateTime('Fri, 17 Jul 2026 17:40:15 GMT')).toMatch(/17 Jul 2026/)
    expect(formatDateTime('Fri, 17 Jul 2026 17:40:15 GMT')).toMatch(/17[.:]40/)
    expect(formatDate('Mon, 02 Nov 2026 00:00:00 GMT')).toMatch(/02 Nov 2026/)
  })

  it('menangani DATETIME MySQL dan tanggal ISO', () => {
    expect(formatDateTime('2026-10-22 08:18:00')).toMatch(/22 Okt 2026/)
    expect(formatDateTime('2026-10-22 08:18:00')).toMatch(/08[.:]18/)
    expect(formatDate('2026-11-02')).toMatch(/02 Nov 2026/)
  })

  it('mengembalikan nilai asli bila tidak bisa diparse, dan — bila kosong', () => {
    expect(formatDateTime('bukan tanggal')).toBe('bukan tanggal')
    expect(formatDate('')).toBe('—')
  })
})
