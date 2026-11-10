// Label & helper bersama untuk modul Inventaris IT (v2.78.0).
// Dipakai ItInventoryView, ItAssetDetailView, dan ItScanView agar bahasa dan
// warna status/kondisi konsisten di seluruh modul.

export const CATEGORY_LABEL = {
  pc: 'PC / Desktop',
  laptop: 'Laptop',
  monitor: 'Monitor',
  printer: 'Printer / Scanner',
  network: 'Jaringan',
  ups: 'UPS / Power',
  projector: 'Proyektor / TV',
  cctv: 'CCTV',
  server: 'Server / NAS',
  phone: 'Telepon',
  peripheral: 'Periferal',
  license: 'Lisensi',
  consumable: 'Consumable',
  other: 'Lainnya',
}

export const STATUS_LABEL = {
  stok: 'Stok',
  aktif: 'Aktif',
  dipinjam: 'Dipinjam',
  service: 'Service',
  rusak: 'Rusak',
  hilang: 'Hilang',
  disposed: 'Disposed',
}

export const COND_LABEL = {
  baik: 'Baik',
  rusak_ringan: 'Rusak Ringan',
  rusak_berat: 'Rusak Berat',
}

export const COND_META = {
  baik: { label: 'Baik', icon: '✅', color: '#059669', badge: 'badge-green' },
  rusak_ringan: { label: 'Rusak Ringan', icon: '⚠️', color: '#d97706', badge: 'badge-amber' },
  rusak_berat: { label: 'Rusak Berat', icon: '⛔', color: '#dc2626', badge: 'badge-red' },
}

export const STATUS_BADGE = {
  stok: 'badge-gray',
  aktif: 'badge-green',
  dipinjam: 'badge-cyan',
  service: 'badge-amber',
  rusak: 'badge-red',
  hilang: 'badge-red',
  disposed: 'badge-gray',
}

export const EVENT_LABEL = {
  created: 'Dibuat',
  updated: 'Diperbarui',
  condition: 'Kondisi',
  status: 'Status',
  location: 'Lokasi',
  pic: 'PIC',
  label: 'Label',
  scan: 'Scan',
  note: 'Catatan',
  repair: 'Perbaikan',
  service: 'Servis',
  assign: 'Penugasan',
  transfer: 'Mutasi',
  import: 'Impor',
  dispose: 'Disposal',
}

export function categoryLabel(code) {
  return CATEGORY_LABEL[code] || code || '—'
}

export function assetTitle(asset) {
  if (!asset) return '—'
  const parts = [asset.brand, asset.model].filter(Boolean)
  return parts.join(' ') || categoryLabel(asset.category)
}

export function downloadBlob(blob, filename) {
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  document.body.appendChild(a)
  a.click()
  a.remove()
  setTimeout(() => URL.revokeObjectURL(url), 4000)
}

export function maskMac(mac) {
  return mac || ''
}
