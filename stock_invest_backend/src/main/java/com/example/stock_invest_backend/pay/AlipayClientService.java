package com.example.stock_invest_backend.pay;

import com.alipay.api.AlipayApiException;
import com.alipay.api.AlipayClient;
import com.alipay.api.DefaultAlipayClient;
import com.alipay.api.internal.util.AlipaySignature;
import com.alipay.api.request.AlipayTradePagePayRequest;
import jakarta.annotation.PostConstruct;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;

import java.math.BigDecimal;
import java.util.Map;

@Service
public class AlipayClientService {

    private static final Logger log = LoggerFactory.getLogger(AlipayClientService.class);
    private final AlipayProperties props;
    private AlipayClient alipayClient;

    public AlipayClientService(AlipayProperties props) {
        this.props = props;
    }

    @PostConstruct
    public void init() {
        this.alipayClient = new DefaultAlipayClient(
                props.getGateway(), props.getAppId(), props.getPrivateKey(),
                "json", "UTF-8", props.getAlipayPublicKey(), "RSA2");
        log.info("AlipayClient initialized: appId={}, gateway={}", props.getAppId(), props.getGateway());
    }

    public String createPagePay(String payOrderId, long amountFen, String subject) throws AlipayApiException {
        AlipayTradePagePayRequest request = new AlipayTradePagePayRequest();
        request.setNotifyUrl(props.getNotifyUrl());
        request.setReturnUrl(props.getReturnUrl());

        String amountYuan = BigDecimal.valueOf(amountFen).divide(BigDecimal.valueOf(100), 2, BigDecimal.ROUND_HALF_UP).toPlainString();
        request.setBizContent("{" +
                "\"out_trade_no\":\"" + payOrderId + "\"," +
                "\"total_amount\":\"" + amountYuan + "\"," +
                "\"subject\":\"" + subject + "\"," +
                "\"product_code\":\"FAST_INSTANT_TRADE_PAY\"" +
                "}");
        return alipayClient.pageExecute(request).getBody();
    }

    public boolean verifyNotifySign(Map<String, String> params) {
        try {
            return AlipaySignature.rsaCheckV1(params, props.getAlipayPublicKey(), "UTF-8", "RSA2");
        } catch (AlipayApiException e) {
            log.error("Alipay notify sign verify failed", e);
            return false;
        }
    }
}
