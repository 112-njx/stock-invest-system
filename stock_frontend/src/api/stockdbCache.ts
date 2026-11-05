/** Page-independent memory and IndexedDB caches. Network updates never clear usable entries. */
const schema = 2
const memoryLimit = 16 * 1024 * 1024
const diskLimit = 32 * 1024 * 1024
const entryLimit = 128
interface Entry<T = unknown> {
  key: string
  schema: number
  value: T
  etag?: string
  savedAt: number
  size: number
}
const memory = new Map<string, Entry>()
let memoryBytes = 0
let database: Promise<IDBDatabase | null> | undefined

function openDatabase() {
  if (!database) database = new Promise<IDBDatabase | null>((resolve) => {
    if (!('indexedDB' in window)) { resolve(null); return }
    let settled = false
    const finish = (db: IDBDatabase | null) => {
      if (settled) { db?.close(); return }
      settled = true
      clearTimeout(timeout)
      resolve(db)
    }
    const timeout = setTimeout(() => finish(null), 1500)
    try {
      const request = indexedDB.open('stockdb-workspace', schema)
      request.onupgradeneeded = () => {
        const db = request.result
        if (db.objectStoreNames.contains('entries')) db.deleteObjectStore('entries')
        db.createObjectStore('entries', { keyPath: 'key' }).createIndex('savedAt', 'savedAt')
      }
      request.onsuccess = () => {
        request.result.onversionchange = () => { request.result.close(); database = undefined }
        finish(request.result)
      }
      request.onerror = () => finish(null)
      request.onblocked = () => finish(null)
    } catch { finish(null) }
  })
  return database
}

function remember(entry: Entry) {
  const previous = memory.get(entry.key)
  if (previous) memoryBytes -= previous.size
  memory.delete(entry.key)
  if (entry.size <= memoryLimit) {
    memory.set(entry.key, entry)
    memoryBytes += entry.size
  }
  while (memory.size > entryLimit || memoryBytes > memoryLimit) {
    const oldest = memory.entries().next().value
    if (!oldest) break
    memory.delete(oldest[0])
    memoryBytes -= oldest[1].size
  }
}

export function peekCache<T>(key: string): T | undefined {
  const entry = memory.get(key)
  if (!entry) return undefined
  memory.delete(key)
  memory.set(key, entry)
  return entry.value as T
}

async function readEntry<T>(key: string): Promise<Entry<T> | undefined> {
  const cached = memory.get(key)
  if (cached) return cached as Entry<T>
  const db = await openDatabase()
  if (!db) return undefined
  return new Promise((resolve) => {
    try {
      const request = db.transaction('entries').objectStore('entries').get(key)
      request.onsuccess = () => {
        const entry = request.result as Entry<T> | undefined
        if (entry?.schema === schema && entry.key === key && Number.isFinite(entry.size) && entry.value !== undefined) {
          remember(entry)
          resolve(entry)
        } else resolve(undefined)
      }
      request.onerror = () => resolve(undefined)
    } catch { resolve(undefined) }
  })
}

export async function readCache<T>(key: string) { return (await readEntry<T>(key))?.value }

async function writeEntry(entry: Entry) {
  const db = await openDatabase()
  if (!db) return
  try {
    const transaction = db.transaction('entries', 'readwrite')
    const store = transaction.objectStore('entries')
    store.put(entry)
    // Keep recent entries within both an entry count and a serialized byte budget.
    let bytes = 0
    let count = 0
    const cursor = store.index('savedAt').openCursor(null, 'prev')
    cursor.onsuccess = () => {
      const current = cursor.result
      if (!current) return
      const value = current.value as Entry
      bytes += value.size
      count++
      if (bytes > diskLimit || count > entryLimit) current.delete()
      current.continue()
    }
    transaction.onerror = () => { /* Memory cache remains usable if browser storage is full. */ }
  } catch { /* Browser storage is optional. */ }
}

export function putCache<T>(key: string, value: T, etag?: string) {
  const entry: Entry<T> = {
    key, value, etag, schema, savedAt: Date.now(),
    size: new TextEncoder().encode(JSON.stringify(value)).length,
  }
  remember(entry)
  void writeEntry(entry)
}

export class StockDbHttpError extends Error {
  readonly status: number
  constructor(message: string, status: number) {
    super(message)
    this.status = status
  }
}

/** Only explicit page/hover requests and the default home bootstrap call this function. */
export async function fetchStockDb<T>(path: string, codes?: string[]): Promise<T> {
  const key = 'api:' + path + (codes ? ':' + JSON.stringify(codes) : '')
  const saved = await readEntry<T>(key)
  const headers: Record<string, string> = {}
  if (saved?.etag) headers['If-None-Match'] = saved.etag
  if (codes) headers['Content-Type'] = 'application/json'
  const response = await fetch('/api/v1/stockdb' + path, {
    headers,
    signal: AbortSignal.timeout(40000),
    ...(codes ? { method: 'POST', body: JSON.stringify({ codes }) } : {}),
  })
  if (response.status === 304 && saved) return saved.value
  const value = await response.json()
  if (!response.ok) throw new StockDbHttpError(value.msg || value.detail || '读取本地数据失败', response.status)
  if (path !== '/status') putCache(key, value, response.headers.get('etag') ?? undefined)
  return value as T
}

export async function cachedStockDb<T>(path: string, codes?: string[], maxAge = Infinity): Promise<T> {
  const saved = await readEntry<T>('api:' + path + (codes ? ':' + JSON.stringify(codes) : ''))
  return saved && Date.now() - saved.savedAt <= maxAge ? saved.value : fetchStockDb<T>(path, codes)
}

let homePrepared = false
export async function prepareStockDbHome() {
  if (homePrepared) return
  homePrepared = true
  try { await fetchStockDb('/home') }
  catch { homePrepared = false }
}
