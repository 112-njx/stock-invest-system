package com.example.stock_invest_backend.controller;

import com.example.stock_invest_backend.dto.MaRequest;
import com.example.stock_invest_backend.dto.MaResponse;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.client.RestTemplate;
import java.util.List;

@RestController
@RequestMapping("/test")
public class MaController {

    @PostMapping("/ma")
    public MaResponse testMa() {

        RestTemplate restTemplate = new RestTemplate();

        MaRequest request = new MaRequest();
        request.setSymbol("000001");
        request.setPeriod(5);
        request.setPrices(List.of(10.1,10.5,10.8,11.0,10.9));

        return restTemplate.postForObject(
                "http://localhost:8080/api/analysis/ma",
                request,
                MaResponse.class
        );
    }
}
