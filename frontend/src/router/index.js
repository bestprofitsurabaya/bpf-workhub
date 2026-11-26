import { createRouter, createWebHistory } from 'vue-router'
import { useAuthStore, ROLE_META } from '../stores/auth'

// v2.113.2 — tautan laporan lama (bookmark/WA/email) membawa periode dengan
// nama lama: `start_date`/`end_date` (Rekap & Analisis) atau `from`/`to`.
// Context bar /cash hanya membaca `start`/`end`, jadi dulu periode itu hilang
// begitu redirect terjadi. Petakan eksplisit; parameter lain (driver/nopol/
// type/year) tetap dibawa agar tautan tidak putus.
function legacyReportQuery(query, view) {
  const q = { ...(query || {}), tab: 'laporan', view }
  const start = q.start || q.start_date || q.from
  const end = q.end || q.end_date || q.to
  if (start) q.start = start
  if (end) q.end = end
  for (const key of ['start_date', 'end_date', 'from', 'to']) delete q[key]
  return q
}

const routes = [
  { path: '/login', name: 'login', component: () => import('../views/LoginView.vue'), meta: { public: true } },
  // v2.112.0 — langkah kedua login (kode authenticator / pendaftaran MFA).
  { path: '/mfa', name: 'mfa', component: () => import('../views/MfaView.vue'), meta: { public: true, mfa: true } },
  { path: '/403', name: 'forbidden', component: () => import('../views/ForbiddenView.vue'), meta: { public: true } },
  // Form publik pelamar kerja (v2.16) — tanpa login
  // Rilis C: form publik lama dipensiunkan; bookmark /apply masuk ke portal cabang.
  { path: '/apply', redirect: { name: 'recruitment-portal' }, meta: { public: true } },
  // Form publik overtime OB/Security (v2.22) — tanpa login
  { path: '/overtime-form', name: 'overtime-form', component: () => import('../views/OvertimeFormView.vue'), meta: { public: true } },
  // Form publik Absensi FirstWork (v2.80.0) — tanpa login, mobile-first.
  // Path sengaja BUKAN /first-work: path itu milik halaman data di dalam layout.
  // Kalau sama, Vue Router memilih record pertama (form) sehingga user login
  // yang membuka menu "Absensi FirstWork" justru melihat form, bukan datanya.
  { path: '/first-work-form', name: 'first-work-form', component: () => import('../views/FirstWorkFormView.vue'), meta: { public: true } },
  // Form publik Registrasi CV Online (v2.113.0) — tanpa login, mobile-first.
  // Dipisah dari /cv-online supaya menu "Registrasi CV Online" tetap membuka
  // halaman data, bukan form.
  { path: '/cv-online-form', name: 'cv-online-form', component: () => import('../views/CvOnlineFormView.vue'), meta: { public: true } },
  // Absensi training portal (2 hari) — tanpa login, mobile-first.
  { path: '/training-form', name: 'training-form', component: () => import('../views/TrainingFormView.vue'), meta: { public: true } },
  // Rilis A (Task 7) — portal satu tautan per cabang: empat kartu langkah,
  // token cabang dibawa dari query ke form CV Online / FirstWork.
  { path: '/recruitment-portal', name: 'recruitment-portal', component: () => import('../views/RecruitmentPortalView.vue'), meta: { public: true } },
  // Driver PWA (v2.4): layout mobile mandiri, wajib login PIN driver
  { path: '/driver', name: 'driver', component: () => import('../views/driver/DriverView.vue'), meta: { roles: ['driver'] } },
  {
    path: '/',
    component: () => import('../layouts/AppLayout.vue'),
    children: [
      { path: '', name: 'home', component: () => import('../views/HomeView.vue') },
      { path: 'dashboard', name: 'dashboard', component: () => import('../views/dashboard/AdminDashboard.vue'), meta: { roles: ['admin'] } },
      { path: 'finance', name: 'finance', component: () => import('../views/dashboard/FinanceDashboard.vue'), meta: { roles: ['finance', 'admin'] } },
      { path: 'ga', name: 'ga', component: () => import('../views/dashboard/GaDashboard.vue'), meta: { roles: ['ga', 'admin'] } },
      { path: 'marketing', name: 'marketing', component: () => import('../views/dashboard/MarketingDashboard.vue'), meta: { roles: ['marketing'] } },
      { path: 'chief-driver', name: 'chief-driver', component: () => import('../views/dashboard/ChiefDriverDashboard.vue'), meta: { roles: ['chief_driver', 'ga', 'admin'] } },
      { path: 'trips', name: 'trips', component: () => import('../views/TripsView.vue'), meta: { roles: ['ga', 'admin'] } },
      { path: 'assignments', name: 'assignments', component: () => import('../views/AssignmentsView.vue'), meta: { roles: ['ga', 'admin'] } },
      // v2.100.0 — laporan pindah ke meja kerja /cash (Fase 1). Rute lama tetap
      // hidup sebagai redirect dengan query dibawa agar bookmark tidak putus.
      { path: 'rekap', name: 'rekap', redirect: (to) => ({ path: '/cash', query: legacyReportQuery(to.query, 'rekap') }), meta: { roles: ['ga', 'finance', 'admin'] } },
      { path: 'cash', name: 'cash', component: () => import('../views/CashView.vue'), meta: { roles: ['ga', 'finance', 'admin'] } },
      { path: 'analytics', name: 'analytics', redirect: (to) => ({ path: '/cash', query: legacyReportQuery(to.query, 'analisis') }), meta: { roles: ['ga', 'finance', 'admin'] } },
      { path: 'users', name: 'users', component: () => import('../views/UsersView.vue'), meta: { roles: ['admin'] } },
      { path: 'approvals', name: 'approvals', component: () => import('../views/ApprovalsView.vue'), meta: { roles: ['chief_driver', 'ga', 'ga_hr'] } },
      { path: 'access-review', name: 'access-review', component: () => import('../views/AccessReviewView.vue'), meta: { roles: ['admin'] } },
      // Profil Saya (v2.81.0) — semua role boleh ganti nama & PIN sendiri.
      { path: 'profile', name: 'profile', component: () => import('../views/ProfileView.vue'), meta: { title: 'Profil Saya' } },
      { path: 'settings', name: 'settings', component: () => import('../views/SettingsView.vue'), meta: { roles: ['admin'] } },
      { path: 'logs', name: 'logs', component: () => import('../views/LogsView.vue'), meta: { roles: ['admin'] } },
      { path: 'water', name: 'water', component: () => import('../views/WaterView.vue'), meta: { roles: ['ob', 'finance', 'admin'] } },
      // Rekap Pengeluaran (v2.71.0) — lintas modul, angka terukur saja
      { path: 'expenses', name: 'expenses', redirect: (to) => ({ path: '/cash', query: legacyReportQuery(to.query, 'realisasi') }), meta: { roles: ['finance', 'admin'] } },
      // Form overtime user OB & Security (v2.39) — dari dalam aplikasi (login)
      { path: 'overtime-me', name: 'overtime-me', component: () => import('../views/OvertimeMeView.vue'), meta: { roles: ['ob', 'security'] } },
      // Satu pintu Rekrutmen: semua modul staff jadi tab di /recruitment.
      { path: 'recruitment', name: 'recruitment', component: () => import('../views/RecruitmentHubView.vue'), meta: { roles: ['receptionist', 'traineer', 'finance', 'ga_hr', 'admin'], title: 'Rekrutmen' } },
      // URL lama tetap dikenali agar bookmark & tautan beredar tidak putus.
      // Redirect diproses sebelum beforeEach: meta pada record redirect TIDAK
      // pernah dipakai guard. Otorisasi ada di /recruitment (meta.roles hub)
      // dan di filter tab per role di dalam hub.
      { path: 'receptionist', redirect: { path: '/recruitment', query: { tab: 'pelamar' } } },
      // URL lama "Rekrutan Saya" — diarahkan ke tab Pelamar di hub.
      { path: 'traineer', redirect: { path: '/recruitment', query: { tab: 'pelamar' } } },
      // Rilis A (Task 6) — dashboard kasus rekrutmen: NIK termasker, empat
      // langkah, riwayat cabang, dan pengecualian langkah untuk staff.
      { path: 'recruitment-cases', redirect: { path: '/recruitment', query: { tab: 'kasus' } } },
      // In-Out Karyawan (v2.41.0) — catatan keluar-masuk (read-only, sync sheet)
      { path: 'inout', name: 'inout', component: () => import('../views/dashboard/EmployeeInOutView.vue'), meta: { roles: ['receptionist', 'admin'] } },
      // Absensi FirstWork (v2.80.0) — verifikasi Traineer, lihat Finance, kelola Admin
      { path: 'first-work', name: 'first-work', component: () => import('../views/FirstWorkView.vue'), meta: { roles: ['traineer', 'finance', 'ga_hr', 'admin'], title: 'Absensi FirstWork' } },
      // Registrasi CV Online (v2.113.0) — data pelamar kini menjadi tab di hub;
      // URL lama membuka tab CV, lalu hub menyesuaikan tab sesuai peran.
      { path: 'cv-online', redirect: { path: '/recruitment', query: { tab: 'cv' } } },
      { path: 'assets', name: 'assets', component: () => import('../views/dashboard/AssetsView.vue'), meta: { roles: ['ga', 'admin'] } },
      { path: 'ga-hr', name: 'ga-hr', component: () => import('../views/dashboard/OvertimeView.vue'), meta: { roles: ['ga_hr', 'admin'] } },
      { path: 'it', name: 'it', component: () => import('../views/ItEfView.vue'), meta: { roles: ['it_sby', 'it_hu', 'it_jkt2', 'it_bdg', 'it_smg', 'it_mlg', 'it_mdn', 'it_bjm', 'it_plm', 'it_lpg', 'admin'] } },
      // v2.78.0 — Inventaris IT (aset non-jaringan, label QR, kondisi, discovery)
      { path: 'it/inventory', name: 'it-inventory', component: () => import('../views/ItInventoryView.vue'), meta: { roles: ['it_sby', 'it_hu', 'it_jkt2', 'it_bdg', 'it_smg', 'it_mlg', 'it_mdn', 'it_bjm', 'it_plm', 'it_lpg', 'admin'] } },
      { path: 'it/assets/:tag', name: 'it-asset-detail', component: () => import('../views/ItAssetDetailView.vue'), meta: { roles: ['it_sby', 'it_hu', 'it_jkt2', 'it_bdg', 'it_smg', 'it_mlg', 'it_mdn', 'it_bjm', 'it_plm', 'it_lpg', 'admin'] } },
      { path: 'it/scan', name: 'it-scan', component: () => import('../views/ItScanView.vue'), meta: { roles: ['it_sby', 'it_hu', 'it_jkt2', 'it_bdg', 'it_smg', 'it_mlg', 'it_mdn', 'it_bjm', 'it_plm', 'it_lpg', 'admin'] } },
      // Transcoder (v2.46.0) — konversi link YouTube ke format audio/video
      // Agenda (v2.123.0) — semua role baca; tulis dibatasi admin/content_creator.
      { path: 'agenda', name: 'agenda', component: () => import('../views/AgendaView.vue'), meta: { title: 'Agenda', roles: ['admin', 'ga', 'finance', 'marketing', 'chief_driver', 'driver', 'ob', 'receptionist', 'traineer', 'ga_hr', 'security', 'content_creator', 'it_sby', 'it_hu', 'it_jkt2', 'it_bdg', 'it_smg', 'it_mlg', 'it_mdn', 'it_bjm', 'it_plm', 'it_lpg'] } },
      { path: 'transcoder', name: 'transcoder', component: () => import('../views/TranscoderView.vue'), meta: { roles: ['it_sby', 'it_hu', 'it_jkt2', 'it_bdg', 'it_smg', 'it_mlg', 'it_mdn', 'it_bjm', 'it_plm', 'it_lpg', 'admin', 'content_creator'] } },
      // PDF Kit (v2.47.0) — kompres PDF (role IT cabang + admin)
      { path: 'pdfkit', name: 'pdfkit', component: () => import('../views/PdfKitView.vue'), meta: { roles: ['it_sby', 'it_hu', 'it_jkt2', 'it_bdg', 'it_smg', 'it_mlg', 'it_mdn', 'it_bjm', 'it_plm', 'it_lpg', 'admin'] } },
    ],
  },
  { path: '/:pathMatch(.*)*', name: 'not-found', component: () => import('../views/NotFoundView.vue'), meta: { public: true } },
]

const router = createRouter({
  history: createWebHistory('/app/'),
  routes,
  scrollBehavior: () => ({ top: 0 }),
})

router.beforeEach(async (to) => {
  const auth = useAuthStore()
  if (!auth.ready) await auth.bootstrap()

  // v2.112.0 — sesi pending MFA: hanya /mfa yang boleh dibuka.
  if (auth.mfaPending) {
    return to.name === 'mfa' ? true : { name: 'mfa' }
  }

  if (to.meta.public) {
    if (to.name === 'login' && auth.isAuthenticated) {
      return ROLE_META[auth.role] ? { path: ROLE_META[auth.role].home } : true
    }
    if (to.name === 'mfa') {
      return auth.isAuthenticated
        ? (ROLE_META[auth.role] ? { path: ROLE_META[auth.role].home } : true)
        : { name: 'login' }
    }
    return true
  }

  if (!auth.isAuthenticated) {
    // Tautan form yang sudah tersebar memakai /first-work — arahkan ke form
    // publik yang baru alih-alih memaksa pendaftar login.
    if (to.name === 'first-work') return { name: 'first-work-form', query: to.query }
    return { name: 'login', query: { next: to.fullPath } }
  }
  // Halaman data FirstWork tetap terdaftar (bukan redirect murni) supaya
  // bookmark lama terbuka. Setelah login, arahkan ke tab FirstWork di hub dan
  // bawa query yang ada (mis. filter/cabang dari tautan lama).
  if (to.name === 'first-work') {
    return { path: '/recruitment', query: { ...to.query, tab: 'pelamar', view: 'firstwork' } }
  }
  const roles = to.meta.roles
  if (roles && !roles.includes(auth.role)) {
    return { name: 'forbidden' }
  }
  return true
})

export default router
