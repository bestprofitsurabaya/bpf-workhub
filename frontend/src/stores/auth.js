import { defineStore } from 'pinia'
import { api } from '../api'

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
  it_hu:        { label: 'IT Jakarta HO', home: '/it',           color: '#0891b2', icon: '📰' },
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
    meta: (s) => (s.user ? ROLE_META[s.user.role] : null),
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
      }
      this.ready = true
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
    },
  },
})
