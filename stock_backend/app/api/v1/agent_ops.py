"""Agent 运行记录 / 本地记忆文件 API（阶段五补齐：前端已对接但后端缺失的编排接口）。

- GET /api/v1/agent/runs          运行历史（前端 AgentRunsDialog）
- GET /api/v1/agent/runs/{id}     运行详情（内嵌 agent_steps）
- GET /api/v1/memory/files        本地记忆文件列表（前端 MemoryFilesDialog）
"""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db
from app.core.response import ok
from app.models.user import User
from app.schemas.agent import AgentRunOut, AgentStepOut, MemoryFileOut
from app.services import agent_service

router = APIRouter(prefix="/api/v1", tags=["agent-ops"])


@router.get("/agent/runs")
def list_agent_runs(current: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    rows = agent_service.list_runs(db, current.id)
    return ok(data=[AgentRunOut.model_validate(r).model_dump(mode="json") for r in rows])


@router.get("/agent/runs/{run_id}")
def get_agent_run(
    run_id: int,
    current: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    run = agent_service.get_run(db, current.id, run_id)
    steps = agent_service.list_steps(db, run.id)
    return ok(
        data={
            **AgentRunOut.model_validate(run).model_dump(mode="json"),
            "steps": [AgentStepOut.model_validate(s).model_dump(mode="json") for s in steps],
        }
    )


@router.get("/memory/files")
def list_memory_files(current: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    rows = agent_service.list_memory_files(db, current.id)
    return ok(data=[MemoryFileOut.model_validate(f).model_dump(mode="json") for f in rows])
