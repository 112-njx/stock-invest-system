<script setup lang="ts">
import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useAdminConsole, type AdminSection } from '@/composables/useAdminConsole'
import AdminOverview from '@/components/admin/AdminOverview.vue'
import AdminSources from '@/components/admin/AdminSources.vue'
import AdminTasks from '@/components/admin/AdminTasks.vue'
import AdminRequests from '@/components/admin/AdminRequests.vue'
import AdminDisplay from '@/components/admin/AdminDisplay.vue'
import '@/components/admin/admin.css'

const route = useRoute()
const router = useRouter()
const sections = [
  {
    id: 'overview',
    title: '运行概览',
    subtitle: '本地行情、任务执行与系统状态，一目了然。',
    icon: '◫',
  },
  {
    id: 'sources',
    title: '行情与数据源',
    subtitle: '管理本地服务、同步流程及外部补充策略。',
    icon: '▤',
  },
  { id: 'tasks', title: '任务与队列', subtitle: '检查任务积压、执行情况和消费者响应。', icon: '≡' },
  {
    id: 'requests',
    title: '请求监控',
    subtitle: '跟踪当前行情请求、处理阶段和内部重试。',
    icon: '↗',
  },
  {
    id: 'display',
    title: '显示设置',
    subtitle: '配置行情展示参数，独立于原始数据与策略计算。',
    icon: '⚙',
  },
] as const
const section = computed<AdminSection>(
  () => sections.find((s) => s.id === route.query.section)?.id ?? 'overview'
)
const current = computed(() => sections.find((s) => s.id === section.value)!)
const controller = useAdminConsole(section)
function navigate(id: AdminSection) {
  void router.replace({ query: { ...route.query, section: id } })
}
</script>

<template>
  <main class="admin-console">
    <aside class="admin-sidebar">
      <div class="console-brand">
        <span class="console-mark">A</span>
        <div><strong>管理控制台</strong><small>系统运行与数据管理</small></div>
      </div>
      <span class="nav-caption">工作空间</span>
      <nav aria-label="管理功能">
        <button
          v-for="item in sections"
          :key="item.id"
          :class="{ selected: section === item.id }"
          :aria-current="section === item.id ? 'page' : undefined"
          @click="navigate(item.id)"
        >
          <span aria-hidden="true">{{ item.icon }}</span
          >{{ item.title }}<b v-if="section === item.id">›</b>
        </button>
      </nav>
      <div class="sidebar-bottom">
        <span class="status-dot online" />
        <div><b>本地数据优先</b><small>Free-StockDB 工作流</small></div>
      </div>
    </aside>
    <div class="admin-workspace">
      <header class="workspace-header">
        <div>
          <div class="breadcrumb">系统管理 <span>/</span> {{ current.title }}</div>
          <h1>{{ current.title }}</h1>
          <p>{{ current.subtitle }}</p>
        </div>
        <button
          class="secondary"
          :disabled="controller.refreshing.value"
          @click="controller.refresh"
        >
          {{ controller.refreshing.value ? '更新中…' : '↻ 刷新当前页' }}
        </button>
      </header>
      <div class="admin-content">
        <AdminOverview
          v-if="section === 'overview'"
          :controller="controller"
          @navigate="navigate"
        />
        <AdminSources v-else-if="section === 'sources'" :controller="controller" />
        <AdminTasks v-else-if="section === 'tasks'" :controller="controller" />
        <AdminRequests v-else-if="section === 'requests'" :controller="controller" />
        <AdminDisplay v-else :controller="controller" />
      </div>
    </div>
  </main>
</template>
