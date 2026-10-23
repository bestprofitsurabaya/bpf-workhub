import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'

const { apiMock } = vi.hoisted(() => ({ apiMock: vi.fn() }))
vi.mock('../api', () => ({ api: apiMock }))

import ClaimVerifyCard from './ClaimVerifyCard.vue'

// Detail klaim penuh — semua field rantai verifikasi (wave-17) terisi
const DETAIL_FULL = {
  id: 12, display_id: 'BBM-012', driver_name: 'RIVAN', nopol: 'L 1 A',
  nominal: 100000, liter: 20, odo_km: 45000, status: 'archived',
  created_at: '2026-10-20 08:00:00',
  ga_approved_by: 'ga_sby', ga_approved_at: '2026-10-20 09:30:00',
  anomaly_cleared_by: null, anomaly_cleared_at: null,
  finance_payout_by: 'fin_sby', finance_payout_at: '2026-10-20 10:00:00',
  subsidy_linked_by: 'fin_sby', subsidy_linked_at: '2026-10-20 10:05:00',
  archived_by: 'admin_ho', archived_at: '2026-10-21 06:00:00',
  modified_by: null, modification_note: null, rejection_reason: null,
  photos: [],
}
const CANDIDATE = { id: 1, transaction_id: 'TB-1', product: 'Pertamax', transaction_date: '2026-10-20 08:10', volume: 20, amount: 100000, dvol: 0, dnom: 0, spbu_id: 'SPBU-1', verdict: 'match' }
const LINKED = {
  verdict: 'match', candidates: [CANDIDATE],
  linked: { transaction_id: 'TB-1', volume: 20, amount: 100000, transaction_date: '2026-10-20 08:10', spbu_id: 'SPBU-1', witel: '', city: '' },
  linked_by: 'fin_sby',
}
// klaim baru: belum ada aktor mana pun
const DETAIL_PENDING = { ...DETAIL_FULL, status: 'pending', ga_approved_by: null, ga_approved_at: null, anomaly_cleared_by: null, anomaly_cleared_at: null, finance_payout_by: null, finance_payout_at: null, subsidy_linked_by: null, subsidy_linked_at: null, archived_by: null, archived_at: null }

function mockApi(subsidy = null, detail = DETAIL_FULL) {
  apiMock.mockImplementation((path) => {
    if (path === `/api/transactions/detail/${detail.id}`) return Promise.resolve(detail)
    if (path.startsWith('/api/cross-check/')) return Promise.resolve(null)
    if (path.startsWith('/api/subsidy/match/')) return Promise.resolve(subsidy)
    return Promise.resolve(null)
  })
}

async function mountCard() {
  const w = mount(ClaimVerifyCard, { props: { txId: DETAIL_FULL.id } })
  await flushPromises()
  return w
}

describe('ClaimVerifyCard — ⛓ Rantai Verifikasi', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockApi(LINKED)
  })

  it('blok Rantai Verifikasi tampil setelah Subsidi Tepat, urutan judul benar', async () => {
    const w = await mountCard()
    expect(w.text()).toContain('⛓ Rantai Verifikasi')
    const idxCross = w.text().indexOf('Cross-Check Otomatis')
    const idxSubsidi = w.text().indexOf('Subsidi Tepat')
    const idxChain = w.text().indexOf('⛓ Rantai Verifikasi')
    expect(idxSubsidi).toBeGreaterThan(idxCross)
    expect(idxChain).toBeGreaterThan(idxSubsidi)
  })

  it('langkah penuh: nama + waktu driver/GA/Finance/arsip tersaji', async () => {
    const w = await mountCard()
    const chain = w.find('.cvc-chain')
    expect(chain.text()).toContain('🚗 Klaim diajukan driver')
    expect(chain.text()).toContain('RIVAN')
    expect(chain.text()).toContain('BBM-012')
    expect(chain.text()).toContain('2026-10-20 08:00:00')
    expect(chain.text()).toContain('🛡 Verifikasi GA')
    expect(chain.text()).toContain('ga_sby')
    expect(chain.text()).toContain('2026-10-20 09:30:00')
    expect(chain.find('.badge-green').exists()).toBe(true)
    expect(chain.text()).toContain('🏦 Verifikasi & Pencairan Finance')
    expect(chain.text()).toContain('fin_sby')
    expect(chain.text()).toContain('2026-10-20 10:00:00')
    // sub-baris penjodohan SPBU (subsidy.linked ada, field Tugas 1 terisi)
    expect(chain.text()).toContain('Penjodohan SPBU: fin_sby')
    expect(chain.text()).toContain('2026-10-20 10:05:00')
    expect(chain.text()).toContain('🗄 Arsip')
    expect(chain.text()).toContain('admin_ho')
    expect(chain.text()).toContain('2026-10-21 06:00:00')
    // tidak ada baris menunggu
    expect(chain.text()).not.toContain('Menunggu verifikasi GA')
    expect(chain.text()).not.toContain('Belum diarsipkan')
  })

  it('klaim baru tanpa aktor: langkah redup menunggu muncul', async () => {
    mockApi(null, DETAIL_PENDING)
    const w = await mountCard()
    const chain = w.find('.cvc-chain')
    expect(chain.text()).toContain('RIVAN') // langkah driver tetap ada
    expect(chain.text()).toContain('Menunggu verifikasi GA')
    expect(chain.text()).toContain('Menunggu Finance')
    expect(chain.text()).toContain('Belum diarsipkan')
    // tidak ada nama aktor yang belum bertindak
    expect(chain.text()).not.toContain('ga_sby')
    expect(chain.text()).not.toContain('admin_ho')
    // langkah pending memakai class redup
    expect(chain.findAll('.cvc-step-pending').length).toBe(3)
  })

  it('status rejected + alasan → langkah merah ditolak', async () => {
    mockApi(null, { ...DETAIL_PENDING, status: 'rejected', rejection_reason: 'Foto nota buram' })
    const w = await mountCard()
    const rej = w.find('.cvc-step-rejected')
    expect(rej.exists()).toBe(true)
    expect(rej.text()).toContain('Ditolak — Foto nota buram')
  })
})
