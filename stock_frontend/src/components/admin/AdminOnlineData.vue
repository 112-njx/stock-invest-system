<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { request } from '@/api/http'
const interval = ref(30)
const feedback = ref('')
const busy = ref(false)
onMounted(async () => {
  try {
    interval.value = (
      await request<{ interval_seconds: number }>({ url: '/all-data/status' })
    ).interval_seconds
  } catch {
    feedback.value = '读取在线接口配置失败'
  }
})
async function save() {
  busy.value = true
  try {
    await request({
      method: 'PUT',
      url: '/admin/online-data-policy',
      data: { interval_seconds: interval.value },
    })
    feedback.value = '已保存，对所有用户和标签页立即生效'
  } catch {
    feedback.value = '保存失败，请检查管理员权限及服务状态'
  } finally {
    busy.value = false
  }
}
</script>
<template>
  <section class="admin-card">
    <h2>在线数据接口请求频率</h2>
    <p>所有用户、标签页共享请求间隔，默认 30 秒。配置持久保存，失败请求也计入冷却。</p>
    <label
      >请求间隔（秒） <input v-model.number="interval" type="number" min="30" max="86400"
    /></label>
    <button :disabled="busy" @click="save">{{ busy ? '保存中' : '保存配置' }}</button>
    <p role="status">{{ feedback }}</p>
  </section>
</template>
