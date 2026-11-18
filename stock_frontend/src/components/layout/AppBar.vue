<script setup lang="ts">
/**
 * 顶部导航栏：品牌 + 路由 + 主题切换。
 * 优化1：删除顶部用户头像/用户名和退出按钮，统一收归行情页 I 区用户 Cell 下拉菜单。
 * G35：头像区回归顶部（方案 B）——未登录显示「登录」入口，已登录显示头像 + 下拉菜单；
 * 与 G16 铃铛并存，I 区用户 Cell 保留。
 */
import NotificationBell from '@/components/layout/NotificationBell.vue'
import UserMenu from '@/components/layout/UserMenu.vue'
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import StockSearch from '@/components/layout/StockSearch.vue'
import { useThemeStore } from '@/stores/theme'
import { useUserStore } from '@/stores/user'

const theme = useThemeStore()
const user = useUserStore()
const route = useRoute()
const router = useRouter()
const opened = ref<'menu' | 'search' | null>(null)
const menuButton = ref<HTMLButtonElement>()
const searchButton = ref<HTMLButtonElement>()
const titles: Record<string, string> = {
  'market-home': '行情', 'market-detail': '行情详情', stocks: '股票',
  stockdb: '指数', heatmap: '大盘云图', ai: 'AI 策略', forecast: '预测走势', admin: '管理后台',
}
const title = computed(() => titles[String(route.name)] || '量化交易终端')
watch(() => route.fullPath, () => { opened.value = null })

function toggle(panel: 'menu' | 'search') {
  opened.value = opened.value === panel ? null : panel
}
function browseStock(code: string) {
  opened.value = null
  void router.push({ name: 'market-detail', query: { symbol: code, asset_type: 'stock' } })
}
function closePanel(event: KeyboardEvent) {
  if (!opened.value || event.defaultPrevented ||
      document.querySelector('[aria-modal="true"], dialog[open]')) return
  event.stopPropagation()
  const button = opened.value === 'menu' ? menuButton.value : searchButton.value
  opened.value = null
  button?.focus()
}
function prepareBlueprint() {
  void import('@/api/stockdbCache').then(({ prepareStockDbHome }) => prepareStockDbHome())
  void import('@/views/StockDbView.vue')
}
let prepareTimer: ReturnType<typeof setTimeout> | undefined
onMounted(() => {
  if (location.pathname !== '/stockdb') prepareTimer = setTimeout(prepareBlueprint, 1500)
})
onBeforeUnmount(() => clearTimeout(prepareTimer))
</script>

<template>
  <header class="appbar" @keydown.esc="closePanel">
    <div class="appbar__brand">
      <span class="appbar__logo">K</span>
      <span class="appbar__name">量化交易终端</span>
      <span class="appbar__mobile-title">{{ title }}</span>
    </div>

    <nav id="app-navigation" class="appbar__nav" :class="{ 'appbar__nav--open': opened === 'menu' }" aria-label="主导航" @click="opened = null">
      <RouterLink :to="{ name: 'market-home' }" class="appbar__link">行情</RouterLink>
      <RouterLink to="/stocks" class="appbar__link">股票</RouterLink>
      <RouterLink to="/stockdb" class="appbar__link" @pointerenter="prepareBlueprint" @focus="prepareBlueprint">指数</RouterLink>
      <RouterLink to="/heatmap" class="appbar__link">大盘</RouterLink>
      <RouterLink to="/ai" class="appbar__link">AI 策略</RouterLink>
      <RouterLink :to="{ name: 'forecast' }" class="appbar__link">预测走势</RouterLink>
      <RouterLink v-if="user.user?.username === 'root' && user.user.is_admin" to="/admin" class="appbar__link appbar__admin-mobile">管理后台</RouterLink>
    </nav>

    <div class="appbar__right">
      <RouterLink v-if="user.user?.username === 'root' && user.user.is_admin" to="/admin" class="appbar__link appbar__admin-desktop">管理后台</RouterLink>
      <button ref="searchButton" class="appbar__mobile-action" type="button" :aria-expanded="opened === 'search'" aria-controls="app-search" @click="toggle('search')">搜索</button>
      <NotificationBell />
      <!-- G35：头像区（未登录=登录入口；已登录=下拉菜单） -->
      <UserMenu />
      <button
        class="icon-btn"
        :title="theme.mode === 'dark' ? '切换到明亮模式' : '切换到暗黑模式'"
        @click="theme.toggle()"
      >
        {{ theme.mode === 'dark' ? '☀' : '🌙' }}
      </button>
      <button ref="menuButton" class="appbar__mobile-action" type="button" :aria-expanded="opened === 'menu'" aria-controls="app-navigation" @click="toggle('menu')">菜单</button>
    </div>
    <div v-if="opened === 'search'" id="app-search" class="appbar__search">
      <StockSearch browse @select="browseStock" />
    </div>
  </header>
</template>

<style scoped>
.appbar {
  display: flex;
  align-items: center;
  gap: 24px;
  flex: none;
  height: 44px;
  padding: 0 16px;
  background: var(--bg-panel);
  border-bottom: 1px solid var(--border);
}
.appbar__brand {
  display: flex;
  align-items: center;
  gap: 8px;
}
.appbar__logo {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 26px;
  height: 26px;
  border-radius: 5px;
  background: var(--accent);
  color: #fff;
  font-size: 14px;
  font-weight: 700;
}
.appbar__name {
  font-size: 14px;
  font-weight: 600;
}
.appbar__nav {
  display: flex;
  gap: 4px;
}
.appbar__link {
  padding: 5px 12px;
  border-radius: 4px;
  font-size: 13px;
  color: var(--text-secondary);
  text-decoration: none;
  transition:
    background-color 0.15s,
    color 0.15s;
}
.appbar__link:hover {
  color: var(--text);
  background: var(--bg-hover);
}
.appbar__link.router-link-active {
  color: var(--text);
  background: var(--bg-active);
}
.appbar__right {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-left: auto;
}
.icon-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 28px;
  border-radius: 4px;
  font-size: 15px;
  color: var(--text-secondary);
}
.icon-btn:hover {
  background: var(--bg-hover);
  color: var(--text);
}
.appbar__mobile-title, .appbar__mobile-action, .appbar__admin-mobile, .appbar__search { display: none; }

@media (max-width: 1023px) {
  .appbar { gap: 8px; padding-inline: 8px; }
  .appbar__right { gap: 4px; }
  .appbar__link { padding-inline: 8px; }
}

@media (max-width: 767px), (max-width: 1023px) and (max-height: 500px) and (pointer: coarse) {
  .appbar { position: relative; height: auto; min-height: 52px; }
  .appbar__brand { flex: 1; min-width: 0; }
  .appbar__logo { flex: none; }
  .appbar__name, .appbar__admin-desktop { display: none; }
  .appbar__mobile-title { display: block; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .appbar__mobile-action, .appbar__admin-mobile { display: block; }
  .appbar__mobile-action, .appbar__right :deep(.icon-btn), .appbar__right :deep(.um__btn) {
    min-width: var(--touch-target); min-height: var(--touch-target); padding-inline: 4px;
  }
  .appbar__right :deep(.um__name) { display: none; }
  .appbar__nav, .appbar__search {
    position: absolute;
    z-index: 120;
    inset: 100% 0 auto;
    padding: 8px;
    background: var(--bg-panel);
    border: 1px solid var(--border);
    box-shadow: var(--shadow);
  }
  .appbar__nav { display: none; }
  .appbar__nav--open { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .appbar__nav .appbar__link { min-height: var(--touch-target); display: flex; align-items: center; }
  .appbar__search { display: block; }
  .appbar__search :deep(.stock-search) { width: 100%; min-width: 0; }
  .appbar__search :deep(.stock-search__input) { min-height: var(--touch-target); font-size: 16px; }
  .appbar__search :deep(.stock-search__dropdown) { width: 100%; }
}
</style>
