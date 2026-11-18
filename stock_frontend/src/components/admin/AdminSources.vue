<script setup lang="ts">
import { type AdminConsole, providerNames, stateLabel } from '@/composables/useAdminConsole'
import AdminNotice from './AdminNotice.vue'
import AdminErrors from './AdminErrors.vue'
import AdminUpdateDetails from './AdminUpdateDetails.vue'
import AdminIndicators from './AdminIndicators.vue'
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
      <div><h2>一键更新原始数据</h2><p>更新 D 盘 StockDB 数据文件，并恢复本地读取服务</p></div>
      <span class="badge" :class="{ danger: s.update.data?.status === 'failed' }">{{ stateLabel(s.update.data?.status || 'idle') }}</span>
    </div>
    <div class="notice">
      此操作会暂停本地源读取，暂停 RD 和 SDK 读取进程，运行容器内 Linux 更新器下载原始文件，
      按清单校验后生成新的数据版本，再启动服务并检查真实查询。不会创建备份，也不会自动导入项目数据库。
      更新完成后，个股与 ETF 行情直接读取新版本。
    </div>
    <AdminNotice :resource="s.update" />
    <p v-if="s.update.data && !s.update.data.helper_online" class="notice danger">容器更新控制器未连接，请检查 stockdb-local 容器。</p>
    <template v-if="s.update.data">
      <p class="sync-message">{{ s.update.data.message }}</p>
      <progress :value="s.update.data.progress" max="100" />
      <AdminErrors v-if="s.update.data.error" :error="s.update.data.error" />
      <AdminUpdateDetails :task-id="s.update.data.task_id" :running="controller.busyUpdate.value" :details="s.update.data.details" />
      <small v-if="s.update.data.data_version">当前数据版本 {{ s.update.data.data_version }}</small>
    </template>
    <div class="form-actions">
      <button class="primary" :disabled="!s.update.data?.helper_online || controller.busyUpdate.value || (s.update.data.maintenance && !s.update.data.can_retry)" @click="controller.startUpdate">
        {{ controller.busyUpdate.value ? '原始数据更新中…' : s.update.data?.can_retry ? '重试原始数据更新' : '一键更新原始数据' }}
      </button>
      <span class="success" role="status">{{ s.feedback.update }}</span>
      <span class="danger" role="alert">{{ s.saveError.update }}</span>
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
            ><small>本地源缺少数据时允许使用 AkShare 缓存补充。</small>
          </div>
          <input
            v-model="s.policyForm.akshare_enabled"
            type="checkbox"
            @change="policyChanged" /></label
        >
        <label class="switch-row"><div><b>每日 16:30 自动更新 StockDB</b><small>北京时间每天 16:30 运行本地数据更新程序，默认关闭。</small></div><input v-model="s.policyForm.auto_update_enabled" type="checkbox" @change="policyChanged" /></label>
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
  <AdminIndicators />
</template>
