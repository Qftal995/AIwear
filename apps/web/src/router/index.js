import { createRouter, createWebHistory } from 'vue-router'
import { useAuthStore } from '../store/auth'

const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes: [
    { path: '/', redirect: '/chat' },
    { path: '/login', name: 'login', component: () => import('../views/LoginView.vue'), meta: { title: '登录' } },
    { path: '/chat', name: 'chat', component: () => import('../views/ChatView.vue'), meta: { auth: true, title: '智能搭配' } },
    { path: '/wardrobe', name: 'wardrobe', component: () => import('../views/WardrobeView.vue'), meta: { auth: true, title: '衣橱管理' } },
    { path: '/images', name: 'images', component: () => import('../views/ImagesView.vue'), meta: { auth: true, title: '我的图片' } },
    { path: '/records', name: 'records', component: () => import('../views/RecordsView.vue'), meta: { auth: true, title: '历史记录' } },
    { path: '/edit', name: 'edit', component: () => import('../views/EditView.vue'), meta: { auth: true, title: '图片编辑' } },
    { path: '/merge', name: 'merge', component: () => import('../views/MergeView.vue'), meta: { auth: true, title: '图片合并' } },
    { path: '/dashboard', name: 'dashboard', component: () => import('../views/DashboardView.vue'), meta: { auth: true, title: '控制面板' } },
    { path: '/:pathMatch(.*)*', redirect: '/chat' },
  ],
})

router.beforeEach((to, _from, next) => {
  const auth = useAuthStore()
  if (to.meta.auth && !auth.isLoggedIn) {
    next({ name: 'login', query: { redirect: to.fullPath } })
  } else if (to.name === 'login' && auth.isLoggedIn) {
    next({ path: '/chat' })
  } else {
    next()
  }
})

export default router
