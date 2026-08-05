package com.example.stock_invest_backend.market.history.service;

import com.example.stock_invest_backend.market.history.config.PythonResearchProperties;
import com.example.stock_invest_backend.market.history.dto.IngestResult;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;

import java.io.BufferedReader;
import java.io.File;
import java.io.IOException;
import java.io.InputStreamReader;
import java.nio.charset.StandardCharsets;
import java.time.LocalDate;
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.TimeUnit;

@Service
public class PythonIngestInvoker {

    private static final Logger log = LoggerFactory.getLogger(PythonIngestInvoker.class);
    private static final ObjectMapper MAPPER = new ObjectMapper();

    private final PythonResearchProperties properties;

    public PythonIngestInvoker(PythonResearchProperties properties) {
        this.properties = properties;
    }

    public IngestResult ingestSingle(String symbol,
                                     LocalDate startDate,
                                     LocalDate endDate,
                                     String adjustType,
                                     String requestId) {
        List<String> cmd = new ArrayList<>();
        cmd.add(properties.getCommandBase());
        cmd.add(properties.getSingleScript());
        cmd.add("--symbol"); cmd.add(symbol);
        cmd.add("--start-date"); cmd.add(startDate.toString());
        cmd.add("--end-date"); cmd.add(endDate.toString());
        cmd.add("--adjust-type"); cmd.add(adjustType);
        if (requestId != null && !requestId.isBlank()) {
            cmd.add("--request-id"); cmd.add(requestId);
        }

        log.info("[{}] INGEST_INVOKE symbol={} range={}~{} adjust={} cwd={}",
                requestId, symbol, startDate, endDate, adjustType, properties.getWorkingDir());

        ProcessBuilder pb = new ProcessBuilder(cmd)
                .directory(new File(properties.getWorkingDir()))
                .redirectErrorStream(false);

        long t0 = System.currentTimeMillis();
        Process process = null;
        try {
            process = pb.start();
            List<String> stdoutLines = new ArrayList<>();
            List<String> stderrLines = new ArrayList<>();
            Thread outThread = drain(process, true, stdoutLines);
            Thread errThread = drain(process, false, stderrLines);

            boolean finished = process.waitFor(properties.getTimeoutSeconds(), TimeUnit.SECONDS);
            outThread.join(1000);
            errThread.join(1000);

            if (!finished) {
                process.destroyForcibly();
                return fail(symbol, requestId, "INVOKE_TIMEOUT",
                        "python ingest timed out after " + properties.getTimeoutSeconds() + "s");
            }

            long elapsed = System.currentTimeMillis() - t0;
            IngestResult parsed = parseLastJson(stdoutLines);
            if (parsed == null) {
                String tail = stderrLines.isEmpty()
                        ? "no stdout json emitted"
                        : String.join(" | ", stderrLines.subList(Math.max(0, stderrLines.size() - 3), stderrLines.size()));
                log.warn("[{}] INGEST_UNPARSEABLE exitCode={} stderr={}", requestId, process.exitValue(), tail);
                return fail(symbol, requestId, "INVOKE_UNPARSEABLE", tail);
            }

            if (parsed.getElapsedMs() == null) parsed.setElapsedMs(elapsed);
            log.info("[{}] INGEST_DONE symbol={} status={} rows={} elapsedMs={}",
                    requestId, symbol, parsed.getStatus(), parsed.getRows(), parsed.getElapsedMs());
            return parsed;
        } catch (IOException ex) {
            return fail(symbol, requestId, "INVOKE_IO", ex.getMessage());
        } catch (InterruptedException ex) {
            Thread.currentThread().interrupt();
            if (process != null) process.destroyForcibly();
            return fail(symbol, requestId, "INVOKE_INTERRUPTED", ex.getMessage());
        }
    }

    private Thread drain(Process process, boolean stdout, List<String> sink) {
        Thread t = new Thread(() -> {
            try (BufferedReader reader = new BufferedReader(new InputStreamReader(
                    stdout ? process.getInputStream() : process.getErrorStream(),
                    StandardCharsets.UTF_8))) {
                String line;
                while ((line = reader.readLine()) != null) {
                    sink.add(line);
                    if (!stdout) log.debug("[python-stderr] {}", line);
                }
            } catch (IOException ignored) {
            }
        }, stdout ? "py-stdout" : "py-stderr");
        t.setDaemon(true);
        t.start();
        return t;
    }

    private IngestResult parseLastJson(List<String> lines) {
        for (int i = lines.size() - 1; i >= 0; i--) {
            String line = lines.get(i).trim();
            if (line.startsWith("{") && line.endsWith("}")) {
                try {
                    return MAPPER.readValue(line, IngestResult.class);
                } catch (IOException ignored) {
                }
            }
        }
        return null;
    }

    private IngestResult fail(String symbol, String requestId, String errorCode, String message) {
        IngestResult r = new IngestResult();
        r.setSymbol(symbol);
        r.setRequestId(requestId);
        r.setStatus("FAIL");
        r.setErrorCode(errorCode);
        r.setMessage(message);
        return r;
    }
}
