/**
 * Deteksi konektivitas nyata (v2.127.5).
 *
 * `navigator.onLine` tidak selalu benar: setelah mode pesawat dimatikan,
 * Chrome Android/Safari bisa tetap melaporkan `false` walau jaringan sudah
 * pulih — antrean driver pun tidak pernah dicoba. Sebaliknya `true` tidak
 * menjamin server terjangkau (captive portal / Wi-Fi tanpa internet).
 *
 * Probe ini menembak endpoint ringan dan menganggap "online" bila server
 * menjawab (2xx/3xx/401/403 — 401/403 tetap berarti server hidup).
 */
export const HEALTH_PATH = '/api/health'

export async function probeConnectivity({ timeoutMs = 4000, fetchImpl } = {}) {
  const f = fetchImpl || (typeof fetch !== 'undefined' ? fetch : null)
  if (!f) return false
  const ctrl = typeof AbortController !== 'undefined' ? new AbortController() : null
  const timer = ctrl ? setTimeout(() => ctrl.abort(), timeoutMs) : null
  try {
    const r = await f(HEALTH_PATH, {
      method: 'GET',
      cache: 'no-store',
      headers: { 'X-Requested-With': 'XMLHttpRequest' },
      signal: ctrl ? ctrl.signal : undefined,
    })
    if (!r) return false
    return Boolean(r.ok) || r.status === 401 || r.status === 403
  } catch {
    return false
  } finally {
    if (timer) clearTimeout(timer)
  }
}
