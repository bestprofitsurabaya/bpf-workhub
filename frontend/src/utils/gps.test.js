import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { detailedLocation, formatAddress, locateWithAddress } from './gps'

const ADDRESS = {
  road: 'Jl. Jend. Sudirman',
  house_number: '52',
  suburb: 'Senayan',
  city_district: 'Kebayoran Baru',
  city: 'Jakarta Selatan',
  state: 'DKI Jakarta',
  postcode: '12190',
  country: 'Indonesia',
}

function okJson(data) {
  return { ok: true, status: 200, json: () => Promise.resolve(data) }
}

describe('GPS utils', () => {
  const originalGeo = Object.getOwnPropertyDescriptor(navigator, 'geolocation')
  beforeEach(() => {
    vi.restoreAllMocks()
  })
  afterEach(() => {
    vi.unstubAllGlobals()
    if (originalGeo) Object.defineProperty(navigator, 'geolocation', originalGeo)
    else delete navigator.geolocation
  })

  it('formatAddress menyusun alamat ringkas tanpa bagian kosong', () => {
    expect(formatAddress({
      jalan: 'Jl. A', nomor: '1', kelurahan: 'Kel', kecamatan: 'Kec',
      kota: 'Kota', provinsi: 'Prov', kode_pos: '12345',
    })).toBe('Jl. A, No. 1, Kel, Kec, Kota, Prov, Kode Pos 12345')
    expect(formatAddress(null)).toBe('')
  })

  it('detailedLocation memakai cache untuk koordinat yang sama', async () => {
    const fetchMock = vi.fn(() => Promise.resolve(okJson({ display_name: 'X', address: ADDRESS })))
    vi.stubGlobal('fetch', fetchMock)

    const a = await detailedLocation(-6.22451, 106.80231)
    const b = await detailedLocation(-6.22452, 106.80234) // masih 4 desimal sama
    expect(a.kota).toBe('Jakarta Selatan')
    expect(b).toBe(a)
    expect(fetchMock).toHaveBeenCalledTimes(1)
  })

  it('detail gagal (HTTP 429) tidak disimpan di cache', async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce({ ok: false, status: 429, json: () => Promise.resolve({}) })
      .mockResolvedValueOnce(okJson({ display_name: 'Y', address: ADDRESS }))
    vi.stubGlobal('fetch', fetchMock)

    await expect(detailedLocation(-7.1, 112.1)).rejects.toThrow('HTTP 429')
    const second = await detailedLocation(-7.1, 112.1)
    expect(second.full_address).toBe('Y')
    expect(fetchMock).toHaveBeenCalledTimes(2)
  })

  it('locateWithAddress hanya 1 reverse + 1 pencarian SPBU, meneruskan accuracy', async () => {
    const fetchMock = vi.fn((url) => Promise.resolve(okJson(
      String(url).includes('/search') ? [] : { display_name: 'Z', address: ADDRESS }
    )))
    vi.stubGlobal('fetch', fetchMock)
    Object.defineProperty(navigator, 'geolocation', {
      configurable: true,
      value: {
        getCurrentPosition: (ok) => ok({
          coords: { latitude: -6.2, longitude: 106.8, accuracy: 25.4 },
          timestamp: Date.now(),
        }),
      },
    })

    const res = await locateWithAddress()
    expect(fetchMock).toHaveBeenCalledTimes(2)
    expect(res.addr).toContain('Jl. Jend. Sudirman')
    expect(res.accuracy).toBe(25)
    expect(res.detail.kota).toBe('Jakarta Selatan')
    expect(res.at).toMatch(/\d{4}-\d{2}-\d{2}T/)
  })
})
