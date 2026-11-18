/**
 * Helper ekspor CSV (v2.113.2 — Fase 4 "rapikan PDF & CSV").
 *
 * Sebelumnya setiap halaman menulis Blob, BOM, dan aturan quoting sendiri:
 * Rekap/Realisasi/Analisis memakai escaping yang benar, sedangkan UsersView
 * membungkus semua sel dengan kutip tanpa meng-escape kutip di dalamnya
 * (nama seperti `Budi "BS" Santoso` merusak kolom). Satu helper ini menjaga
 * format file sama di semua ekspor dan mudah diuji.
 */

/** Escape satu sel CSV: kutip bila berisi koma, kutip, titik-koma, atau baris baru. */
export function csvCell(value) {
  const text = String(value ?? '')
  return /[",\n\r;]/.test(text) ? '"' + text.replace(/"/g, '""') + '"' : text
}

/** Gabungkan satu baris sel menjadi teks CSV. */
export function csvLine(cells) {
  return cells.map(csvCell).join(',')
}

/**
 * Baris meta selebar `columns` kolom — judul/keterangan laporan di kolom
 * pertama, sisanya kosong, agar tetap sejajar saat dibuka di Excel.
 */
export function csvMeta(label, columns) {
  const width = Math.max(1, Number(columns) || 1)
  return csvLine([label, ...Array(width - 1).fill('')])
}

/** Unduh CSV UTF-8 dengan BOM supaya Excel membaca karakter non-ASCII. */
export function downloadCsv(filename, lines) {
  const blob = new Blob(['\ufeff' + lines.join('\n')], { type: 'text/csv;charset=utf-8;' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  a.click()
  URL.revokeObjectURL(url)
}
