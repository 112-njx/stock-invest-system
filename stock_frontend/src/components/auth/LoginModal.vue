<script setup lang="ts">
/**
 * G35（方案 B）· 登录/注册弹窗：
 * 与独立登录页（LoginView）共用 AuthForm，机制增量（G33 邮箱必填 / G03 协议勾选 /
 * G18 账户恢复）随组件一并复用。
 *
 * 登录成功后**关闭弹窗、不跳转**，当前页用户态自动刷新：
 * - user store 已由 AuthForm 写入（App.vue 的 token watch 会初始化通知中心）
 * - E/D 区关注列表 watch 了 user.token，会自动重新拉取
 * - AI 页 watch 了 user.token，会自动重新拉取会话/策略/Agent 列表
 */
import { onBeforeUnmount, onMounted } from 'vue'
import AuthForm from '@/components/auth/AuthForm.vue'
import { useAuthModalStore } from '@/stores/authModal'
import { toast } from '@/utils/toast'

const modal = useAuthModalStore()

function onSuccess() {
  modal.hide()
  toast.success('登录成功')
}

function onKeydown(e: KeyboardEvent) {
  if (e.key === 'Escape') modal.hide()
}

onMounted(() => document.addEventListener('keydown', onKeydown))
onBeforeUnmount(() => document.removeEventListener('keydown', onKeydown))
</script>

<template>
  <Teleport to="body">
    <div v-if="modal.open" class="login-mask" @click.self="modal.hide()">
      <div class="login-modal" role="dialog" aria-modal="true" aria-label="登录或注册">
        <button class="login-modal__close" title="关闭" @click="modal.hide()">×</button>
        <!-- v-if 保证每次打开都重新挂载，初始 Tab 生效且表单状态干净 -->
        <AuthForm :initial-tab="modal.tab" @success="onSuccess" />
      </div>
    </div>
  </Teleport>
</template>

<style scoped>
.login-mask {
  position: fixed;
  inset: 0;
  z-index: 1500;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 16px;
  background: rgba(0, 0, 0, 0.55);
}
.login-modal {
  position: relative;
  width: 400px;
  max-width: 100%;
  max-height: calc(100vh - 32px);
  overflow-y: auto;
  padding: 26px 28px 24px;
  background: var(--bg-panel);
  border: 1px solid var(--border-strong);
  border-radius: 12px;
  box-shadow: 0 16px 48px rgba(0, 0, 0, 0.45);
}
.login-modal__close {
  position: absolute;
  top: 10px;
  right: 12px;
  width: 26px;
  height: 26px;
  font-size: 18px;
  line-height: 1;
  color: var(--text-muted);
  border-radius: 4px;
}
.login-modal__close:hover {
  background: var(--bg-hover);
  color: var(--text);
}
</style>
