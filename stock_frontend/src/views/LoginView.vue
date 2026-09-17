<script setup lang="ts">
import { ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { restoreAccount } from '@/api/account'
import BaseButton from '@/components/base/BaseButton.vue'
import BaseInput from '@/components/base/BaseInput.vue'
import { useUserStore } from '@/stores/user'
import { toast } from '@/utils/toast'

const route = useRoute()
const router = useRouter()
const userStore = useUserStore()

const tab = ref<'login' | 'register'>('login')
const username = ref('')
const password = ref('')
const confirm = ref('')
const nickname = ref('')
const email = ref('')
const errors = ref<Record<string, string>>({})
const loading = ref(false)

function validate(): boolean {
  const e: Record<string, string> = {}
  const name = username.value.trim()
  if (!name) e.username = '请输入用户名'
  else if (name.length < 3 || name.length > 32) e.username = '用户名长度需在 3~32 之间'
  if (!password.value) e.password = '请输入密码'
  else if (password.value.length < 6) e.password = '密码至少 6 位'
  if (tab.value === 'register') {
    // G23/G33：邮箱必填且需格式合法
    const mail = email.value.trim()
    if (!mail) e.email = '请输入邮箱'
    else if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(mail)) e.email = '邮箱格式不正确'
    if (!nickname.value.trim()) e.nickname = '请输入昵称'
    if (password.value !== confirm.value) e.confirm = '两次密码不一致'
  }
  errors.value = e
  return Object.keys(e).length === 0
}

async function submit() {
  if (loading.value || !validate()) return
  loading.value = true
  try {
    if (tab.value === 'login') {
      await userStore.login(username.value.trim(), password.value)
    } else {
      // 注册成功即自动登录（后端注册签发 JWT，并发送验证邮件）
      await userStore.register(
        username.value.trim(),
        password.value,
        email.value.trim(),
        nickname.value.trim(),
      )
    }
    const redirect = (route.query.redirect as string) || '/market'
    router.push(redirect)
  } catch {
    // 错误提示已由 axios 拦截器统一 toast，此处静默
  } finally {
    loading.value = false
  }
}

function goForgot() {
  router.push({ name: 'forgot-password' })
}

// ---- G18：账户恢复（注销后 30 天宽限期内可自助恢复）----
const restoreOpen = ref(false)
const restorePassword = ref('')
const restoreError = ref('')
const restoreLoading = ref(false)

function openRestore() {
  restoreOpen.value = true
  restorePassword.value = ''
  restoreError.value = ''
}

function closeRestore() {
  if (restoreLoading.value) return
  restoreOpen.value = false
}

async function submitRestore() {
  const name = username.value.trim()
  if (!name) {
    restoreError.value = '请输入用户名'
    return
  }
  if (!restorePassword.value) {
    restoreError.value = '请输入密码'
    return
  }
  restoreError.value = ''
  restoreLoading.value = true
  try {
    const data = await restoreAccount(name, restorePassword.value)
    userStore.token = data.token
    await userStore.fetchMe().catch(() => {})
    toast.success('账户已恢复')
    restoreOpen.value = false
    router.push((route.query.redirect as string) || '/market')
  } catch {
    // 错误提示由 axios 拦截器统一 toast
  } finally {
    restoreLoading.value = false
  }
}
</script>

<template>
  <div class="login-page">
    <div class="login-card">
      <div class="brand">
        <div class="brand__logo">K</div>
        <h1 class="brand__title">量化交易终端</h1>
        <p class="brand__sub">行情 · 策略 · AI Agent</p>
      </div>

      <div class="tabs" role="tablist">
        <button
          :class="['tab', { active: tab === 'login' }]"
          @click="tab = 'login'"
        >
          登录
        </button>
        <button
          :class="['tab', { active: tab === 'register' }]"
          @click="tab = 'register'"
        >
          注册
        </button>
      </div>

      <form class="form" @submit.prevent="submit">
        <BaseInput
          v-model="username"
          label="用户名"
          placeholder="请输入用户名"
          :error="errors.username"
          autocomplete="username"
        />
        <BaseInput
          v-model="password"
          label="密码"
          type="password"
          placeholder="请输入密码"
          :error="errors.password"
          autocomplete="current-password"
        />

        <template v-if="tab === 'register'">
          <BaseInput
            v-model="confirm"
            label="确认密码"
            type="password"
            placeholder="请再次输入密码"
            :error="errors.confirm"
            autocomplete="new-password"
          />
          <BaseInput
            v-model="email"
            label="邮箱"
            placeholder="用于账号验证与密码找回"
            :error="errors.email"
            autocomplete="email"
          />
          <BaseInput
            v-model="nickname"
            label="昵称"
            placeholder="请输入昵称（展示用）"
            :error="errors.nickname"
            autocomplete="nickname"
            :maxlength="64"
          />
          <p class="form__hint">注册后将向该邮箱发送验证链接（10 分钟内有效）。</p>
        </template>

        <!-- G33：忘记密码入口 / G18：账户恢复入口（仅登录态展示） -->
        <div v-if="tab === 'login'" class="form__aux">
          <button type="button" class="link" @click="goForgot">忘记密码？</button>
          <span class="divider">·</span>
          <button type="button" class="link" @click="openRestore">恢复账户</button>
        </div>

        <BaseButton type="submit" block size="lg" :loading="loading" class="submit">
          {{ tab === 'login' ? '登 录' : '注册并登录' }}
        </BaseButton>
      </form>
    </div>

    <!-- G18：账户恢复弹窗（注销后 30 天宽限期内） -->
    <Teleport to="body">
      <div v-if="restoreOpen" class="restore-mask" @click.self="closeRestore">
        <div class="restore-dialog">
          <h3 class="restore-dialog__title">恢复账户</h3>
          <p class="restore-dialog__hint">
            若您的账户在 30 天内被注销，可用原用户名与密码恢复。逾期数据已永久删除，无法恢复。
          </p>
          <BaseInput
            v-model="username"
            label="用户名"
            placeholder="请输入原用户名"
            autocomplete="username"
          />
          <BaseInput
            v-model="restorePassword"
            label="密码"
            type="password"
            placeholder="请输入原密码"
            :error="restoreError"
            autocomplete="current-password"
          />
          <div class="restore-dialog__actions">
            <BaseButton type="button" variant="ghost" @click="closeRestore">取消</BaseButton>
            <BaseButton type="button" :loading="restoreLoading" @click="submitRestore">确认恢复</BaseButton>
          </div>
        </div>
      </div>
    </Teleport>
  </div>
</template>

<style scoped>
.login-page {
  display: flex;
  align-items: center;
  justify-content: center;
  flex: 1;
  height: 100%;
  background: var(--bg);
}
.login-card {
  width: 380px;
  padding: 36px 36px 32px;
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
}
.tabs {
  display: grid;
  grid-template-columns: 1fr 1fr;
  margin-bottom: 20px;
  border-bottom: 1px solid var(--border);
}
.tab {
  padding: 10px 0;
  font-size: 14px;
  color: var(--text-secondary);
  border-bottom: 2px solid transparent;
  margin-bottom: -1px;
  transition:
    color 0.15s,
    border-color 0.15s;
}
.tab:hover {
  color: var(--text);
}
.tab.active {
  color: var(--text);
  border-bottom-color: var(--accent);
  font-weight: 600;
}
.form {
  display: flex;
  flex-direction: column;
  gap: 14px;
}
.submit {
  margin-top: 6px;
}
.form__hint {
  font-size: 12px;
  color: var(--text-muted);
  line-height: 1.5;
}
.form__aux {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 6px;
  margin-top: -4px;
}
.divider {
  font-size: 12px;
  color: var(--text-muted);
}
.link {
  font-size: 13px;
  color: var(--accent);
  cursor: pointer;
}
.link:hover {
  text-decoration: underline;
}

/* G18：账户恢复弹窗 */
.restore-mask {
  position: fixed;
  inset: 0;
  z-index: 2000;
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgba(0, 0, 0, 0.5);
}
.restore-dialog {
  width: 360px;
  max-width: calc(100vw - 32px);
  padding: 22px 22px 18px;
  background: var(--bg-panel);
  border: 1px solid var(--border-strong);
  border-radius: 8px;
  box-shadow: 0 12px 32px rgba(0, 0, 0, 0.35);
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.restore-dialog__title {
  font-size: 15px;
  font-weight: 600;
}
.restore-dialog__hint {
  font-size: 12px;
  line-height: 1.6;
  color: var(--text-muted);
}
.restore-dialog__actions {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  margin-top: 4px;
}
</style>
