/**
 * Utilitas GPS driver (port dari static/js/driver.js).
 * Prioritas alamat: nilai tersimpan → reverse geocode (Nominatim) → koordinat mentah.
 *
 * v2.127.2 — audit GPS:
 * - Satu reverse geocode per lokasi (hasil detail dipakai ulang), bukan 3 panggilan.
 * - Cache hasil geocode per ±11 m selama sesi (hemat kuota + patuhi 1 req/dtk).
 * - Semua fetch punya timeout 8 dtk + cek r.status (tidak menggantung/menelan 429).
 * - Posisi default maximumAge 30 dtk (bukan 5 menit) + accuracy diteruskan.
 */
export const NOMINATIM = 'https://nominatim.openstreetmap.org'

const GEO_TIMEOUT_MS = 8000
const GEO_CACHE_TTL_MS = 10 * 60 * 1000
const GEO_CACHE_MAX = 40
const _geoCache = new Map()   // key: 'lat,lon' 4 desimal → { at, promise }

async function fetchJson(url, timeoutMs = GEO_TIMEOUT_MS) {
  const ctrl = new AbortController()
  const timer = setTimeout(() => ctrl.abort(), timeoutMs)
  try {
    const r = await fetch(url, {
      headers: { 'User-Agent': 'BPF-BBM/1.0' },
      signal: ctrl.signal,
    })
    if (!r.ok) throw new Error(`HTTP ${r.status}`)
    return await r.json()
  } finally {
    clearTimeout(timer)
  }
}

function geoKey(lat, lon) {
  return `${Number(lat).toFixed(4)},${Number(lon).toFixed(4)}`
}

function pruneCache() {
  if (_geoCache.size <= GEO_CACHE_MAX) return
  const oldest = [..._geoCache.entries()].sort((a, b) => a[1].at - b[1].at)
  for (const [k] of oldest.slice(0, _geoCache.size - GEO_CACHE_MAX)) _geoCache.delete(k)
}

async function reverseGeocode(lat, lon) {
  const d = await fetchJson(
    `${NOMINATIM}/reverse?lat=${lat}&lon=${lon}&format=json&zoom=18&addressdetails=1&accept-language=id`
  )
  if (d?.address) {
    const a = d.address
    const parts = []
    // Prioritas: jalan → gang → area → kelurahan → kecamatan → kota → provinsi
    if (a.road || a.pedestrian) parts.push(a.road || a.pedestrian)
    if (a.house_number) parts.push('No. ' + a.house_number)
    if (a.hamlet || a.neighbourhood) parts.push(a.hamlet || a.neighbourhood)
    if (a.suburb || a.village || a.residential) parts.push(a.suburb || a.village || a.residential)
    if (a.city_district || a.county || a.municipality || a.district || a.subdistrict) parts.push(a.city_district || a.county || a.municipality || a.district || a.subdistrict)
    if (a.city || a.town || a.municipality) parts.push(a.city || a.town || a.municipality)
    if (a.state) parts.push(a.state)
    if (a.postcode) parts.push('Kode Pos ' + a.postcode)
    return parts.join(', ') || d.display_name || ''
  }
  return d?.display_name || ''
}

/** Susun alamat ringkas dari objek detail (dipakai watermark & payload). */
export function formatAddress(detail) {
  if (!detail) return ''
  const parts = [
    detail.jalan,
    detail.nomor ? 'No. ' + detail.nomor : '',
    detail.gang,
    detail.kelurahan,
    detail.kecamatan,
    detail.kota,
    detail.provinsi,
    detail.kode_pos ? 'Kode Pos ' + detail.kode_pos : '',
  ].filter(Boolean)
  return parts.join(', ') || detail.full_address || ''
}

/**
 * Detail lokasi lengkap (untuk watermark dan display).
 * Hasil di-cache 10 menit per koordinat 4 desimal agar tidak menembak
 * Nominatim berulang untuk lokasi yang sama.
 */
export async function detailedLocation(lat, lon) {
  const key = geoKey(lat, lon)
  const hit = _geoCache.get(key)
  if (hit && Date.now() - hit.at < GEO_CACHE_TTL_MS) return hit.promise

  const promise = (async () => {
    const d = await fetchJson(
      `${NOMINATIM}/reverse?lat=${lat}&lon=${lon}&format=json&zoom=18&addressdetails=1&accept-language=id`
    )
    // Parse display_name sebagai fallback untuk kecamatan
    const parts = (d?.display_name || '').split(',').map(p => p.trim())
    const addr = d?.address || {}
    const kotaVal = addr.city || addr.town || addr.municipality || ''
    let kecamatanFallback = ''
    if (kotaVal && parts.length > 2) {
      const kotaIdx = parts.findIndex(p => p.toLowerCase().includes(kotaVal.toLowerCase()))
      if (kotaIdx > 0) kecamatanFallback = parts[kotaIdx - 1] || ''
    }
    return {
      full_address: d?.display_name || '',
      jalan: addr.road || addr.pedestrian || '',
      nomor: addr.house_number || '',
      gang: addr.hamlet || addr.neighbourhood || '',
      kelurahan: addr.suburb || addr.village || addr.residential || addr.neighbourhood || '',
      kecamatan: addr.city_district || addr.county || addr.municipality || addr.district || addr.subdistrict || kecamatanFallback || '',
      kota: kotaVal,
      provinsi: addr.state || '',
      kode_pos: addr.postcode || '',
      negara: addr.country || '',
      lat, lon,
    }
  })()

  _geoCache.set(key, { at: Date.now(), promise })
  pruneCache()
  try {
    return await promise
  } catch (e) {
    _geoCache.delete(key)   // jangan cache kegagalan
    throw e
  }
}

/** Alamat dari koordinat GPS (atau string koordinat bila gagal). */
export async function addressFromCoords(lat, lon) {
  try {
    const addr = await reverseGeocode(lat, lon)
    return addr || `${lat.toFixed(5)}, ${lon.toFixed(5)}`
  } catch {
    return `${lat.toFixed(5)}, ${lon.toFixed(5)}`
  }
}

/** SPBU terdekat (2 teratas) dari koordinat. Return string deskriptif atau ''. */
export async function nearbySpbu(lat, lon) {
  try {
    const data = await fetchJson(
      `${NOMINATIM}/search?q=SPBU&format=json&limit=3&lat=${lat}&lon=${lon}&bounded=1&addressdetails=1&accept-language=id`,
      6000
    )
    if (Array.isArray(data) && data.length) {
      return data.slice(0, 2).map((d) => {
        const dist = d.dist ? `${Math.round(d.dist)}m` : ''
        const name = (d.display_name || '').split(',')[0].trim()
        return name + (dist ? ` (${dist})` : '')
      }).join(' | ')
    }
  } catch { /* abaikan */ }
  return ''
}

/**
 * Ambil posisi GPS sekali (promise).
 * maximumAge default 30 dtk — posisi 5 menit lalu tidak layak untuk bukti foto.
 */
export function getPosition(timeout = 15000, { maximumAge = 30000, highAccuracy = true } = {}) {
  return new Promise((resolve, reject) => {
    if (!navigator.geolocation) {
      reject(new Error('GPS tidak didukung perangkat ini'))
      return
    }
    navigator.geolocation.getCurrentPosition(resolve, reject, {
      enableHighAccuracy: highAccuracy, timeout, maximumAge,
    })
  })
}

/** Ambil posisi + alamat + SPBU terdekat sekaligus (satu reverse geocode). */
export async function locateWithAddress() {
  const pos = await getPosition()
  const { latitude: lat, longitude: lon, accuracy } = pos.coords
  let detail = null
  let addr = ''
  try {
    detail = await detailedLocation(lat, lon)
    addr = formatAddress(detail)
  } catch { /* alamat opsional — koordinat tetap dipakai */ }
  if (!addr) addr = `${lat.toFixed(5)}, ${lon.toFixed(5)}`
  let spbu = ''
  try { spbu = await nearbySpbu(lat, lon) } catch { /* fallback */ }
  return {
    lat, lon, addr, spbu, detail,
    accuracy: Number.isFinite(accuracy) ? Math.round(accuracy) : null,
    at: pos.timestamp ? new Date(pos.timestamp).toISOString() : new Date().toISOString(),
  }
}
