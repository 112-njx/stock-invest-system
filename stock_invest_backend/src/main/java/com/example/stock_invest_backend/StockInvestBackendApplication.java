package com.example.stock_invest_backend;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.jdbc.autoconfigure.DataSourceAutoConfiguration;
import org.springframework.scheduling.annotation.EnableScheduling;

@EnableScheduling
@SpringBootApplication(
        exclude = { DataSourceAutoConfiguration.class }
)
public class StockInvestBackendApplication {

    public static void main(String[] args) {
        SpringApplication.run(StockInvestBackendApplication.class, args);
    }

}
