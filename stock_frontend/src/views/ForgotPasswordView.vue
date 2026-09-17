<script setup lang="ts">
/**
 * G33 · 忘记密码页（P0-4b）
 * 输入注册邮箱 → 调 POST /auth/forgot-password → 提示查收邮件。
 * 后端防枚举：无论邮箱是否注册均返回相同成功响应，前端统一展示提示。
 */
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { forgotPasswordApi } from '@/api/auth'
import BaseButton from '@/components/base/BaseButton.vue'
import BaseInput from '@/components/base/BaseInput.vue'

const router = useRouter()

const email = ref('')
const error = ref('')
const loading = ref(false)
const sent = ref(false)

function validate(): boolean {
  const value = email.value.trim()
  if (!value) {
    error.value = '请输入邮箱'
    return false
  }
  if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(value)) {
    error.value = '邮箱格式不正确'
    return false
  }
  error.value = ''
  return true
}

async function submit() {
  if (loading.value || !validate()) return
  loading.value = true
  try {
    await forgotPasswordApi(email.value.trim())
    sent.value = true
  } catch {
    // 错误提示由 axios 拦截器统一 toast，此处静默
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <div class="auth-page">
    <div class="auth-card">
      <div class="brand">
        <div class="brand__logo">K</div>
        <h1 class="brand__title">忘记密码</h1>
        <p class="brand__sub">输入注册邮箱，我们将发送重置链接</p>
      </div>

      <template v-if="!sent">
        <form class="form" @submit.prevent="submit">
          <BaseInput
            v-model="email"
            label="邮箱"
            type="text"
            placeholder="请输入注册时使用的邮箱"
            :error="error"
            autocomplete="email"
          />
          <BaseButton type="submit" block size="lg" :loading="loading" class="submit">
            发送重置邮件
          </BaseButton>
        </form>
      </template>

      <div v-else class="sent">
        <div class="sent__icon">✉</div>
        <p class="sent__text">如果该邮箱已注册，重置密码邮件已发送，请查收邮箱。</p>
        <p class="sent__hint">链接 1 小时内有效。未收到请检查垃圾邮件，或稍后重试。</p>
      </div>

      <div class="footer">
        <button class="link" @click="router.push({ name: 'login' })">返回登录</button>
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
.brand__sub {
  font-size: 12px;
  color: var(--text-muted);
  text-align: center;
}
.form {
  display: flex;
  flex-direction: column;
  gap: 14px;
}
.submit {
  margin-top: 6px;
}
.sent {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
  text-align: center;
}
.sent__icon {
  font-size: 34px;
  color: var(--accent);
  line-height: 1;
}
.sent__text {
  font-size: 14px;
  color: var(--text);
}
.sent__hint {
  font-size: 12px;
  color: var(--text-muted);
}
.footer {
  display: flex;
  justify-content: center;
  margin-top: 20px;
  padding-top: 16px;
  border-top: 1px solid var(--border);
}
.link {
  font-size: 13px;
  color: var(--accent);
  cursor: pointer;
}
.link:hover {
  text-decoration: underline;
}
</style>
