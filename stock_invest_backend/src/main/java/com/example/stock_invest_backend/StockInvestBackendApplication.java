package com.example.stock_invest_backend;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.ComponentScan;
import org.springframework.context.annotation.FilterType;
import org.springframework.scheduling.annotation.EnableScheduling;

@EnableScheduling
@SpringBootApplication
@ComponentScan(
        basePackages = "com.example.stock_invest_backend",
        excludeFilters = @ComponentScan.Filter(
                type = FilterType.REGEX,
                pattern = "com\\.example\\.stock_invest_backend\\.pay\\..*"
        )
)
public class StockInvestBackendApplication {

    public static void main(String[] args) {
        SpringApplication.run(StockInvestBackendApplication.class, args);
    }

}
