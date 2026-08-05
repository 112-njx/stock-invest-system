import client from './client';
import type { MaBacktestRequest, MaBacktestResponse, BacktestResultView } from '@/types/backtest';

export const executeMaBacktest = (req: MaBacktestRequest): Promise<MaBacktestResponse> =>
  client.post('/api/backtest/ma', req);

export const fetchBacktestResults = (params: {
  symbol: string;
  strategyCode?: string;
  limit?: number;
}): Promise<BacktestResultView[]> =>
  client.get('/api/backtest/results', { params });
