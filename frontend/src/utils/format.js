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

export function formatDateTime(value, withYear = true) {
  if (!value) return '—'
  const d = new Date(String(value).replace(' ', 'T'))
  if (Number.isNaN(d.getTime())) return value
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
  const d = new Date(String(value).replace(' ', 'T'))
  if (Number.isNaN(d.getTime())) return value
  return d.toLocaleDateString('id-ID', { day: '2-digit', month: 'short', year: 'numeric' })
}
