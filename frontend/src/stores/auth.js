import { defineStore } from 'pinia'
import { api } from '../api'

const BRANCH_NAMES = {
  sby: 'Surabaya', hu: 'Jakarta HO', jkt2: 'Jakarta 2', bdg: 'Bandung',
  smg: 'Semarang', mlg: 'Malang', mdn: 'Medan', bjm: 'Banjarmasin',
  plm: 'Palembang', lpg: 'Lampung',
}

const BASE_ROLE_LABELS = {
  admin: 'Admin', ga: 'GA', finance: 'Finance', marketing: 'Marketing',
  chief_driver: 'Chief Driver', driver: 'Driver', ob: 'OB',
  receptionist: 'Receptionist', traineer: 'Traineer', ga_hr: 'GA HR',
  it: 'IT',
}

function deriveLabel(username, role) {
  // e.g. finance_sby → Finance Surabaya, ga_bdg → GA Bandung, it_sby → IT Surabaya
  const parts = (username || '').split('_')
  if (parts.length >= 2) {
    const base = parts[0]
    const branch = parts.slice(1).join('_')
    const branchName = BRANCH_NAMES[branch]
    if (branchName) {
      const baseLabel = BASE_ROLE_LABELS[base] || base.toUpperCase()
      return `${baseLabel} ${branchName}`
    }
  }
  return ROLE_META[role]?.label || role
}

/** Metadata per role (ISO/IEC 27001: hak akses minimal per peran). */
export const ROLE_META = {
  admin:        { label: 'Admin',        home: '/dashboard',    color: '#2563eb', icon: '🛡️' },
  ga:           { label: 'GA Officer',   home: '/ga',           color: '#0891b2', icon: '🧾' },
  finance:      { label: 'Finance',      home: '/finance',      color: '#059669', icon: '💰' },
  marketing:    { label: 'Marketing',    home: '/marketing',    color: '#d97706', icon: '📣' },
  chief_driver: { label: 'Chief Driver', home: '/chief-driver', color: '#7c3aed', icon: '🚛' },
  driver:       { label: 'Driver',       home: '/driver',       color: '#16a34a', icon: '🚛' },
  ob:           { label: 'OB',           home: '/water',        color: '#0d9488', icon: '🚰' },
  receptionist: { label: 'Receptionist', home: '/receptionist', color: '#db2777', icon: '🪪' },
  traineer:     { label: 'Traineer',     home: '/traineer',     color: '#b45309', icon: '🎯' },
  ga_hr:        { label: 'GA HR',        home: '/ga-hr',        color: '#7e22ce', icon: '⏰' },
  it_sby:       { label: 'IT Surabaya',  home: '/it',           color: '#0891b2', icon: '📰' },
  it_hu:        { label: 'IT Jakarta HO', home: '/it',          color: '#0891b2', icon: '📰' },
  it_jkt2:      { label: 'IT Jakarta 2', home: '/it',           color: '#0891b2', icon: '📰' },
  it_bdg:       { label: 'IT Bandung',   home: '/it',           color: '#0891b2', icon: '📰' },
  it_smg:       { label: 'IT Semarang',  home: '/it',           color: '#0891b2', icon: '📰' },
  it_mlg:       { label: 'IT Malang',    home: '/it',           color: '#0891b2', icon: '📰' },
  it_mdn:       { label: 'IT Medan',     home: '/it',           color: '#0891b2', icon: '📰' },
  it_bjm:       { label: 'IT Banjarmasin', home: '/it',         color: '#0891b2', icon: '📰' },
  it_plm:       { label: 'IT Palembang', home: '/it',           color: '#0891b2', icon: '📰' },
  it_lpg:       { label: 'IT Lampung',   home: '/it',           color: '#0891b2', icon: '📰' },
}

export const useAuthStore = defineStore('auth', {
  state: () => ({
    ready: false,
    user: null,
  }),
  getters: {
    role: (s) => s.user?.role || null,
    isAuthenticated: (s) => !!s.user,
    meta: (s) => {
      if (!s.user) return null
      const base = ROLE_META[s.user.role] || {}
      return {
        ...base,
        label: deriveLabel(s.user.user_name, s.user.role),
      }
    },
  },
  actions: {
    /** Pulihkan sesi saat SPA dimuat. */
    async bootstrap() {
      try {
        const me = await api('/api/auth/me')
        if (me?.authenticated) {
          this.user = me.user
        } else {
          this.user = null
        }
        if (me?.csrf_token) localStorage.setItem('bpf_csrf', me.csrf_token)
      } catch {
        this.user = null
      } finally {
        this.ready = true
      }
      return !!this.user
    },
    async login(username, pin) {
      const d = await api('/api/auth/login', { method: 'POST', body: { username, pin } })
      this.user = d.user
      if (d.csrf_token) localStorage.setItem('bpf_csrf', d.csrf_token)
      return d
    },
    async logout() {
      try { await api('/api/auth/logout', { method: 'POST' }) } catch { /* noop */ }
      this.user = null
      localStorage.removeItem('bpf_csrf')
      window.location.href = '/app/login'
    },
  },
})
