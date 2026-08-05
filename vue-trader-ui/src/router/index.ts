import { createRouter, createWebHistory, type RouteRecordRaw } from 'vue-router';

const routes: RouteRecordRaw[] = [
  {
    path: '/',
    redirect: '/stock/sh600519',
  },
  {
    path: '/stock/:symbol',
    name: 'StockDetail',
    component: () => import('@/views/StockDetailPage.vue'),
    meta: { title: '股票行情' },
  },
  {
    path: '/ai-backtest',
    name: 'AiBacktest',
    component: () => import('@/views/AiBacktestPage.vue'),
    meta: { title: 'AI 策略回测' },
  },
  {
    path: '/:pathMatch(.*)*',
    redirect: '/',
  },
];

const router = createRouter({
  history: createWebHistory(),
  routes,
});

export default router;
