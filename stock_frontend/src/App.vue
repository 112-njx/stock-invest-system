<script setup lang="ts">
import { computed } from 'vue'
import { useRoute } from 'vue-router'
import { useThemeStore } from '@/stores/theme'
import AppBar from '@/components/layout/AppBar.vue'

// 应用启动时应用持久化主题（默认暗黑）
const theme = useThemeStore()
theme.init()

const route = useRoute()
const showAppbar = computed(() => !route.meta.public)
</script>

<template>
  <div class="app-shell">
    <AppBar v-if="showAppbar" />
    <main class="app-main">
      <RouterView />
    </main>
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
