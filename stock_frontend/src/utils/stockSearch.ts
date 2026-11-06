import { customPinyin, pinyin } from 'pinyin-pro'
import type { SearchStock } from '../api/stockSearch'

// Common equity names whose pronunciation cannot be inferred character by character.
customPinyin({ 银行: 'yin hang', 重庆: 'chong qing', 长安: 'chang an', 长江: 'chang jiang',
  长城: 'chang cheng', 厦门: 'xia men' })

export interface IndexedStock extends SearchStock {
  searchName: string
  fullPinyin: string
  initials: string
}

export function normalizeSearch(value: string) {
  return value.normalize('NFKC').toLowerCase().replace(/[\s'’]+/g, '').replace(/ü/g, 'v')
}

export function indexStocks(items: SearchStock[]): IndexedStock[] {
  return [...items].sort((a, b) => a.code.localeCompare(b.code)).map((item, i) => {
    const syllables = pinyin(item.name, { toneType: 'none', type: 'array', v: true })
    return { ...item, ordinal: i + 1, searchName: normalizeSearch(item.name),
      fullPinyin: normalizeSearch(syllables.join('')),
      initials: normalizeSearch(syllables.map((word) => word[0] ?? '').join('')) }
  })
}

export function filterStocks(items: IndexedStock[], query: string) {
  const q = normalizeSearch(query)
  if (!q) return items
  return items.filter((s) => s.code.startsWith(q) || s.searchName.includes(q) ||
    s.fullPinyin.includes(q) || s.initials.includes(q))
}
