<script setup lang="ts">
import { computed } from 'vue'
import { type AdminConsole, stateLabel } from '@/composables/useAdminConsole'
import AdminNotice from './AdminNotice.vue'
import AdminErrors from './AdminErrors.vue'
const props = defineProps<{ controller: AdminConsole }>()
const emit = defineEmits<{ navigate: [section: 'sources' | 'tasks' | 'requests'] }>()
const s = props.controller.state
const totals = computed(() =>
  Object.values(s.queues.data?.queues ?? {}).reduce(
    (a, q) => ({
      ready: a.ready + q.ready,
      active: a.active + q.active,
    }),
    { ready: 0, active: 0 }
  )
)
</script>
<template>
  <div class="metric-grid">
    <article class="metric">
      <span>本地数据服务</span
      ><strong :class="{ danger: s.services.data?.stockdb.state === 'unavailable' }">{{
        s.services.data ? stateLabel(s.services.data.stockdb.state) : '—'
      }}</strong
      ><small>Free-StockDB 数据库</small>
    </article>
    <article class="metric">
      <span>行情数据日期</span><strong>{{ s.services.data?.stockdb.latest_date || '—' }}</strong
      ><small>贵州茅台日 K 采样日期</small>
    </article>
    <article class="metric">
      <span>执行中任务</span><strong>{{ s.queues.data ? totals.active : '—' }}</strong
      ><small>等待执行 {{ s.queues.data ? totals.ready : '—' }} 项</small>
    </article>
  </div>
  <div class="two-column">
    <section class="admin-card">
      <div class="card-title">
        <div>
          <h2>行情数据工作流</h2>
          <p>更新并验证 StockDB 原始行情</p>
        </div>
        <span class="badge">本地优先</span>
      </div>
      <p>更新原始行情文件后，个股和 ETF 查询会直接读 StockDB 的新版本。</p>

      <button class="primary" @click="emit('navigate', 'sources')">管理行情与数据源 →</button>
    </section>
    <section class="admin-card">
      <div class="card-title">
        <div>
          <h2>最近原始数据更新</h2>
          <p>手动或定时提交的 StockDB 更新</p>
        </div>
        <span class="badge" :class="{ danger: s.update.data?.status === 'failed' }">{{
          s.update.data ? stateLabel(s.update.data.status) : '等待读取'
        }}</span>
      </div>
      <AdminNotice :resource="s.update" />
      <template v-if="s.update.data"
        ><p class="sync-message">{{ s.update.data.message }}</p>
        <progress :value="Math.max(0, Math.min(100, s.update.data.progress))" max="100" />
        <div class="split">
          <small>处理进度</small><b>{{ s.update.data.progress }}%</b>
        </div>
        <AdminErrors v-if="s.update.data.error" :error="s.update.data.error" /></template
      >
      <div class="divider" />
      <h3>当前数据源策略</h3>
      <AdminNotice :resource="s.policy" />
      <p>
        {{
          s.policy.data
            ? s.policy.data.akshare_enabled
              ? '本地数据优先，已启用外部补充'
              : '仅使用本地 Free-StockDB'
            : '策略尚未读取'
        }}
      </p>
      <p v-if="s.policy.data">每日 16:30 自动更新 {{ s.policy.data.auto_update_enabled ? '开启' : '关闭' }}</p>

    </section>
  </div>
  <section class="admin-card">
    <div class="card-title">
      <div>
        <h2>运行检查</h2>
        <p>服务、任务及数据读取状态分别观测</p>
      </div>
    </div>
    <AdminNotice :resource="s.services" /><AdminNotice :resource="s.queues" />
    <div class="quick-grid">
      <button class="quick" @click="emit('navigate', 'sources')">
        <b>数据服务</b><span>数据库与历史计算服务</span><em>查看 →</em></button
      ><button class="quick" @click="emit('navigate', 'tasks')">
        <b>任务队列</b><span>积压、执行与消费者响应</span><em>查看 →</em></button
      ><button class="quick" @click="emit('navigate', 'requests')">
        <b>请求监控</b><span>当前数据请求及内部重试</span><em>查看 →</em>
      </button>
    </div>
  </section>
</template>
