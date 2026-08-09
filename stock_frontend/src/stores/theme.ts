import { defineStore } from 'pinia'

export type ThemeMode = 'dark' | 'light'

const THEME_KEY = 'stock_invest_theme'

/** 主题状态：暗黑/明亮，持久化 localStorage 并应用到 html[data-theme] */
export const useThemeStore = defineStore('theme', {
  state: () => ({
    mode: (localStorage.getItem(THEME_KEY) as ThemeMode) || 'dark',
  }),
  actions: {
    apply() {
      document.documentElement.setAttribute('data-theme', this.mode)
    },
    init() {
      this.apply()
    },
    toggle() {
      this.mode = this.mode === 'dark' ? 'light' : 'dark'
      localStorage.setItem(THEME_KEY, this.mode)
      this.apply()
    },
    setMode(mode: ThemeMode) {
      this.mode = mode
      localStorage.setItem(THEME_KEY, mode)
      this.apply()
    },
  },
})
