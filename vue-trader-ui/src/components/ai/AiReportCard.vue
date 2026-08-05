<template>
  <div class="ai-report-card">
    <el-card shadow="always" class="ai-inner">
      <template #header>
        <div class="ai-header">
          <span class="ai-title">AI 投资分析（{{ report.mode }}）</span>
          <el-button size="small" text @click="$emit('close')">
            <el-icon color="#fff"><Close /></el-icon>
          </el-button>
        </div>
      </template>

      <div v-if="report.degraded" class="degraded-banner">
        AI 分析已降级：{{ report.fallbackReason || 'unknown' }}
      </div>

      <div class="analysis-text">{{ report.analysisText }}</div>

      <div v-if="report.toolCalls && report.toolCalls.length > 0" class="tool-list">
        <div class="tool-title">调用工具：</div>
        <div v-for="(t, idx) in report.toolCalls" :key="idx" class="tool-item">
          {{ t.toolName }}({{ formatArgs(t.arguments) }})
        </div>
      </div>

      <div class="meta-row">
        <span>{{ formatTime(report.replyTime) }}</span>
        <span v-if="report.usedDays > 0">· 使用 {{ report.usedDays }} 天 K 线</span>
        <span v-if="report.symbol">· {{ report.symbol }}</span>
      </div>

      <p class="disclaimer">{{ report.disclaimer }}</p>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { Close } from '@element-plus/icons-vue';
import type { AiAnalyzeResponse } from '@/types/ai';

defineProps<{ report: AiAnalyzeResponse }>();
defineEmits<{ close: [] }>();

function formatArgs(args: Record<string, unknown>): string {
  return Object.entries(args)
    .map(([k, v]) => `${k}=${v}`)
    .join(', ');
}

function formatTime(iso: string): string {
  if (!iso) return '';
  try {
    return new Date(iso).toLocaleString('zh-CN', { hour12: false });
  } catch {
    return iso;
  }
}
</script>

<style scoped>
.ai-report-card {
  position: absolute;
  top: 240px;
  right: 340px;
  z-index: 200;
  width: 340px;
  max-height: 60vh;
  overflow: hidden;
}
.ai-inner {
  background: rgba(26, 26, 46, 0.95);
  border: 1px solid #444;
  max-height: 60vh;
  overflow-y: auto;
}
.ai-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-size: 13px;
}
.ai-title { color: #fff; font-weight: 600; }
.degraded-banner {
  margin-bottom: 8px;
  padding: 6px 8px;
  font-size: 11px;
  color: #FFE082;
  background: rgba(255, 152, 0, 0.15);
  border-left: 2px solid #FFA726;
}
.analysis-text {
  font-size: 13px;
  color: #e0e0e0;
  line-height: 1.6;
  white-space: pre-wrap;
  word-break: break-word;
}
.tool-list {
  margin-top: 10px;
  padding-top: 8px;
  border-top: 1px dashed #333;
  font-size: 11px;
  color: #888;
}
.tool-title { color: #aaa; margin-bottom: 3px; }
.tool-item { color: #9C27B0; font-family: monospace; }
.meta-row {
  margin-top: 8px;
  font-size: 11px;
  color: #666;
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
}
.disclaimer {
  margin-top: 6px;
  padding: 4px 6px;
  font-size: 10px;
  color: #F8BBD0;
  background: rgba(248, 187, 208, 0.08);
  border-left: 2px solid #F8BBD0;
  line-height: 1.4;
}
</style>
