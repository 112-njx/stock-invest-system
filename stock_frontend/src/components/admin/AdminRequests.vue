<script setup lang="ts">
import {
  type AdminConsole,
  providerNames,
  queueNames,
  stateLabel,
} from '@/composables/useAdminConsole'
import type { ProviderRequest } from '@/api/admin'
import AdminNotice from './AdminNotice.vue'
const props = defineProps<{ controller: AdminConsole }>()
const s = props.controller.state
function target(item: ProviderRequest) {
  return (
    item.symbol_name ||
    item.symbol ||
    item.symbols
      ?.slice(0, 3)
      .map((s) => s.name || s.code)
      .join('、') ||
    '全市场 / 目录'
  )
}
function time(value: string) {
  return value ? new Date(value).toLocaleString('zh-CN') : '—'
}
</script>
<template>
  <section class="admin-card">
    <div class="card-title">
      <div>
        <h2>当前行情请求</h2>
        <p>展示已接入请求观测的行情任务；空列表不代表本地数据库没有读取活动。</p>
      </div>
      <span class="badge">每 3 秒更新</span>
    </div>
    <AdminNotice :resource="s.requests" />
    <div
      v-if="s.requests.data && !s.requests.data.requests.length && !s.requests.error"
      class="empty-state"
    >
      <span class="empty-symbol">✓</span>
      <h3>当前没有可观测的行情请求</h3>
      <p>新请求出现后会自动更新，切换到后台标签页时暂停刷新。</p>
    </div>
    <div v-if="s.requests.data?.requests.length" class="table-wrap">
      <table>
        <thead>
          <tr>
            <th>标的与范围</th>
            <th>数据源</th>
            <th>业务队列</th>
            <th>状态</th>
            <th>尝试</th>
            <th>详情</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="item in s.requests.data.requests" :key="item.id">
            <td>
              <b>{{ target(item) }}</b
              ><small class="block"
                >{{ item.symbol }} {{ item.period
                }}<template v-if="item.symbol_count">
                  · {{ item.symbol_count }} 个标的</template
                ></small
              >
            </td>
            <td>{{ providerNames[item.provider] || item.provider }}</td>
            <td>{{ queueNames[item.queue] || item.queue }}</td>
            <td>
              <span class="badge">{{ stateLabel(item.phase) }}</span
              ><small v-if="item.retry_after" class="block"
                >重试间隔 {{ item.retry_after }} 秒</small
              >
            </td>
            <td>{{ item.attempt }} / {{ item.attempts }}</td>
            <td>
              <details>
                <summary>查看详情</summary>
                <div class="request-details">
                  <p>
                    接口 <code>{{ item.interface }}</code>
                  </p>
                  <p>范围 {{ item.start || '未指定' }} ～ {{ item.end || '未指定' }}</p>
                  <p>开始 {{ time(item.started_at) }}</p>
                  <p>更新 {{ time(item.updated_at) }}</p>
                  <p class="task-id">任务 {{ item.task_id }}</p>
                </div>
              </details>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  </section>
</template>
