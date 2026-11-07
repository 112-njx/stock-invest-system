<script setup lang="ts">
import { ref, watch, nextTick, onMounted, onUnmounted } from 'vue'
import { request } from '@/api/http'
const props = defineProps<{ taskId: string | null; running: boolean; details?: Record<string, string | number> }>()
interface EventRow { seq: number; time: number; phase: string; level: string; file: string | null; message: string }
interface FileRow { file: string; status: string; retries: number }
interface Page { events: EventRow[]; files: FileRow[]; has_more: boolean }
const rows = ref<EventRow[]>([])
const files = ref<FileRow[]>([])
const error = ref('')
const follow = ref(true)
const more = ref(false)
const viewport = ref<HTMLElement>()
let generation = 0
let loading = false
let timer: ReturnType<typeof setTimeout> | undefined
let alive = true
const labels: Record<string,string> = { checking:'更新前检查',stopping:'暂停读取',downloading:'下载与续传',merging:'文件合并',verifying:'文件校验',starting:'恢复服务',done:'完成',failed:'失败',retrying:'重试中',deleting:'待删除',deleted:'已删除',reused:'已复用' }
function scrolled() {
  const el = viewport.value
  if (el) follow.value = el.scrollHeight - el.scrollTop - el.clientHeight < 32
}
async function load(mode: 'new' | 'older' | 'latest' = 'new') {
  if (!props.taskId || loading || !alive) return
  loading = true
  const version = generation
  try {
    const page = await request<Page>({url:'/admin/local-market/update/events',silent:true,params:{
      task_id:props.taskId, limit:200,
      ...(mode === 'older' ? {before_seq:rows.value[0]?.seq} : mode === 'latest' || !rows.value.length ? {before_seq:Number.MAX_SAFE_INTEGER} : {after_seq:rows.value.at(-1)?.seq ?? 0}),
    }})
    if (!alive || version !== generation) return
    files.value = page.files ?? []
    const incoming = page.events ?? []
    if (mode === 'older') {
      const el = viewport.value
      const top = el?.scrollTop ?? 0, height = el?.scrollHeight ?? 0
      follow.value = false
      rows.value = [...incoming, ...rows.value].slice(0, 1000)
      more.value = page.has_more
      await nextTick()
      if (el) el.scrollTop = top + el.scrollHeight - height
    } else if (mode === 'latest' || follow.value) {
      const fresh = mode === 'latest' || !rows.value.length
      const merged = fresh ? incoming : [...rows.value, ...incoming]
      rows.value = [...new Map(merged.map(row => [row.seq,row])).values()].slice(-1000)
      if (fresh) more.value = page.has_more
      else if (merged.length > 1000) more.value = true
      error.value = ''
      await nextTick()
      if (viewport.value && follow.value) viewport.value.scrollTop = viewport.value.scrollHeight
    }
    error.value = ''
  } catch { if (alive && version === generation) error.value = '日志读取失败，已保留现有记录，可重试' }
  finally { loading = false }
}
function latest() { follow.value = true; void load('latest') }
function schedule() {
  clearTimeout(timer)
  if (!alive || !props.running || document.hidden) return
  timer = setTimeout(async () => { await load(); schedule() }, 1000)
}
watch(() => props.taskId, () => {
  generation++; rows.value=[]; files.value=[]; follow.value=true; more.value=false; error.value=''
  // An older request may still own the in-flight slot; resume after it settles.
  void (async () => { while (loading && alive) await new Promise(r => setTimeout(r,50)); if(alive) await load('latest') })()
}, { immediate:true })
watch(() => props.running, () => { void load(); schedule() })
function visibility() { if(!document.hidden) {void load(); schedule()} else clearTimeout(timer) }
onMounted(() => { schedule(); document.addEventListener('visibilitychange',visibility) })
onUnmounted(() => {alive=false;generation++;clearTimeout(timer);document.removeEventListener('visibilitychange',visibility)})
</script>
<template>
  <section v-if="taskId" class="update-details" aria-label="原始数据更新详情">
    <div class="split"><h3>更新运行详情</h3><span class="task-id">任务 {{ taskId }}</span></div>
    <dl class="update-stats">
      <div><dt>待下载文件</dt><dd>{{ details?.download_files ?? '—' }}</dd></div>
      <div><dt>待删除文件</dt><dd>{{ details?.delete_files ?? '—' }}</dd></div>
      <div><dt>下载量</dt><dd>{{ details?.downloaded ?? '—' }} / {{ details?.total ?? '—' }}</dd></div>
      <div><dt>下载进度</dt><dd>{{ details?.download_percent ?? '—' }}%</dd></div>
      <div><dt>速度</dt><dd>{{ details?.speed ?? '—' }}</dd></div>
      <div><dt>已校验文件</dt><dd>{{ details?.verified_files ?? '—' }}</dd></div>
    </dl>
    <details v-if="files.length"><summary>文件状态（当前展示 {{ files.length }} 项）</summary>
      <div class="update-files"><table><thead><tr><th>文件</th><th>状态</th><th>重试次数</th></tr></thead><tbody><tr v-for="file in files" :key="file.file"><td>{{ file.file }}</td><td>{{ labels[file.status] || file.status }}</td><td>{{ file.retries }}</td></tr></tbody></table></div>
    </details>
    <div class="update-log-actions"><button type="button" :disabled="!more" @click="load('older')">加载更早记录</button><button type="button" @click="latest">返回最新</button><span>{{ follow ? '跟随最新日志' : '正在查看历史，已暂停跟随' }}</span></div>
    <p v-if="error" class="danger" role="alert">{{ error }} <button type="button" @click="load()">重试</button></p>
    <div ref="viewport" class="update-log" tabindex="0" aria-label="更新日志" @scroll="scrolled">
      <p v-for="row in rows" :key="row.seq" :class="{danger:row.level === 'error'}"><time>{{ new Date(row.time*1000).toLocaleTimeString('zh-CN') }}</time><b>{{ labels[row.phase] || row.phase }}</b><span>{{ row.message }}</span></p>
      <p v-if="!rows.length">等待更新事件…</p>
    </div>
  </section>
</template>
