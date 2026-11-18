import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { csvCell, csvLine, csvMeta, downloadCsv } from './csv'

describe('utils/csv — ekspor CSV bersama (v2.113.2)', () => {
  it('mengutip sel yang berisi koma, kutip, titik-koma, atau baris baru', () => {
    expect(csvCell('Budi')).toBe('Budi')
    expect(csvCell('Budi, S.T.')).toBe('"Budi, S.T."')
    expect(csvCell('Budi "BS" Santoso')).toBe('"Budi ""BS"" Santoso"')
    expect(csvCell('baris1\nbaris2')).toBe('"baris1\nbaris2"')
    expect(csvCell('a;b')).toBe('"a;b"')
    expect(csvCell(null)).toBe('')
    expect(csvCell(0)).toBe('0')
  })

  it('csvLine menggabungkan sel dengan escaping yang sama', () => {
    expect(csvLine(['SBY', 'Budi, S.T.', 12])).toBe('SBY,"Budi, S.T.",12')
  })

  it('csvMeta membuat baris selebar kolom tabel', () => {
    expect(csvMeta('Periode 1–30 Nov', 4)).toBe('Periode 1–30 Nov,,,')
    expect(csvMeta('Judul', 0)).toBe('Judul')
    expect(csvMeta('Judul')).toBe('Judul')
  })

  describe('downloadCsv', () => {
    let captured = null
    let clicked = null

    beforeEach(() => {
      captured = null
      clicked = null
      URL.createObjectURL = vi.fn((blob) => { captured = blob; return 'blob:uji' })
      URL.revokeObjectURL = vi.fn()
      vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(function () {
        clicked = this
      })
    })

    afterEach(() => {
      vi.restoreAllMocks()
    })

    it('menyusun file UTF-8 ber-BOM dengan nama unduhan yang diminta', async () => {
      downloadCsv('rekap.csv', ['Judul', 'a,b', '1,2'])
      expect(captured).toBeInstanceOf(Blob)
      expect(captured.type).toBe('text/csv;charset=utf-8;')
      const text = typeof captured.text === 'function'
        ? await captured.text()
        : await new Response(captured).text()
      expect(text.startsWith('\ufeff')).toBe(true)
      expect(text.slice(1)).toBe('Judul\na,b\n1,2')
      expect(clicked?.download).toBe('rekap.csv')
      expect(URL.revokeObjectURL).toHaveBeenCalledWith('blob:uji')
    })
  })
})
