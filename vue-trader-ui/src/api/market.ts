import client from './client';
import type {
  MarketQuote,
  KLineDataPoint,
  HistoryIngestResult,
  CompletenessResult,
  BackfillResponse,
} from '@/types/market';

export const fetchQuotes = (symbols: string[]): Promise<MarketQuote[]> =>
  client.get('/api/market/quotes', { params: { symbols: symbols.join(',') } });

export const fetchKLineHistory = (params: {
  symbol: string;
  startDate?: string;
  endDate?: string;
  days?: number;
  adjustType?: string;
}): Promise<KLineDataPoint[]> =>
  client.get('/api/market/history/kline', { params });

export const ingestHistory = (symbols: string[], months: number): Promise<HistoryIngestResult> =>
  client.post('/api/market/history/ingest', { symbols, months });

export const checkCompleteness = (params: {
  symbol: string;
  startDate: string;
  endDate: string;
  adjustType?: string;
}): Promise<CompletenessResult> =>
  client.get('/api/market/history/completeness', { params });

export const triggerBackfill = (body: {
  symbol: string;
  startDate: string;
  endDate: string;
  adjustType?: string;
}): Promise<BackfillResponse> =>
  client.post('/api/market/history/backfill', body, { timeout: 120000 });
