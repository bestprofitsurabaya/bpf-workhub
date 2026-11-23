import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { useRealtimeStore } from './realtime'

// Mock socket.io-client mengikuti pola DriverView.test.js: handler disimpan
// agar bisa dipicu manual (simulasi 'connect' dan event dari server).
const sio = vi.hoisted(() => {
  const handlers = {}
  const socket = {
    on: vi.fn((event, cb) => { handlers[event] = cb }),
    emit: vi.fn(),
    disconnect: vi.fn(),
  }
  return { handlers, socket }
})
vi.mock('socket.io-client', () => ({ io: vi.fn(() => sio.socket) }))

function connectAs(role) {
  const pinia = createPinia()
  setActivePinia(pinia)
  const store = useRealtimeStore(pinia)
  store.connect(role)
  return store
}

function joinedRooms() {
  return sio.socket.emit.mock.calls
    .filter(([event]) => event === 'join_room')
    .map(([, payload]) => payload.room)
}

describe('realtime store — langganan event & room', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  afterEach(() => {
    // `socket` di store bersifat module-level — wajib di-reset antar tes.
    useRealtimeStore().disconnect()
    for (const key of Object.keys(sio.handlers)) delete sio.handlers[key]
  })

  it('finance mendaftar new_finance_task dan join finance_board', () => {
    connectAs('finance')
    expect(sio.socket.on).toHaveBeenCalledWith('new_finance_task', expect.any(Function))
    expect(sio.handlers['new_finance_task']).toBeTypeOf('function')
    sio.handlers['connect']()
    expect(sio.socket.emit).toHaveBeenCalledWith('join_room', { room: 'finance_board' })
    expect(joinedRooms()).toContain('finance_board')
  })

  it('event new_finance_task masuk ke items dengan type dan payload benar', () => {
    const store = connectAs('finance')
    const d = { id: 5, display_id: 'BPF-1', nominal: 100000 }
    sio.handlers['new_finance_task'](d)
    expect(store.items[0].type).toBe('new_finance_task')
    expect(store.items[0].text).toContain('BPF-1')
    expect(store.items[0].data).toEqual(d)
  })

  it('ga mendaftar new_service_report dan join appointments_board', () => {
    connectAs('ga')
    expect(sio.socket.on).toHaveBeenCalledWith('new_service_report', expect.any(Function))
    expect(sio.handlers['new_service_report']).toBeTypeOf('function')
    sio.handlers['connect']()
    expect(sio.socket.emit).toHaveBeenCalledWith('join_room', { room: 'appointments_board' })
    expect(joinedRooms()).toContain('appointments_board')
  })

  it('event new_service_report masuk ke items dengan type benar', () => {
    const store = connectAs('ga')
    sio.handlers['new_service_report']({ id: 9, display_id: 'SRV-009', nopol: 'L 1 AB' })
    expect(store.items[0].type).toBe('new_service_report')
    expect(store.items[0].text).toContain('SRV-009')
  })

  it('admin mendapat kedua event dan kedua room', () => {
    connectAs('admin')
    expect(sio.handlers['new_finance_task']).toBeTypeOf('function')
    expect(sio.handlers['new_service_report']).toBeTypeOf('function')
    sio.handlers['connect']()
    expect(joinedRooms()).toEqual(expect.arrayContaining([
      'finance_board', 'appointments_board', 'ga_hr_board',
    ]))
  })

  it('driver tidak mendaftar event finance/service dan tidak join room board', () => {
    connectAs('driver')
    expect(sio.handlers['new_finance_task']).toBeUndefined()
    expect(sio.handlers['new_service_report']).toBeUndefined()
    sio.handlers['connect']()
    expect(joinedRooms()).toEqual([])
  })
})
