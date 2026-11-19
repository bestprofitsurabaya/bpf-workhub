import { describe, it, expect, vi } from 'vitest'
import { probeConnectivity } from './connectivity'

describe('probeConnectivity', () => {
  it('menganggap online bila server menjawab 200', async () => {
    const f = vi.fn(() => Promise.resolve({ ok: true, status: 200 }))
    await expect(probeConnectivity({ fetchImpl: f })).resolves.toBe(true)
    expect(f).toHaveBeenCalledTimes(1)
    expect(f.mock.calls[0][0]).toBe('/api/health')
    expect(f.mock.calls[0][1].cache).toBe('no-store')
  })

  it('401/403 tetap berarti server hidup (online)', async () => {
    await expect(probeConnectivity({ fetchImpl: async () => ({ ok: false, status: 401 }) })).resolves.toBe(true)
    await expect(probeConnectivity({ fetchImpl: async () => ({ ok: false, status: 403 }) })).resolves.toBe(true)
  })

  it('5xx / jaringan gagal / timeout dianggap offline', async () => {
    await expect(probeConnectivity({ fetchImpl: async () => ({ ok: false, status: 502 }) })).resolves.toBe(false)
    await expect(probeConnectivity({ fetchImpl: async () => { throw new Error('network') } })).resolves.toBe(false)
    const slow = vi.fn((_url, opts) => new Promise((_res, rej) => {
      opts.signal.addEventListener('abort', () => rej(new Error('aborted')))
    }))
    await expect(probeConnectivity({ fetchImpl: slow, timeoutMs: 20 })).resolves.toBe(false)
  })
})
