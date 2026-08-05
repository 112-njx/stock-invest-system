export interface AiToolCall {
  toolName: string;
  arguments: Record<string, unknown>;
}

export interface AiDataSource {
  api: string;
  purpose: string;
}

export interface AiAnalyzeRequest {
  prompt: string;
}

export interface AiAnalyzeResponse {
  requestId: string;
  mode: 'TOOL_CHAIN' | 'MACRO_ONLY' | string;
  prompt: string;
  symbol: string | null;
  usedDays: number;
  toolCalls: AiToolCall[];
  dataSources: AiDataSource[];
  analysisText: string;
  disclaimer: string;
  replyTime: string;
  degraded: boolean;
  fallbackReason: string | null;
  rawData: Record<string, unknown> | null;
}
