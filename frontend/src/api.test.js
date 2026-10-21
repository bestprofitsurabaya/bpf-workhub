/**
 * api() — penanganan 401.
 *
 * Insiden v2.47.2: upload scraper gagal karena kredensial WordPress ditolak,
 * endpoint mengembalikan 401 → wrapper langsung memicu `bpf:unauthorized` →
 * App.vue membuang sesi dan user dilempar ke /login padahal sesi sehat.
 *
 * Kontrak yang diuji:
 * 1. 401 + sesi masih hidup (/api/auth/me 200) → TIDAK memicu logout,
 *    error tetap dibuang ke pemanggil.
 * 2. 401 + sesi benar-benar habis (/api/auth/me 401) → logout dipicu.
 * 3. Probe sesi di-dedupe (banyak 401 paralel → satu request me).
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

function jsonResponse(status, body) {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => body,
    blob: async () => new Blob(),
  }
}

describe('api() 401 handling', () => {
  let listeners
  let fetchMock
  let api, isSessionAlive, notifyUnauthorized

  beforeEach(async () => {
    listeners = []
    vi.stubGlobal('window', {
      dispatchEvent: (e) => listeners.push(e.type),
      addEventListener: () => {},
      removeEventListener: () => {},
    })
    fetchMock = vi.fn()
    vi.stubGlobal('fetch', fetchMock)
    localStorage.clear()
    vi.resetModules()
    // impor ulang tiap test: state dedupe probe ada di module scope
    ;({ api, isSessionAlive, notifyUnauthorized } = await import('./api'))
  })

  afterEach(() => {
    vi.unstubAllGlobals()
    vi.restoreAllMocks()
  })

  function meRoute(status) {
    return (url) =>
      Promise.resolve(
        String(url).includes('/api/auth/me')
          ? jsonResponse(status, status === 200 ? { user: { role: 'it_sby' } } : {})
          : jsonResponse(401, { ok: false, error: 'WordPress login gagal: kredensial ditolak' })
      )
  }

  it('401 dari upstream TIDAK memicu logout saat sesi masih hidup', async () => {
    fetchMock.mockImplementation(meRoute(200))

    await expect(api('/api/scraper/upload', { method: 'POST', body: {} }))
      .rejects.toThrow(/WordPress login gagal/)

    expect(listeners).not.toContain('bpf:unauthorized')
  })

  it('401 karena sesi habis TETAP memicu logout', async () => {
    fetchMock.mockImplementation(meRoute(401))

    await expect(api('/api/queue', {})).rejects.toThrow()

    expect(listeners).toContain('bpf:unauthorized')
  })

  it('banyak 401 paralel hanya memicu probe sesi sekali', async () => {
    fetchMock.mockImplementation(meRoute(200))

    const settled = await Promise.allSettled([
      api('/api/scraper/upload', { method: 'POST', body: {} }),
      api('/api/scraper/duplicates', { method: 'POST', body: {} }),
      api('/api/scraper/upload-multi', { method: 'POST', body: {} }),
    ])
    expect(settled.every((s) => s.status === 'rejected')).toBe(true)

    const probes = fetchMock.mock.calls.filter(([u]) => String(u).includes('/api/auth/me'))
    expect(probes).toHaveLength(1)
    expect(listeners).not.toContain('bpf:unauthorized')
  })

  it('isSessionAlive() membedakan sesi hidup vs habis', async () => {
    fetchMock.mockImplementation(meRoute(200))
    expect(await isSessionAlive()).toBe(true)

    fetchMock.mockImplementation(meRoute(401))
    await new Promise((r) => setTimeout(r, 2100))   // tunggu cache kedaluwarsa
    expect(await isSessionAlive()).toBe(false)
  })

  it('notifyUnauthorized() tidak melempar event bila sesi hidup', async () => {
    fetchMock.mockImplementation(meRoute(200))
    expect(await notifyUnauthorized()).toBe(false)
    expect(listeners).not.toContain('bpf:unauthorized')

    fetchMock.mockImplementation(meRoute(401))
    await new Promise((r) => setTimeout(r, 2100))
    expect(await notifyUnauthorized()).toBe(true)
    expect(listeners).toContain('bpf:unauthorized')
  })
})
