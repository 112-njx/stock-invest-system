<script setup lang="ts">
/**
 * G33 · 邮箱验证结果页（P0-4b）
 * 邮件中的验证链接指向 /verify-email?token=xxx，进入本页即调
 * GET /auth/verify-email 完成验证，展示成功/失败态。
 */
import { onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { verifyEmailApi } from '@/api/auth'
import BaseButton from '@/components/base/BaseButton.vue'

const route = useRoute()
const router = useRouter()

const status = ref<'loading' | 'success' | 'error'>('loading')
const message = ref('')

onMounted(async () => {
  const token = (route.query.token as string) || ''
  if (!token) {
    status.value = 'error'
    message.value = '链接无效：缺少验证令牌。'
    return
  }
  try {
    const data = await verifyEmailApi(token)
    status.value = 'success'
    message.value = data.message || '邮箱验证成功'
  } catch (e: unknown) {
    status.value = 'error'
    message.value = '验证链接无效或已过期，请重新登录后在个人设置中重新发送验证邮件。'
    void e
  }
})
</script>

<template>
  <div class="auth-page">
    <div class="auth-card">
      <div class="brand">
        <div class="brand__logo">K</div>
        <h1 class="brand__title">邮箱验证</h1>
      </div>

      <div class="status">
        <template v-if="status === 'loading'">
          <div class="status__icon status__icon--spin">◌</div>
          <p class="status__text">正在验证…</p>
        </template>
        <template v-else-if="status === 'success'">
          <div class="status__icon status__icon--ok">✓</div>
          <p class="status__text">{{ message }}</p>
        </template>
        <template v-else>
          <div class="status__icon status__icon--err">!</div>
          <p class="status__text">{{ message }}</p>
        </template>
      </div>

      <div class="footer">
        <BaseButton block @click="router.push({ name: 'login' })">前往登录</BaseButton>
      </div>
    </div>
  </div>
</template>

<style scoped>
.auth-page {
  display: flex;
  align-items: center;
  justify-content: center;
  flex: 1;
  height: 100%;
  background: var(--bg);
}
.auth-card {
  width: 380px;
  padding: 36px 36px 28px;
  background: var(--bg-panel);
  border: 1px solid var(--border);
  border-radius: 8px;
  box-shadow: var(--shadow);
}
.brand {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 6px;
  margin-bottom: 24px;
}
.brand__logo {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 44px;
  height: 44px;
  border-radius: 10px;
  background: var(--accent);
  color: #fff;
  font-size: 22px;
  font-weight: 700;
}
.brand__title {
  font-size: 18px;
  font-weight: 600;
}
.status {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 10px;
  text-align: center;
  min-height: 96px;
  justify-content: center;
}
.status__icon {
  font-size: 34px;
  line-height: 1;
}
.status__icon--ok {
  color: var(--up, #22c55e);
}
.status__icon--err {
  color: var(--down, #ef4444);
}
.status__icon--spin {
  color: var(--accent);
  animation: spin 1s linear infinite;
}
@keyframes spin {
  to {
    transform: rotate(360deg);
  }
}
.status__text {
  font-size: 14px;
  color: var(--text);
  line-height: 1.6;
}
.footer {
  margin-top: 20px;
  padding-top: 16px;
  border-top: 1px solid var(--border);
}
</style>
