import { computed, onMounted, onUnmounted, reactive, watch, type Ref } from 'vue'
import {
  adminApi,
  type DisplaySettings,
  type LocalServices,
  type LocalSync,
  type ProviderRequest,
  type SourcePolicy,
  type TaskQueues,
  type Traffic,
} from '@/api/admin'
import { syntheticWickFactor } from '@/composables/useSyntheticWicks'

export type AdminSection = 'overview' | 'sources' | 'tasks' | 'requests' | 'display'
interface Resource<T> {
  data: T | null
  loading: boolean
  error: string
  updated: string
}
const resource = <T>(): Resource<T> => ({ data: null, loading: false, error: '', updated: '' })
export const queueNames: Record<string, string> = {
  watchlist: '关注股票',
  fixed_indices: '本地行情与固定指数',
  backfill: '历史补拉',
  control: '任务协调',
  sync: '目录与常规同步',
  backtest: '策略回测',
  ai: 'AI、记忆与导出',
  backup: '数据备份',
}
export const providerNames: Record<string, string> = {
  stockdb: 'Free-StockDB',
  eastmoney: '东方财富',
  sina: '新浪',
  ths: '同花顺',
}
export function stateLabel(state?: string) {
  return (
    (
      {
        idle: '尚未执行',
        queued: '等待执行',
        running: '执行中',
        success: '已完成',
        done: '已完成',
        partial: '部分完成',
        failed: '失败',
        online: '在线',
        unavailable: '不可用',
        disabled: '已禁用',
        open: '熔断中',
        half_open: '恢复探测中',
        closed: '可用',
        throttling: '等待限流',
        requesting: '请求中',
        retry_wait: '等待重试',
      } as Record<string, string>
    )[state ?? ''] ??
    state ??
    '未知'
  )
}
export function useAdminConsole(section: Ref<AdminSection>) {
  const state = reactive({
    services: resource<LocalServices>(),
    policy: resource<SourcePolicy>(),
    traffic: resource<Traffic>(),
    queues: resource<TaskQueues>(),
    sync: resource<LocalSync>(),
    requests: resource<{ requests: ProviderRequest[] }>(),
    display: resource<DisplaySettings>(),
    policyForm: { akshare_enabled: false, snapshots_enabled: false },
    limitsForm: { interval_seconds: 2, retry_interval_seconds: 10, daily_budget: 2000 },
    displayForm: { synthetic_wick_factor: 0.5 },
    dirty: { policy: false, limits: false, display: false },
    saving: { policy: false, limits: false, display: false, sync: false },
    feedback: { policy: '', limits: '', display: '', sync: '' },
    saveError: { policy: '', limits: '', display: '', sync: '' },
  })
  let alive = true
  let timer: ReturnType<typeof setTimeout> | undefined
  const pending = new Map<object, Promise<void>>()
  const revisions = new Map<object, number>()
  function invalidate(target: object) {
    revisions.set(target, (revisions.get(target) ?? 0) + 1)
  }
  async function load<T>(target: Resource<T>, fetch: () => Promise<T>, apply?: (value: T) => void) {
    if (pending.has(target)) return pending.get(target)
    const revision = revisions.get(target) ?? 0
    const task = (async () => {
      target.loading = true
      try {
        const value = await fetch()
        if (!alive || revision !== (revisions.get(target) ?? 0)) return
        target.data = value
        target.error = ''
        target.updated = new Date().toLocaleTimeString('zh-CN')
        apply?.(value)
      } catch {
        if (alive && revision === (revisions.get(target) ?? 0))
          target.error = '读取失败，请刷新重试；已保留上次结果'
      } finally {
        target.loading = false
        pending.delete(target)
      }
    })()
    pending.set(target, task)
    return task
  }
  const loaders = {
    services: () => load(state.services, adminApi.services),
    queues: () => load(state.queues, adminApi.queues),
    sync: () => load(state.sync, adminApi.sync),
    requests: () => load(state.requests, adminApi.requests),
    policy: () =>
      load(state.policy, adminApi.policy, (value) => {
        if (!state.dirty.policy && !state.saving.policy) Object.assign(state.policyForm, value)
      }),
    traffic: () =>
      load(state.traffic, adminApi.traffic, (value) => {
        if (!state.dirty.limits && !state.saving.limits)
          Object.assign(state.limitsForm, {
            interval_seconds: value.interval_seconds,
            retry_interval_seconds: value.retry_interval_seconds,
            daily_budget: value.daily_budget,
          })
      }),
    display: () =>
      load(state.display, adminApi.display, (value) => {
        if (!state.dirty.display && !state.saving.display) Object.assign(state.displayForm, value)
      }),
  }
  const busySync = computed(
    () => state.saving.sync || ['queued', 'running'].includes(state.sync.data?.status ?? '')
  )
  const refreshing = computed(() =>
    Object.values(state).some((value) => value && 'loading' in value && value.loading)
  )
  async function refresh() {
    const keys = {
      overview: ['services', 'policy', 'queues', 'sync'],
      sources: ['services', 'policy', 'traffic', 'sync'],
      tasks: ['queues'],
      requests: ['requests'],
      display: ['display'],
    } as const
    await Promise.all(keys[section.value].map((key) => loaders[key]()))
  }
  async function save(kind: 'policy' | 'limits' | 'display') {
    if (state.saving[kind]) return
    state.saveError[kind] = ''
    state.feedback[kind] = ''
    if (
      kind === 'limits' &&
      ![
        [state.limitsForm.interval_seconds, 1, 60],
        [state.limitsForm.retry_interval_seconds, 1, 120],
        [state.limitsForm.daily_budget, 100, 100000],
      ].every(([n, min, max]) => Number.isInteger(n) && n! >= min! && n! <= max!)
    ) {
      state.saveError[kind] = '请输入范围内的整数'
      return
    }
    const factor = state.displayForm.synthetic_wick_factor
    if (kind === 'display' && (!Number.isFinite(factor) || factor < 0 || factor > 1)) {
      state.saveError[kind] = '影线系数须为 0 到 1'
      return
    }
    state.saving[kind] = true
    const target =
      kind === 'policy' ? state.policy : kind === 'limits' ? state.traffic : state.display
    invalidate(target)
    try {
      if (kind === 'policy') {
        const draft = {
          ...state.policyForm,
          snapshots_enabled: state.policyForm.akshare_enabled && state.policyForm.snapshots_enabled,
        }
        const result = await adminApi.savePolicy(draft)
        invalidate(target)
        state.policy.data = result
        Object.assign(state.policyForm, result)
        void (async () => {
          await pending.get(state.traffic)
          if (alive) await loaders.traffic()
        })()
      } else if (kind === 'limits') {
        const result = await adminApi.saveLimits({ ...state.limitsForm })
        invalidate(target)
        state.traffic.data = result
      } else {
        const result = await adminApi.saveDisplay({ ...state.displayForm })
        invalidate(target)
        state.display.data = result
        Object.assign(state.displayForm, result)
        syntheticWickFactor.value = result.synthetic_wick_factor
      }
      target.error = ''
      target.updated = new Date().toLocaleTimeString('zh-CN')
      state.dirty[kind] = false
      state.feedback[kind] = '已保存'
    } catch {
      state.saveError[kind] = '保存失败，修改尚未生效，请重试'
    } finally {
      state.saving[kind] = false
    }
  }
  async function startSync() {
    if (busySync.value) return
    state.saving.sync = true
    state.saveError.sync = ''
    state.feedback.sync = ''
    invalidate(state.sync)
    try {
      const submitted = await adminApi.startSync()
      invalidate(state.sync)
      state.sync.data = {
        status: submitted.status,
        task_id: submitted.task_id,
        progress: 0,
        error: null,
        message: '等待本地行情同步',
      }
      state.sync.error = ''
      state.feedback.sync = '同步请求已提交'
      await loaders.sync()
    } catch {
      state.saveError.sync = '提交失败，请重试'
    } finally {
      state.saving.sync = false
    }
  }
  async function poll() {
    if (!alive || document.hidden) return
    if (section.value === 'requests') await loaders.requests()
    else if (section.value === 'tasks') await loaders.queues()
    else if (['overview', 'sources'].includes(section.value)) {
      const wasBusy = busySync.value
      await loaders.sync()
      if (wasBusy && !busySync.value) await Promise.all([loaders.services(), loaders.queues()])
    }
  }
  function schedule() {
    clearTimeout(timer)
    if (!alive || document.hidden) return
    timer = setTimeout(
      async () => {
        try {
          await poll()
        } finally {
          schedule()
        }
      },
      section.value === 'requests' || busySync.value ? 3000 : 10000
    )
  }
  function visibility() {
    if (!document.hidden) void refresh()
    schedule()
  }
  watch(section, () => {
    void refresh()
    schedule()
  })
  onMounted(() => {
    void refresh()
    schedule()
    document.addEventListener('visibilitychange', visibility)
  })
  onUnmounted(() => {
    alive = false
    clearTimeout(timer)
    document.removeEventListener('visibilitychange', visibility)
  })
  function edit(kind: 'policy' | 'limits' | 'display') {
    state.dirty[kind] = true
    state.feedback[kind] = ''
  }
  return { state, busySync, refreshing, refresh, save, startSync, edit }
}
export type AdminConsole = ReturnType<typeof useAdminConsole>
