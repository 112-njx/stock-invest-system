export function displaySyntheticCandle<T extends { open: number; high: number; low: number; close: number }>(bar: T, factor: number): T {
  const top = Math.max(bar.open, bar.close)
  const bottom = Math.min(bar.open, bar.close)
  return { ...bar, high: top + (bar.high - top) * factor, low: bottom - (bottom - bar.low) * factor }
}
