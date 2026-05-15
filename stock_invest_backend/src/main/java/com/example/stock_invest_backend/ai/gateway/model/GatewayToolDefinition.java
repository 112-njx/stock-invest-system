package com.example.stock_invest_backend.ai.gateway.model;

import java.util.List;
import java.util.Map;

public class GatewayToolDefinition {

    private String name;
    private String description;
    private Map<String, Object> parameters;
    private List<String> required;

    public GatewayToolDefinition() {
    }

    public GatewayToolDefinition(String name, String description,
                                  Map<String, Object> parameters, List<String> required) {
        this.name = name;
        this.description = description;
        this.parameters = parameters;
        this.required = required;
    }

    public String getName() {
        return name;
    }

    public void setName(String name) {
        this.name = name;
    }

    public String getDescription() {
        return description;
    }

    public void setDescription(String description) {
        this.description = description;
    }

    public Map<String, Object> getParameters() {
        return parameters;
    }

    public void setParameters(Map<String, Object> parameters) {
        this.parameters = parameters;
    }

    public List<String> getRequired() {
        return required;
    }

    public void setRequired(List<String> required) {
        this.required = required;
    }
}
