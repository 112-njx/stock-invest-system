"""智能体域读写：user_agents / agent_runs / agent_steps / memory_chunks。

多租户隔离（借鉴 QuantDinger）：所有查询强制带 user_id 过滤。
"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.agent import AgentRun, AgentStep, MemoryChunk, UserAgent
from app.models.user import UserMemoryFile


# ---- user_agents（3.7 使用）----
def create_agent(
    db: Session,
    user_id: int,
    name: str,
    agent_type: str,
    system_prompt: str | None,
    tools: dict | None,
    llm_config: dict | None,
    memory_config: dict | None,
    status: str,
) -> UserAgent:
    ag = UserAgent(
        user_id=user_id,
        name=name,
        agent_type=agent_type,
        system_prompt=system_prompt,
        tools=tools,
        llm_config=llm_config,
        memory_config=memory_config,
        status=status,
    )
    db.add(ag)
    db.flush()
    return ag


def list_agents(db: Session, user_id: int) -> list[UserAgent]:
    return list(db.scalars(select(UserAgent).where(UserAgent.user_id == user_id).order_by(UserAgent.id.desc())))


def get_agent(db: Session, user_id: int, agent_id: int) -> UserAgent | None:
    return db.scalar(select(UserAgent).where(UserAgent.id == agent_id, UserAgent.user_id == user_id))


def update_agent(db: Session, ag: UserAgent, **fields) -> UserAgent:
    for k, v in fields.items():
        if v is not None:
            setattr(ag, k, v)
    db.flush()
    return ag


def delete_agent(db: Session, user_id: int, agent_id: int) -> bool:
    ag = get_agent(db, user_id, agent_id)
    if ag is None:
        return False
    db.delete(ag)
    db.flush()
    return True


# ---- agent_runs ----
def create_run(
    db: Session,
    user_id: int,
    run_type: str,
    input_text: str | None,
    agent_id: int | None = None,
    conversation_id: int | None = None,
    symbol_id: int | None = None,
) -> AgentRun:
    run = AgentRun(
        user_id=user_id,
        agent_id=agent_id,
        conversation_id=conversation_id,
        symbol_id=symbol_id,
        run_type=run_type,
        status="running",
        input=input_text,
    )
    db.add(run)
    db.flush()
    return run


def finish_run(db: Session, run: AgentRun, *, status: str, output: str | None = None, tokens: int | None = None, error: str | None = None) -> None:
    run.status = status
    if output is not None:
        run.output = output
    if tokens is not None:
        run.tokens = tokens
    if error is not None:
        run.error = error
    db.flush()


# ---- agent_runs 查询（5.5 补齐：GET /agent/runs 运行记录）----
def list_runs(db: Session, user_id: int, limit: int = 50) -> list[AgentRun]:
    return list(
        db.scalars(select(AgentRun).where(AgentRun.user_id == user_id).order_by(AgentRun.id.desc()).limit(limit))
    )


def get_run(db: Session, user_id: int, run_id: int) -> AgentRun | None:
    return db.scalar(select(AgentRun).where(AgentRun.id == run_id, AgentRun.user_id == user_id))


# ---- agent_steps ----
def add_step(
    db: Session,
    run_id: int,
    step_name: str,
    agent_role: str,
    content: str | None,
    meta: dict | None = None,
) -> AgentStep:
    step = AgentStep(run_id=run_id, step_name=step_name, agent_role=agent_role, content=content, meta=meta)
    db.add(step)
    db.flush()
    return step


def list_steps(db: Session, run_id: int) -> list[AgentStep]:
    return list(db.scalars(select(AgentStep).where(AgentStep.run_id == run_id).order_by(AgentStep.id)))


# ---- user_memory_files（5.5 补齐：GET /memory/files 记忆文件）----
def list_memory_files(db: Session, user_id: int) -> list[UserMemoryFile]:
    return list(
        db.scalars(select(UserMemoryFile).where(UserMemoryFile.user_id == user_id).order_by(UserMemoryFile.id.desc()))
    )


# ---- memory_chunks ----
def add_memory_chunk(
    db: Session,
    user_id: int,
    source_type: str,
    source_id: int | None,
    content: str,
    vector_id: str,
    file_path: str | None,
) -> MemoryChunk:
    row = MemoryChunk(
        user_id=user_id,
        source_type=source_type,
        source_id=source_id,
        content=content,
        vector_id=vector_id,
        file_path=file_path,
    )
    db.add(row)
    db.flush()
    return row


def delete_memory_chunk_by_vector(db: Session, user_id: int, vector_id: str) -> None:
    row = db.scalar(select(MemoryChunk).where(MemoryChunk.user_id == user_id, MemoryChunk.vector_id == vector_id))
    if row:
        db.delete(row)
        db.flush()


def upsert_memory_file(db: Session, user_id: int, file_path: str, content_type: str) -> UserMemoryFile:
    row = db.scalar(select(UserMemoryFile).where(UserMemoryFile.user_id == user_id, UserMemoryFile.file_path == file_path))
    if row:
        row.content_type = content_type
    else:
        row = UserMemoryFile(user_id=user_id, file_path=file_path, content_type=content_type)
        db.add(row)
    db.flush()
    return row
