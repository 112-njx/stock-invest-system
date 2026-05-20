package com.example.stock_invest_backend.market.config;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.web.reactive.function.client.WebClient;

@Configuration
@EnableConfigurationProperties({MarketDataProperties.class, EastMoneyProperties.class})
public class MarketDataConfig {

    @Bean
    @Qualifier("eastMoneyWebClient")
    public WebClient eastMoneyWebClient(EastMoneyProperties eastMoneyProperties) {
        return WebClient.builder()
                .baseUrl(eastMoneyProperties.getBaseUrl())
                .defaultHeader(HttpHeaders.USER_AGENT,
                        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
                                + " (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36")
                .defaultHeader(HttpHeaders.ACCEPT, MediaType.APPLICATION_JSON_VALUE)
                .build();
    }

    @Bean
    @Qualifier("eastMoneyHistoryWebClient")
    public WebClient eastMoneyHistoryWebClient() {
        return WebClient.builder()
                .baseUrl("https://push2his.eastmoney.com")
                .defaultHeader(HttpHeaders.USER_AGENT,
                        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
                                + " (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36")
                .defaultHeader(HttpHeaders.ACCEPT, MediaType.APPLICATION_JSON_VALUE)
                .build();
    }
}
