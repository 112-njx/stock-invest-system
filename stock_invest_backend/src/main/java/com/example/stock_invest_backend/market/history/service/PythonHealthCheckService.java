package com.example.stock_invest_backend.market.history.service;

import com.example.stock_invest_backend.market.history.config.PythonResearchProperties;
import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;

import java.io.BufferedReader;
import java.io.File;
import java.io.IOException;
import java.io.InputStreamReader;
import java.nio.charset.StandardCharsets;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.concurrent.TimeUnit;

@Service
public class PythonHealthCheckService {

    private static final Logger log = LoggerFactory.getLogger(PythonHealthCheckService.class);
    private static final ObjectMapper MAPPER = new ObjectMapper();

    private final PythonResearchProperties properties;

    public PythonHealthCheckService(PythonResearchProperties properties) {
        this.properties = properties;
    }

    public Map<String, Object> runHealthCheck() {
        List<String> cmd = List.of(properties.getCommandBase(), properties.getHealthScript());
        ProcessBuilder pb = new ProcessBuilder(cmd)
                .directory(new File(properties.getWorkingDir()))
                .redirectErrorStream(false);
        Process process = null;
        try {
            process = pb.start();
            String stdout;
            try (BufferedReader reader = new BufferedReader(
                    new InputStreamReader(process.getInputStream(), StandardCharsets.UTF_8))) {
                stdout = reader.readLine();
                while (reader.readLine() != null) { /* drain */ }
            }
            boolean finished = process.waitFor(30, TimeUnit.SECONDS);
            if (!finished) {
                process.destroyForcibly();
                return Map.of("overall", "FAIL", "message", "health check timeout");
            }
            if (stdout == null || stdout.isBlank()) {
                return Map.of("overall", "FAIL", "message", "empty stdout");
            }
            return MAPPER.readValue(stdout, new TypeReference<Map<String, Object>>() {});
        } catch (IOException | InterruptedException ex) {
            if (ex instanceof InterruptedException) Thread.currentThread().interrupt();
            if (process != null) process.destroyForcibly();
            log.warn("health check failed: {}", ex.getMessage());
            Map<String, Object> err = new HashMap<>();
            err.put("overall", "FAIL");
            err.put("message", ex.getMessage());
            return err;
        }
    }
}
