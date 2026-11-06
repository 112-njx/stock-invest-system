export interface HeatStock {
  code: string; name: string; close: number; change: number
  totalMv: number; deltaMv: number; value: number
}
export interface HeatBoard {
  code: string; name: string; change: number; value: number
  up: number; down: number; children: HeatStock[]
}
export interface Heatmap {
  date: number; previousDate: number; updatedAt: string; version: string
  count: number; total: number; missing: number; duplicates: number; zero: number
  warning?: string; boards: HeatBoard[]
}
export interface Rect { x: number; y: number; w: number; h: number }

/** Balanced weighted binary treemap; zero changes deliberately receive no area. */
export function tiles<T extends { value: number }>(items: T[], box: Rect): { item: T; box: Rect }[] {
  const sorted = items.filter(x => x.value > 0).sort((a, b) => b.value - a.value)
  const result: { item: T; box: Rect }[] = []
  function split(list: T[], rect: Rect) {
    if (!list.length || rect.w <= 0 || rect.h <= 0) return
    if (list.length === 1) { result.push({ item: list[0]!, box: rect }); return }
    const total = list.reduce((s, x) => s + x.value, 0)
    let sum = list[0]!.value, at = 1
    while (at < list.length - 1 && Math.abs(sum + list[at]!.value - total / 2) < Math.abs(sum - total / 2)) {
      sum += list[at++]!.value
    }
    const ratio = sum / total
    if (rect.w >= rect.h) {
      const w = rect.w * ratio
      split(list.slice(0, at), { ...rect, w })
      split(list.slice(at), { ...rect, x: rect.x + w, w: rect.w - w })
    } else {
      const h = rect.h * ratio
      split(list.slice(0, at), { ...rect, h })
      split(list.slice(at), { ...rect, y: rect.y + h, h: rect.h - h })
    }
  }
  split(sorted, box)
  return result
}
