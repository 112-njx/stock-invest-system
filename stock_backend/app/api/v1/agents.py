"""用户定制 Agent API：创建（支持从模板）/列表/详情/启停更新/删除。"""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db
from app.core.response import ok
from app.models.user import User
from app.schemas.agent import AgentCreateIn, AgentOut, AgentUpdateIn
from app.services import agent_service

router = APIRouter(prefix="/api/v1/agents", tags=["agents"])


@router.post("")
def create_agent(
    payload: AgentCreateIn,
    current: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    ag = agent_service.create_agent(db, current.id, payload)
    return ok(data=AgentOut.model_validate(ag).model_dump(mode="json"), msg="创建成功")


@router.get("")
def list_agents(current: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    rows = agent_service.list_agents(db, current.id)
    return ok(data=[AgentOut.model_validate(a).model_dump(mode="json") for a in rows])


@router.get("/{agent_id}")
def get_agent(
    agent_id: int,
    current: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    ag = agent_service.get_agent(db, current.id, agent_id)
    return ok(data=AgentOut.model_validate(ag).model_dump(mode="json"))


@router.patch("/{agent_id}")
def update_agent(
    agent_id: int,
    payload: AgentUpdateIn,
    current: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    ag = agent_service.update_agent(db, current.id, agent_id, payload)
    return ok(data=AgentOut.model_validate(ag).model_dump(mode="json"), msg="更新成功")


@router.delete("/{agent_id}")
def delete_agent(
    agent_id: int,
    current: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    agent_service.delete_agent(db, current.id, agent_id)
    return ok(msg="删除成功")
