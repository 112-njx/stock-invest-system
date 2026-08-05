import client from './client';
import type { AiAnalyzeRequest, AiAnalyzeResponse } from '@/types/ai';

export const postAiAnalyze = (body: AiAnalyzeRequest): Promise<AiAnalyzeResponse> =>
  client.post('/api/ai/invest/analyze', body, { timeout: 60000 });
