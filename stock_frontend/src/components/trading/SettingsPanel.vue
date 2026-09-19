<script setup lang="ts">
/**
 * I 区 · 通用设置与开发者信息（第二层市场页）：
 * - 上部：用户 Cell（头像 + 用户名+箭头 / 免费用户），点击弹出下拉菜单（退出登录）
 * - 中间：显示风格设置（暗黑/明亮）
 * - 下方：开发者信息
 * 优化1：删除顶部 AppBar 的退出按钮和用户信息，统一收归 I 区用户 Cell 下拉菜单。
 */
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { createExport, deleteAccount, exportDownloadUrl, fetchExportStatus } from '@/api/account'
import type { ExportTaskInfo } from '@/api/account'
import { fetchApiKeyStatus, fetchTokenUsage, saveApiKey } from '@/api/account'
import type { ApiKeyStatus, TokenUsage } from '@/api/account'
import { changeEmailApi, changePasswordApi } from '@/api/auth'
import { fetchAnnouncementHistory } from '@/api/notifications'
import BaseButton from '@/components/base/BaseButton.vue'
import BaseInput from '@/components/base/BaseInput.vue'
import type { Announcement } from '@/api/types'
import { useAuthModalStore } from '@/stores/authModal'
import { useLegalModalStore } from '@/stores/legalModal'
import { useNotificationStore } from '@/stores/notification'
import { useThemeStore } from '@/stores/theme'
import { useUserStore } from '@/stores/user'
import { toast } from '@/utils/toast'

const route = useRoute()
const router = useRouter()
const theme = useThemeStore()
const user = useUserStore()
const notification = useNotificationStore()
const authModal = useAuthModalStore()
const legalModal = useLegalModalStore()

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

// ---- G16：系统公告入口（I 区查看历史公告）----
const annOpen = ref(false)
const annLoading = ref(false)
const annList = ref<Announcement[]>([])

async function openAnnouncements() {
  annOpen.value = true
  annLoading.value = true
  try {
    annList.value = await fetchAnnouncementHistory()
  } catch {
    annList.value = []
  } finally {
    annLoading.value = false
  }
}

function annTimeText(iso: string): string {
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return iso
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`
}

// ---- G17：数据导出（个人设置页「导出我的数据」按钮 + 进度 + 下载链接）----
const exportTask = ref<ExportTaskInfo | null>(null)
const exportLoading = ref(false)
let exportTimer: ReturnType<typeof setInterval> | null = null

function stopExportPolling() {
  if (exportTimer) {
    clearInterval(exportTimer)
    exportTimer = null
  }
}

onBeforeUnmount(stopExportPolling)

async function onExport() {
  if (exportLoading.value) return
  exportLoading.value = true
  try {
    exportTask.value = await createExport()
    toast.info('导出任务已提交，正在打包…')
    startExportPolling()
  } catch {
    // 错误提示由 axios 拦截器统一 toast
  } finally {
    exportLoading.value = false
  }
}

function startExportPolling() {
  stopExportPolling()
  exportTimer = setInterval(async () => {
    const id = exportTask.value?.task_id
    if (!id) return stopExportPolling()
    try {
      const info = await fetchExportStatus(id)
      exportTask.value = info
      if (info.status === 'success' || info.status === 'failed' || info.status === 'expired') {
        stopExportPolling()
        if (info.status === 'success') toast.success('导出完成，可点击下载')
        if (info.status === 'failed') toast.error('导出失败，请稍后重试')
      }
    } catch {
      stopExportPolling()
    }
  }, 2000)
}

function onDownloadExport() {
  const url = exportTask.value?.download_url
  if (!url) return
  window.open(exportDownloadUrl(url), '_blank')
}

function exportSizeText(size: number | null): string {
  if (!size) return ''
  if (size < 1024) return `${size} B`
  if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)} KB`
  return `${(size / 1024 / 1024).toFixed(1)} MB`
}

// ---- G14：AI 模型设置（自填 API Key + 累计 token 用量）----
const apiKeyInput = ref('')
const apiKeyStatus = ref<ApiKeyStatus>({ has_api_key: false, masked: null })
const apiKeyLoading = ref(false)
const apiKeyEditing = ref(false)
const tokenUsage = ref<TokenUsage>({ prompt: 0, completion: 0, total: 0 })

async function loadApiKeyState() {
  try {
    apiKeyStatus.value = await fetchApiKeyStatus()
  } catch {
    /* 未登录或接口异常时保持默认空态，不打断设置页 */
  }
  try {
    const me = await fetchTokenUsage()
    tokenUsage.value = {
      prompt: me.llm_tokens_prompt ?? 0,
      completion: me.llm_tokens_completion ?? 0,
      total: me.llm_tokens_total ?? 0,
    }
  } catch {
    /* 同上 */
  }
}

function startEditApiKey() {
  apiKeyEditing.value = true
  apiKeyInput.value = ''
}

function cancelEditApiKey() {
  apiKeyEditing.value = false
  apiKeyInput.value = ''
}

async function onSaveApiKey() {
  const key = apiKeyInput.value.trim()
  if (!key) {
    toast.error('请输入 API Key')
    return
  }
  if (!key.startsWith('sk-')) {
    toast.error('API Key 格式不正确，应以 sk- 开头')
    return
  }
  apiKeyLoading.value = true
  try {
    apiKeyStatus.value = await saveApiKey(key)
    toast.success('已保存，后续 AI 调用将优先使用你的 Key')
    apiKeyEditing.value = false
    apiKeyInput.value = ''
  } catch (e) {
    toast.error(e instanceof Error ? e.message : '保存失败')
  } finally {
    apiKeyLoading.value = false
  }
}

async function onClearApiKey() {
  apiKeyLoading.value = true
  try {
    apiKeyStatus.value = await saveApiKey('')
    toast.success('已清除，将使用服务端默认 Key')
    apiKeyEditing.value = false
    apiKeyInput.value = ''
  } catch (e) {
    toast.error(e instanceof Error ? e.message : '清除失败')
  } finally {
    apiKeyLoading.value = false
  }
}

/** 累计 token 展示（千分位；估算值，非精确计费） */
function tokenText(n: number): string {
  return n.toLocaleString('zh-CN')
}

// ---- G03：关于本产品（产品定位声明）----
const aboutOpen = ref(false)

function openAbout() {
  aboutOpen.value = true
}
const DANGER_PHRASE = '确认删除我的账户和所有数据'
const dangerOpen = ref(false)
const dangerInput = ref('')
const dangerLoading = ref(false)

function openDanger() {
  dangerOpen.value = false
  dangerInput.value = ''
  dangerOpen.value = true
}

function closeDanger() {
  if (dangerLoading.value) return
  dangerOpen.value = false
  dangerInput.value = ''
}

async function confirmDelete() {
  if (dangerInput.value.trim() !== DANGER_PHRASE) {
    toast.error('请输入指定确认文字')
    return
  }
  dangerLoading.value = true
  try {
    await deleteAccount()
    toast.info('账户已注销，30 天内可恢复')
    dangerOpen.value = false
    notification.clear()
    user.clearAuth()
    router.push({ name: 'login' })
  } catch {
    // 错误提示由 axios 拦截器统一 toast
  } finally {
    dangerLoading.value = false
  }
}

/** G35：从顶部头像菜单「个人设置 / 我的数据」跳转过来时，滚动到对应区块 */
function scrollToHash(hash: string) {
  const id = hash.replace(/^#/, '')
  if (!id) return
  const el = document.getElementById(id)
  if (el) el.scrollIntoView({ behavior: 'smooth', block: 'start' })
}

watch(
  () => route.hash,
  (hash) => scrollToHash(hash)
)

onMounted(() => {
  if (!user.user && user.token) user.fetchMe().catch(() => {})
  document.addEventListener('click', onDocClick)
  // G14：加载 API Key 状态与累计 token 用量（G35：未登录不发鉴权请求，
  // 否则 401 会触发 axios 拦截器的 refresh 失败分支，把免登录访客弹去登录页）
  if (user.token) loadApiKeyState()
  // 跨页跳转（如从 AI 页点「我的数据」）时组件刚挂载，等 DOM 就绪再滚动
  nextTick(() => scrollToHash(route.hash))
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

/** 下拉菜单：打开改密 / 改邮箱弹窗（先收起菜单，避免弹窗关闭后菜单仍残留） */
function pickSecurity(dialog: Exclude<SecurityDialog, null>) {
  menuOpen.value = false
  openSecurity(dialog)
}

/** 下拉菜单：打开系统公告历史（先收起菜单） */
function pickAnnouncements() {
  menuOpen.value = false
  void openAnnouncements()
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
  <div id="settings" class="settings-panel">
    <!-- 用户 Cell（优化1：移动端设置项 Cell 样式） -->
    <div class="user-cell" ref="cellRef">
      <!-- G35：未登录点击直接弹登录框；已登录才展开下拉菜单 -->
      <button class="user-cell__btn" @click="user.token ? toggleMenu() : authModal.show('login')">
        <span class="user-cell__avatar" :class="{ 'user-cell__avatar--guest': !user.token }">
          {{ user.token ? user.avatarText : '👤' }}
        </span>
        <div class="user-cell__meta">
          <div class="user-cell__name-row">
            <span class="user-cell__name">{{ user.displayName || '未登录' }}</span>
            <span class="user-cell__arrow">›</span>
          </div>
          <span class="user-cell__sub">{{ user.token ? '免费用户' : '登录后同步您的数据' }}</span>
        </div>
      </button>

      <!-- 下拉菜单 Popover：退出登录 + 原「账号安全」三入口（改密 / 改邮箱 / 系统公告） -->
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

          <div class="user-menu__sep" />

          <!-- 原「账号安全」模块三入口，保持原上下编排：修改密码 → 修改邮箱 → 系统公告 -->
          <button type="button" class="user-menu__row" @click="pickSecurity('password')">
            <span class="user-menu__row-label">修改密码</span>
            <span class="user-menu__arrow">›</span>
          </button>
          <button type="button" class="user-menu__row" @click="pickSecurity('email')">
            <span class="user-menu__row-label">修改邮箱</span>
            <!-- 邮箱绑定状态移到「修改邮箱」右侧（原面板底部的当前邮箱注记） -->
            <span class="user-menu__email">
              当前邮箱：{{ user.user?.email || '未绑定' }}<template v-if="user.user?.email && !user.user?.email_verified">（未验证）</template>
            </span>
            <span class="user-menu__arrow">›</span>
          </button>
          <button type="button" class="user-menu__row" @click="pickAnnouncements">
            <span class="user-menu__row-label">系统公告</span>
            <span class="user-menu__arrow">›</span>
          </button>
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

    <!-- 原「账号安全」模块（修改密码 / 修改邮箱 / 系统公告 / 当前邮箱）已上移至用户 Cell 下拉菜单，
         该区域按需求暂时保留空白，不再放置其它内容。对应弹窗与逻辑保留在本组件下方。 -->

    <!-- G17：数据与隐私（导出我的数据）；G35：未登录隐藏 -->
    <div v-if="user.token" id="settings-data" class="settings-block settings-block--col">
      <span class="settings-block__label">数据与隐私</span>
      <div class="security-rows">
        <button class="security-row" :disabled="exportLoading" @click="onExport">
          <span class="security-row__text">导出我的数据</span>
          <span class="security-row__arrow">›</span>
        </button>
        <button
          v-if="exportTask?.status === 'success' && exportTask.download_url"
          class="security-row"
          @click="onDownloadExport"
        >
          <span class="security-row__text security-row__text--accent">
            下载导出文件（{{ exportSizeText(exportTask.file_size) }}）
          </span>
          <span class="security-row__arrow">›</span>
        </button>
      </div>
      <span v-if="exportTask && exportTask.status !== 'success'" class="security-note">
        导出进度：{{ exportTask.status === 'failed' ? '失败' : exportTask.progress + '%' }}
      </span>
      <span v-else class="security-note">导出包含账号、关注、策略、回测、会话与记忆等全部数据，24 小时内有效。</span>
    </div>

    <!-- G14：AI 模型设置（自填 API Key + 累计 token 用量），仅新增区块，不改上方结构；G35：未登录隐藏 -->
    <div v-if="user.token" class="settings-block settings-block--col">
      <span class="settings-block__label">AI 模型设置</span>
      <div class="security-rows">
        <button v-if="!apiKeyEditing" class="security-row" @click="startEditApiKey">
          <span class="security-row__text">
            {{ apiKeyStatus.has_api_key ? '更换 API Key' : '填写我的 API Key' }}
          </span>
          <span class="security-row__arrow">›</span>
        </button>
        <button v-if="apiKeyStatus.has_api_key && !apiKeyEditing" class="security-row" :disabled="apiKeyLoading" @click="onClearApiKey">
          <span class="security-row__text">清除 API Key</span>
          <span class="security-row__arrow">›</span>
        </button>
      </div>

      <div v-if="apiKeyEditing" class="apikey-edit">
        <BaseInput
          v-model="apiKeyInput"
          type="password"
          placeholder="sk-xxxxxxxx（DeepSeek API Key）"
          autocomplete="off"
        />
        <div class="apikey-edit__actions">
          <BaseButton :loading="apiKeyLoading" @click="onSaveApiKey">保存</BaseButton>
          <BaseButton variant="ghost" :disabled="apiKeyLoading" @click="cancelEditApiKey">取消</BaseButton>
        </div>
      </div>

      <span class="security-note">
        <template v-if="apiKeyStatus.has_api_key">
          当前：{{ apiKeyStatus.masked }}（密文存储，AI 调用优先使用你的 Key）
        </template>
        <template v-else>未填写时使用服务端默认 Key。Key 以 AES-256-GCM 密文存储，不回显明文。</template>
      </span>
      <span class="security-note">
        累计 token 用量（估算）：{{ tokenText(tokenUsage.total) }}（输入 {{ tokenText(tokenUsage.prompt) }} / 输出 {{ tokenText(tokenUsage.completion) }}）
      </span>
      <span class="security-note">用量按模型返回的 usage 估算，仅供成本自估，非精确计费。</span>
    </div>

    <!-- G18：危险区（删除账户）；G35：未登录隐藏 -->
    <div v-if="user.token" class="settings-block settings-block--col danger-block">
      <span class="settings-block__label danger-block__label">危险操作</span>
      <button class="danger-btn" @click="openDanger">删除账户</button>
      <span class="security-note">注销后 30 天内可恢复，逾期将永久删除全部数据。</span>
    </div>

    <!-- G03：关于/法律入口 + 产品定位声明 -->
    <div class="settings-block settings-block--col about-block">
      <span class="settings-block__label">关于 / 法律</span>
      <div class="security-rows">
        <button class="security-row" @click="openAbout">
          <span class="security-row__text">关于本产品</span>
          <span class="security-row__arrow">›</span>
        </button>
        <RouterLink to="/terms" class="security-row">
          <span class="security-row__text">用户协议</span>
          <span class="security-row__arrow">›</span>
        </RouterLink>
        <button class="security-row" @click="legalModal.show('privacy')">
          <span class="security-row__text">隐私政策</span>
          <span class="security-row__arrow">›</span>
        </button>
        <button class="security-row" @click="legalModal.show('disclaimer')">
          <span class="security-row__text">免责声明</span>
          <span class="security-row__arrow">›</span>
        </button>
      </div>
    </div>

    <div class="settings-dev">
      <span class="settings-dev__text">本软件由 Xhope(发誓不做夜猫子)全程开发</span>
    </div>

    <!-- G16：系统公告历史弹窗 -->
    <Teleport to="body">
      <div v-if="annOpen" class="sec-mask" @click.self="annOpen = false">
        <div class="sec-dialog sec-dialog--wide">
          <h3 class="sec-dialog__title">系统公告</h3>
          <div v-if="annLoading" class="ann-empty">加载中…</div>
          <div v-else-if="annList.length === 0" class="ann-empty">暂无公告</div>
          <ul v-else class="ann-list">
            <li v-for="a in annList" :key="a.id" class="ann-list__item">
              <div class="ann-list__head">
                <span class="ann-list__title">{{ a.title }}</span>
                <span v-if="!a.is_active" class="ann-list__badge">已停用</span>
              </div>
              <p class="ann-list__content">{{ a.content }}</p>
              <span class="ann-list__time">{{ annTimeText(a.created_at) }}</span>
            </li>
          </ul>
          <div class="sec-dialog__actions">
            <BaseButton type="button" variant="ghost" @click="annOpen = false">关闭</BaseButton>
          </div>
        </div>
      </div>
    </Teleport>

    <!-- G03：关于本产品弹窗（产品定位声明） -->
    <Teleport to="body">
      <div v-if="aboutOpen" class="sec-mask" @click.self="aboutOpen = false">
        <div class="sec-dialog">
          <h3 class="sec-dialog__title">关于量化回测助手</h3>
          <div class="about-body">
            <p class="about-claim">
              <strong>本产品为量化研究辅助工具，非证券投资咨询服务。</strong>
            </p>
            <p>
              量化回测助手面向个人投资者，提供行情数据展示、技术指标计算、
              策略描述转写、历史回测验证与 AI 辅助分析等功能，
              旨在帮助用户整理交易思路、验证策略逻辑、观察历史数据表现。
            </p>
            <p>
              本产品不提供任何投资建议、荐股或代客理财服务，
              所展示的数据、指标、回测结果与 AI 生成内容仅供研究参考。
              投资有风险，决策需谨慎，请您独立判断并自行承担投资决策风险。
            </p>
            <p class="about-meta">版本 v0.3 · © 2026 stock-agent-聂久翔</p>
          </div>
          <div class="sec-dialog__actions">
            <BaseButton type="button" variant="ghost" @click="aboutOpen = false">关闭</BaseButton>
          </div>
        </div>
      </div>
    </Teleport>

    <!-- G18：删除账户二次确认弹窗（需输入指定确认文字） -->
    <Teleport to="body">
      <div v-if="dangerOpen" class="sec-mask" @click.self="closeDanger">
        <div class="sec-dialog danger-dialog">
          <h3 class="sec-dialog__title danger-dialog__title">删除账户</h3>
          <p class="danger-dialog__warn">
            此操作将注销您的账户并删除全部数据（关注、策略、回测、会话、AI 记忆等）。
            30 天内可登录后申请恢复，逾期将<strong>永久删除且不可恢复</strong>。
          </p>
          <BaseInput
            v-model="dangerInput"
            label="请输入以下文字以确认"
            :placeholder="DANGER_PHRASE"
            autocomplete="off"
          />
          <p class="danger-dialog__phrase">{{ DANGER_PHRASE }}</p>
          <div class="sec-dialog__actions">
            <BaseButton type="button" variant="ghost" @click="closeDanger">取消</BaseButton>
            <BaseButton
              type="button"
              variant="danger"
              :loading="dangerLoading"
              :disabled="dangerInput.trim() !== DANGER_PHRASE"
              @click="confirmDelete"
            >
              确认删除
            </BaseButton>
          </div>
        </div>
      </div>
    </Teleport>

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
/* G35：未登录头像（灰底人形图标） */
.user-cell__avatar--guest {
  background: var(--bg-active);
  color: var(--text-muted);
  font-size: 18px;
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
/* 浮层分隔线（退出登录 与 账号安全入口之间） */
.user-menu__sep {
  height: 1px;
  margin: 4px 6px;
  background: var(--border);
}
/* 浮层内的功能行（修改密码 / 修改邮箱 / 系统公告） */
.user-menu__row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  width: 100%;
  padding: 8px 10px;
  border: none;
  border-radius: 5px;
  background: transparent;
  font-size: 13px;
  font-family: inherit;
  color: var(--text);
  text-align: left;
  cursor: pointer;
  transition: background-color 0.15s;
}
.user-menu__row:hover {
  background: var(--bg-hover);
}
.user-menu__row-label {
  flex: none;
}
/* 邮箱绑定状态：位于「修改邮箱」右侧、箭头之前，超长省略 */
.user-menu__email {
  flex: 1 1 auto;
  min-width: 0;
  font-size: 11px;
  color: var(--text-muted);
  text-align: right;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.user-menu__arrow {
  flex: none;
  font-size: 16px;
  line-height: 1;
  color: var(--text-muted);
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
/* G14：较长的说明文案需换行，避免被 ellipsis 截断 */
.security-note--wrap {
  white-space: normal;
  line-height: 1.6;
}
/* G14：API Key 编辑区 */
.apikey-edit {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 6px;
}
.apikey-edit__actions {
  display: flex;
  gap: 8px;
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

/* G16：系统公告历史弹窗 */
.sec-dialog--wide {
  width: 460px;
}
.ann-empty {
  padding: 24px 0;
  text-align: center;
  font-size: 12px;
  color: var(--text-muted);
}
.ann-list {
  list-style: none;
  margin: 0 0 4px;
  padding: 0;
  max-height: 320px;
  overflow-y: auto;
}
.ann-list__item {
  padding: 10px 0;
  border-bottom: 1px solid var(--border);
}
.ann-list__head {
  display: flex;
  align-items: center;
  gap: 6px;
}
.ann-list__title {
  font-size: 13px;
  font-weight: 600;
  color: var(--text);
}
.ann-list__badge {
  padding: 1px 5px;
  border-radius: 3px;
  border: 1px solid var(--border);
  font-size: 10px;
  color: var(--text-muted);
}
.ann-list__content {
  margin: 4px 0 0;
  font-size: 12px;
  color: var(--text-secondary);
  line-height: 1.6;
  white-space: pre-wrap;
}
.ann-list__time {
  display: block;
  margin-top: 4px;
  font-size: 11px;
  color: var(--text-muted);
}

/* G17：数据导出 */
.security-row__text--accent {
  color: var(--accent);
}

/* G18：危险区（删除账户） */
.danger-block {
  margin-top: 2px;
  padding-top: 8px;
  border-top: 1px solid var(--border);
}
.danger-block__label {
  color: var(--down, #ef4444);
}
.danger-btn {
  padding: 7px 10px;
  border: 1px solid var(--down, #ef4444);
  border-radius: 4px;
  color: var(--down, #ef4444);
  font-size: 13px;
  cursor: pointer;
  transition: background-color 0.15s;
}
.danger-btn:hover {
  background: rgba(239, 68, 68, 0.12);
}
.danger-dialog__title {
  color: var(--down, #ef4444);
}
.danger-dialog__warn {
  margin-bottom: 14px;
  font-size: 12px;
  line-height: 1.7;
  color: var(--text-secondary);
}
.danger-dialog__warn strong {
  color: var(--down, #ef4444);
}
.danger-dialog__phrase {
  margin-top: 6px;
  padding: 6px 8px;
  background: var(--bg-panel-2);
  border: 1px dashed var(--border-strong);
  border-radius: 4px;
  font-size: 12px;
  color: var(--text);
  user-select: all;
}

/* G03：关于/法律 */
.about-block {
  padding-top: 8px;
  border-top: 1px solid var(--border);
}
.about-body {
  font-size: 12.5px;
  line-height: 1.8;
  color: var(--text-secondary);
}
.about-body p {
  margin: 0 0 10px;
}
.about-claim {
  padding: 8px 10px;
  background: var(--bg-panel-2);
  border-left: 3px solid var(--accent);
  border-radius: 4px;
  color: var(--text);
}
.about-meta {
  color: var(--text-muted);
  font-size: 11.5px;
}
</style>
