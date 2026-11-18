import { describe, it, expect, beforeEach } from 'vitest'
import { useBranchContext, _resetBranchContext, BRANCH_CTX_KEY } from './branchContext'

describe('stores/branchContext — konteks cabang Admin Pusat (v2.114.0)', () => {
  beforeEach(() => {
    localStorage.removeItem(BRANCH_CTX_KEY)
    _resetBranchContext()
  })

  it('enter mencatat konteks, menormalkan kode, dan menyimpannya', () => {
    const ctx = useBranchContext()
    ctx.enter('sby', 'Surabaya')
    expect(ctx.active.value).toEqual({ code: 'SBY', name: 'Surabaya' })
    expect(JSON.parse(localStorage.getItem(BRANCH_CTX_KEY))).toEqual({
      code: 'SBY', name: 'Surabaya',
    })
  })

  it('nama kosong memakai kode sebagai label', () => {
    const ctx = useBranchContext()
    ctx.enter('MLG')
    expect(ctx.active.value.name).toBe('MLG')
  })

  it('kode kosong diabaikan — tidak mengaktifkan konteks palsu', () => {
    const ctx = useBranchContext()
    ctx.enter('', 'Tanpa Kode')
    expect(ctx.active.value).toBeNull()
  })

  it('leave membersihkan state & localStorage', () => {
    const ctx = useBranchContext()
    ctx.enter('SBY', 'Surabaya')
    ctx.leave()
    expect(ctx.active.value).toBeNull()
    expect(localStorage.getItem(BRANCH_CTX_KEY)).toBeNull()
  })

  it('state dipulihkan dari localStorage (banner bertahan saat reload)', () => {
    localStorage.setItem(BRANCH_CTX_KEY, JSON.stringify({ code: 'BDG', name: 'Bandung' }))
    _resetBranchContext()
    const ctx = useBranchContext()
    expect(ctx.active.value).toEqual({ code: 'BDG', name: 'Bandung' })
  })

  it('data rusak di localStorage tidak membuat aplikasi gagal', () => {
    localStorage.setItem(BRANCH_CTX_KEY, '{bukan json')
    _resetBranchContext()
    expect(useBranchContext().active.value).toBeNull()
  })
})
