<script setup lang="ts">
import { computed, onMounted, onUnmounted, watch } from 'vue'
import { useRoute } from 'vue-router'
import AnnouncementBanner from '@/components/layout/AnnouncementBanner.vue'
import AppBar from '@/components/layout/AppBar.vue'
import AppFooter from '@/components/layout/AppFooter.vue'
import LoginModal from '@/components/auth/LoginModal.vue'
import LegalModal from '@/components/legal/LegalModal.vue'
import { useNotificationStore } from '@/stores/notification'
import { useThemeStore } from '@/stores/theme'
import { useUserStore } from '@/stores/user'

// 应用启动时应用持久化主题（默认暗黑）
const theme = useThemeStore()
theme.init()

const route = useRoute()
const user = useUserStore()
const notification = useNotificationStore()
// G35：独立页（登录/找回密码/法律页）不显示顶部导航与公告条；其余页面一律显示
const showAppbar = computed(() => !route.meta.bare)

const viewport = window.visualViewport
function syncVisibleHeight() {
  if (viewport && viewport.scale === 1 && viewport.height < window.innerHeight) {
    document.documentElement.style.setProperty('--visible-height', `${Math.floor(viewport.height)}px`)
  } else {
    document.documentElement.style.removeProperty('--visible-height')
  }
}
onMounted(() => viewport?.addEventListener('resize', syncVisibleHeight))
onUnmounted(() => {
  viewport?.removeEventListener('resize', syncVisibleHeight)
  document.documentElement.style.removeProperty('--visible-height')
})

// G16：登录后初始化通知（WS 绑定 + 未读数 + 活跃公告），登出时清理
onMounted(() => {
  if (user.token) notification.init()
})
watch(
  () => user.token,
  (token) => {
    if (token) notification.init()
    else notification.clear()
  },
)
</script>

<template>
  <div class="app-shell" :class="{ 'app-shell--workspace': route.name === 'ai', 'app-shell--forecast': route.name === 'forecast' }">
    <AppBar v-if="showAppbar" />
    <!-- G16：系统公告 banner（有活跃公告时展示，可关闭） -->
    <AnnouncementBanner v-if="showAppbar" />
    <main class="app-main">
      <RouterView />
    </main>
    <!-- G03：底部版权条（所有页面可见，含登录/注册/法律页） -->
    <AppFooter />
    <!-- G35：登录/注册弹窗（全局单例，由 authModal store 控制显隐） -->
    <LoginModal />
    <!-- G03 改造：法律文档轻量弹窗（全局单例，由 legalModal store 控制） -->
    <LegalModal />
  </div>
</template>

<style scoped>
.app-shell {
  display: flex;
  flex-direction: column;
  height: 100%;
}
.app-main {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
}
.app-main { min-width: 0; }
@media (max-width: 767px), (max-width: 1023px) and (max-height: 500px) and (pointer: coarse) {
  .app-shell {
    height: auto;
    min-height: var(--screen-height);
    padding: var(--safe-top) var(--safe-right) var(--safe-bottom) var(--safe-left);
  }
  .app-shell--workspace { height: var(--visible-height, var(--screen-height)); min-height: 0; }
  .app-shell--forecast { height: var(--screen-height); min-height: 0; }
}
</style>
