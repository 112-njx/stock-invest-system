package com.example.stock_invest_backend.ai.gateway;

import com.example.stock_invest_backend.ai.gateway.model.GatewayAnalysisResult;
import com.example.stock_invest_backend.ai.gateway.model.GatewayToolCallResult;
import com.example.stock_invest_backend.ai.gateway.model.GatewayToolDefinition;

import java.util.List;

public interface AiGatewayClient {

    /**
     * 请求 LLM 根据用户 prompt 生成标准 Tool Call 列表。
     * 若 LLM 判断无需调用工具，返回空列表（success=true, toolCalls=[]）。
     */
    GatewayToolCallResult requestToolCalls(String systemPrompt, String userPrompt,
                                           List<GatewayToolDefinition> tools);

    /**
     * 请求 LLM 生成文本分析。
     **/
    GatewayAnalysisResult generateAnalysis(String systemPrompt, String userPrompt);

    /**
     * 返回当前使用的模型厂商名称，用于日志/监控。
     */
    String getProviderName();
}
