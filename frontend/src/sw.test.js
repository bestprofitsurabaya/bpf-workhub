/**
 * Regression guard v2.37.8 — Service Worker tidak boleh meng-cache /api/*.
 *
 * Bug: SW v2.37.5 meng-intercept SEMUA GET same-origin (termasuk /api/...)
 * dengan stale-while-revalidate → setelah verifikasi air minum / input
 * kehadiran training, list tetap menampilkan data lama sampai refresh manual.
 *
 * Test ini mengeksekusi public/sw.js di sandbox VM lalu memeriksa apakah
 * handler fetch memanggil respondWith() untuk berbagai jenis request.
 */
import { describe, it, expect, vi } from 'vitest'
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import path from 'node:path'
import vm from 'node:vm'

const swPath = path.join(path.dirname(fileURLToPath(import.meta.url)), '..', 'public', 'sw.js')
const src = readFileSync(swPath, 'utf8')

function loadSW() {
  const handlers = {}
  const cachesStub = {
    match: vi.fn(() => Promise.resolve(undefined)),
    open: vi.fn(() => Promise.resolve({ put: vi.fn(() => Promise.resolve()) })),
    keys: vi.fn(() => Promise.resolve([])),
    delete: vi.fn(() => Promise.resolve(true)),
  }
  const self = {
    addEventListener: (type, fn) => { handlers[type] = fn },
    location: { origin: 'https://bpf.test' },
  }
  vm.runInNewContext(src, {
    self,
    caches: cachesStub,
    fetch: vi.fn(() => Promise.resolve({ ok: true, clone() { return this } })),
    URL,
    console,
    Promise,
  })
  return { handlers, cachesStub }
}

function fetchEvent(url, mode = 'same-origin') {
  return { request: { method: 'GET', url, mode }, respondWith: vi.fn() }
}

describe('service worker (public/sw.js)', () => {
  it('TIDAK mengintercept GET /api/* — data API selalu dari jaringan', () => {
    const { handlers } = loadSW()
    const ev = fetchEvent('https://bpf.test/api/water/purchases?type_id=1&from=2026-09-01')
    handlers.fetch(ev)
    expect(ev.respondWith).not.toHaveBeenCalled()
  })

  it('TIDAK mengintercept POST ke /api/*', () => {
    const { handlers } = loadSW()
    const ev = { request: { method: 'POST', url: 'https://bpf.test/api/water/purchases', mode: 'same-origin' }, respondWith: vi.fn() }
    handlers.fetch(ev)
    expect(ev.respondWith).not.toHaveBeenCalled()
  })

  it('TIDAK mengintercept socket.io (realtime notif)', () => {
    const { handlers } = loadSW()
    const ev = fetchEvent('https://bpf.test/socket.io/?EIO=4&transport=polling')
    handlers.fetch(ev)
    expect(ev.respondWith).not.toHaveBeenCalled()
  })

  it('tetap meng-handle navigasi (offline fallback shell)', () => {
    const { handlers } = loadSW()
    const ev = fetchEvent('https://bpf.test/app/dashboard', 'navigate')
    handlers.fetch(ev)
    expect(ev.respondWith).toHaveBeenCalled()
  })

  it('tetap meng-cache asset ber-hash (cache-first)', () => {
    const { handlers } = loadSW()
    const ev = fetchEvent('https://bpf.test/app/assets/index-AbCdEf123.js')
    handlers.fetch(ev)
    expect(ev.respondWith).toHaveBeenCalled()
  })

  it('nama CACHE memuat marker v2401 (memicu aktivasi SW baru di klien lama)', () => {
    expect(src).toMatch(/const CACHE = 'bpf-spa-\d{8}-v2401'/)
  })
})
