<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { adminApi } from '@/api/admin'
const enabled = ref(false)
const loaded = ref(false)
const saving = ref(false)
const error = ref('')
const feedback = ref('')
async function load() {
  try {
    const value = await adminApi.indicatorSettings()
    enabled.value = value.pandas_enabled
    loaded.value = true
    error.value = ''
  } catch { error.value = '指标设置读取失败，请重试' }
}
onMounted(load)
async function save() {
  saving.value = true
  error.value = feedback.value = ''
  try {
    const value = await adminApi.saveIndicatorSettings({ pandas_enabled: enabled.value })
    enabled.value = value.pandas_enabled
    feedback.value = '已保存，在线图表将重新加载指标'
  } catch { error.value = '保存失败，当前修改尚未生效' }
  finally { saving.value = false }
}
</script>
<template>
  <section class="admin-card">
    <div class="card-title"><h2>技术指标计算</h2><span class="badge">默认 SDK</span></div>
    <form @submit.prevent="save">
      <fieldset :disabled="!loaded || saving">
        <label class="switch-row"><div><b>使用项目 pandas 计算技术指标</b><small>默认关闭，使用本地 StockDB SDK 引擎。开启后 MACD、KDJ 和成交量均线使用 pandas；主图价格 MA 始终使用 SDK。</small></div><input v-model="enabled" aria-label="使用项目 pandas 计算技术指标" type="checkbox" @change="feedback = ''" /></label>
      </fieldset>
      <p>指标始终使用图表同一份前复权 K 线；SDK 失败时不自动切换计算方式。</p>
      <p v-if="error" class="danger" role="alert">{{ error }}</p>
      <p v-if="feedback" class="success" role="status">{{ feedback }}</p>
      <button v-if="!loaded" type="button" @click="load">重新读取</button>
      <button class="primary" :disabled="!loaded || saving">{{ saving ? '保存中…' : '保存指标计算设置' }}</button>
    </form>
  </section>
</template>
