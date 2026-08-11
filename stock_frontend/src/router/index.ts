import { nextTick } from 'vue'
import { createRouter, createWebHistory } from 'vue-router'
import { useUserStore } from '@/stores/user'
import { trackTiming } from '@/utils/monitor'

declare module 'vue-router' {
  interface RouteMeta {
    /** 无需登录即可访问（如登录页） */
    public?: boolean
  }
}

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', redirect: '/market' },
    {
      path: '/login',
      name: 'login',
      component: () => import('@/views/LoginView.vue'),
      meta: { public: true },
    },
    {
      path: '/market',
      name: 'market',
      component: () => import('@/views/MarketView.vue'),
    },
    {
      path: '/market/detail',
      name: 'market-detail',
      component: () => import('@/views/MarketDetailView.vue'),
    },
    {
      path: '/ai',
      name: 'ai',
      component: () => import('@/views/AIView.vue'),
    },
  ],
})

// 登录守卫：未登录跳登录页，已登录访问登录页跳行情页
router.beforeEach((to) => {
  const user = useUserStore()
  if (!to.meta.public && !user.token) {
    return { name: 'login', query: { redirect: to.fullPath } }
  }
  if (to.name === 'login' && user.token) {
    return { name: 'market' }
  }
})

// 页面切换耗时埋点（5.3）：nextTick 后近似「组件渲染完成」时刻
router.afterEach(async (to) => {
  const start = performance.now()
  await nextTick()
  trackTiming('route_change', performance.now() - start, { to: to.fullPath })
})

export default router
