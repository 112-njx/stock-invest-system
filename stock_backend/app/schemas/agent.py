"""用户定制 Agent 响应模型（user_agents CRUD，统一由 {code, msg, data} 包裹）。"""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class AgentCreateIn(BaseModel):
    name: str = Field(..., min_length=1, max_length=64)
    agent_type: str = Field("custom", pattern="^(diagnostic|plan|radar|strategy|custom)$")
    system_prompt: str | None = None
    tools: dict[str, Any] | None = None
    llm_config: dict[str, Any] | None = None
    memory_config: dict[str, Any] | None = None
    status: str = Field("draft", pattern="^(active|draft)$")
    template: str | None = Field(None, description="从预设模板创建（technical/fundamental/risk_control）")


class AgentUpdateIn(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=64)
    agent_type: str | None = Field(None, pattern="^(diagnostic|plan|radar|strategy|custom)$")
    system_prompt: str | None = None
    tools: dict[str, Any] | None = None
    llm_config: dict[str, Any] | None = None
    memory_config: dict[str, Any] | None = None
    status: str | None = Field(None, pattern="^(active|draft)$")


class AgentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    agent_type: str
    system_prompt: str | None = None
    tools: dict[str, Any] | None = None
    llm_config: dict[str, Any] | None = None
    memory_config: dict[str, Any] | None = None
    status: str
    created_at: datetime
    updated_at: datetime
