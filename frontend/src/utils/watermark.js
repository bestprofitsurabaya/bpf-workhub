/**
 * Mesin watermark foto (port dari static/js/driver.js).
 * Bar hitam di bawah foto berisi: nama perusahaan, tanggal & jam, lokasi GPS.
 * Nama perusahaan mengikuti identitas system_config (multi-cabang).
 * Return Blob JPEG yang siap dikirim sebagai file.
 */
import { identity } from '../stores/identity'

export function watermarkCompany() {
  return (identity.company_name || 'PT BESTPROFIT FUTURES').slice(0, 30)
}

export async function applyWatermark(file, gpsText, dateText = null, gpsCoords = null) {
  if (!file || !file.type.startsWith('image/')) return null
  try {
    const now = dateText || new Date().toLocaleString('id-ID', { dateStyle: 'medium', timeStyle: 'short' })
    const url = URL.createObjectURL(file)
    const img = await new Promise((resolve, reject) => {
      const i = new Image()
      i.onload = () => resolve(i)
      i.onerror = reject
      i.src = url
    })

    const canvas = document.createElement('canvas')
    const ctx = canvas.getContext('2d')
    canvas.width = img.width
    canvas.height = img.height
    ctx.drawImage(img, 0, 0)

    // Font proporsional: kecil tapi terbaca
    const fontSize = Math.max(12, Math.floor(canvas.width / 45))
    const pad = Math.max(10, Math.floor(canvas.width / 80))
    const lineH = fontSize * 1.4

    // Hitung bar height (4 baris: perusahaan, tanggal, alamat, koordinat)
    const lines = [watermarkCompany(), `📅 ${now}`, `📍 ${gpsText}`]
    if (gpsCoords) lines.push(`🌐 ${gpsCoords}`)
    const barH = lineH * lines.length + pad * 2

    // Background bar — kiri bawah, semi-transparent
    ctx.fillStyle = 'rgba(0,0,0,0.55)'
    ctx.fillRect(0, canvas.height - barH, canvas.width, barH)

    // Baris 1: Nama perusahaan (kuning)
    ctx.fillStyle = '#FFD700'
    ctx.font = `bold ${fontSize}px Arial, sans-serif`
    ctx.fillText(lines[0], pad, canvas.height - barH + lineH + pad * 0.5)

    // Baris 2+: Tanggal, Alamat, Koordinat (putih, lebih kecil)
    ctx.fillStyle = '#FFFFFF'
    ctx.font = `${fontSize * 0.85}px Arial, sans-serif`
    for (let i = 1; i < lines.length; i++) {
      ctx.fillText(lines[i], pad, canvas.height - barH + lineH * (i + 1) + pad * 0.5)
    }

    URL.revokeObjectURL(url)
    return await new Promise((resolve) => {
      canvas.toBlob((blob) => resolve(blob), 'image/jpeg', 0.85)
    })
  } catch {
    return null
  }
}

/** Baca file jadi dataURL untuk preview. */
export function fileToDataUrl(file) {
  return new Promise((resolve, reject) => {
    const r = new FileReader()
    r.onload = (e) => resolve(e.target.result)
    r.onerror = reject
    r.readAsDataURL(file)
  })
}
