package com.example.stock_invest_backend.market.history.config;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.context.annotation.Configuration;

@Configuration
@ConfigurationProperties(prefix = "python.research.service")
public class PythonResearchProperties {

    private String commandBase = "python";
    private String workingDir = "../python-research-service";
    private int timeoutSeconds = 300;
    private String singleScript = "scripts/ingest_single.py";
    private String healthScript = "scripts/health_check.py";

    public String getCommandBase() { return commandBase; }
    public void setCommandBase(String commandBase) { this.commandBase = commandBase; }

    public String getWorkingDir() { return workingDir; }
    public void setWorkingDir(String workingDir) { this.workingDir = workingDir; }

    public int getTimeoutSeconds() { return timeoutSeconds; }
    public void setTimeoutSeconds(int timeoutSeconds) { this.timeoutSeconds = timeoutSeconds; }

    public String getSingleScript() { return singleScript; }
    public void setSingleScript(String singleScript) { this.singleScript = singleScript; }

    public String getHealthScript() { return healthScript; }
    public void setHealthScript(String healthScript) { this.healthScript = healthScript; }
}
