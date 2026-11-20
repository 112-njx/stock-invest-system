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
        <p>查看各队列的积压、执行和消费者状态。</p>
      </div>
      <span class="badge">每 10 秒更新</span>
    </div>
    <AdminNotice :resource="s.queues" />
    <div v-if="s.queues.data" class="table-wrap">
      <table>
        <thead>
          <tr>
            <th>业务队列</th>
            <th>待执行</th>
            <th>执行中</th>
            <th>延迟重试</th>
            <th>消费者</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="(q, name) in s.queues.data.queues" :key="name">
            <td>
              <b>{{ queueNames[name] || name }}</b
              ><small class="block">{{ name }}</small>
            </td>
            <td>{{ q.ready + q.reserved }}</td>
            <td>{{ q.active }}</td>
            <td>{{ q.delayed }}</td>
            <td>
              <span class="status-dot" :class="{ online: s.queues.data.workers[name] }" />
              {{ s.queues.data.workers[name] ? '在线' : '未响应' }}
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  </section>
</template>
