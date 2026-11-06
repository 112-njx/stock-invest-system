<script setup lang="ts">
import { computed } from 'vue'
import { type AdminConsole, stateLabel } from '@/composables/useAdminConsole'
import AdminNotice from './AdminNotice.vue'
const props = defineProps<{ controller: AdminConsole }>()
const emit = defineEmits<{ navigate: [section: 'sources' | 'tasks' | 'requests'] }>()
const s = props.controller.state
const totals = computed(() =>
  Object.values(s.queues.data?.queues ?? {}).reduce(
    (a, q) => ({
      ready: a.ready + q.ready,
      active: a.active + q.active,
      abnormal: a.abnormal + q.abnormal,
    }),
    { ready: 0, active: 0, abnormal: 0 }
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
    <article class="metric">
      <span>异常记录</span
      ><strong :class="{ danger: totals.abnormal > 0 }">{{
        s.queues.data ? totals.abnormal : '—'
      }}</strong
      ><small>关注股、同步及近期补拉</small>
    </article>
  </div>
  <div class="two-column">
    <section class="admin-card">
      <div class="card-title">
        <div>
          <h2>行情数据工作流</h2>
          <p>从本地数据更新到项目行情入库</p>
        </div>
        <span class="badge">本地优先</span>
      </div>
      <ol class="workflow">
        <li>
          <b>01</b>
          <div>
            <h3>更新 stockdb 数据</h3>
            <p>在本机运行数据更新程序，等待数据文件更新完成。</p>
          </div>
        </li>
        <li>
          <b>02</b>
          <div>
            <h3>同步至项目</h3>
            <p>导入证券目录，并同步受支持的固定指数与关注标的行情。</p>
          </div>
        </li>
        <li>
          <b>03</b>
          <div>
            <h3>检查同步结果</h3>
            <p>查看处理进度、任务状态及失败原因。</p>
          </div>
        </li>
      </ol>
      <button class="primary" @click="emit('navigate', 'sources')">管理行情与数据源 →</button>
    </section>
    <section class="admin-card">
      <div class="card-title">
        <div>
          <h2>最近本地同步</h2>
          <p>管理员提交的行情导入任务</p>
        </div>
        <span class="badge" :class="{ danger: s.sync.data?.status === 'failed' }">{{
          s.sync.data ? stateLabel(s.sync.data.status) : '等待读取'
        }}</span>
      </div>
      <AdminNotice :resource="s.sync" />
      <template v-if="s.sync.data"
        ><p class="sync-message">{{ s.sync.data.message }}</p>
        <progress :value="Math.max(0, Math.min(100, s.sync.data.progress))" max="100" />
        <div class="split">
          <small>处理进度</small><b>{{ s.sync.data.progress }}%</b>
        </div>
        <p v-if="s.sync.data.error" class="notice danger">{{ s.sync.data.error }}</p></template
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
      <p>
        {{
          s.policy.data
            ? s.policy.data.snapshots_enabled
              ? '实时快照已启用'
              : '实时快照未启用'
            : '—'
        }}
      </p>
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
        <b>任务队列</b><span>积压、异常与消费者响应</span><em>查看 →</em></button
      ><button class="quick" @click="emit('navigate', 'requests')">
        <b>请求监控</b><span>当前数据请求及内部重试</span><em>查看 →</em>
      </button>
    </div>
  </section>
</template>
