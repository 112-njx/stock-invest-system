import { nextTick } from 'vue'
import { createRouter, createWebHistory } from 'vue-router'
import { useUserStore } from '@/stores/user'
import { trackTiming } from '@/utils/monitor'

declare module 'vue-router' {
  interface RouteMeta {
    /**
     * 独立页：不渲染顶部导航栏与系统公告条（登录 / 找回密码 / 法律页等）。
     * G35 起与「是否需要登录」解耦——方案 B 下所有业务页均免登录可浏览。
     */
    bare?: boolean
  }
}

const router = createRouter({
  history: createWebHistory(),
  routes: [
    // G35（方案 B）：`/` 为行情首页，免登录即可浏览；原登录页独立保留在 `/login`
    {
      path: '/',
      name: 'market-home',
      component: () => import('@/views/MarketView.vue'),
    },
    // 兼容既有链接与外部 deep link
    { path: '/market', redirect: '/' },
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
    // 独立页（不显示顶部导航/公告条）
    {
      path: '/login',
      name: 'login',
      component: () => import('@/views/LoginView.vue'),
      meta: { bare: true },
    },
    // G33：忘记密码 / 重置密码 / 邮箱验证
    {
      path: '/forgot-password',
      name: 'forgot-password',
      component: () => import('@/views/ForgotPasswordView.vue'),
      meta: { bare: true },
    },
    {
      path: '/reset-password',
      name: 'reset-password',
      component: () => import('@/views/ResetPasswordView.vue'),
      meta: { bare: true },
    },
    {
      path: '/verify-email',
      name: 'verify-email',
      component: () => import('@/views/VerifyEmailView.vue'),
      meta: { bare: true },
    },
    // G03：法律页面
    // 《用户协议》保留独立页面；免责声明 / 隐私政策改为全局轻量弹窗（LegalModal），
    // 不再配置专属 URL。旧链接（书签、邮件等）重定向回首页，避免落到空白页。
    {
      path: '/terms',
      name: 'terms',
      component: () => import('@/views/legal/TermsView.vue'),
      meta: { bare: true },
    },
    { path: '/privacy', redirect: '/' },
    { path: '/disclaimer', redirect: '/' },
  ],
})

/**
 * G35（方案 B）：免登录浏览，不再有「未登录强制跳登录页」的守卫。
 * 唯一的方向性跳转是已登录用户访问 `/login` 时回到首页；直接访问 `/login`（deep link）
 * 仍正常展示登录页，用于强制登录场景。
 */
router.beforeEach((to) => {
  const user = useUserStore()
  if (to.name === 'login' && user.token) {
    return { name: 'market-home' }
  }
})

// 页面切换耗时埋点（5.3）：nextTick 后近似「组件渲染完成」时刻
router.afterEach(async (to) => {
  const start = performance.now()
  await nextTick()
  trackTiming('route_change', performance.now() - start, { to: to.fullPath })
})

export default router
