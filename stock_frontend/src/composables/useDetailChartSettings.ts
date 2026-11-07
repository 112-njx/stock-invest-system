import { ref, watch, onScopeDispose } from 'vue'
import { useUserStore } from '@/stores/user'
import { request } from '@/api/http'

export type PanelKey = 'volume' | 'amount' | 'macd' | 'kdj'
export interface MaLine { period: number; visible: boolean }
export interface DetailChartSettings { ma: { lines: MaLine[] }; panels: PanelKey[] }
export const PANEL_KEYS: PanelKey[] = ['volume', 'amount', 'macd', 'kdj']
export const defaultChartSettings = (): DetailChartSettings => ({ ma: { lines: [5,10,20,30].map(period => ({ period, visible: true })) }, panels: ['volume','macd'] })
const KEY = 'detail_chart_settings_v1'
export function validateMa(lines: MaLine[]) {
  return lines.length >= 1 && lines.length <= 6 && lines.every(l => Number.isInteger(l.period) && l.period >= 1 && l.period <= 10000 && typeof l.visible === 'boolean') && new Set(lines.map(l => l.period)).size === lines.length
}
function guestSettings(): DetailChartSettings {
  try {
    const raw = localStorage.getItem(KEY)
    if (raw) {
      const value = JSON.parse(raw) as DetailChartSettings
      if (validateMa(value.ma.lines) && Array.isArray(value.panels)) return { ma: value.ma, panels: PANEL_KEYS.filter(p => value.panels.includes(p)).slice(0,3) }
    }
    const legacy = JSON.parse(localStorage.getItem('indicator_visibility') || 'null')
    if (Array.isArray(legacy)) return { ...defaultChartSettings(), panels: PANEL_KEYS.filter(p => legacy.includes(p)).slice(0,3) }
  } catch { /* invalid browser preferences use defaults */ }
  return defaultChartSettings()
}
export function useDetailChartSettings(enabled: () => boolean) {
  const user = useUserStore()
  const settings = ref(defaultChartSettings())
  const ready = ref(false)
  const saving = ref(false)
  const error = ref('')
  let generation = 0
  async function load() {
    const token = ++generation
    saving.value = false
    error.value = ''
    ready.value = false
    settings.value = defaultChartSettings()
    if (!enabled()) return
    const id = user.user?.id
    if (!id) { settings.value = guestSettings(); ready.value = true; return }
    try {
      const value = await request<DetailChartSettings>({ url: '/users/me/chart-settings', silent: true })
      if (token !== generation) return
      settings.value = value
      ready.value = true
    } catch { if (token === generation) error.value = '图表设置读取失败，请重试' }
  }
  watch(() => [enabled(), user.user?.id] as const, load, { immediate: true })
  onScopeDispose(() => { generation++ })
  async function save(value: DetailChartSettings) {
    if (!ready.value || saving.value) return false
    if (!validateMa(value.ma.lines) || value.panels.length > 3 || new Set(value.panels).size !== value.panels.length || value.panels.some(p => !PANEL_KEYS.includes(p))) {
      error.value = 'MA须为1～6个不重复的整数周期（1～10000），副图最多3个'
      return false
    }
    const token = generation
    saving.value = true
    error.value = ''
    try {
      const next = JSON.parse(JSON.stringify(value)) as DetailChartSettings
      const saved = user.user?.id
        ? await request<DetailChartSettings>({ url: '/users/me/chart-settings', method: 'put', data: next, silent: true })
        : (localStorage.setItem(KEY, JSON.stringify(next)), next)
      if (token !== generation) return false
      settings.value = saved
      return true
    } catch { if (token === generation) error.value = '保存失败，仍使用上次成功保存的配置'; return false }
    finally { if (token === generation) saving.value = false }
  }
  return { settings, ready, saving, error, save, load }
}
