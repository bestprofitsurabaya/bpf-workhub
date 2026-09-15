import { createRouter, createWebHistory } from 'vue-router'
import { useAuthStore, ROLE_META } from '../stores/auth'

const routes = [
  { path: '/login', name: 'login', component: () => import('../views/LoginView.vue'), meta: { public: true } },
  { path: '/403', name: 'forbidden', component: () => import('../views/ForbiddenView.vue'), meta: { public: true } },
  // Form publik pelamar kerja (v2.16) — tanpa login
  { path: '/apply', name: 'apply', component: () => import('../views/ApplyView.vue'), meta: { public: true } },
  // Form publik overtime OB/Security (v2.22) — tanpa login
  { path: '/overtime-form', name: 'overtime-form', component: () => import('../views/OvertimeFormView.vue'), meta: { public: true } },
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
      { path: 'trips', name: 'trips', component: () => import('../views/TripsView.vue'), meta: { roles: ['ga', 'finance', 'admin'] } },
      { path: 'assignments', name: 'assignments', component: () => import('../views/AssignmentsView.vue'), meta: { roles: ['ga', 'admin'] } },
      { path: 'rekap', name: 'rekap', component: () => import('../views/RekapView.vue'), meta: { roles: ['finance', 'admin'] } },
      { path: 'cash', name: 'cash', component: () => import('../views/CashView.vue'), meta: { roles: ['ga', 'finance', 'admin'] } },
      { path: 'analytics', name: 'analytics', component: () => import('../views/AnalyticsView.vue'), meta: { roles: ['ga', 'finance', 'admin'] } },
      { path: 'users', name: 'users', component: () => import('../views/UsersView.vue'), meta: { roles: ['admin'] } },
      { path: 'approvals', name: 'approvals', component: () => import('../views/ApprovalsView.vue'), meta: { roles: ['chief_driver', 'ga', 'finance', 'ga_hr', 'admin'] } },
      { path: 'access-review', name: 'access-review', component: () => import('../views/AccessReviewView.vue'), meta: { roles: ['admin'] } },
      { path: 'settings', name: 'settings', component: () => import('../views/SettingsView.vue'), meta: { roles: ['admin'] } },
      { path: 'logs', name: 'logs', component: () => import('../views/LogsView.vue'), meta: { roles: ['admin'] } },
      { path: 'water', name: 'water', component: () => import('../views/WaterView.vue'), meta: { roles: ['ob', 'finance', 'admin'] } },
      // Form overtime user OB & Security (v2.39) — dari dalam aplikasi (login)
      { path: 'overtime-me', name: 'overtime-me', component: () => import('../views/OvertimeMeView.vue'), meta: { roles: ['ob', 'security'] } },
      { path: 'receptionist', name: 'receptionist', component: () => import('../views/dashboard/ReceptionistView.vue'), meta: { roles: ['receptionist', 'admin'] } },
      // In-Out Karyawan (v2.41.0) — catatan keluar-masuk (read-only, sync sheet)
      { path: 'inout', name: 'inout', component: () => import('../views/dashboard/EmployeeInOutView.vue'), meta: { roles: ['receptionist', 'admin'] } },
      { path: 'traineer', name: 'traineer', component: () => import('../views/dashboard/TraineerView.vue'), meta: { roles: ['traineer'] } },
      { path: 'assets', name: 'assets', component: () => import('../views/dashboard/AssetsView.vue'), meta: { roles: ['ga', 'admin'] } },
      { path: 'ga-hr', name: 'ga-hr', component: () => import('../views/dashboard/OvertimeView.vue'), meta: { roles: ['ga_hr', 'admin'] } },
      { path: 'it', name: 'it', component: () => import('../views/ItEfView.vue'), meta: { roles: ['it_sby', 'it_hu', 'it_jkt2', 'it_bdg', 'it_smg', 'it_mlg', 'it_mdn', 'it_bjm', 'it_plm', 'it_lpg', 'admin'] } },
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
    return { name: 'login', query: { next: to.fullPath } }
  }
  const roles = to.meta.roles
  if (roles && !roles.includes(auth.role)) {
    return { name: 'forbidden' }
  }
  return true
})

export default router
