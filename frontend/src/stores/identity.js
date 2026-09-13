/**
 * Identitas perusahaan / cabang (v2.19.2) — variabel branding dinamis.
 *
 * Dibaca dari GET /api/system-config/identity (publik) sekali saat aplikasi
 * dimuat, dipakai di halaman login, sidebar, judul tab & watermark foto.
 * Admin bisa mengubahnya di /app/settings (multi-cabang tanpa ubah kode).
 */
import { reactive } from 'vue'
import { api } from '../api'

export const IDENTITY_KEYS = ['company_name', 'company_subtitle', 'system_name', 'system_version', 'company_address', 'company_phone']

export const identity = reactive({
  company_name: 'PT BESTPROFIT FUTURES',
  company_subtitle: 'Kantor Pusat | Jakarta',
  system_name: 'BPF WorkHub',
  system_version: 'v2.40.0',
  company_address: 'Equity Tower, SCBD Lot 9, Jl. Jend. Sudirman Kav. 52-53, Jakarta Selatan 12190',
  company_phone: '031-5349888',
  loaded: false,
})

/** Cabang/kota dari subtitle (mis. 'Sistem Operasional Kantor | Surabaya' → 'Surabaya'). */
export function companyCity() {
  const s = identity.company_subtitle || ''
  if (s.includes('|')) return s.split('|').pop().trim()
  return s.trim()
}

let _loading = null

export function loadIdentity() {
  if (_loading) return _loading
  _loading = (async () => {
    try {
      const d = await api('/api/system-config/identity')
      if (d && !d.error) {
        for (const k of IDENTITY_KEYS) {
          if (d[k]) identity[k] = d[k]
        }
        identity.loaded = true
        document.title = identity.system_name
      }
    } catch { /* tetap pakai default */ }
    finally { _loading = null }
  })()
  return _loading
}
