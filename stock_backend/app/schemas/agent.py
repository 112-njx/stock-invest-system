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


class AgentRunOut(BaseModel):
    """Agent 运行记录（GET /agent/runs，供前端 AgentRunsDialog）。"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    agent_id: int | None = None
    conversation_id: int | None = None
    symbol_id: int | None = None
    run_type: str
    status: str
    input: str | None = None
    output: str | None = None
    tokens: int | None = None
    error: str | None = None
    created_at: datetime
    updated_at: datetime


class AgentStepOut(BaseModel):
    """Agent 运行步骤（GET /agent/runs/{id} 内嵌）。"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    run_id: int
    step_name: str
    agent_role: str
    content: str | None = None
    meta: dict[str, Any] | None = None
    created_at: datetime


class MemoryFileOut(BaseModel):
    """本地记忆文件（GET /memory/files，path 对应模型 file_path）。"""

    model_config = ConfigDict(from_attributes=True)

    path: str = Field(validation_alias="file_path")
    content_type: str
    updated_at: datetime


class MemoryFactOut(BaseModel):
    """单条记忆事实（GET /memory/facts，阶段六 6.4 记忆管理 API）。"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    content: str
    importance: int
    source_type: str
    source_id: int | None = None
    created_at: datetime
