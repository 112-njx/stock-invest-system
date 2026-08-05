package com.example.stock_invest_backend.pay;

import com.alipay.api.AlipayApiException;
import com.baomidou.mybatisplus.core.metadata.IPage;
import jakarta.servlet.http.HttpServletRequest;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

import java.util.HashMap;
import java.util.List;
import java.util.Map;

@RestController
@RequestMapping("/api/pay")
public class PayOrderController {

    private static final Logger log = LoggerFactory.getLogger(PayOrderController.class);
    private final PayOrderService payOrderService;
    private final AlipayClientService alipayClientService;

    public PayOrderController(PayOrderService payOrderService, AlipayClientService alipayClientService) {
        this.payOrderService = payOrderService;
        this.alipayClientService = alipayClientService;
    }

    @PostMapping("/create")
    public ResponseEntity<?> createOrder(@RequestBody CreatePayOrderRequest req) {
        if (req.getAmount() == null) {
            return ResponseEntity.badRequest().body(Map.of("error", "amount不能为空"));
        }
        PayOrder order;
        try {
            order = payOrderService.createOrder(req.getAmount());
        } catch (IllegalArgumentException e) {
            return ResponseEntity.badRequest().body(Map.of("error", e.getMessage()));
        }
        try {
            String payForm = alipayClientService.createPagePay(
                    order.getPayOrderId(), order.getAmount(), order.getSubject());
            CreatePayOrderResponse resp = new CreatePayOrderResponse();
            resp.setPayOrderId(order.getPayOrderId());
            resp.setAmount(order.getAmount());
            resp.setSubject(order.getSubject());
            resp.setPayForm(payForm);
            return ResponseEntity.ok(resp);
        } catch (AlipayApiException e) {
            log.error("创建支付宝订单失败: orderId={}", order.getPayOrderId(), e);
            return ResponseEntity.internalServerError()
                    .body(Map.of("error", "支付宝接口调用失败", "payOrderId", order.getPayOrderId()));
        }
    }

    @PostMapping("/notify")
    public String alipayNotify(HttpServletRequest request) {
        Map<String, String> params = new HashMap<>();
        request.getParameterMap().forEach((k, v) -> params.put(k, v[0]));

        if (!alipayClientService.verifyNotifySign(params)) {
            log.warn("支付回调验签失败");
            return "failure";
        }

        String payOrderId = params.get("out_trade_no");
        String tradeNo = params.get("trade_no");
        String tradeStatus = params.get("trade_status");
        String totalAmount = params.get("total_amount");
        log.info("支付回调: payOrderId={}, tradeNo={}, status={}, amount={}",
                payOrderId, tradeNo, tradeStatus, totalAmount);

        PayOrder order = payOrderService.getById(payOrderId);
        if (order == null) {
            log.warn("回调订单不存在: payOrderId={}", payOrderId);
            return "failure";
        }

        long notifyAmountFen = Math.round(Double.parseDouble(totalAmount) * 100);
        if (notifyAmountFen != order.getAmount()) {
            log.warn("回调金额不匹配: orderId={}, expected={}, got={}",
                    payOrderId, order.getAmount(), notifyAmountFen);
            return "failure";
        }

        if ("TRADE_SUCCESS".equals(tradeStatus) || "TRADE_FINISHED".equals(tradeStatus)) {
            payOrderService.updateToSuccess(payOrderId, tradeNo);
        }
        return "success";
    }

    @GetMapping("/query")
    public ResponseEntity<?> queryOrder(@RequestParam String payOrderId) {
        PayOrder order = payOrderService.getById(payOrderId);
        if (order == null) {
            return ResponseEntity.badRequest().body(Map.of("error", "订单不存在"));
        }
        return ResponseEntity.ok(PayOrderStatusResponse.fromEntity(order));
    }

    @GetMapping("/orders")
    public ResponseEntity<?> listOrders(@RequestParam(defaultValue = "1") int page,
                                        @RequestParam(defaultValue = "20") int size) {
        IPage<PayOrder> result = payOrderService.listOrders(page, size);
        List<PayOrderStatusResponse> items = result.getRecords().stream()
                .map(PayOrderStatusResponse::fromEntity).toList();
        return ResponseEntity.ok(Map.of(
                "items", items,
                "total", result.getTotal(),
                "page", result.getCurrent(),
                "size", result.getSize()
        ));
    }
}