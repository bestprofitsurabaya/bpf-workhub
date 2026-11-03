const TX_STATUS_LABEL = {
  pending: 'Menunggu GA',
  modified: 'Perlu review ulang',
  verified_ga: 'Terverifikasi GA',
  os_finance: 'Menunggu Finance',
  archived: 'Terarsip',
  rejected: 'Ditolak',
}

export function formatRupiah(value) {
  return 'Rp ' + Number(value || 0).toLocaleString('id-ID')
}

export function formatNumber(value) {
  return Number(value || 0).toLocaleString('id-ID')
}

export function transactionStatusLabel(status) {
  return TX_STATUS_LABEL[status] || status || '—'
}

function parseDateValue(value) {
  if (!value) return null
  const s = String(value).trim()
  // Tanggal saja (YYYY-MM-DD) → perlakukan sebagai tanggal lokal, bukan UTC.
  const dateOnly = s.match(/^(\d{4})-(\d{2})-(\d{2})$/)
  if (dateOnly) {
    return new Date(Number(dateOnly[1]), Number(dateOnly[2]) - 1, Number(dateOnly[3]))
  }
  // DATETIME MySQL (YYYY-MM-DD HH:mm[:ss]) → ISO lokal tanpa pergeseran zona.
  const sql = s.match(/^(\d{4})-(\d{2})-(\d{2})[ T](\d{2}):(\d{2})(?::(\d{2}))?(?:\.\d+)?$/)
  if (sql) {
    return new Date(
      Number(sql[1]), Number(sql[2]) - 1, Number(sql[3]),
      Number(sql[4]), Number(sql[5]), Number(sql[6] || 0),
    )
  }
  // RFC 2822 dari sheet (mis. "Fri, 17 Jul 2026 17:40:15 GMT"). Label GMT di
  // ekspor sheet sebenarnya adalah jam dinding lokal — jangan digeser zona.
  const MONTHS = { jan: 0, feb: 1, mar: 2, apr: 3, may: 4, jun: 5, jul: 6, aug: 7, sep: 8, oct: 9, nov: 10, dec: 11 }
  const rfc = s.match(/^(?:[A-Za-z]{3},\s*)?(\d{1,2})\s+([A-Za-z]{3})\s+(\d{4})\s+(\d{2}):(\d{2})(?::(\d{2}))?/)
  if (rfc && MONTHS[rfc[2].toLowerCase()] !== undefined) {
    return new Date(
      Number(rfc[3]), MONTHS[rfc[2].toLowerCase()], Number(rfc[1]),
      Number(rfc[4]), Number(rfc[5]), Number(rfc[6] || 0),
    )
  }
  // ISO dengan zona waktu (Z / +07:00) → biarkan Date menangani konversi.
  const d = new Date(s)
  return Number.isNaN(d.getTime()) ? null : d
}

export function formatDateTime(value, withYear = true) {
  if (!value) return '—'
  const d = parseDateValue(value)
  if (!d) return value
  return d.toLocaleString('id-ID', {
    day: '2-digit',
    month: 'short',
    ...(withYear ? { year: 'numeric' } : {}),
    hour: '2-digit',
    minute: '2-digit',
  })
}

export function formatDate(value) {
  if (!value) return '—'
  const d = parseDateValue(value)
  if (!d) return value
  return d.toLocaleDateString('id-ID', { day: '2-digit', month: 'short', year: 'numeric' })
}
