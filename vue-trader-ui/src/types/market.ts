export interface MarketQuote {
  symbol: string;
  lastPrice: number;
  changePercent: number;
  openPrice: number;
  highPrice: number;
  lowPrice: number;
  prevClosePrice: number;
  volume: number;
  turnover: number;
  quoteTimestamp: number;
  source: string;
}

export interface KLineDataPoint {
  tradeDate: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
  turnover: number;
}

export interface HistoryIngestResult {
  symbols: string[];
  months: number;
  affectedRows: number;
  note: string;
}

export interface MissingRange {
  start: string;
  end: string;
}

export interface CompletenessResult {
  symbol: string;
  adjustType: string;
  startDate: string;
  endDate: string;
  expected: number;
  actual: number;
  complete: boolean;
  missingRanges: MissingRange[];
  message: string;
}

export interface IngestResult {
  requestId?: string;
  symbol: string;
  status: 'OK' | 'FAIL' | string;
  errorCode?: string;
  message?: string;
  rows?: number;
  affected?: number;
  batches?: number;
  startDate?: string;
  endDate?: string;
  adjustType?: string;
  elapsedMs?: number;
}

export interface BackfillResponse {
  requestId: string;
  symbol: string;
  status: 'OK' | 'PARTIAL' | 'FAIL' | string;
  ingestResults: IngestResult[];
  completenessBefore: CompletenessResult;
  completenessAfter: CompletenessResult;
  elapsedMs: number;
}
