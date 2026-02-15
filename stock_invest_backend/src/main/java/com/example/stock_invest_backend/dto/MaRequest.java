package com.example.stock_invest_backend.dto;
import lombok.Data;
import java.util.List;

@Data
public class MaRequest {
    private String symbol;
    private int period;
    private List<Double> prices;
}
