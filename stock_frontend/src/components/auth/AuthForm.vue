<script setup lang="ts">
/**
 * G35 · 登录/注册表单（共享组件）：
 * 独立登录页（LoginView）与登录弹窗（LoginModal）复用同一份表单与校验逻辑，
 * 避免两处实现漂移。机制类需求按既有泳道增量保留：
 * - G33：注册邮箱必填 + 格式校验；登录态「忘记密码？」入口
 * - G03：注册协议勾选（默认不勾选，未勾选不能提交）
 * - G18：注销后 30 天内「恢复账户」入口
 * - 规格书 §3.2：「使用 QQ 邮箱登录」按钮（V0.3 仅视觉就位，点击提示接入中）
 */
import { computed, ref } from 'vue'
import { useRouter } from 'vue-router'
import { restoreAccount } from '@/api/account'
import BaseButton from '@/components/base/BaseButton.vue'
import BaseInput from '@/components/base/BaseInput.vue'
import { useUserStore } from '@/stores/user'
import { toast } from '@/utils/toast'

const props = withDefaults(
  defineProps<{
    /** 初始 Tab（登录页默认 login，注册视角可传 register） */
    initialTab?: 'login' | 'register'
  }>(),
  { initialTab: 'login' }
)

const emit = defineEmits<{
  /** 登录/注册成功（父级决定跳转或关闭弹窗并刷新用户态） */
  (e: 'success'): void
}>()

const router = useRouter()
const userStore = useUserStore()

const tab = ref<'login' | 'register'>(props.initialTab)
const username = ref('')
const password = ref('')
const confirm = ref('')
const nickname = ref('')
const email = ref('')
const agreed = ref(false) // G03：注册协议勾选（默认不勾选）
const errors = ref<Record<string, string>>({})
const loading = ref(false)

/** 注册态主标题（规格书 §3.1） */
const title = computed(() => (tab.value === 'login' ? '欢迎回来' : '创建你的账户'))
const subtitle = computed(() =>
  tab.value === 'login' ? '登录后可同步关注、策略与 AI 记忆' : '数分钟内开始追踪你的收益'
)

function switchTab(next: 'login' | 'register') {
  if (tab.value === next) return
  tab.value = next
  errors.value = {}
}

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
    // G03：未勾选协议不能注册
    if (!agreed.value) e.agreed = '请先阅读并同意用户协议、隐私政策与免责声明'
  }
  errors.value = e
  return Object.keys(e).length === 0
}

function openLegal(name: 'terms' | 'privacy' | 'disclaimer') {
  const url = router.resolve({ name }).href
  window.open(url, '_blank')
}

function onQqLogin() {
  // 规格书 §3.2：V0.3 无 OAuth 后端，视觉先就位
  toast.info('QQ 邮箱登录接入中')
}

async function submit() {
  if (loading.value || !validate()) return
  loading.value = true
  try {
    if (tab.value === 'login') {
      await userStore.login(username.value.trim(), password.value)
    } else {
      // 注册成功即自动登录（后端注册签发双 token，并发送验证邮件）
      await userStore.register(
        username.value.trim(),
        password.value,
        email.value.trim(),
        nickname.value.trim()
      )
    }
    emit('success')
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
    emit('success')
  } catch {
    // 错误提示由 axios 拦截器统一 toast
  } finally {
    restoreLoading.value = false
  }
}

/** 供父级（登录弹窗）读取：是否有未完成的恢复流程（避免误关弹窗） */
defineExpose({ restoreOpen })
</script>

<template>
  <div class="auth-form">
    <!-- Tab 切换（规格书 §3.1：激活项底部 2px accent 条 + 加粗） -->
    <div class="tabs" role="tablist">
      <button
        class="tab"
        :class="{ active: tab === 'login' }"
        role="tab"
        :aria-selected="tab === 'login'"
        @click="switchTab('login')"
      >
        登录
      </button>
      <button
        class="tab"
        :class="{ active: tab === 'register' }"
        role="tab"
        :aria-selected="tab === 'register'"
        @click="switchTab('register')"
      >
        注册
      </button>
    </div>

    <h2 class="auth-form__title">{{ title }}</h2>
    <p class="auth-form__sub">{{ subtitle }}</p>

    <!-- 规格书 §3.2：QQ 邮箱登录（替代参考图 Google 按钮） -->
    <button type="button" class="qq-btn" @click="onQqLogin">
      <span class="qq-btn__icon" aria-hidden="true">@</span>
      <span>使用 QQ 邮箱登录</span>
    </button>

    <!-- 规格书 §3.3：居中分隔线 -->
    <div class="or"><span>或者继续使用</span></div>

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
          label="邮箱地址"
          placeholder="请输入邮箱"
          :error="errors.email"
          autocomplete="email"
        />
        <BaseInput
          v-model="nickname"
          label="全名"
          placeholder="请输入全名（展示用）"
          :error="errors.nickname"
          autocomplete="nickname"
          :maxlength="64"
        />
        <p class="form__hint">注册后将向该邮箱发送验证链接（10 分钟内有效）。</p>

        <!-- G03：注册协议勾选（默认不勾选，未勾选不能提交） -->
        <label class="agree">
          <input v-model="agreed" type="checkbox" class="agree__box" />
          <span class="agree__text">
            我已阅读并同意
            <button type="button" class="link" @click.prevent="openLegal('terms')">《用户协议》</button>
            <button type="button" class="link" @click.prevent="openLegal('privacy')">《隐私政策》</button>
            <button type="button" class="link" @click.prevent="openLegal('disclaimer')">《免责声明》</button>
          </span>
        </label>
        <span v-if="errors.agreed" class="agree__error">{{ errors.agreed }}</span>
      </template>

      <!-- G33：忘记密码入口 / G18：账户恢复入口（仅登录态展示） -->
      <div v-if="tab === 'login'" class="form__aux">
        <button type="button" class="link" @click="goForgot">忘记密码？</button>
        <span class="divider">·</span>
        <button type="button" class="link" @click="openRestore">恢复账户</button>
      </div>

      <BaseButton type="submit" block size="lg" :loading="loading" class="submit">
        {{ tab === 'login' ? '登 录' : '创建账户' }}
      </BaseButton>
    </form>

    <!-- 规格书 §3.6：底部链接（切换 Tab，不跳页） -->
    <p class="switch-line">
      <template v-if="tab === 'login'">
        还没有账户？<button type="button" class="link" @click="switchTab('register')">注册</button>
      </template>
      <template v-else>
        已经有账户？<button type="button" class="link" @click="switchTab('login')">登录</button>
      </template>
    </p>

    <!-- G18：账户恢复弹窗 -->
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
.auth-form {
  display: flex;
  flex-direction: column;
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
.auth-form__title {
  font-size: 23px;
  font-weight: 600;
  color: var(--text);
}
.auth-form__sub {
  margin-top: 6px;
  margin-bottom: 18px;
  font-size: 13px;
  color: var(--text-muted);
}
/* 规格书 §3.2：通栏 44px 浅底描边按钮 */
.qq-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  width: 100%;
  height: 44px;
  border-radius: 10px;
  font-size: 13px;
  color: var(--text);
  background: rgba(127, 127, 127, 0.1);
  border: 1px solid var(--border-strong);
  transition: background-color 0.15s;
}
.qq-btn:hover {
  background: var(--bg-hover);
}
.qq-btn__icon {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 18px;
  height: 18px;
  border-radius: 50%;
  font-size: 11px;
  font-weight: 700;
  color: #fff;
  background: var(--accent);
}
/* 规格书 §3.3：居中分隔线 */
.or {
  display: flex;
  align-items: center;
  gap: 10px;
  margin: 16px 0 14px;
  font-size: 12px;
  color: var(--text-muted);
}
.or::before,
.or::after {
  content: '';
  flex: 1;
  height: 1px;
  background: var(--border-strong);
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
.switch-line {
  margin-top: 16px;
  text-align: center;
  font-size: 12px;
  color: var(--text-muted);
}

/* G03：注册协议勾选 */
.agree {
  display: flex;
  align-items: flex-start;
  gap: 7px;
  cursor: pointer;
}
.agree__box {
  flex: none;
  margin-top: 2px;
  width: 13px;
  height: 13px;
  accent-color: var(--accent);
  cursor: pointer;
}
.agree__text {
  font-size: 12px;
  line-height: 1.6;
  color: var(--text-secondary);
}
.agree__text .link {
  font-size: 12px;
  padding: 0;
  vertical-align: baseline;
}
.agree__error {
  margin-top: -8px;
  font-size: 11px;
  color: var(--up);
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
