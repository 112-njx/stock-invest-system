//注意：该history包属于自动生成假k线数据模块并且写入
package com.example.stock_invest_backend.market.history.config;

import lombok.Getter;
import lombok.Setter;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.stereotype.Component;

import java.util.ArrayList;
import java.util.List;

@Setter
@Getter
@Component
@ConfigurationProperties(prefix = "market.history.ingestion")
//读取 market.history.ingestion.* 配置。
//包含：
//enabled（是否启用定时导入）、months（默认回溯月数）、defaultSymbols（默认股票列表）。
public class HistoryIngestionProperties {

    private boolean enabled = false;
    private int months = 3;
    private List<String> defaultSymbols = new ArrayList<>(List.of("sh600519", "sz000001"));

}
