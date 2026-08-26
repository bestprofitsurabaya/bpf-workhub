/**
 * Fetch wrapper — JSON + CSRF + error normalization.
 * CSRF token disimpan dari /api/auth/me atau /api/auth/login (session-based).
 *
 * Stale CSRF recovery: bila server menolak POST/PUT/DELETE dengan error CSRF
 * (mis. tab lama yang masih memegang token sesi sebelum re-login di tab lain),
 * wrapper mengambil token baru dari /api/auth/me lalu retry SEKALI.
 */
export async function api(path, { method = 'GET', body, params, raw = false } = {}, _retried = false) {
  const opts = { method, headers: raw ? {} : { Accept: 'application/json' } }
  if (body !== undefined) {
    opts.headers['Content-Type'] = 'application/json'
    opts.body = JSON.stringify(body)
  }
  const csrf = localStorage.getItem('bpf_csrf') || sessionStorage.getItem('bpf_csrf')
  if (csrf && !['GET', 'HEAD', 'OPTIONS'].includes(method)) {
    opts.headers['X-CSRF-Token'] = csrf
  }
  if (params) {
    const q = new URLSearchParams(
      Object.entries(params).filter(([, v]) => v !== undefined && v !== null && v !== '')
    ).toString()
    if (q) path += (path.includes('?') ? '&' : '?') + q
  }

  let r
  try {
    r = await fetch(path, opts)
  } catch (e) {
    throw new Error('Koneksi ke server gagal. Periksa jaringan Anda.')
  }

  if (r.status === 401) {
    window.dispatchEvent(new CustomEvent('bpf:unauthorized'))
  }

  if (raw) {
    if (!r.ok) {
      let msg = `HTTP ${r.status}`
      try { const d = await r.json(); msg = (d && (d.msg || d.error)) || msg } catch { /* bukan JSON */ }
      const err = new Error(msg)
      err.status = r.status
      throw err
    }
    return await r.blob()
  }

  let data = null
  try { data = await r.json() } catch { data = null }

  if (!r.ok) {
    const msg = (data && (data.msg || data.error)) || `HTTP ${r.status}`
    // Token CSRF stale → refresh dari /api/auth/me lalu retry sekali.
    if (
      r.status === 400 &&
      typeof msg === 'string' &&
      msg.includes('CSRF') &&
      path !== '/api/auth/me' &&
      !_retried
    ) {
      try {
        const meResp = await fetch('/api/auth/me', { headers: { Accept: 'application/json' } })
        const meData = await meResp.json()
        if (meData?.csrf_token) {
          localStorage.setItem('bpf_csrf', meData.csrf_token)
          return api(path, { method, body, params, raw }, true)
        }
      } catch { /* fall through ke throw normal */ }
    }
    const err = new Error(msg)
    err.status = r.status
    err.data = data
    throw err
  }
  return data
}
