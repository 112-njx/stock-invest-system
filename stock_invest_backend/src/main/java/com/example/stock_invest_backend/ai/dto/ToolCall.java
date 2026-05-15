package com.example.stock_invest_backend.ai.dto;

import java.util.Map;

public class ToolCall {

    private String toolName;
    private Map<String, Object> arguments;

    public ToolCall() {
    }

    public ToolCall(String toolName, Map<String, Object> arguments) {
        this.toolName = toolName;
        this.arguments = arguments;
    }

    public String getToolName() {
        return toolName;
    }

    public void setToolName(String toolName) {
        this.toolName = toolName;
    }

    public Map<String, Object> getArguments() {
        return arguments;
    }

    public void setArguments(Map<String, Object> arguments) {
        this.arguments = arguments;
    }
}
