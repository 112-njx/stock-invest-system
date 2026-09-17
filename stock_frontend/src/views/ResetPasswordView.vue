<script setup lang="ts">
/**
 * G33 · 重置密码页（P0-4b）
 * 从 URL query 取 token（邮件链接 /reset-password?token=xxx）→ 输入新密码
 * → POST /auth/reset-password → 成功后吊销全部会话，跳登录页。
 * token 无效/过期由后端返回 400(40012)，前端展示错误态并提供重新申请入口。
 */
import { computed, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { resetPasswordApi } from '@/api/auth'
import BaseButton from '@/components/base/BaseButton.vue'
import BaseInput from '@/components/base/BaseInput.vue'

const route = useRoute()
const router = useRouter()

const token = computed(() => (route.query.token as string) || '')
const password = ref('')
const confirm = ref('')
const errors = ref<Record<string, string>>({})
const loading = ref(false)
const done = ref(false)

function validate(): boolean {
  const e: Record<string, string> = {}
  if (!password.value) e.password = '请输入新密码'
  else if (password.value.length < 6) e.password = '密码至少 6 位'
  if (password.value !== confirm.value) e.confirm = '两次密码不一致'
  errors.value = e
  return Object.keys(e).length === 0
}

async function submit() {
  if (loading.value || !validate()) return
  loading.value = true
  try {
    await resetPasswordApi(token.value, password.value)
    done.value = true
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
        <h1 class="brand__title">重置密码</h1>
        <p class="brand__sub">设置新密码后，所有设备需重新登录</p>
      </div>

      <!-- 缺少 token：邮件链接不完整 -->
      <div v-if="!token" class="notice">
        <p class="notice__text">链接无效：缺少重置令牌。</p>
        <p class="notice__hint">请从邮件中的链接进入，或重新申请重置邮件。</p>
      </div>

      <!-- 重置成功 -->
      <div v-else-if="done" class="notice">
        <div class="notice__icon">✓</div>
        <p class="notice__text">密码重置成功，请使用新密码登录。</p>
      </div>

      <form v-else class="form" @submit.prevent="submit">
        <BaseInput
          v-model="password"
          label="新密码"
          type="password"
          placeholder="请输入新密码（至少 6 位）"
          :error="errors.password"
          autocomplete="new-password"
        />
        <BaseInput
          v-model="confirm"
          label="确认新密码"
          type="password"
          placeholder="请再次输入新密码"
          :error="errors.confirm"
          autocomplete="new-password"
        />
        <BaseButton type="submit" block size="lg" :loading="loading" class="submit">
          确认重置
        </BaseButton>
      </form>

      <div class="footer">
        <button class="link" @click="router.push({ name: 'forgot-password' })">重新申请重置邮件</button>
        <span class="divider">·</span>
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
.notice {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
  text-align: center;
}
.notice__icon {
  font-size: 34px;
  color: var(--accent);
  line-height: 1;
}
.notice__text {
  font-size: 14px;
  color: var(--text);
}
.notice__hint {
  font-size: 12px;
  color: var(--text-muted);
}
.footer {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
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
.divider {
  color: var(--text-muted);
  font-size: 12px;
}
</style>
