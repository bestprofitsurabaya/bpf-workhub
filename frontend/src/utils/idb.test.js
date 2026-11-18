import { describe, it, expect } from 'vitest'
import { QUEUE_STORES } from './idb'

describe('store antrean offline driver', () => {
  it('mencakup kelima jalur submit (v2.120.0)', () => {
    expect(QUEUE_STORES).toEqual([
      'fuel_queue', 'trip_queue', 'lpj_queue', 'overtime_queue', 'cash_queue',
    ])
  })
})
