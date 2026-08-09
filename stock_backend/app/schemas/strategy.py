"""策略域响应模型：AI 生成、交易策略 CRUD（统一由 {code, msg, data} 包裹）。"""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


# ---- AI 策略生成（3.5 结构化输出）----
class StrategyGenerateIn(BaseModel):
    description: str = Field(..., min_length=1, description="用户交易想法描述")
    symbol: str | None = Field(None, description="绑定标的（代码或 symbol_id，可选）")


class StrategyParams(BaseModel):
    """策略参数（docs.md：入场/止损/止盈/仓位）。"""

    entry: dict[str, Any] = Field(default_factory=dict, description="入场规则参数")
    stop_loss: dict[str, Any] = Field(default_factory=dict, description="止损规则参数")
    take_profit: dict[str, Any] = Field(default_factory=dict, description="止盈规则参数")
    position: dict[str, Any] = Field(default_factory=dict, description="仓位规则参数")


class StrategyOutput(BaseModel):
    """AI 生成策略的结构化输出（with_structured_output schema）。"""

    strategy_name: str = Field(..., description="策略名")
    description: str = Field(..., description="策略逻辑说明（中文）")
    code: str = Field(..., description="Python 策略代码（initialize/on_bar 接口）")
    params: StrategyParams = Field(default_factory=StrategyParams)
    risk_warning: str = Field(default="", description="风险提示")


# ---- 交易策略 CRUD（3.6）----
class StrategyCreateIn(BaseModel):
    title: str = Field(..., min_length=1, max_length=128)
    description: str | None = None
    code: str | None = None
    params: dict[str, Any] | None = None
    status: str = Field("draft", pattern="^(active|draft)$")


class StrategyUpdateIn(BaseModel):
    title: str | None = Field(None, min_length=1, max_length=128)
    description: str | None = None
    code: str | None = None
    params: dict[str, Any] | None = None
    status: str | None = Field(None, pattern="^(active|draft)$")


class StrategyOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    description: str | None = None
    code: str | None = None
    params: dict[str, Any] | None = None
    status: str
    created_at: datetime
    updated_at: datetime
