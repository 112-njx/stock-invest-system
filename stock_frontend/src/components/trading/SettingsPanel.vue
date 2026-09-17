<script setup lang="ts">
/**
 * I 区 · 通用设置与开发者信息（第二层市场页）：
 * - 上部：用户 Cell（头像 + 用户名+箭头 / 免费用户），点击弹出下拉菜单（退出登录）
 * - 中间：显示风格设置（暗黑/明亮）
 * - 下方：开发者信息
 * 优化1：删除顶部 AppBar 的退出按钮和用户信息，统一收归 I 区用户 Cell 下拉菜单。
 */
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { changeEmailApi, changePasswordApi } from '@/api/auth'
import BaseButton from '@/components/base/BaseButton.vue'
import BaseInput from '@/components/base/BaseInput.vue'
import { useThemeStore } from '@/stores/theme'
import { useUserStore } from '@/stores/user'
import { toast } from '@/utils/toast'

const router = useRouter()
const theme = useThemeStore()
const user = useUserStore()

const menuOpen = ref(false)
const cellRef = ref<HTMLElement | null>(null)
const menuPos = ref({ top: 0, left: 0, width: 0 })

// ---- G33：账号安全（改密 / 改邮箱）区块 ----
// 仅新增本区块，不改动上方用户 Cell / 显示风格 / 开发者信息结构。
type SecurityDialog = 'password' | 'email' | null

const securityDialog = ref<SecurityDialog>(null)
const secLoading = ref(false)
const secErrors = ref<Record<string, string>>({})
// 改密表单
const oldPassword = ref('')
const newPassword = ref('')
const confirmPassword = ref('')
// 改邮箱表单
const emailPassword = ref('')
const newEmail = ref('')

function openSecurity(dialog: Exclude<SecurityDialog, null>) {
  securityDialog.value = dialog
  secErrors.value = {}
  oldPassword.value = ''
  newPassword.value = ''
  confirmPassword.value = ''
  emailPassword.value = ''
  newEmail.value = ''
}

function closeSecurity() {
  if (secLoading.value) return
  securityDialog.value = null
}

async function submitPassword() {
  const e: Record<string, string> = {}
  if (!oldPassword.value) e.oldPassword = '请输入当前密码'
  if (!newPassword.value) e.newPassword = '请输入新密码'
  else if (newPassword.value.length < 6) e.newPassword = '密码至少 6 位'
  if (newPassword.value !== confirmPassword.value) e.confirmPassword = '两次密码不一致'
  if (newPassword.value && newPassword.value === oldPassword.value) e.newPassword = '新密码不能与当前密码相同'
  secErrors.value = e
  if (Object.keys(e).length > 0) return

  secLoading.value = true
  try {
    await changePasswordApi(oldPassword.value, newPassword.value)
    toast.success('密码修改成功，请重新登录')
    securityDialog.value = null
    // 后端已吊销全部会话 → 清本地状态回登录页
    user.clearAuth()
    router.push({ name: 'login' })
  } catch {
    // 错误提示由 axios 拦截器统一 toast，此处静默
  } finally {
    secLoading.value = false
  }
}

async function submitEmail() {
  const e: Record<string, string> = {}
  if (!emailPassword.value) e.emailPassword = '请输入当前密码'
  const mail = newEmail.value.trim()
  if (!mail) e.newEmail = '请输入新邮箱'
  else if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(mail)) e.newEmail = '邮箱格式不正确'
  secErrors.value = e
  if (Object.keys(e).length > 0) return

  secLoading.value = true
  try {
    await changeEmailApi(emailPassword.value, mail)
    toast.success('邮箱已更新，请查收验证邮件')
    securityDialog.value = null
    await user.fetchMe().catch(() => {})
  } catch {
    // 错误提示由 axios 拦截器统一 toast，此处静默
  } finally {
    secLoading.value = false
  }
}

onMounted(() => {
  if (!user.user && user.token) user.fetchMe().catch(() => {})
  document.addEventListener('click', onDocClick)
})
onBeforeUnmount(() => {
  document.removeEventListener('click', onDocClick)
})

function onDocClick(e: MouseEvent) {
  if (menuOpen.value && cellRef.value && !cellRef.value.contains(e.target as Node)) {
    menuOpen.value = false
  }
}

function toggleMenu() {
  if (cellRef.value) {
    const rect = cellRef.value.getBoundingClientRect()
    menuPos.value = { top: rect.bottom + 4, left: rect.left, width: rect.width }
  }
  menuOpen.value = !menuOpen.value
}

async function onLogout() {
  menuOpen.value = false
  await user.logout() // G19：调后端吊销会话 + 清 Cookie + 清本地状态
  toast.info('已退出登录')
  router.push({ name: 'login' })
}

const menuStyle = computed(() => ({
  top: `${menuPos.value.top}px`,
  left: `${menuPos.value.left}px`,
  width: `${menuPos.value.width}px`,
}))
</script>

<template>
  <div class="settings-panel">
    <!-- 用户 Cell（优化1：移动端设置项 Cell 样式） -->
    <div class="user-cell" ref="cellRef">
      <button class="user-cell__btn" @click="toggleMenu">
        <span class="user-cell__avatar">{{ user.avatarText }}</span>
        <div class="user-cell__meta">
          <div class="user-cell__name-row">
            <span class="user-cell__name">{{ user.displayName || '未登录' }}</span>
            <span class="user-cell__arrow">›</span>
          </div>
          <span class="user-cell__sub">免费用户</span>
        </div>
      </button>

      <!-- 下拉菜单 Popover -->
      <Teleport to="body">
        <div v-if="menuOpen" class="user-menu" :style="menuStyle">
          <div class="user-menu__item" @click="onLogout">
            <svg class="user-menu__icon" viewBox="0 0 16 16" width="16" height="16" fill="none" stroke="currentColor" stroke-width="1.3" stroke-linecap="round" stroke-linejoin="round">
              <!-- 开口朝右的方框轮廓（C形） -->
              <path d="M6 3 H3 a1 1 0 0 0 -1 1 V12 a1 1 0 0 0 1 1 H6" />
              <!-- 箭头从方框内部向右穿出 -->
              <path d="M10 8 L2 8" />
              <path d="M7 5 L10 8 L7 11" />
            </svg>
            <span>退出登录</span>
          </div>
        </div>
      </Teleport>
    </div>

    <div class="settings-block">
      <span class="settings-block__label">显示风格</span>
      <!-- 优化3：iOS风格圆形滑块开关 -->
      <button
        class="theme-switch"
        :class="{ 'is-light': theme.mode === 'light' }"
        role="switch"
        :aria-checked="theme.mode === 'light'"
        :title="theme.mode === 'dark' ? '切换到明亮模式' : '切换到暗黑模式'"
        @click="theme.toggle()"
      >
        <span class="theme-switch__thumb">{{ theme.mode === 'dark' ? '🌙' : '☀' }}</span>
      </button>
    </div>

    <!-- G33：账号安全区块（改密 / 改邮箱），仅新增，不改上方结构 -->
    <div class="settings-block settings-block--col">
      <span class="settings-block__label">账号安全</span>
      <div class="security-rows">
        <button class="security-row" @click="openSecurity('password')">
          <span class="security-row__text">修改密码</span>
          <span class="security-row__arrow">›</span>
        </button>
        <button class="security-row" @click="openSecurity('email')">
          <span class="security-row__text">修改邮箱</span>
          <span class="security-row__arrow">›</span>
        </button>
      </div>
      <span class="security-note">
        当前邮箱：{{ user.user?.email || '未绑定' }}
        <template v-if="user.user?.email && !user.user?.email_verified">（未验证）</template>
      </span>
    </div>

    <div class="settings-dev">
      <span class="settings-dev__text">本软件由 Xhope(发誓不做夜猫子)全程开发</span>
    </div>

    <!-- G33：改密 / 改邮箱弹窗 -->
    <Teleport to="body">
      <div v-if="securityDialog" class="sec-mask" @click.self="closeSecurity">
        <div class="sec-dialog">
          <h3 class="sec-dialog__title">
            {{ securityDialog === 'password' ? '修改密码' : '修改邮箱' }}
          </h3>

          <form
            v-if="securityDialog === 'password'"
            class="sec-dialog__form"
            @submit.prevent="submitPassword"
          >
            <BaseInput
              v-model="oldPassword"
              label="当前密码"
              type="password"
              placeholder="请输入当前密码"
              :error="secErrors.oldPassword"
              autocomplete="current-password"
            />
            <BaseInput
              v-model="newPassword"
              label="新密码"
              type="password"
              placeholder="请输入新密码（至少 6 位）"
              :error="secErrors.newPassword"
              autocomplete="new-password"
            />
            <BaseInput
              v-model="confirmPassword"
              label="确认新密码"
              type="password"
              placeholder="请再次输入新密码"
              :error="secErrors.confirmPassword"
              autocomplete="new-password"
            />
            <p class="sec-dialog__hint">修改成功后所有设备将退出登录，需用新密码重新登录。</p>
            <div class="sec-dialog__actions">
              <BaseButton type="button" variant="ghost" @click="closeSecurity">取消</BaseButton>
              <BaseButton type="submit" variant="primary" :loading="secLoading">确认修改</BaseButton>
            </div>
          </form>

          <form v-else class="sec-dialog__form" @submit.prevent="submitEmail">
            <BaseInput
              v-model="emailPassword"
              label="当前密码"
              type="password"
              placeholder="请输入当前密码"
              :error="secErrors.emailPassword"
              autocomplete="current-password"
            />
            <BaseInput
              v-model="newEmail"
              label="新邮箱"
              placeholder="请输入新邮箱"
              :error="secErrors.newEmail"
              autocomplete="email"
            />
            <p class="sec-dialog__hint">新邮箱需重新验证，我们将向新邮箱发送验证链接。</p>
            <div class="sec-dialog__actions">
              <BaseButton type="button" variant="ghost" @click="closeSecurity">取消</BaseButton>
              <BaseButton type="submit" variant="primary" :loading="secLoading">确认修改</BaseButton>
            </div>
          </form>
        </div>
      </div>
    </Teleport>
  </div>
</template>

<style scoped>
.settings-panel {
  display: flex;
  flex-direction: column;
  gap: 10px;
  height: 100%;
  min-height: 0;
  padding: 10px;
  background: var(--bg-panel);
  border: 1px solid var(--border);
  border-radius: 6px;
  overflow: hidden;
  position: relative;
}

/* 用户 Cell（优化1：移动端设置项 Cell 样式） */
.user-cell {
  position: relative;
}
.user-cell__btn {
  display: flex;
  align-items: center;
  gap: 10px;
  width: 100%;
  padding: 6px 4px 10px;
  border-bottom: 1px solid var(--border);
  text-align: left;
  cursor: pointer;
  transition: background-color 0.15s;
  border-radius: 4px;
}
.user-cell__btn:hover {
  background: var(--bg-hover);
}
.user-cell__avatar {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 40px;
  height: 40px;
  border-radius: 50%;
  background: var(--accent);
  color: #fff;
  font-size: 17px;
  font-weight: 600;
  flex: none;
}
.user-cell__meta {
  display: flex;
  flex-direction: column;
  min-width: 0;
  flex: 1;
}
.user-cell__name-row {
  display: flex;
  align-items: center;
  gap: 4px;
}
.user-cell__name {
  font-size: 14px;
  font-weight: 400;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.user-cell__arrow {
  font-size: 16px;
  color: var(--text-muted);
  line-height: 1;
  flex: none;
}
.user-cell__sub {
  font-size: 11px;
  color: var(--text-muted);
  margin-top: 2px;
}

/* 下拉菜单 Popover */
.user-menu {
  position: fixed;
  z-index: 1000;
  background: var(--bg-panel);
  border: 1px solid var(--border-strong);
  border-radius: 8px;
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.25);
  padding: 4px;
  min-width: 160px;
}
.user-menu__item {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 8px 10px;
  font-size: 13px;
  color: var(--text);
  border-radius: 5px;
  cursor: pointer;
  transition: background-color 0.15s;
}
.user-menu__item:hover {
  background: var(--bg-hover);
}
.user-menu__icon {
  flex: none;
  color: var(--text-secondary);
}

.settings-block {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  padding: 2px 4px;
}
.settings-block__label {
  font-size: 13px;
  color: var(--text-secondary);
  flex: none;
}

/* 优化3：iOS风格主题开关 */
.theme-switch {
  position: relative;
  flex: none;
  width: 46px;
  height: 26px;
  border-radius: 13px;
  background: var(--bg-panel-2);
  border: 1px solid var(--border-strong);
  cursor: pointer;
  transition: background-color 0.25s ease;
  padding: 0;
}
.theme-switch.is-light {
  background: var(--bg-hover);
  border-color: var(--border-strong);
}
.theme-switch__thumb {
  position: absolute;
  top: 2px;
  left: 2px;
  width: 20px;
  height: 20px;
  border-radius: 50%;
  background: #fff;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 12px;
  line-height: 1;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.25);
  transition: transform 0.25s cubic-bezier(0.4, 0, 0.2, 1);
}
.theme-switch.is-light .theme-switch__thumb {
  transform: translateX(20px);
}
.settings-dev {
  margin-top: auto;
  padding: 6px 4px 2px;
  border-top: 1px solid var(--border);
}
.settings-dev__text {
  font-size: 11px;
  color: var(--text-muted);
  line-height: 1.6;
}

/* G33：账号安全区块 */
.settings-block--col {
  flex-direction: column;
  align-items: stretch;
  gap: 6px;
}
.security-rows {
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.security-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  width: 100%;
  padding: 7px 6px;
  border-radius: 4px;
  font-size: 13px;
  color: var(--text);
  text-align: left;
  cursor: pointer;
  transition: background-color 0.15s;
}
.security-row:hover {
  background: var(--bg-hover);
}
.security-row__arrow {
  font-size: 16px;
  color: var(--text-muted);
  line-height: 1;
}
.security-note {
  font-size: 11px;
  color: var(--text-muted);
  padding: 0 6px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

/* G33：改密/改邮箱弹窗 */
.sec-mask {
  position: fixed;
  inset: 0;
  z-index: 2000;
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgba(0, 0, 0, 0.5);
}
.sec-dialog {
  width: 360px;
  max-width: calc(100vw - 32px);
  padding: 22px 22px 18px;
  background: var(--bg-panel);
  border: 1px solid var(--border-strong);
  border-radius: 8px;
  box-shadow: 0 12px 32px rgba(0, 0, 0, 0.35);
}
.sec-dialog__title {
  font-size: 15px;
  font-weight: 600;
  margin-bottom: 16px;
}
.sec-dialog__form {
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.sec-dialog__hint {
  font-size: 12px;
  color: var(--text-muted);
  line-height: 1.5;
}
.sec-dialog__actions {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  margin-top: 4px;
}
</style>
