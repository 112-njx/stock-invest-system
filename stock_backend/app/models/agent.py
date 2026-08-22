"""智能体域（LangChain/LangGraph）：定制 Agent、运行记录、步骤、向量记忆切片。"""

from datetime import datetime

from sqlalchemy import JSON, BigInteger, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class UserAgent(Base):
    __tablename__ = "user_agents"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    name: Mapped[str] = mapped_column(String(64), nullable=False)
    agent_type: Mapped[str] = mapped_column(
        String(32), nullable=False, default="custom"
    )  # diagnostic/plan/radar/strategy/custom
    system_prompt: Mapped[str | None] = mapped_column(Text)
    tools: Mapped[dict | None] = mapped_column(JSON)
    llm_config: Mapped[dict | None] = mapped_column(JSON)
    memory_config: Mapped[dict | None] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="draft")  # active/draft
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default="now()")
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default="now()")


class AgentRun(Base):
    __tablename__ = "agent_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    agent_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("user_agents.id", ondelete="SET NULL"))
    conversation_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("conversations.id", ondelete="SET NULL"))
    symbol_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("symbols.id", ondelete="SET NULL"))
    run_type: Mapped[str] = mapped_column(String(32), nullable=False)  # diagnostic/strategy/radar/plan/custom
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="queued")  # queued/running/success/failed
    input: Mapped[str | None] = mapped_column(Text)
    output: Mapped[str | None] = mapped_column(Text)
    tokens: Mapped[int | None] = mapped_column(Integer)
    error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default="now()")
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default="now()")


class AgentStep(Base):
    __tablename__ = "agent_steps"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("agent_runs.id", ondelete="CASCADE"), nullable=False)
    step_name: Mapped[str] = mapped_column(String(64), nullable=False)
    agent_role: Mapped[str] = mapped_column(String(32), nullable=False)  # analyst/researcher/manager/trader
    content: Mapped[str | None] = mapped_column(Text)
    meta: Mapped[dict | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default="now()")


class MemoryChunk(Base):
    __tablename__ = "memory_chunks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    source_type: Mapped[str] = mapped_column(String(32), nullable=False)  # strategy/rule/preference/backtest
    source_id: Mapped[int | None] = mapped_column(BigInteger)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    vector_id: Mapped[str | None] = mapped_column(String(64))
    file_path: Mapped[str | None] = mapped_column(String(512))
    importance: Mapped[int] = mapped_column(Integer, nullable=False, default=5)  # 重要性 1-10（检索加权 + 低重要性清理）
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default="now()")
