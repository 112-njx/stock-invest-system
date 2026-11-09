/** Split into independent lines so the chart never bridges days or missing values. */
export function averageSegments<T extends {date: number; average: number | null}>(rows: T[]): T[][] {
  const segments: T[][] = []
  let current: T[] = []
  let day = ''
  for (const row of rows) {
    const nextDay = String(row.date).slice(0, 8)
    if (row.average == null || nextDay !== day) {
      current = []
    }
    if (row.average != null) {
      if (!current.length) segments.push(current)
      current.push(row)
    }
    day = nextDay
  }
  return segments
}
