import { describe, it, expect, vi, beforeEach } from 'vitest'
import { urlBase64ToUint8Array, getPushState, isIOS } from './push'

describe('web push utils', () => {
  beforeEach(() => {
    vi.restoreAllMocks()
  })

  it('urlBase64ToUint8Array mendekode base64url tanpa padding', () => {
    // bytes [1,2,3,4] → base64url 'AQIDBA'
    const arr = urlBase64ToUint8Array('AQIDBA')
    expect(Array.from(arr)).toEqual([1, 2, 3, 4])
  })

  it('isIOS mendeteksi iPhone dari user-agent', () => {
    const original = navigator.userAgent
    Object.defineProperty(navigator, 'userAgent', {
      configurable: true,
      value: 'Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15',
    })
    expect(isIOS()).toBe(true)
    Object.defineProperty(navigator, 'userAgent', { configurable: true, value: original })
  })

  it('getPushState melaporkan tidak didukung bila PushManager tidak ada', async () => {
    const originalPush = Object.getOwnPropertyDescriptor(window, 'PushManager')
    delete window.PushManager
    const st = await getPushState()
    expect(st.supported).toBe(false)
    if (originalPush) Object.defineProperty(window, 'PushManager', originalPush)
  })
})
