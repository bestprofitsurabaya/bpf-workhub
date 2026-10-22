const MODE_KEY = 'bpf_p5'
const T0_KEY = 'bpf_p5_t0'
const FIRST_KEY = 'bpf_p5_first_action'

export function enableUsabilityModeFromUrl(search = '') {
  try {
    if (new URLSearchParams(search).get('p5') === '1') localStorage.setItem(MODE_KEY, '1')
  } catch { /* URLSearchParams tidak tersedia */ }
}

export function isUsabilityMode() {
  return localStorage.getItem(MODE_KEY) === '1'
}

export function markSessionStart({ force = false } = {}) {
  if (force || !sessionStorage.getItem(T0_KEY)) {
    sessionStorage.setItem(T0_KEY, String(Date.now()))
  }
}

export function markFirstAction(label) {
  if (!isUsabilityMode() || sessionStorage.getItem(FIRST_KEY)) return null
  const started = Number(sessionStorage.getItem(T0_KEY))
  if (!started) return null
  const record = { label, ms: Date.now() - started, at: new Date().toISOString() }
  sessionStorage.setItem(FIRST_KEY, JSON.stringify(record))
  return record
}

export function firstAction() {
  try { return JSON.parse(sessionStorage.getItem(FIRST_KEY) || 'null') } catch { return null }
}

export function resetUsabilitySession() {
  sessionStorage.removeItem(FIRST_KEY)
  markSessionStart({ force: true })
}

export function formatDuration(ms) {
  const n = Number(ms)
  if (!Number.isFinite(n) || n < 0) return '—'
  return `${(n / 1000).toFixed(1)} dtk`
}
