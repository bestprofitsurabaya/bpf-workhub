<script setup>
import { ref, onMounted, computed, watch } from 'vue'
import { api } from '../api'
import Modal from '../components/Modal.vue'

// --- State ---
const loading = ref(true)
const err = ref('')
const msg = ref('')
const busy = ref(false)
const activeTab = ref('dashboard')
const darkMode = ref(localStorage.getItem('scraper_dark') === 'true')
const showOnboarding = ref(false)
const onboardingStep = ref(0)

// Dashboard stats
const analytics = ref({ total_articles: 0, by_site: {}, by_date: {} })
const schedule = ref({ optimal_time: '', published_today: 0, can_publish: true, daily_limit: 10 })
const scraperSettings = ref({ daily_limit: 10 })
const historyList = ref([])

// Sites
const sites = ref([])
const showSiteForm = ref(false)
const siteForm = ref({ name: '', wp_url: '', wp_media_url: '', username: '', app_password: '', branch_code: '' })
const showFormPassword = ref(false)
import { reactive } from 'vue'
const showCardPassword = reactive({}) // {siteName: true/false}

// Scraper
const scrapePages = ref(2)
const selectedSource = ref('all')
const articles = ref([])
const scrapeBusy = ref(false)
const selectedArticles = ref(new Set())
const sourceFilter = ref('all') // filter articles by source
const filteredArticles = computed(() => {
  if (sourceFilter.value === 'all') return articles.value
  return articles.value.filter(a => a.source === sourceFilter.value)
})
const sourceCount = computed(() => {
  const counts = { all: articles.value.length, newsmaker: 0, detik_finance: 0 }
  articles.value.forEach(a => { if (counts[a.source] !== undefined) counts[a.source]++ })
  return counts
})
const sourceLabel = (src) => ({ newsmaker: '📰 Newsmaker.id', detik_finance: '📰 Detik Finance' })[src] || src

// Upload
const selectedSite = ref('')
const uploadBusy = ref(false)
const uploadResult = ref(null)
const uploadLog = ref([])
const showUploadLog = ref(false)
const settings = ref({
  backlinks: true, max_backlinks: 3, seo_optimize: true,
  static_tags: 'newsmaker.id, Market, Geopolitics, Financial News',
})

// Progress
const progress = ref(null)
const progressInterval = ref(null)

// Duplicates
const dupSite = ref('')
const duplicates = ref([])
const dupBusy = ref(false)

// Backlinks
const showBacklinks = ref(false)
const authoritySites = ref({})
const keywordMapping = ref({})
const newKeyword = ref('')
const newSiteName = ref('')

// History modal
const showHistory = ref(false)
const historyFilter = ref({ date_from: '', date_to: '', action: '' })
const historyBusy = ref(false)

// Log
const logs = ref([])
const showLog = ref(false)
const logLevelFilter = ref('')
const filteredLogs = computed(() => {
  if (!logLevelFilter.value) return logs.value
  return logs.value.filter(l => l.level === logLevelFilter.value)
})
function logLevelColor(level) {
  const colors = { ERROR: '#ef4444', WARNING: '#f59e0b', INFO: '#10b981', DEBUG: '#6b7280', CRITICAL: '#ec4899' }
  return colors[level] || '#6b7280'
}
function formatLogTime(ts) {
  if (!ts) return ''
  try {
    const d = new Date(ts)
    return d.toLocaleTimeString('id-ID', { hour: '2-digit', minute: '2-digit', second: '2-digit' })
  } catch { return ts }
}

// Report
const reportArticles = ref([])
const reportSummary = ref({ total: 0, new: 0, updated: 0, error: 0, avg_seo: 0 })
const reportFilter = ref({ date_from: '', date_to: '', site: '', status: '', source: '', search: '' })
const reportFilterOptions = ref({ sites: [], sources: [] })
const reportBusy = ref(false)

// FAB
const showFab = ref(false)

// --- Computed ---
const siteNames = computed(() => sites.value.map(s => s.name))
const selectedCount = computed(() => selectedArticles.value.size)
const tabList = [
  { key: 'dashboard', icon: '📊', label: 'Dashboard' },
  { key: 'sites', icon: '🌐', label: 'Sites' },
  { key: 'scrape', icon: '🔍', label: 'Scrape' },
  { key: 'upload', icon: '📤', label: 'Upload' },
  { key: 'seo', icon: '🔗', label: 'SEO' },
  { key: 'analytics', icon: '📈', label: 'Analytics' },
  { key: 'report', icon: '📋', label: 'Report' },
]
const onboardingTasks = [
  { icon: '🌐', text: 'Add WordPress Site', done: computed(() => sites.value.length > 0) },
  { icon: '🔌', text: 'Test Connection', done: computed(() => false) },
  { icon: '🔗', text: 'Configure Backlinks', done: computed(() => Object.keys(keywordMapping.value).length > 0) },
  { icon: '🔍', text: 'Scrape Articles', done: computed(() => articles.value.length > 0) },
  { icon: '📤', text: 'Upload to WordPress', done: computed(() => (uploadResult.value?.new_posts || 0) + (uploadResult.value?.updated_posts || 0) > 0) },
  { icon: '📊', text: 'View Analytics', done: computed(() => false) },
]
const onboardingProgress = computed(() => {
  const done = onboardingTasks.filter(t => t.done.value).length
  return Math.round((done / onboardingTasks.length) * 100)
})

// --- Dark Mode ---
watch(darkMode, (v) => {
  localStorage.setItem('scraper_dark', v)
  document.documentElement.classList.toggle('dark', v)
})

// --- Load ---
async function loadSites() {
  loading.value = true; err.value = ''
  try {
    sites.value = await api('/api/scraper/sites')
    if (!sites.value.length) showOnboarding.value = true
  } catch (e) { err.value = e.message }
  finally { loading.value = false }
}

async function loadDashboard() {
  try {
    const [a, s, h, st] = await Promise.all([
      api('/api/scraper/analytics'),
      api('/api/scraper/schedule'),
      api('/api/scraper/history?limit=10'),
      api('/api/scraper/settings'),
    ])
    analytics.value = a
    schedule.value = s
    historyList.value = h.history || []
    scraperSettings.value = st
  } catch { /* noop */ }
}

async function saveDailyLimit() {
  try {
    const r = await api('/api/scraper/settings', { method: 'POST', body: { daily_limit: scraperSettings.value.daily_limit } })
    if (r.ok) {
      schedule.value.daily_limit = r.settings.daily_limit
      msg.value = `✅ Limit diubah ke ${r.settings.daily_limit}/hari`
    }
  } catch (e) { msg.value = '❌ ' + e.message }
}

// --- Progress ---
async function pollProgress(taskId) {
  if (progressInterval.value) clearInterval(progressInterval.value)
  progress.value = { stage: 'start', progress: 0, message: 'Memulai...', total: 0, current: 0 }
  progressInterval.value = setInterval(async () => {
    try {
      const r = await api(`/api/scraper/progress/${taskId}`)
      if (r.ok) {
        progress.value = r
        if (r.stage === 'done') { clearInterval(progressInterval.value); progressInterval.value = null }
      }
    } catch { /* ignore */ }
  }, 800)
}
function stopProgress() { if (progressInterval.value) { clearInterval(progressInterval.value); progressInterval.value = null }; progress.value = null }

// --- WP Site Management ---
function openSiteForm(site) {
  siteForm.value = site ? { ...site } : { name: '', wp_url: '', wp_media_url: '', username: '', app_password: '', branch_code: '' }
  showSiteForm.value = true
}
async function saveSite() {
  busy.value = true; msg.value = ''
  try {
    const body = { ...siteForm.value }
    if (!body.app_password && body.name) delete body.app_password
    await api('/api/scraper/sites', { method: 'POST', body })
    msg.value = '✅ Site disimpan'; showSiteForm.value = false; await loadSites()
  } catch (e) { msg.value = '❌ ' + e.message }
  finally { busy.value = false }
}
async function deleteSite(name) {
  if (!confirm(`Hapus "${name}"?`)) return
  busy.value = true
  try { await api(`/api/scraper/sites/${encodeURIComponent(name)}`, { method: 'DELETE' }); msg.value = `✅ "${name}" dihapus`; await loadSites() }
  catch (e) { msg.value = '❌ ' + e.message }
  finally { busy.value = false }
}
async function testConnection(site) {
  msg.value = '⏳ Menguji koneksi...'
  try {
    const r = await api('/api/scraper/test-connection', { method: 'POST', body: { site_name: site.name } })
    msg.value = r.ok ? '✅ ' + r.message : '❌ ' + r.message
  } catch (e) { msg.value = '❌ ' + e.message }
}
async function testFromForm() {
  msg.value = '⏳ Menguji koneksi...'
  try {
    const r = await api('/api/scraper/test-connection', {
      method: 'POST',
      body: { wp_url: siteForm.value.wp_url, username: siteForm.value.username, app_password: siteForm.value.app_password }
    })
    msg.value = r.ok ? '✅ ' + r.message : '❌ ' + r.message
  } catch (e) { msg.value = '❌ ' + e.message }
}

// --- Scrape ---
async function scrapeArticles() {
  scrapeBusy.value = true; msg.value = ''; articles.value = []; selectedArticles.value = new Set()
  const taskId = `scrape_${Date.now()}`
  pollProgress(taskId)
  try {
    const r = await api(`/api/scraper/check?task_id=${taskId}`, { method: 'POST', body: { pages: scrapePages.value, source: selectedSource.value } })
    articles.value = r.articles || []
    // Auto-select all
    articles.value.forEach((_, i) => selectedArticles.value.add(i))
    msg.value = r.ok ? `✅ ${r.count} artikel ditemukan` : '⚠️ Tidak ada artikel'
  } catch (e) { msg.value = '❌ ' + e.message }
  finally { scrapeBusy.value = false }
}

function toggleArticle(idx) {
  const s = new Set(selectedArticles.value)
  s.has(idx) ? s.delete(idx) : s.add(idx)
  selectedArticles.value = s
}
function toggleAllArticles() {
  const visible = filteredArticles.value
  const allSelected = visible.every(a => selectedArticles.value.has(articles.value.indexOf(a)))
  if (allSelected) {
    visible.forEach(a => selectedArticles.value.delete(articles.value.indexOf(a)))
  } else {
    visible.forEach(a => selectedArticles.value.add(articles.value.indexOf(a)))
  }
  selectedArticles.value = new Set(selectedArticles.value)
}

// --- Upload ---
async function uploadToWP() {
  if (!selectedSite.value) { msg.value = '⚠️ Pilih site'; return }
  const toUpload = articles.value.filter((_, i) => selectedArticles.value.has(i))
  if (!toUpload.length) { msg.value = '⚠️ Pilih artikel'; return }
  uploadBusy.value = true; msg.value = ''; uploadResult.value = null; uploadLog.value = []; showUploadLog.value = true
  const taskId = `upload_${Date.now()}`
  pollProgress(taskId)
  try {
    const r = await api(`/api/scraper/upload?task_id=${taskId}`, {
      method: 'POST',
      body: { site_name: selectedSite.value, articles: toUpload, settings: { ...settings.value } },
    })
    uploadResult.value = r
    uploadLog.value.push({ time: new Date().toLocaleTimeString('id-ID'), type: 'success', text: `Selesai: ${r.new_posts} baru, ${r.updated_posts} update` })
    if (r.errors?.length) r.errors.forEach(e => uploadLog.value.push({ time: new Date().toLocaleTimeString('id-ID'), type: 'error', text: e }))
    msg.value = `✅ ${r.new_posts} baru, ${r.updated_posts} update`
    loadDashboard()
  } catch (e) { msg.value = '❌ ' + e.message }
  finally { uploadBusy.value = false }
}

// --- Duplicates ---
async function checkDuplicates() {
  if (!dupSite.value) return
  dupBusy.value = true; duplicates.value = []
  try { duplicates.value = (await api('/api/scraper/duplicates', { method: 'POST', body: { site_name: dupSite.value } })).duplicates || [] }
  catch { /* noop */ }
  finally { dupBusy.value = false }
}
async function deleteDuplicate(postIds) {
  if (!confirm(`Hapus ${postIds.length} duplikat?`)) return
  dupBusy.value = true
  try { await api('/api/scraper/duplicates/delete', { method: 'POST', body: { site_name: dupSite.value, post_ids: postIds } }); await checkDuplicates() }
  catch { /* noop */ }
  finally { dupBusy.value = false }
}

// --- Backlinks ---
async function loadBacklinks() {
  try { const r = await api('/api/scraper/backlinks'); authoritySites.value = r.authority_sites || {}; keywordMapping.value = r.keyword_mapping || {} } catch { /* noop */ }
}
function openBacklinksModal() { loadBacklinks(); showBacklinks.value = true }
async function saveKeywordMapping() {
  if (!newKeyword.value || !newSiteName.value) return
  busy.value = true
  try { await api('/api/scraper/backlinks/add-keyword', { method: 'POST', body: { keyword: newKeyword.value, site_name: newSiteName.value } }); keywordMapping.value[newKeyword.value] = newSiteName.value; newKeyword.value = ''; newSiteName.value = '' }
  catch { /* noop */ }
  finally { busy.value = false }
}

// --- History ---
async function loadHistory() {
  historyBusy.value = true
  try { const p = new URLSearchParams(); if (historyFilter.value.date_from) p.set('date_from', historyFilter.value.date_from); if (historyFilter.value.date_to) p.set('date_to', historyFilter.value.date_to); if (historyFilter.value.action) p.set('action', historyFilter.value.action); historyList.value = (await api(`/api/scraper/history?${p}`)).history || [] }
  catch { historyList.value = [] }
  finally { historyBusy.value = false }
}

// --- Log ---
async function loadLog() { try { logs.value = await api('/api/scraper/log?limit=100') } catch { logs.value = [] } }
function openLog() { loadLog(); showLog.value = true }

// --- Report ---
async function loadReport() {
  reportBusy.value = true
  try {
    const params = new URLSearchParams()
    for (const [k, v] of Object.entries(reportFilter.value)) {
      if (v) params.set(k, v)
    }
    const r = await api(`/api/scraper/report?${params}`)
    reportArticles.value = r.articles || []
    reportSummary.value = r.summary || {}
    reportFilterOptions.value = r.filter_options || { sites: [], sources: [] }
  } catch { reportArticles.value = [] }
  finally { reportBusy.value = false }
}

function exportReportCSV() {
  const params = new URLSearchParams()
  for (const [k, v] of Object.entries(reportFilter.value)) {
    if (v) params.set(k, v)
  }
  window.open(`/api/scraper/report/export?${params}`, '_blank')
}

function resetReportFilter() {
  reportFilter.value = { date_from: '', date_to: '', site: '', status: '', source: '', search: '' }
  loadReport()
}

// --- SEO Score Visual ---
function seoColor(score) { return score >= 80 ? '#10b981' : score >= 60 ? '#f59e0b' : '#ef4444' }
function seoLabel(score) { return score >= 80 ? 'Excellent' : score >= 60 ? 'Good' : 'Needs Work' }

onMounted(() => { loadSites(); loadDashboard(); document.documentElement.classList.toggle('dark', darkMode.value) })
</script>

<template>
  <div class="scraper-app" :class="{ dark: darkMode }">
    <!-- Header -->
    <div class="scraper-header">
      <div class="header-left">
        <h3>📰 News Scraper</h3>
        <span class="header-badge" v-if="schedule.can_publish">🟢 Siap Publish</span>
        <span class="header-badge warn" v-else>⏸️ Jeda — {{ schedule.published_today }}/{{ schedule.daily_limit || 10 }} hari ini</span>
      </div>
      <div class="header-right">
        <span class="optimal-time" v-if="schedule.optimal_time">⏰ {{ schedule.optimal_time }}</span>
        <button class="icon-btn" @click="darkMode = !darkMode" :title="darkMode ? '☀️ Light' : '🌙 Dark'">
          {{ darkMode ? '☀️' : '🌙' }}
        </button>
        <button class="icon-btn" @click="openLog" title="📝 Log">📝</button>
        <button class="icon-btn" @click="showOnboarding = true" title="❓ Help">❓</button>
      </div>
    </div>

    <!-- Tab Navigation -->
    <div class="tab-nav">
      <button v-for="tab in tabList" :key="tab.key" class="tab-btn" :class="{ active: activeTab === tab.key }" @click="activeTab = tab.key; if (tab.key === 'report') loadReport()">
        <span class="tab-icon">{{ tab.icon }}</span>
        <span class="tab-label">{{ tab.label }}</span>
      </button>
    </div>

    <!-- Progress Bar -->
    <div v-if="progress && progress.stage !== 'done'" class="progress-card">
      <div class="progress-header">
        <span class="progress-msg">⏳ {{ progress.message || 'Memproses...' }}</span>
        <span class="progress-pct">{{ progress.progress }}%</span>
      </div>
      <div class="progress-bar">
        <div class="progress-fill" :style="{ width: progress.progress + '%' }"></div>
      </div>
      <div class="progress-footer">
        <span>{{ progress.stage }}</span>
        <span v-if="progress.total">{{ progress.current }}/{{ progress.total }}</span>
      </div>
    </div>

    <!-- Message -->
    <div v-if="msg" class="alert" :class="msg.startsWith('✅') ? 'alert-success' : msg.startsWith('❌') ? 'alert-error' : 'alert-info'">{{ msg }}</div>

    <!-- Loading -->
    <div v-if="loading" class="empty skeleton">⏳ Memuat…</div>
    <div v-else-if="err" class="alert alert-error">{{ err }}</div>

    <template v-else>

      <!-- ===== TAB: DASHBOARD ===== -->
      <div v-if="activeTab === 'dashboard'" class="tab-content">
        <div class="stats-grid">
          <div class="stat-card">
            <div class="stat-icon">📝</div>
            <div class="stat-value">{{ analytics.total_articles }}</div>
            <div class="stat-label">Artikel Published</div>
          </div>
          <div class="stat-card">
            <div class="stat-icon">📅</div>
            <div class="stat-value">{{ schedule.published_today }}/{{ schedule.daily_limit || 10 }}</div>
            <div class="stat-label">Publish Hari Ini</div>
          </div>
          <div class="stat-card">
            <div class="stat-icon">🌐</div>
            <div class="stat-value">{{ sites.length }}</div>
            <div class="stat-label">WordPress Sites</div>
          </div>
          <div class="stat-card">
            <div class="stat-icon">🔗</div>
            <div class="stat-value">{{ Object.keys(keywordMapping).length }}</div>
            <div class="stat-label">Keyword Mappings</div>
          </div>
        </div>

        <!-- Settings -->
        <div class="card card-pad">
          <h4>⚙️ Pengaturan</h4>
          <div class="scrape-controls" style="flex-wrap:wrap;gap:12px;align-items:end;">
            <div class="field" style="min-width:140px;">
              <label>📊 Limit Publish / Hari</label>
              <div style="display:flex;gap:6px;align-items:center;">
                <input class="input" type="number" v-model.number="scraperSettings.daily_limit" min="1" max="100" style="width:70px;" />
                <button class="btn btn-sm btn-primary" @click="saveDailyLimit">💾 Simpan</button>
              </div>
              <span style="font-size:11px;color:var(--muted,#64748b);">1–100 artikel/hari. Atur sesuai kebutuhan SEO.</span>
            </div>
          </div>
        </div>

        <!-- Recent Activity -->
        <div class="card card-pad">
          <h4>📋 Aktivitas Terakhir</h4>
          <div v-if="!historyList.length" class="empty">Belum ada aktivitas</div>
          <div v-else class="activity-list">
            <div v-for="(h, i) in historyList.slice(0, 8)" :key="i" class="activity-item">
              <span class="activity-badge" :class="h.action === 'upload' ? 'badge-blue' : 'badge-purple'">
                {{ h.action === 'upload' ? '📤' : '🔍' }}
              </span>
              <div class="activity-info">
                <span class="activity-text">{{ h.action === 'upload' ? `Upload ${h.new_posts || 0} baru` : `Scrape ${h.articles_found || 0} artikel` }}</span>
                <span class="activity-meta">{{ h.date }} {{ h.time }} • {{ h.user }}</span>
              </div>
            </div>
          </div>
        </div>

        <!-- Quick Actions -->
        <div class="quick-actions">
          <button class="quick-btn" @click="activeTab = 'scrape'">🔍 Scrape Baru</button>
          <button class="quick-btn" @click="activeTab = 'upload'">📤 Upload</button>
          <button class="quick-btn" @click="activeTab = 'seo'">🔗 SEO Settings</button>
          <button class="quick-btn" @click="showHistory = true">📊 History</button>
        </div>
      </div>

      <!-- ===== TAB: SITES ===== -->
      <div v-if="activeTab === 'sites'" class="tab-content">
        <div class="card card-pad">
          <div class="card-header">
            <h4>🌐 WordPress Sites</h4>
            <button class="btn btn-primary btn-sm" @click="openSiteForm(null)">➕ Add</button>
          </div>
          <div v-if="!sites.length" class="empty">Klik <b>Add Site</b> untuk menambah</div>
          <div v-else class="site-list">
            <div v-for="s in sites" :key="s.name" class="site-card" :class="{ pending: !s.username || s.username === 'PENDING' }">
              <div class="site-info">
                <div class="site-name">{{ s.name }} <span v-if="!s.username || s.username === 'PENDING'" class="badge badge-yellow">⏳ Belum Diisi</span></div>
                <div class="site-url">{{ s.wp_url }}</div>
                <div class="site-user">👤 {{ s.username === 'PENDING' ? 'Belum diisi — klik ✏️ Edit' : s.username }}</div>
                <div class="site-pass" v-if="s.username && s.username !== 'PENDING'">
                  🔑 <span v-if="showCardPassword[s.name]">{{ s.app_password }}</span><span v-else>••••••••</span>
                  <button class="btn-icon" @click.stop="showCardPassword[s.name] = !showCardPassword[s.name]" style="background:none;border:none;cursor:pointer;font-size:14px;padding:2px 6px;">
                    {{ showCardPassword[s.name] ? '🙈' : '👁' }}
                  </button>
                </div>
              </div>
              <div class="site-actions">
                <button class="btn btn-sm" @click="openSiteForm(s)">✏️</button>
                <button class="btn btn-sm" @click="testConnection(s)">🔌</button>
                <button class="btn btn-sm btn-danger" @click="deleteSite(s.name)">🗑</button>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- ===== TAB: SCRAPE ===== -->
      <div v-if="activeTab === 'scrape'" class="tab-content">
        <div class="card card-pad">
          <h4>🔍 Scrape Articles</h4>
          <div class="scrape-controls">
            <div class="field">
              <label>Sumber Berita</label>
              <select class="select" v-model="selectedSource">
                <option value="all">🌐 Semua Sumber</option>
                <option value="newsmaker">📰 Newsmaker.id</option>
                <option value="detik">📰 Detik Finance</option>
              </select>
            </div>
            <div class="field">
              <label>Halaman</label>
              <input class="input" type="number" v-model.number="scrapePages" min="1" max="20" style="width:70px;" />
            </div>
            <button class="btn btn-primary" :disabled="scrapeBusy" @click="scrapeArticles">
              {{ scrapeBusy ? '⏳ Scraping...' : '🔍 Check Articles' }}
            </button>
          </div>
        </div>

        <!-- Articles Preview -->
        <div v-if="articles.length" class="card card-pad">
          <div class="card-header">
            <h4>📄 {{ articles.length }} Artikel Ditemukan</h4>
            <div class="card-actions">
              <span class="selected-count">{{ selectedCount }} dipilih</span>
              <button class="btn btn-sm" @click="sourceFilter = 'all'" :class="{ 'btn-primary': sourceFilter === 'all' }">🌐 Semua ({{ sourceCount.all }})</button>
              <button class="btn btn-sm" @click="sourceFilter = 'newsmaker'" :class="{ 'btn-primary': sourceFilter === 'newsmaker' }">📰 Newsmaker ({{ sourceCount.newsmaker }})</button>
              <button class="btn btn-sm" @click="sourceFilter = 'detik_finance'" :class="{ 'btn-primary': sourceFilter === 'detik_finance' }">📰 Detik ({{ sourceCount.detik_finance }})</button>
              <button class="btn btn-sm" @click="toggleAllArticles">{{ selectedCount === filteredArticles.length ? 'Deselect All' : 'Select All' }}</button>
              <button class="btn btn-primary btn-sm" :disabled="!selectedCount || !selectedSite" @click="activeTab = 'upload'">
                📤 Upload {{ selectedCount }} →
              </button>
            </div>
          </div>
          <div class="article-grid">
            <div v-for="(a, i) in filteredArticles" :key="articles.indexOf(a)" class="article-card" :class="{ selected: selectedArticles.has(articles.indexOf(a)) }" @click="toggleArticle(articles.indexOf(a))">
              <div class="article-check">
                <input type="checkbox" :checked="selectedArticles.has(articles.indexOf(a))" @click.stop />
              </div>
              <div class="article-thumb" v-if="a.image_url">
                <img :src="a.image_url" :alt="a.title" loading="lazy" @error="$event.target.style.display='none'" />
              </div>
              <div class="article-body">
                <div class="article-title">{{ a.title }}</div>
                <div class="article-meta">
                  <span class="badge" :class="a.source === 'newsmaker' ? 'badge-cyan' : 'badge-orange'">{{ sourceLabel(a.source) }}</span>
                  <span class="badge badge-purple">{{ a.category }}</span>
                  <span class="article-date">{{ a.publish_date }}</span>
                  <span class="article-chars" v-if="a.content">{{ a.content.length }} chars</span>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- ===== TAB: UPLOAD ===== -->
      <div v-if="activeTab === 'upload'" class="tab-content">
        <div class="card card-pad">
          <h4>📤 Upload to WordPress</h4>
          <div class="scrape-controls">
            <div class="field" style="flex:1">
              <label>Target Site</label>
              <select class="select" v-model="selectedSite">
                <option value="">— Pilih Site —</option>
                <option v-for="s in siteNames" :key="s" :value="s">{{ s }}</option>
              </select>
            </div>
          </div>

          <!-- SEO Settings -->
          <div class="settings-panel">
            <label class="toggle-label"><input type="checkbox" v-model="settings.seo_optimize" /> 🔍 Auto-SEO</label>
            <label class="toggle-label"><input type="checkbox" v-model="settings.backlinks" /> 🔗 Backlinks</label>
            <div class="inline-field">
              Max: <input class="input input-sm" type="number" v-model.number="settings.max_backlinks" min="1" max="10" />
            </div>
            <input class="input" v-model="settings.static_tags" placeholder="Tags (comma separated)" style="flex:1;min-width:200px;" />
          </div>

          <button class="btn btn-primary btn-lg" :disabled="uploadBusy || !selectedSite || !selectedCount" @click="uploadToWP" style="width:100%;margin-top:12px;">
            {{ uploadBusy ? '⏳ Uploading...' : `📤 Upload ${selectedCount} Artikel` }}
          </button>
        </div>

        <!-- Upload Result -->
        <div v-if="uploadResult" class="card card-pad result-card">
          <h4>📊 Hasil Upload</h4>
          <div class="result-stats">
            <div class="result-stat green"><span class="result-num">{{ uploadResult.new_posts }}</span><span>Baru</span></div>
            <div class="result-stat blue"><span class="result-num">{{ uploadResult.updated_posts }}</span><span>Update</span></div>
            <div class="result-stat red" v-if="uploadResult.errors?.length"><span class="result-num">{{ uploadResult.errors.length }}</span><span>Error</span></div>
          </div>
          <div v-if="uploadResult.sitemap_ping?.length" class="ping-info">
            📡 Sitemap ping: {{ uploadResult.sitemap_ping.join(', ') }}
          </div>
        </div>

        <!-- Upload Log -->
        <div v-if="showUploadLog && uploadLog.length" class="card card-pad">
          <h4>📝 Upload Log</h4>
          <div class="log-list">
            <div v-for="(l, i) in uploadLog" :key="i" class="log-item" :class="l.type">
              <span class="log-time">{{ l.time }}</span>
              <span class="log-text">{{ l.text }}</span>
            </div>
          </div>
        </div>
      </div>

      <!-- ===== TAB: SEO ===== -->
      <div v-if="activeTab === 'seo'" class="tab-content">
        <!-- Duplicate Checker -->
        <div class="card card-pad">
          <h4>🔍 Duplicate Checker</h4>
          <div class="scrape-controls">
            <select class="select" v-model="dupSite" style="flex:1">
              <option value="">— Pilih Site —</option>
              <option v-for="s in siteNames" :key="s" :value="s">{{ s }}</option>
            </select>
            <button class="btn" :disabled="dupBusy || !dupSite" @click="checkDuplicates">
              {{ dupBusy ? '⏳ Checking...' : '🔍 Check' }}
            </button>
          </div>
          <div v-if="duplicates.length" class="dup-list">
            <div v-for="(d, i) in duplicates" :key="i" class="dup-item">
              <div class="dup-info">
                <span class="dup-title">{{ d.title }}</span>
                <span class="badge badge-red">{{ d.count }}x</span>
              </div>
              <button class="btn btn-sm btn-danger" @click="deleteDuplicate(d.post_ids)">🗑 Hapus {{ d.count }}</button>
            </div>
          </div>
          <div v-else-if="dupSite && !dupBusy" class="empty">Tidak ada duplikat ✅</div>
        </div>

        <!-- Backlinks Config -->
        <div class="card card-pad">
          <div class="card-header">
            <h4>🔗 Backlinks Config</h4>
            <button class="btn btn-sm" @click="openBacklinksModal">⚙️ Manage</button>
          </div>
          <div class="seo-stats">
            <div class="seo-stat">
              <span class="seo-stat-num">{{ Object.keys(authoritySites).length }}</span>
              <span>Authority Sites</span>
            </div>
            <div class="seo-stat">
              <span class="seo-stat-num">{{ Object.keys(keywordMapping).length }}</span>
              <span>Keyword Mappings</span>
            </div>
          </div>
        </div>
      </div>

      <!-- ===== TAB: ANALYTICS ===== -->
      <div v-if="activeTab === 'analytics'" class="tab-content">
        <div class="card card-pad">
          <h4>📈 Performance Analytics</h4>
          <div class="stats-grid small">
            <div class="stat-card mini">
              <div class="stat-value">{{ analytics.total_articles }}</div>
              <div class="stat-label">Total Published</div>
            </div>
            <div class="stat-card mini" v-for="(count, site) in analytics.by_site" :key="site">
              <div class="stat-value">{{ count }}</div>
              <div class="stat-label">{{ site }}</div>
            </div>
          </div>

          <!-- Daily Breakdown -->
          <div v-if="Object.keys(analytics.by_date).length" class="daily-chart">
            <h5>📅 Harian</h5>
            <div class="chart-bars">
              <div v-for="(count, date) in analytics.by_date" :key="date" class="chart-bar-wrapper">
                <div class="chart-bar" :style="{ height: Math.min(count * 10, 100) + '%' }"></div>
                <div class="chart-label">{{ date.slice(5) }}</div>
                <div class="chart-value">{{ count }}</div>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- ===== TAB: REPORT ===== -->
      <div v-if="activeTab === 'report'" class="tab-content">
        <div class="card card-pad">
          <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:12px;">
            <h4>📋 Upload Report</h4>
            <div style="display:flex;gap:6px;">
              <button class="btn btn-sm btn-primary" @click="exportReportCSV">📥 Export CSV</button>
              <button class="btn btn-sm" @click="loadReport">🔄 Refresh</button>
            </div>
          </div>

          <!-- Summary -->
          <div class="stats-grid small" style="margin-bottom:16px;">
            <div class="stat-card mini"><div class="stat-value">{{ reportSummary.total }}</div><div class="stat-label">Total</div></div>
            <div class="stat-card mini"><div class="stat-value" style="color:#10b981;">{{ reportSummary.new }}</div><div class="stat-label">New</div></div>
            <div class="stat-card mini"><div class="stat-value" style="color:#3b82f6;">{{ reportSummary.updated }}</div><div class="stat-label">Updated</div></div>
            <div class="stat-card mini"><div class="stat-value" style="color:#ef4444;">{{ reportSummary.error }}</div><div class="stat-label">Error</div></div>
            <div class="stat-card mini"><div class="stat-value">{{ reportSummary.avg_seo }}</div><div class="stat-label">Avg SEO</div></div>
          </div>

          <!-- Filters -->
          <div style="display:flex;gap:8px;flex-wrap:wrap;margin-bottom:12px;align-items:end;">
            <div class="field" style="min-width:120px;"><label style="font-size:11px;">Dari</label><input class="input" type="date" v-model="reportFilter.date_from" style="font-size:12px;" /></div>
            <div class="field" style="min-width:120px;"><label style="font-size:11px;">Sampai</label><input class="input" type="date" v-model="reportFilter.date_to" style="font-size:12px;" /></div>
            <div class="field" style="min-width:100px;">
              <label style="font-size:11px;">Site</label>
              <select class="select" v-model="reportFilter.site" style="font-size:12px;"><option value="">Semua</option><option v-for="s in reportFilterOptions.sites" :key="s" :value="s">{{ s }}</option></select>
            </div>
            <div class="field" style="min-width:100px;">
              <label style="font-size:11px;">Status</label>
              <select class="select" v-model="reportFilter.status" style="font-size:12px;">
                <option value="">Semua</option><option value="new">✅ New</option><option value="updated">🔄 Updated</option><option value="error">❌ Error</option>
              </select>
            </div>
            <div class="field" style="min-width:100px;">
              <label style="font-size:11px;">Sumber</label>
              <select class="select" v-model="reportFilter.source" style="font-size:12px;"><option value="">Semua</option><option v-for="s in reportFilterOptions.sources" :key="s" :value="s">{{ s }}</option></select>
            </div>
            <div class="field" style="min-width:120px;"><label style="font-size:11px;">Cari Judul</label><input class="input" v-model="reportFilter.search" placeholder="keyword..." style="font-size:12px;" /></div>
            <button class="btn btn-sm btn-primary" @click="loadReport">🔍 Filter</button>
            <button class="btn btn-sm" @click="resetReportFilter">↩️ Reset</button>
          </div>

          <!-- Loading -->
          <div v-if="reportBusy" style="text-align:center;padding:20px;color:var(--muted,#64748b);">⏳ Memuat report...</div>

          <!-- Empty -->
          <div v-else-if="!reportArticles.length" class="empty">Belum ada data upload. Lakukan upload terlebih dahulu.</div>

          <!-- Table -->
          <div v-else class="report-table-wrapper" style="overflow-x:auto;max-height:500px;overflow-y:auto;">
            <table class="report-table" style="width:100%;border-collapse:collapse;font-size:12px;">
              <thead style="position:sticky;top:0;background:var(--bg,#fff);z-index:1;">
                <tr style="border-bottom:2px solid var(--border,#e2e8f0);text-align:left;">
                  <th style="padding:8px;">Tanggal</th>
                  <th style="padding:8px;">Judul</th>
                  <th style="padding:8px;">Kategori</th>
                  <th style="padding:8px;">Sumber</th>
                  <th style="padding:8px;">Status</th>
                  <th style="padding:8px;">SEO</th>
                  <th style="padding:8px;">Site</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="(a, i) in reportArticles" :key="i" style="border-bottom:1px solid var(--border,#f1f5f9);">
                  <td style="padding:6px 8px;white-space:nowrap;">{{ a.upload_date }} {{ a.upload_time }}</td>
                  <td style="padding:6px 8px;max-width:280px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">{{ a.title }}</td>
                  <td style="padding:6px 8px;"><span style="padding:2px 8px;background:#e0e7ff;color:#3730a3;border-radius:10px;font-size:11px;">{{ a.category || '-' }}</span></td>
                  <td style="padding:6px 8px;font-size:11px;">{{ a.source || '-' }}</td>
                  <td style="padding:6px 8px;">
                    <span v-if="a.status === 'new'" style="color:#10b981;font-weight:600;">✅ New</span>
                    <span v-else-if="a.status === 'updated'" style="color:#3b82f6;font-weight:600;">🔄 Updated</span>
                    <span v-else style="color:#ef4444;font-weight:600;">❌ {{ a.error || 'Error' }}</span>
                  </td>
                  <td style="padding:6px 8px;">
                    <span :style="{ color: seoColor(a.seo_score), fontWeight: 600 }">{{ a.seo_score }}</span>
                  </td>
                  <td style="padding:6px 8px;font-size:11px;">{{ a.upload_site }}</td>
                </tr>
              </tbody>
            </table>
          </div>
          <div style="margin-top:8px;font-size:11px;color:var(--muted,#64748b);">Menampilkan {{ reportArticles.length }} artikel</div>
        </div>
      </div>

    </template>

    <!-- FAB -->
    <div class="fab-container">
      <div v-if="showFab" class="fab-menu">
        <button class="fab-item" @click="activeTab = 'scrape'; showFab = false">🔍 Scrape</button>
        <button class="fab-item" @click="activeTab = 'upload'; showFab = false">📤 Upload</button>
        <button class="fab-item" @click="openBacklinksModal; showFab = false">🔗 Backlinks</button>
        <button class="fab-item" @click="showHistory = true; showFab = false">📊 History</button>
      </div>
      <button class="fab-btn" @click="showFab = !showFab" :class="{ open: showFab }">+</button>
    </div>

    <!-- Onboarding Modal -->
    <Modal v-if="showOnboarding" title="🎯 Getting Started" @close="showOnboarding = false" style="max-width:500px;">
      <div class="onboarding">
        <div class="onboarding-progress">
          <div class="onboarding-bar"><div class="onboarding-fill" :style="{ width: onboardingProgress + '%' }"></div></div>
          <span>{{ onboardingProgress }}%</span>
        </div>
        <div v-for="(task, i) in onboardingTasks" :key="i" class="onboarding-item" :class="{ done: task.done.value }">
          <span class="onboarding-check">{{ task.done.value ? '✅' : '⬜' }}</span>
          <span class="onboarding-icon">{{ task.icon }}</span>
          <span>{{ task.text }}</span>
        </div>
      </div>
    </Modal>

    <!-- Modal: Site Form -->
    <Modal v-if="showSiteForm" :title="siteForm.name ? '✏️ Edit Site' : '➕ Add Site'" @close="showSiteForm = false">
      <div class="form-grid">
        <div class="field"><label>Name *</label><input class="input" v-model="siteForm.name" :disabled="!!siteForm.name" /></div>
        <div class="field"><label>Branch Code</label><input class="input" v-model="siteForm.branch_code" placeholder="SBY, JKT, BDG, ..." style="text-transform:uppercase;" /></div>
        <div class="field"><label>API URL *</label><input class="input" v-model="siteForm.wp_url" placeholder="https://site.com/wp-json/wp/v2/posts" /></div>
        <div class="field"><label>Media URL</label><input class="input" v-model="siteForm.wp_media_url" /></div>
        <div class="field"><label>Username *</label><input class="input" v-model="siteForm.username" /></div>
        <div class="field"><label>Password {{ siteForm.name ? '(kosong = skip)' : '*' }}</label>
          <div style="display:flex;gap:4px;align-items:center;">
            <input class="input" v-model="siteForm.app_password" :type="showFormPassword ? 'text' : 'password'" style="flex:1;" />
            <button class="btn-icon" @click="showFormPassword = !showFormPassword" style="background:none;border:1px solid var(--border,#e2e8f0);border-radius:6px;cursor:pointer;font-size:16px;padding:8px 10px;flex-shrink:0;">
              {{ showFormPassword ? '🙈' : '👁' }}
            </button>
          </div>
        </div>
      </div>
      <div class="modal-footer">
        <button class="btn" @click="showSiteForm = false">Batal</button>
        <button class="btn" :disabled="!siteForm.wp_url || !siteForm.username || !siteForm.app_password" @click="testFromForm">🔌 Test</button>
        <button class="btn btn-primary" :disabled="busy || !siteForm.name || !siteForm.wp_url || !siteForm.username" @click="saveSite">💾 Simpan</button>
      </div>
    </Modal>

    <!-- Modal: Backlinks -->
    <Modal v-if="showBacklinks" title="🔗 Backlinks Config" @close="showBacklinks = false" style="max-width:800px;">
      <div class="backlinks-grid">
        <div>
          <h4>Authority Sites ({{ Object.keys(authoritySites).length }})</h4>
          <div class="config-list">
            <div v-for="(url, name) in authoritySites" :key="name" class="config-item">
              <span class="config-name">{{ name }}</span>
              <a :href="url" target="_blank" class="config-url">{{ url }}</a>
            </div>
          </div>
        </div>
        <div>
          <h4>Keyword Mapping ({{ Object.keys(keywordMapping).length }})</h4>
          <div class="config-list">
            <div v-for="(site, kw) in keywordMapping" :key="kw" class="config-item">
              <span class="config-kw">{{ kw }}</span>
              <span class="config-arrow">→</span>
              <span class="config-site">{{ site }}</span>
            </div>
          </div>
          <div class="add-keyword">
            <input class="input input-sm" v-model="newKeyword" placeholder="keyword" />
            <select class="select input-sm" v-model="newSiteName">
              <option value="">—</option>
              <option v-for="(_, n) in authoritySites" :key="n" :value="n">{{ n }}</option>
            </select>
            <button class="btn btn-primary btn-sm" :disabled="busy || !newKeyword || !newSiteName" @click="saveKeywordMapping">➕</button>
          </div>
        </div>
      </div>
    </Modal>

    <!-- Modal: History -->
    <Modal v-if="showHistory" title="📊 Upload History" @close="showHistory = false" style="max-width:800px;">
      <div class="filter-row">
        <input class="input input-sm" type="date" v-model="historyFilter.date_from" />
        <input class="input input-sm" type="date" v-model="historyFilter.date_to" />
        <select class="select input-sm" v-model="historyFilter.action">
          <option value="">Semua</option>
          <option value="scrape">🔍 Scrape</option>
          <option value="upload">📤 Upload</option>
        </select>
        <button class="btn btn-primary btn-sm" @click="loadHistory" :disabled="historyBusy">🔍</button>
      </div>
      <div class="config-list" style="max-height:400px;overflow-y:auto;">
        <div v-for="(h, i) in historyList" :key="i" class="history-item">
          <span class="history-badge" :class="h.action === 'upload' ? 'badge-blue' : 'badge-purple'">{{ h.action === 'upload' ? '📤' : '🔍' }}</span>
          <div class="history-info">
            <span>{{ h.action === 'upload' ? `${h.new_posts || 0} baru` : `${h.articles_found || 0} artikel` }}</span>
            <span class="history-meta">{{ h.date }} {{ h.time }} • {{ h.user }}</span>
          </div>
        </div>
      </div>
    </Modal>

    <!-- Modal: Log -->
    <Modal v-if="showLog" title="📝 Scraper Activity Log" @close="showLog = false" style="max-width:800px;">
      <div class="log-filters" style="display:flex;gap:6px;margin-bottom:12px;flex-wrap:wrap;">
        <button class="btn btn-sm" :class="{ 'btn-primary': logLevelFilter === '' }" @click="logLevelFilter = ''">All</button>
        <button class="btn btn-sm" :class="{ 'btn-primary': logLevelFilter === 'ERROR' }" @click="logLevelFilter = 'ERROR'" style="color:#ef4444;">❌ Error</button>
        <button class="btn btn-sm" :class="{ 'btn-primary': logLevelFilter === 'WARNING' }" @click="logLevelFilter = 'WARNING'" style="color:#f59e0b;">⚠️ Warning</button>
        <button class="btn btn-sm" :class="{ 'btn-primary': logLevelFilter === 'INFO' }" @click="logLevelFilter = 'INFO'" style="color:#10b981;">ℹ️ Info</button>
        <button class="btn btn-sm" :class="{ 'btn-primary': logLevelFilter === 'DEBUG' }" @click="logLevelFilter = 'DEBUG'" style="color:#6b7280;">🔍 Debug</button>
      </div>
      <div class="config-list" style="max-height:400px;overflow-y:auto;font-family:monospace;font-size:12px;">
        <div v-for="(l, i) in filteredLogs" :key="i" class="log-item" :style="{ borderLeft: '3px solid ' + logLevelColor(l.level) }">
          <div style="display:flex;gap:8px;align-items:start;">
            <span class="log-time" style="white-space:nowrap;">{{ formatLogTime(l.ts || l.timestamp) }}</span>
            <span :style="{ color: logLevelColor(l.level), fontWeight: 600, minWidth: '55px' }">[{{ l.level }}]</span>
            <span style="color:#6366f1;font-weight:500;min-width:90px;">{{ l.category || '' }}</span>
            <span class="log-text" style="flex:1;">{{ l.msg || l.message || '' }}</span>
          </div>
          <div v-if="l.extra" style="margin-left:160px;margin-top:2px;font-size:11px;color:#94a3b8;">
            <span v-for="(val, key) in l.extra" :key="key" style="margin-right:8px;">{{ key }}={{ typeof val === 'object' ? JSON.stringify(val) : val }}</span>
          </div>
        </div>
        <div v-if="!filteredLogs.length" style="text-align:center;padding:20px;color:#94a3b8;">Tidak ada log</div>
      </div>
      <div style="display:flex;justify-content:space-between;align-items:center;margin-top:8px;">
        <span style="font-size:11px;color:#94a3b8;">{{ filteredLogs.length }} entries</span>
        <button class="btn btn-sm btn-danger" @click="async () => { await api('/api/scraper/log', { method: 'DELETE' }); logs = [] }">🗑 Clear</button>
      </div>
    </Modal>
  </div>
</template>

<style scoped>
/* === Base === */
.scraper-app { max-width: 900px; margin: 0 auto; }
.card { background: var(--card-bg, #fff); border: 1px solid var(--border, #e2e8f0); border-radius: 12px; margin-bottom: 16px; }
.card-pad { padding: 16px; }
.card-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 12px; flex-wrap: wrap; gap: 8px; }
.card-header h4 { margin: 0; }
.card-actions { display: flex; align-items: center; gap: 8px; }

/* === Header === */
.scraper-header { display: flex; align-items: center; justify-content: space-between; padding: 12px 0; margin-bottom: 8px; }
.header-left { display: flex; align-items: center; gap: 8px; }
.header-left h3 { margin: 0; font-size: 18px; }
.header-badge { font-size: 11px; padding: 2px 8px; border-radius: 12px; background: #d1fae5; color: #065f46; }
.header-badge.warn { background: #fee2e2; color: #991b1b; }
.header-right { display: flex; align-items: center; gap: 8px; }
.optimal-time { font-size: 11px; color: var(--muted, #64748b); }
.icon-btn { background: none; border: none; cursor: pointer; font-size: 18px; padding: 4px; border-radius: 8px; }
.icon-btn:hover { background: var(--hover, #f1f5f9); }

/* === Tabs === */
.tab-nav { display: flex; gap: 4px; overflow-x: auto; padding: 4px; background: var(--card-bg, #fff); border: 1px solid var(--border, #e2e8f0); border-radius: 12px; margin-bottom: 16px; }
.tab-btn { flex: 1; min-width: 60px; padding: 8px 4px; border: none; background: none; border-radius: 8px; cursor: pointer; display: flex; flex-direction: column; align-items: center; gap: 2px; font-size: 11px; color: var(--muted, #64748b); transition: all 0.2s; }
.tab-btn.active { background: var(--primary, #3b82f6); color: #fff; }
.tab-icon { font-size: 16px; }
.tab-label { font-weight: 500; }

/* === Tab Content === */
.tab-content { animation: fadeIn 0.2s ease; }
@keyframes fadeIn { from { opacity: 0; transform: translateY(8px); } to { opacity: 1; transform: translateY(0); } }

/* === Stats Grid === */
.stats-grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; margin-bottom: 16px; }
.stats-grid.small { grid-template-columns: repeat(2, 1fr); }
.stat-card { background: var(--card-bg, #fff); border: 1px solid var(--border, #e2e8f0); border-radius: 12px; padding: 16px; text-align: center; }
.stat-card.mini { padding: 12px; }
.stat-icon { font-size: 24px; margin-bottom: 4px; }
.stat-value { font-size: 24px; font-weight: 700; color: var(--text, #1e293b); }
.stat-label { font-size: 11px; color: var(--muted, #64748b); margin-top: 2px; }

/* === Progress === */
.progress-card { background: var(--card-bg, #fff); border: 1px solid var(--border, #e2e8f0); border-radius: 12px; padding: 12px 16px; margin-bottom: 16px; }
.progress-header { display: flex; justify-content: space-between; margin-bottom: 8px; }
.progress-msg { font-size: 13px; }
.progress-pct { font-size: 12px; color: var(--muted, #64748b); }
.progress-bar { height: 6px; background: var(--border, #e2e8f0); border-radius: 3px; overflow: hidden; }
.progress-fill { height: 100%; background: linear-gradient(90deg, #3b82f6, #10b981); border-radius: 3px; transition: width 0.3s; }
.progress-footer { display: flex; justify-content: space-between; margin-top: 4px; font-size: 11px; color: var(--muted, #64748b); }

/* === Alert === */
.alert { padding: 10px 14px; border-radius: 8px; margin-bottom: 12px; font-size: 13px; }
.alert-success { background: #d1fae5; color: #065f46; }
.alert-error { background: #fee2e2; color: #991b1b; }
.alert-info { background: #dbeafe; color: #1e40af; }

/* === Activity === */
.activity-list { display: flex; flex-direction: column; gap: 8px; }
.activity-item { display: flex; align-items: center; gap: 10px; padding: 8px; border-radius: 8px; background: var(--hover, #f8fafc); }
.activity-badge { font-size: 16px; width: 32px; height: 32px; display: flex; align-items: center; justify-content: center; border-radius: 8px; }
.activity-info { display: flex; flex-direction: column; }
.activity-text { font-size: 13px; font-weight: 500; }
.activity-meta { font-size: 11px; color: var(--muted, #64748b); }

/* === Quick Actions === */
.quick-actions { display: grid; grid-template-columns: repeat(2, 1fr); gap: 8px; margin-top: 16px; }
.quick-btn { padding: 12px; border: 1px solid var(--border, #e2e8f0); border-radius: 10px; background: var(--card-bg, #fff); cursor: pointer; font-size: 13px; font-weight: 500; transition: all 0.2s; }
.quick-btn:hover { border-color: var(--primary, #3b82f6); background: var(--hover, #eff6ff); }

/* === Site Cards === */
.site-list { display: flex; flex-direction: column; gap: 8px; }
.site-card { display: flex; align-items: center; justify-content: space-between; padding: 12px; border: 1px solid var(--border, #e2e8f0); border-radius: 10px; }
.site-card.pending { border-color: #f59e0b; background: #fffbeb; }
.site-name { font-weight: 600; font-size: 14px; }
.site-url { font-size: 11px; color: var(--muted, #64748b); max-width: 300px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.site-user { font-size: 12px; }
.site-pass { font-size: 12px; font-family: monospace; display: flex; align-items: center; gap: 2px; }
.site-actions { display: flex; gap: 4px; }

/* === Scrape Controls === */
.scrape-controls { display: flex; gap: 8px; flex-wrap: wrap; align-items: end; }
.settings-panel { display: flex; gap: 12px; flex-wrap: wrap; align-items: center; margin-top: 12px; padding-top: 12px; border-top: 1px solid var(--border, #e2e8f0); }
.toggle-label { display: flex; align-items: center; gap: 4px; font-size: 13px; cursor: pointer; }
.inline-field { display: flex; align-items: center; gap: 4px; font-size: 13px; }

/* === Article Cards === */
.article-grid { display: flex; flex-direction: column; gap: 8px; max-height: 500px; overflow-y: auto; }
.article-card { display: flex; gap: 12px; padding: 12px; border: 2px solid var(--border, #e2e8f0); border-radius: 10px; cursor: pointer; transition: all 0.2s; }
.article-card:hover { border-color: var(--primary, #3b82f6); background: var(--hover, #f8fafc); }
.article-card.selected { border-color: var(--primary, #3b82f6); background: #eff6ff; }
.article-check { display: flex; align-items: start; padding-top: 4px; }
.article-thumb { width: 80px; height: 60px; border-radius: 8px; overflow: hidden; flex-shrink: 0; }
.article-thumb img { width: 100%; height: 100%; object-fit: cover; }
.article-body { flex: 1; min-width: 0; }
.article-title { font-weight: 600; font-size: 13px; display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; }
.article-meta { display: flex; gap: 8px; margin-top: 4px; align-items: center; flex-wrap: wrap; }
.article-date { font-size: 11px; color: var(--muted, #64748b); }
.article-chars { font-size: 11px; color: var(--muted, #64748b); }
.selected-count { font-size: 12px; color: var(--primary, #3b82f6); font-weight: 500; }

/* === Result === */
.result-stats { display: flex; gap: 16px; margin: 12px 0; }
.result-stat { display: flex; flex-direction: column; align-items: center; }
.result-num { font-size: 28px; font-weight: 700; }
.result-stat.green .result-num { color: #10b981; }
.result-stat.blue .result-num { color: #3b82f6; }
.result-stat.red .result-num { color: #ef4444; }
.ping-info { font-size: 11px; color: var(--muted, #64748b); margin-top: 8px; }

/* === Log === */
.log-list { max-height: 200px; overflow-y: auto; }
.log-item { display: flex; gap: 8px; padding: 6px 0; border-bottom: 1px solid var(--border, #e2e8f0); font-size: 12px; }
.log-time { color: var(--muted, #64748b); white-space: nowrap; }
.log-item.error .log-text { color: #ef4444; }
.log-item.success .log-text { color: #10b981; }

/* === Duplicate === */
.dup-list { margin-top: 12px; }
.dup-item { display: flex; align-items: center; justify-content: space-between; padding: 8px; border-bottom: 1px solid var(--border, #e2e8f0); }
.dup-info { display: flex; align-items: center; gap: 8px; }
.dup-title { font-size: 13px; }

/* === SEO Stats === */
.seo-stats { display: flex; gap: 16px; margin-top: 12px; }
.seo-stat { display: flex; flex-direction: column; align-items: center; padding: 12px; background: var(--hover, #f8fafc); border-radius: 8px; }
.seo-stat-num { font-size: 20px; font-weight: 700; color: var(--primary, #3b82f6); }

/* === Daily Chart === */
.daily-chart { margin-top: 16px; }
.chart-bars { display: flex; gap: 4px; align-items: end; height: 80px; margin-top: 8px; }
.chart-bar-wrapper { flex: 1; display: flex; flex-direction: column; align-items: center; height: 100%; justify-content: end; }
.chart-bar { width: 100%; background: linear-gradient(180deg, #3b82f6, #60a5fa); border-radius: 4px 4px 0 0; min-height: 2px; transition: height 0.3s; }
.chart-label { font-size: 9px; color: var(--muted, #64748b); margin-top: 4px; }
.chart-value { font-size: 10px; font-weight: 600; }

/* === FAB === */
.fab-container { position: fixed; bottom: 24px; right: 24px; z-index: 100; }
.fab-btn { width: 52px; height: 52px; border-radius: 50%; background: var(--primary, #3b82f6); color: #fff; border: none; font-size: 24px; cursor: pointer; box-shadow: 0 4px 12px rgba(59,130,246,0.4); transition: all 0.3s; }
.fab-btn.open { transform: rotate(45deg); background: #ef4444; }
.fab-menu { position: absolute; bottom: 64px; right: 0; display: flex; flex-direction: column; gap: 8px; }
.fab-item { padding: 8px 16px; background: var(--card-bg, #fff); border: 1px solid var(--border, #e2e8f0); border-radius: 8px; cursor: pointer; font-size: 13px; white-space: nowrap; box-shadow: 0 2px 8px rgba(0,0,0,0.1); }
.fab-item:hover { background: var(--hover, #f1f5f9); }

/* === Onboarding === */
.onboarding { padding: 8px 0; }
.onboarding-progress { display: flex; align-items: center; gap: 8px; margin-bottom: 16px; }
.onboarding-bar { flex: 1; height: 8px; background: var(--border, #e2e8f0); border-radius: 4px; overflow: hidden; }
.onboarding-fill { height: 100%; background: linear-gradient(90deg, #10b981, #3b82f6); border-radius: 4px; transition: width 0.3s; }
.onboarding-item { display: flex; align-items: center; gap: 10px; padding: 10px; border-radius: 8px; margin-bottom: 4px; }
.onboarding-item.done { opacity: 0.6; }
.onboarding-check { font-size: 16px; }
.onboarding-icon { font-size: 18px; }

/* === Form === */
.form-grid { display: grid; gap: 12px; }
.field { display: flex; flex-direction: column; gap: 4px; }
.field label { font-size: 12px; font-weight: 500; }
.input, .select { padding: 8px 12px; border: 1px solid var(--border, #e2e8f0); border-radius: 8px; font-size: 13px; background: var(--card-bg, #fff); color: var(--text, #1e293b); }
.input-sm { padding: 6px 10px; font-size: 12px; }
.btn { padding: 8px 14px; border: 1px solid var(--border, #e2e8f0); border-radius: 8px; cursor: pointer; font-size: 13px; background: var(--card-bg, #fff); color: var(--text, #1e293b); transition: all 0.2s; }
.btn:hover { background: var(--hover, #f1f5f9); }
.btn-primary { background: var(--primary, #3b82f6); color: #fff; border-color: var(--primary, #3b82f6); }
.btn-primary:hover { background: #2563eb; }
.btn-danger { background: #fee2e2; color: #991b1b; border-color: #fecaca; }
.btn-sm { padding: 4px 10px; font-size: 12px; }
.btn-lg { padding: 12px 20px; font-size: 15px; }
.badge { display: inline-block; padding: 2px 8px; border-radius: 6px; font-size: 11px; font-weight: 500; }
.badge-green { background: #d1fae5; color: #065f46; }
.badge-yellow { background: #fef3c7; color: #92400e; }
.badge-blue { background: #dbeafe; color: #1e40af; }
.badge-red { background: #fee2e2; color: #991b1b; }
.badge-purple { background: #ede9fe; color: #5b21b6; }
.modal-footer { display: flex; justify-content: flex-end; gap: 8px; margin-top: 16px; }
.filter-row { display: flex; gap: 8px; margin-bottom: 12px; flex-wrap: wrap; }
.empty { text-align: center; padding: 20px; color: var(--muted, #64748b); font-size: 13px; }
.skeleton { animation: pulse 1.5s infinite; }
@keyframes pulse { 0%, 100% { opacity: 1; } 50% { opacity: 0.5; } }

/* === Config Lists === */
.backlinks-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }
.config-list { max-height: 250px; overflow-y: auto; }
.config-item { display: flex; align-items: center; gap: 8px; padding: 6px 0; border-bottom: 1px solid var(--border, #e2e8f0); font-size: 12px; }
.config-name { font-weight: 500; flex: 1; }
.config-url { color: var(--primary, #3b82f6); text-decoration: none; font-size: 11px; }
.config-kw { font-weight: 500; }
.config-arrow { color: var(--muted, #64748b); }
.config-site { color: var(--primary, #3b82f6); }
.add-keyword { display: flex; gap: 6px; margin-top: 8px; }
.history-item { display: flex; align-items: center; gap: 10px; padding: 8px 0; border-bottom: 1px solid var(--border, #e2e8f0); }
.history-badge { font-size: 14px; }
.history-info { display: flex; flex-direction: column; }
.history-meta { font-size: 11px; color: var(--muted, #64748b); }

/* === Dark Mode === */
.dark { --card-bg: #1e293b; --border: #334155; --text: #f1f5f9; --muted: #94a3b8; --hover: #334155; --primary: #60a5fa; }
.dark .article-card.selected { background: #1e3a5f; }
.dark .activity-item { background: #334155; }
.dark .quick-btn:hover { background: #1e3a5f; border-color: #60a5fa; }
.dark .fab-item { background: #1e293b; border-color: #334155; }
.dark .fab-item:hover { background: #334155; }

/* === Mobile === */
@media (max-width: 640px) {
  .stats-grid { grid-template-columns: repeat(2, 1fr); }
  .backlinks-grid { grid-template-columns: 1fr; }
  .tab-label { display: none; }
  .tab-icon { font-size: 20px; }
  .scrape-controls { flex-direction: column; }
  .settings-panel { flex-direction: column; align-items: stretch; }
  .site-card { flex-direction: column; align-items: flex-start; gap: 8px; }
  .result-stats { justify-content: center; }
  .header-right .optimal-time { display: none; }
}
</style>
