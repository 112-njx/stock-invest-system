<template>
  <div class="ai-backtest-page">
    <el-container class="page-container">
      <el-header class="page-header">
        <h2>AI 策略回测助手</h2>
        <el-tag type="info" size="small">即将上线</el-tag>
      </el-header>

      <el-container>
        <el-aside width="60%" class="chat-panel">
          <el-card shadow="never" class="chat-card">
            <template #header>
              <span>策略对话</span>
            </template>
            <div class="chat-messages">
              <div class="empty-state">
                <el-icon :size="48" color="#666"><ChatLineRound /></el-icon>
                <p>输入策略需求开始分析</p>
                <p class="hint">例如："测试平安银行过去10年均线策略表现"</p>
              </div>
            </div>
            <div class="chat-input-area">
              <el-input
                type="textarea"
                :rows="3"
                placeholder="输入自然语言描述您的策略需求..."
                disabled
              />
              <el-button type="primary" disabled class="send-btn">发送</el-button>
            </div>
          </el-card>
        </el-aside>

        <el-main class="result-panel">
          <el-card shadow="never" class="result-card">
            <template #header><span>回测结果</span></template>
            <div class="empty-state">
              <el-icon :size="36" color="#666"><DataAnalysis /></el-icon>
              <p>提交回测任务后在此查看结果</p>
            </div>
          </el-card>

          <el-card shadow="never" class="trade-card" style="margin-top: 12px">
            <template #header><span>交易明细</span></template>
            <div class="empty-state">
              <el-icon :size="36" color="#666"><List /></el-icon>
              <p>暂无交易记录</p>
            </div>
          </el-card>
        </el-main>
      </el-container>

      <el-footer class="page-footer">
        <el-text type="info" size="small">
          仅供学习和研究，不构成投资建议
        </el-text>
      </el-footer>
    </el-container>
  </div>
</template>

<script setup lang="ts">
import { ChatLineRound, DataAnalysis, List } from '@element-plus/icons-vue';
</script>

<style scoped>
.ai-backtest-page {
  width: 100%;
  height: 100vh;
  background: #1a1a2e;
  color: #e0e0e0;
}
.page-container {
  height: 100%;
  display: flex;
  flex-direction: column;
}
.page-header {
  display: flex;
  align-items: center;
  gap: 12px;
  height: 56px;
  border-bottom: 1px solid #333;
}
.page-header h2 {
  margin: 0;
  font-size: 18px;
}
.chat-panel {
  padding: 12px;
}
.chat-card {
  height: 100%;
  display: flex;
  flex-direction: column;
}
.chat-messages {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 300px;
}
.chat-input-area {
  display: flex;
  gap: 8px;
  align-items: flex-end;
  padding-top: 12px;
  border-top: 1px solid #333;
}
.send-btn {
  flex-shrink: 0;
}
.result-panel {
  padding: 12px;
}
.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 40px;
  color: #666;
  gap: 8px;
}
.hint {
  font-size: 12px;
  color: #555;
}
.page-footer {
  display: flex;
  align-items: center;
  justify-content: center;
  height: 40px;
  border-top: 1px solid #333;
}
</style>
