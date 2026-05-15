package com.example.stock_invest_backend.ai.config;

import com.example.stock_invest_backend.ai.gateway.AiGatewayClient;
import com.example.stock_invest_backend.ai.gateway.DeepSeekAiGatewayClient;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Primary;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.web.reactive.function.client.WebClient;

@Configuration
@EnableConfigurationProperties(DeepSeekProperties.class)
public class AiConfig {

    @Bean
    @Qualifier("deepSeekWebClient")
    public WebClient deepSeekWebClient(DeepSeekProperties properties) {
        return WebClient.builder()
                .baseUrl(properties.getBaseUrl())
                .defaultHeader(HttpHeaders.CONTENT_TYPE, MediaType.APPLICATION_JSON_VALUE)
                .defaultHeader(HttpHeaders.AUTHORIZATION, "Bearer " + properties.getApiKey())
                .build();
    }

    @Bean
    @Primary
    public AiGatewayClient aiGatewayClient(DeepSeekAiGatewayClient deepSeekClient) {
        return deepSeekClient;
    }
}
