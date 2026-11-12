import { createRouter, createWebHistory } from 'vue-router'
import { useAuthStore, ROLE_META } from '../stores/auth'

const routes = [
  { path: '/login', name: 'login', component: () => import('../views/LoginView.vue'), meta: { public: true } },
  { path: '/403', name: 'forbidden', component: () => import('../views/ForbiddenView.vue'), meta: { public: true } },
  // Form publik pelamar kerja (v2.16) — tanpa login
  { path: '/apply', name: 'apply', component: () => import('../views/ApplyView.vue'), meta: { public: true } },
  // Form publik overtime OB/Security (v2.22) — tanpa login
  { path: '/overtime-form', name: 'overtime-form', component: () => import('../views/OvertimeFormView.vue'), meta: { public: true } },
  // Form publik Absensi FirstWork (v2.80.0) — tanpa login, mobile-first.
  // Path sengaja BUKAN /first-work: path itu milik halaman data di dalam layout.
  // Kalau sama, Vue Router memilih record pertama (form) sehingga user login
  // yang membuka menu "Absensi FirstWork" justru melihat form, bukan datanya.
  { path: '/first-work-form', name: 'first-work-form', component: () => import('../views/FirstWorkFormView.vue'), meta: { public: true } },
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
      { path: 'rekap', name: 'rekap', redirect: (to) => ({ path: '/cash', query: { tab: 'laporan', view: 'rekap', ...to.query } }), meta: { roles: ['ga', 'finance', 'admin'] } },
      { path: 'cash', name: 'cash', component: () => import('../views/CashView.vue'), meta: { roles: ['ga', 'finance', 'admin'] } },
      { path: 'analytics', name: 'analytics', redirect: (to) => ({ path: '/cash', query: { tab: 'laporan', view: 'analisis', ...to.query } }), meta: { roles: ['ga', 'finance', 'admin'] } },
      { path: 'users', name: 'users', component: () => import('../views/UsersView.vue'), meta: { roles: ['admin'] } },
      { path: 'approvals', name: 'approvals', component: () => import('../views/ApprovalsView.vue'), meta: { roles: ['chief_driver', 'ga', 'ga_hr'] } },
      { path: 'access-review', name: 'access-review', component: () => import('../views/AccessReviewView.vue'), meta: { roles: ['admin'] } },
      // Profil Saya (v2.81.0) — semua role boleh ganti nama & PIN sendiri.
      { path: 'profile', name: 'profile', component: () => import('../views/ProfileView.vue'), meta: { title: 'Profil Saya' } },
      { path: 'settings', name: 'settings', component: () => import('../views/SettingsView.vue'), meta: { roles: ['admin'] } },
      { path: 'logs', name: 'logs', component: () => import('../views/LogsView.vue'), meta: { roles: ['admin'] } },
      { path: 'water', name: 'water', component: () => import('../views/WaterView.vue'), meta: { roles: ['ob', 'finance', 'admin'] } },
      // Pengadaan / PO (v2.70.0) — master supplier + purchase order + penerimaan
      { path: 'procurement', name: 'procurement', component: () => import('../views/ProcurementView.vue'), meta: { roles: ['ga', 'admin'] } },
      // Rekap Pengeluaran (v2.71.0) — lintas modul, angka terukur saja
      { path: 'expenses', name: 'expenses', redirect: (to) => ({ path: '/cash', query: { tab: 'laporan', view: 'realisasi', ...to.query } }), meta: { roles: ['finance', 'admin'] } },
      // Form overtime user OB & Security (v2.39) — dari dalam aplikasi (login)
      { path: 'overtime-me', name: 'overtime-me', component: () => import('../views/OvertimeMeView.vue'), meta: { roles: ['ob', 'security'] } },
      // Rekrutmen (v2.80) — receptionist mengelola, traineer hanya melihat.
      { path: 'receptionist', name: 'receptionist', component: () => import('../views/dashboard/ReceptionistView.vue'), meta: { roles: ['receptionist', 'traineer', 'admin'], title: 'Rekrutmen' } },
      // URL lama "Rekrutan Saya" — diarahkan ke halaman Rekrutmen.
      { path: 'traineer', redirect: '/receptionist' },
      // In-Out Karyawan (v2.41.0) — catatan keluar-masuk (read-only, sync sheet)
      { path: 'inout', name: 'inout', component: () => import('../views/dashboard/EmployeeInOutView.vue'), meta: { roles: ['receptionist', 'admin'] } },
      // Absensi FirstWork (v2.80.0) — verifikasi Traineer, lihat Finance, kelola Admin
      { path: 'first-work', name: 'first-work', component: () => import('../views/FirstWorkView.vue'), meta: { roles: ['traineer', 'finance', 'ga_hr', 'admin'], title: 'Absensi FirstWork' } },
      { path: 'assets', name: 'assets', component: () => import('../views/dashboard/AssetsView.vue'), meta: { roles: ['ga', 'admin'] } },
      { path: 'ga-hr', name: 'ga-hr', component: () => import('../views/dashboard/OvertimeView.vue'), meta: { roles: ['ga_hr', 'admin'] } },
      { path: 'it', name: 'it', component: () => import('../views/ItEfView.vue'), meta: { roles: ['it_sby', 'it_hu', 'it_jkt2', 'it_bdg', 'it_smg', 'it_mlg', 'it_mdn', 'it_bjm', 'it_plm', 'it_lpg', 'admin'] } },
      // v2.78.0 — Inventaris IT (aset non-jaringan, label QR, kondisi, discovery)
      { path: 'it/inventory', name: 'it-inventory', component: () => import('../views/ItInventoryView.vue'), meta: { roles: ['it_sby', 'it_hu', 'it_jkt2', 'it_bdg', 'it_smg', 'it_mlg', 'it_mdn', 'it_bjm', 'it_plm', 'it_lpg', 'admin'] } },
      { path: 'it/assets/:tag', name: 'it-asset-detail', component: () => import('../views/ItAssetDetailView.vue'), meta: { roles: ['it_sby', 'it_hu', 'it_jkt2', 'it_bdg', 'it_smg', 'it_mlg', 'it_mdn', 'it_bjm', 'it_plm', 'it_lpg', 'admin'] } },
      { path: 'it/scan', name: 'it-scan', component: () => import('../views/ItScanView.vue'), meta: { roles: ['it_sby', 'it_hu', 'it_jkt2', 'it_bdg', 'it_smg', 'it_mlg', 'it_mdn', 'it_bjm', 'it_plm', 'it_lpg', 'admin'] } },
      // Transcoder (v2.46.0) — konversi link YouTube ke format audio/video
      { path: 'transcoder', name: 'transcoder', component: () => import('../views/TranscoderView.vue'), meta: { roles: ['it_sby', 'it_hu', 'it_jkt2', 'it_bdg', 'it_smg', 'it_mlg', 'it_mdn', 'it_bjm', 'it_plm', 'it_lpg', 'admin'] } },
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

  if (to.meta.public) {
    if (to.name === 'login' && auth.isAuthenticated) {
      return ROLE_META[auth.role] ? { path: ROLE_META[auth.role].home } : true
    }
    return true
  }

  if (!auth.isAuthenticated) {
    // Tautan form yang sudah tersebar memakai /first-work — arahkan ke form
    // publik yang baru alih-alih memaksa pendaftar login.
    if (to.name === 'first-work') return { name: 'first-work-form', query: to.query }
    return { name: 'login', query: { next: to.fullPath } }
  }
  const roles = to.meta.roles
  if (roles && !roles.includes(auth.role)) {
    return { name: 'forbidden' }
  }
  return true
})

export default router
