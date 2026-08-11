"""用户定制 Agent 服务：创建（支持从预设模板）/列表/启停/更新/删除，按 user 隔离。"""

from sqlalchemy.orm import Session

from app.core.exceptions import ApiError
from app.models.agent import AgentRun, AgentStep, UserAgent
from app.models.user import UserMemoryFile
from app.repositories import agent_repo

# 官方预设模板（借鉴 TradingAgents-CN 预设分析师角色；用户可从模板创建后微调）
AGENT_PRESETS: dict[str, dict] = {
    "technical": {
        "name": "技术分析型",
        "agent_type": "diagnostic",
        "system_prompt": "你是技术面分析师：以K线、量价、MACD/KDJ、支撑压力位为核心，给出明确的趋势判断、买卖点与失效止损。数据不可用必须明说，禁止编造。",
        "tools": {"market": True, "indicator": True, "memory": True},
        "llm_config": {"temperature": 0.3},
        "memory_config": {"enabled": True, "collection": "default"},
    },
    "fundamental": {
        "name": "基本面型",
        "agent_type": "diagnostic",
        "system_prompt": "你是基本面分析师：关注估值(PE/市值)、行业逻辑与长期价值，给出基于基本面的持有/买入/回避判断，并说明主要风险。数据不可用必须明说，禁止编造。",
        "tools": {"market": True, "indicator": True, "memory": True},
        "llm_config": {"temperature": 0.4},
        "memory_config": {"enabled": True, "collection": "default"},
    },
    "risk_control": {
        "name": "保守风控型",
        "agent_type": "custom",
        "system_prompt": "你是风控专员：以控制回撤为先，对每笔交易给出仓位上限、止损位与失效条件，宁可错过不可大亏。数据不可用必须明说，禁止编造。",
        "tools": {"market": True, "indicator": True, "memory": True},
        "llm_config": {"temperature": 0.2},
        "memory_config": {"enabled": True, "collection": "default"},
    },
}


def _apply_preset(payload) -> dict:
    """从模板填充默认配置（用户显式传入的字段优先）。"""
    preset = AGENT_PRESETS.get(payload.template) if payload.template else None
    if preset is None:
        return {}
    return {
        "name": payload.name or preset["name"],
        "agent_type": preset["agent_type"],
        "system_prompt": payload.system_prompt if payload.system_prompt else preset["system_prompt"],
        "tools": payload.tools if payload.tools is not None else preset["tools"],
        "llm_config": payload.llm_config if payload.llm_config is not None else preset["llm_config"],
        "memory_config": payload.memory_config if payload.memory_config is not None else preset["memory_config"],
    }


def create_agent(db: Session, user_id: int, payload) -> UserAgent:
    preset = _apply_preset(payload)
    row = agent_repo.create_agent(
        db,
        user_id,
        name=preset.get("name", payload.name),
        agent_type=preset.get("agent_type", payload.agent_type),
        system_prompt=preset.get("system_prompt", payload.system_prompt),
        tools=preset.get("tools", payload.tools),
        llm_config=preset.get("llm_config", payload.llm_config),
        memory_config=preset.get("memory_config", payload.memory_config),
        status=payload.status,
    )
    db.commit()
    db.refresh(row)
    return row


def list_agents(db: Session, user_id: int) -> list[UserAgent]:
    return agent_repo.list_agents(db, user_id)


def _get_owned(db: Session, user_id: int, agent_id: int) -> UserAgent:
    ag = agent_repo.get_agent(db, user_id, agent_id)
    if ag is None:
        raise ApiError(status_code=404, code=40430, msg="Agent 不存在")
    return ag


def get_agent(db: Session, user_id: int, agent_id: int) -> UserAgent:
    return _get_owned(db, user_id, agent_id)


def update_agent(db: Session, user_id: int, agent_id: int, payload) -> UserAgent:
    ag = _get_owned(db, user_id, agent_id)
    fields = {
        "name": payload.name,
        "agent_type": payload.agent_type,
        "system_prompt": payload.system_prompt,
        "tools": payload.tools,
        "llm_config": payload.llm_config,
        "memory_config": payload.memory_config,
        "status": payload.status,
    }
    ag = agent_repo.update_agent(db, ag, **{k: v for k, v in fields.items() if v is not None})
    db.commit()
    db.refresh(ag)
    return ag


def delete_agent(db: Session, user_id: int, agent_id: int) -> None:
    if not agent_repo.delete_agent(db, user_id, agent_id):
        raise ApiError(status_code=404, code=40430, msg="Agent 不存在")
    db.commit()


# ---- Agent 运行记录 / 记忆文件（5.5 补齐 GET /agent/runs、/memory/files）----
def list_runs(db: Session, user_id: int) -> list[AgentRun]:
    return agent_repo.list_runs(db, user_id)


def get_run(db: Session, user_id: int, run_id: int) -> AgentRun:
    run = agent_repo.get_run(db, user_id, run_id)
    if run is None:
        raise ApiError(status_code=404, code=40440, msg="运行记录不存在")
    return run


def list_steps(db: Session, run_id: int) -> list[AgentStep]:
    return agent_repo.list_steps(db, run_id)


def list_memory_files(db: Session, user_id: int) -> list[UserMemoryFile]:
    return agent_repo.list_memory_files(db, user_id)
