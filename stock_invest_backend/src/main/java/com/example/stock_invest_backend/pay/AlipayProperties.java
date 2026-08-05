package com.example.stock_invest_backend.pay;

import lombok.Data;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.stereotype.Component;

@Data
@Component
@ConfigurationProperties(prefix = "pay.alipay")
public class AlipayProperties {
    private String appId;
    private String privateKey;
    private String alipayPublicKey;
    private String gateway = "https://openapi-sandbox.dl.alipaydev.com/gateway.do";
    private String notifyUrl;
    private String returnUrl;
}
