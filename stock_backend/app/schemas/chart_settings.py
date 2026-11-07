"""Detail-chart preferences and shared MA parameter validation."""
from typing import Annotated, Literal
from pydantic import BaseModel, ConfigDict, Field, StrictBool, field_validator

Period = Annotated[int, Field(strict=True, ge=1, le=10000)]

class MaLine(BaseModel):
    model_config = ConfigDict(extra='forbid')
    period: Period
    visible: StrictBool = True

class MaSettings(BaseModel):
    model_config = ConfigDict(extra='forbid')
    lines: list[MaLine] = Field(default_factory=lambda: [MaLine(period=n) for n in (5,10,20,30)], min_length=1, max_length=6)

    @field_validator('lines')
    @classmethod
    def unique_periods(cls, lines):
        if len({line.period for line in lines}) != len(lines):
            raise ValueError('MA周期不可重复')
        return lines

class ChartSettings(BaseModel):
    model_config = ConfigDict(extra='forbid')
    ma: MaSettings = Field(default_factory=MaSettings)
    panels: list[Literal['volume','amount','macd','kdj']] = Field(default_factory=lambda: ['volume','macd'], max_length=3)

    @field_validator('panels')
    @classmethod
    def unique_panels(cls, panels):
        if len(set(panels)) != len(panels):
            raise ValueError('副图不可重复')
        return panels

class MaParameters(BaseModel):
    model_config = ConfigDict(extra='forbid')
    periods: list[Period] = Field(default_factory=lambda: [5,10,20,30], min_length=1, max_length=6)

    @field_validator('periods')
    @classmethod
    def unique_periods(cls, periods):
        if len(set(periods)) != len(periods):
            raise ValueError('MA周期不可重复')
        return periods
