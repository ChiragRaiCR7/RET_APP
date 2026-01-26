import { createRouter, createWebHistory } from 'vue-router'
import LoginView from '@/views/LoginView.vue'
import MainView from '@/views/MainView.vue'
import AdminView from '@/views/AdminView.vue'
import { useAuthStore } from '@/stores/authStore'

const routes = [
  { path: '/', name: 'login', component: LoginView, meta: { requiresGuest: true } },
  { path: '/app', name: 'main', component: MainView, meta: { requiresAuth: true } },
  { path: '/admin', name: 'admin', component: AdminView, meta: { requiresAuth: true, requiresAdmin: true } },
  { path: '/:pathMatch(.*)*', redirect: '/' }, // Catch-all redirect to login
]

const router = createRouter({
  history: createWebHistory(),
  routes
})

router.beforeEach((to, from, next) => {
  const auth = useAuthStore()
  
  if (to.meta.requiresAuth && !auth.isAuthenticated) {
    // Redirect to login if trying to access protected route without auth
    next({ name: 'login', query: { redirect: to.fullPath } })
  } else if (to.meta.requiresGuest && auth.isAuthenticated) {
    // Redirect authenticated users away from login
    next({ name: 'main' })
  } else if (to.meta.requiresAdmin && !auth.isAdmin) {
    // Redirect non-admins away from admin
    next({ name: 'main' })
  } else {
    next()
  }
})

export default router
