import { nextTick, ref, watch } from 'vue'
import { trackRender } from '@/utils/monitor'

/**
 * G27（P1-6b）：虚拟列表的「按需续拉 + 渲染耗时埋点」通用逻辑。
 *
 * 配合 vue-virtual-scroller 的 RecycleScroller 使用：
 * - `onUpdate` 绑定到 `@update`，可见区间接近末尾时自动续拉下一页（防重入）
 * - 列表长度变化后测量到 DOM 更新完成的耗时，>500ms 由 trackRender 告警
 *
 * 续拉边界由 `hasMore()` 决定（G09 已提供 total / has_more 口径）。
 */
export function useInfiniteList(opts: {
  /** 当前已加载条数（响应式读取） */
  count: () => number
  /** 是否还有未加载的数据 */
  hasMore: () => boolean
  /** 拉取下一页，返回新增条数（返回 0 视为没有更多） */
  loadMore: () => Promise<number>
  /** 埋点名称，如 conversation_list */
  name: string
  /** 距末尾多少条时开始续拉 */
  threshold?: number
}) {
  const loadingMore = ref(false)
  const threshold = opts.threshold ?? 5

  async function requestMore() {
    if (loadingMore.value || !opts.hasMore()) return
    loadingMore.value = true
    try {
      await opts.loadMore()
    } catch {
      /* 失败已由 http 拦截器 toast；下次滚动会重试 */
    } finally {
      loadingMore.value = false
    }
  }

  /** RecycleScroller @update(startIndex, endIndex, visibleStartIndex, visibleEndIndex) */
  function onUpdate(_start: number, _end: number, _visibleStart: number, visibleEndIndex: number) {
    if (visibleEndIndex >= opts.count() - threshold) void requestMore()
  }

  watch(opts.count, async (n) => {
    const t0 = performance.now()
    await nextTick()
    trackRender(opts.name, performance.now() - t0, { count: n })
  })

  return { loadingMore, requestMore, onUpdate }
}
