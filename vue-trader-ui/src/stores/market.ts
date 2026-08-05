import { defineStore } from 'pinia';
import { ref, computed } from 'vue';
import {
  fetchQuotes,
  fetchKLineHistory,
  checkCompleteness,
  triggerBackfill,
} from '@/api/market';
import type { MarketQuote, KLineDataPoint } from '@/types/market';

const BACKFILL_CACHE_KEY = 'vue-trader:backfilled-symbols:v1';
const BACKFILL_TTL_MS = 24 * 60 * 60 * 1000;
const DEFAULT_KLINE_DAYS = 365;
const DEFAULT_BACKFILL_MONTHS = 13;

type LoadStage = 'idle' | 'fetching' | 'checking' | 'backfilling' | 'refetching' | 'ready' | 'error';

function loadCache(): Record<string, number> {
  try {
    return JSON.parse(localStorage.getItem(BACKFILL_CACHE_KEY) || '{}');
  } catch {
    return {};
  }
}

function saveCache(cache: Record<string, number>) {
  try {
    localStorage.setItem(BACKFILL_CACHE_KEY, JSON.stringify(cache));
  } catch {
    /* ignore */
  }
}

function markBackfilled(symbol: string) {
  const cache = loadCache();
  cache[symbol] = Date.now();
  saveCache(cache);
}

function wasRecentlyBackfilled(symbol: string): boolean {
  const cache = loadCache();
  const ts = cache[symbol];
  return typeof ts === 'number' && Date.now() - ts < BACKFILL_TTL_MS;
}

function todayIso(): string {
  return new Date().toISOString().slice(0, 10);
}

function monthsAgoIso(months: number): string {
  const d = new Date();
  d.setMonth(d.getMonth() - months);
  return d.toISOString().slice(0, 10);
}

export const useMarketStore = defineStore('market', () => {
  const currentSymbol = ref('sh600519');
  const realtimeQuote = ref<MarketQuote | null>(null);
  const klineData = ref<KLineDataPoint[]>([]);
  const loading = ref(false);
  const loadStage = ref<LoadStage>('idle');
  const loadMessage = ref<string>('');
  const error = ref<string | null>(null);

  const stockName = computed(() => {
    const nameMap: Record<string, string> = {
      sh600519: '贵州茅台',
      sz000001: '平安银行',
      sh000001: '上证指数',
      sz399001: '深证成指',
    };
    return nameMap[currentSymbol.value] ?? currentSymbol.value;
  });

  async function ensureData(symbol: string): Promise<KLineDataPoint[]> {
    loadStage.value = 'fetching';
    loadMessage.value = '读取历史数据...';
    const initial = await fetchKLineHistory({ symbol, days: DEFAULT_KLINE_DAYS }).catch(() => []);
    if (initial.length > 0) return initial;

    if (wasRecentlyBackfilled(symbol)) {
      return [];
    }

    const endDate = todayIso();
    const startDate = monthsAgoIso(DEFAULT_BACKFILL_MONTHS);

    loadStage.value = 'checking';
    loadMessage.value = '检测历史数据覆盖情况...';
    const cmpl = await checkCompleteness({ symbol, startDate, endDate, adjustType: 'qfq' })
      .catch((e) => {
        console.warn('[completeness] check failed', e);
        return null;
      });
    if (cmpl && cmpl.complete) {
      markBackfilled(symbol);
      return [];
    }

    loadStage.value = 'backfilling';
    loadMessage.value = '首次访问该标的，正在从行情源拉取历史数据（预计 10~30 秒）...';
    const backfill = await triggerBackfill({ symbol, startDate, endDate, adjustType: 'qfq' })
      .catch((e) => {
        console.error('[backfill] failed', e);
        throw new Error('数据补充失败，请稍后重试');
      });

    if (backfill.status === 'FAIL') {
      throw new Error(
        `数据获取失败：${backfill.ingestResults?.[0]?.message || '上游行情接口暂不可用'}`,
      );
    }

    markBackfilled(symbol);
    loadStage.value = 'refetching';
    loadMessage.value = '数据补充完成，重新加载 K 线...';
    return fetchKLineHistory({ symbol, days: DEFAULT_KLINE_DAYS }).catch(() => []);
  }

  async function loadStockData(symbol: string) {
    currentSymbol.value = symbol;
    loading.value = true;
    error.value = null;
    loadStage.value = 'fetching';
    loadMessage.value = '';

    try {
      const [quotes, kline] = await Promise.all([
        fetchQuotes([symbol]).catch((e) => {
          console.warn('Quotes fetch failed, using empty', e);
          return [] as MarketQuote[];
        }),
        ensureData(symbol),
      ]);
      realtimeQuote.value = quotes.length > 0 ? quotes[0] : null;
      klineData.value = kline;
      loadStage.value = 'ready';
      loadMessage.value = '';
    } catch (e) {
      error.value = e instanceof Error ? e.message : '加载失败';
      loadStage.value = 'error';
    } finally {
      loading.value = false;
    }
  }

  return {
    currentSymbol,
    realtimeQuote,
    klineData,
    loading,
    loadStage,
    loadMessage,
    error,
    stockName,
    loadStockData,
  };
});
