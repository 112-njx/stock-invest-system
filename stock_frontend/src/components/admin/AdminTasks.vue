<script setup lang="ts">
import { type AdminConsole, queueNames } from '@/composables/useAdminConsole'
import AdminNotice from './AdminNotice.vue'
const props = defineProps<{ controller: AdminConsole }>()
const s = props.controller.state
</script>
<template>
  <section class="admin-card">
    <div class="card-title">
      <div>
        <h2>任务队列</h2>
        <p>就绪任务来自消息队列；执行、保留和延迟任务来自 Worker 观测。</p>
      </div>
      <span class="badge">每 10 秒更新</span>
    </div>
    <AdminNotice :resource="s.queues" />
    <div v-if="s.queues.data" class="table-wrap">
      <table>
        <thead>
          <tr>
            <th>业务队列</th>
            <th>就绪</th>
            <th>执行中</th>
            <th>已取走</th>
            <th>延迟重试</th>
            <th>异常记录</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="(q, name) in s.queues.data.queues" :key="name">
            <td>
              <b>{{ queueNames[name] || name }}</b
              ><small class="block">{{ name }}</small>
            </td>
            <td>{{ q.ready }}</td>
            <td>{{ q.active }}</td>
            <td>{{ q.reserved }}</td>
            <td>{{ q.delayed }}</td>
            <td :class="{ danger: q.abnormal > 0 }">{{ q.abnormal }}</td>
          </tr>
        </tbody>
      </table>
    </div>
    <p class="updated">
      本地行情手动同步与固定指数任务共用 fixed_indices
      队列。异常记录包括持久化失败任务；历史补拉仅统计最近一小时。
    </p>
  </section>
  <section class="admin-card">
    <div class="card-title">
      <div>
        <h2>消费者响应</h2>
        <p>按队列检查是否观测到在线 Worker，不把未观测到响应直接解释为部署故障。</p>
      </div>
    </div>
    <div v-if="s.queues.data" class="worker-grid">
      <article v-for="(online, name) in s.queues.data.workers" :key="name" class="service">
        <span class="status-dot" :class="{ online }" />
        <h3>{{ queueNames[name] || name }}</h3>
        <p>{{ online ? '发现在线消费者' : '未发现在线消费者' }}</p>
        <small>{{ name }}</small>
      </article>
    </div>
    <p class="notice">
      未发现消费者可能是未部署、暂时离线或检查超时。请结合队列积压及容器运行状态判断。
    </p>
  </section>
</template>
