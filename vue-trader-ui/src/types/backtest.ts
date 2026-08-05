export interface MaBacktestRequest {
  symbol: string;
  period: number;
  startDate: string;
  endDate: string;
}

export interface BacktestSignal {
  date: string;
  signalCode: string;
  signal: string;
  legacySignal5: string;
  closePrice: number;
  ma: number;
}

export interface MaBacktestResponse {
  symbol: string;
  strategyCode: string;
  period: number;
  totalSignals: number;
  winSignals: number;
  successRate: number;
  records: number;
  source: string;
  message: string;
  crossUpDates: string[];
  crossDownDates: string[];
  signals: BacktestSignal[];
}

export interface BacktestResultView {
  id: number;
  strategyCode: string;
  symbol: string;
  period: number;
  startDate: string;
  endDate: string;
  totalSignals: number;
  winSignals: number;
  successRate: number;
  createdAt: string;
  crossUpDates: string[];
  crossDownDates: string[];
  signals: BacktestSignal[];
}

export interface KLineSignalMark {
  date: string;
  text: string;
  color: string;
  position: 'above' | 'below';
}
