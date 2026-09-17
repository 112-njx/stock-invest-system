<script setup lang="ts">
import { computed, onMounted, watch } from 'vue'
import { useRoute } from 'vue-router'
import AnnouncementBanner from '@/components/layout/AnnouncementBanner.vue'
import AppBar from '@/components/layout/AppBar.vue'
import AppFooter from '@/components/layout/AppFooter.vue'
import { useNotificationStore } from '@/stores/notification'
import { useThemeStore } from '@/stores/theme'
import { useUserStore } from '@/stores/user'

// 应用启动时应用持久化主题（默认暗黑）
const theme = useThemeStore()
theme.init()

const route = useRoute()
const user = useUserStore()
const notification = useNotificationStore()
const showAppbar = computed(() => !route.meta.public)

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
  <div class="app-shell">
    <AppBar v-if="showAppbar" />
    <!-- G16：系统公告 banner（有活跃公告时展示，可关闭） -->
    <AnnouncementBanner v-if="showAppbar" />
    <main class="app-main">
      <RouterView />
    </main>
    <!-- G03：底部版权条（所有页面可见，含登录/注册/法律页） -->
    <AppFooter />
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
</style>
