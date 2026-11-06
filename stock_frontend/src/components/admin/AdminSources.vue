<script setup lang="ts">
import { type AdminConsole, providerNames, stateLabel } from '@/composables/useAdminConsole'
import AdminNotice from './AdminNotice.vue'
const props = defineProps<{ controller: AdminConsole }>()
const s = props.controller.state
function policyChanged() {
  s.dirty.policy = true
  s.feedback.policy = ''
}
</script>
<template>
  <section class="admin-card">
    <div class="card-title">
      <div>
        <h2>本地数据服务</h2>
        <p>只读检查数据库连接和历史计算服务</p>
      </div>
      <span class="badge">Free-StockDB</span>
    </div>
    <AdminNotice :resource="s.services" />
    <div class="service-grid">
      <article class="service">
        <div class="split">
          <h3>StockDB RD · 7899</h3>
          <span
            class="badge"
            :class="{ danger: s.services.data?.stockdb.state === 'unavailable' }"
            >{{ s.services.data ? stateLabel(s.services.data.stockdb.state) : '等待读取' }}</span
          >
        </div>
        <p>
          采样数据日期 <b>{{ s.services.data?.stockdb.latest_date || '暂无数据' }}</b>
        </p>
        <small>以贵州茅台日 K 为连接采样，不代表全市场覆盖。</small>
      </article>
      <article class="service">
        <div class="split">
          <h3>SDK 查询桥 · 7900</h3>
          <span class="badge" :class="{ danger: s.services.data?.sdk.state === 'unavailable' }">{{
            s.services.data ? stateLabel(s.services.data.sdk.state) : '等待读取'
          }}</span>
        </div>
        <p>用于周月 K 及支持的合成行情计算</p>
        <small>服务在线仅表示连接成功，数据范围以实际标的为准。</small>
      </article>
    </div>
  </section>
  <section class="admin-card">
    <div class="card-title">
      <div>
        <h2>本地行情同步</h2>
        <p>同步 StockDB 行情；AkShare 是否入库由下方独立开关控制</p>
      </div>
      <span class="badge" :class="{ danger: s.sync.data?.status === 'failed' }">{{
        s.sync.data ? stateLabel(s.sync.data.status) : '等待读取'
      }}</span>
    </div>
    <div class="notice">
      先运行本机“数据更新.exe”，等待 stockdb
      更新完成后再同步。此操作同步证券目录、受支持的固定指数和关注标的行情，不负责下载 stockdb
      数据文件。
    </div>
    <AdminNotice :resource="s.sync" />
    <template v-if="s.sync.data"
      ><p class="sync-message">{{ s.sync.data.message }}</p>
      <progress :value="Math.max(0, Math.min(100, s.sync.data.progress))" max="100" />
      <div class="split">
        <small>同步进度</small><b>{{ s.sync.data.progress }}%</b>
      </div>
      <p v-if="s.sync.data.task_id" class="task-id">任务 {{ s.sync.data.task_id }}</p>
      <p v-if="s.sync.data.error" class="notice danger">{{ s.sync.data.error }}</p></template
    >
    <div class="form-actions">
      <button
        class="primary"
        :disabled="!s.sync.data || controller.busySync.value"
        @click="controller.startSync"
      >
        {{ controller.busySync.value ? '同步任务处理中…' : '同步本地行情' }}</button
      ><span class="success" role="status">{{ s.feedback.sync }}</span
      ><span class="danger" role="alert">{{ s.saveError.sync }}</span>
    </div>
  </section>
  <section class="admin-card">
    <div class="card-title">
      <div>
        <h2>数据源策略</h2>
        <p>默认仅使用本地数据，外部补充需显式启用</p>
      </div>
      <span v-if="s.dirty.policy" class="badge warning">有未保存修改</span>
    </div>
    <AdminNotice :resource="s.policy" />
    <form @submit.prevent="controller.save('policy')">
      <fieldset :disabled="!s.policy.data || s.saving.policy">
        <label class="switch-row"
          ><div>
            <b>启用 AkShare 兜底补充</b
            ><small>允许本地源无法满足请求时按策略访问外部数据源。</small>
          </div>
          <input
            v-model="s.policyForm.akshare_enabled"
            type="checkbox"
            @change="policyChanged" /></label
        ><label class="switch-row"
          ><div><b>保留 AkShare 历史 K 线入库</b><small>默认关闭：AkShare 历史行情只缓存，不写入项目数据库。StockDB 历史入库不受影响。</small></div>
          <input
            v-model="s.policyForm.history_storage_enabled"
            type="checkbox"
            @change="policyChanged"
        /></label>
        <label class="switch-row"><div><b>每日 16:30 自动同步</b><small>默认关闭，使用手动同步。此操作不运行数据更新.exe。</small></div><input v-model="s.policyForm.auto_sync_enabled" type="checkbox" @change="policyChanged" /></label>
      </fieldset>
      <div class="form-actions">
        <button class="primary" :disabled="!s.policy.data || s.saving.policy || !s.dirty.policy">
          {{ s.saving.policy ? '保存中…' : '保存数据源策略' }}</button
        ><span class="success" role="status">{{ s.feedback.policy }}</span
        ><span class="danger" role="alert">{{ s.saveError.policy }}</span>
      </div>
    </form>
  </section>
  <section class="admin-card">
    <div class="card-title">
      <div>
        <h2>外部请求保护</h2>
        <p>仅作用于外部行情请求，本地读取不消耗外部预算</p>
      </div>
    </div>
    <p v-if="!s.policy.data?.akshare_enabled" class="notice">
      当前外部补充未启用，请求保护配置暂不用于外部调用。
    </p>
    <AdminNotice :resource="s.traffic" />
    <form v-if="s.policy.data?.akshare_enabled" @submit.prevent="controller.save('limits')">
      <fieldset class="form-grid" :disabled="!s.traffic.data || s.saving.limits">
        <label
          >最小请求间隔（秒）<input
            v-model.number="s.limitsForm.interval_seconds"
            type="number"
            min="1"
            max="60"
            step="1"
            required
            @input="controller.edit('limits')" /></label
        ><label
          >失败重试间隔（秒）<input
            v-model.number="s.limitsForm.retry_interval_seconds"
            type="number"
            min="1"
            max="120"
            step="1"
            required
            @input="controller.edit('limits')" /></label
        ><label
          >单数据源每日预算<input
            v-model.number="s.limitsForm.daily_budget"
            type="number"
            min="100"
            max="100000"
            step="1"
            required
            @input="controller.edit('limits')"
        /></label>
        <label class="switch-row"><div><b>每日 16:30 自动同步</b><small>默认关闭，使用手动同步。此操作不运行数据更新.exe。</small></div><input v-model="s.policyForm.auto_sync_enabled" type="checkbox" @change="policyChanged" /></label>
      </fieldset>
      <div class="form-actions">
        <button class="primary" :disabled="!s.traffic.data || s.saving.limits || !s.dirty.limits">
          {{ s.saving.limits ? '保存中…' : '保存请求保护' }}</button
        ><span v-if="s.dirty.limits" class="warning">有未保存修改</span
        ><span class="success" role="status">{{ s.feedback.limits }}</span
        ><span class="danger" role="alert">{{ s.saveError.limits }}</span>
      </div>
    </form>
    <div v-if="s.traffic.data" class="table-wrap">
      <table>
        <thead>
          <tr>
            <th>数据源</th>
            <th>当前状态</th>
            <th>今日调用尝试</th>
            <th>连续失败</th>
          </tr>
        </thead>
        <tbody>
          <tr
            v-for="p in s.traffic.data.providers.filter((p) => p.name !== 'stockdb')"
            :key="p.name"
          >
            <td>{{ providerNames[p.name] || p.name }}</td>
            <td>
              <span class="badge">{{
                p.health.state === 'closed' && !p.health.last_success_at
                  ? '尚未观测到成功请求'
                  : stateLabel(p.health.state)
              }}</span>
            </td>
            <td>{{ p.used }} / {{ s.traffic.data.daily_budget }}</td>
            <td>{{ p.health.failures }}</td>
          </tr>
        </tbody>
      </table>
    </div>
    <p v-if="s.traffic.data" class="updated">
      统计日 {{ s.traffic.data.day }} · 状态来自 API 进程；不代表所有 Worker
      的实时状态。一次调用尝试可能包含多次 HTTP 请求。
    </p>
  </section>
</template>
