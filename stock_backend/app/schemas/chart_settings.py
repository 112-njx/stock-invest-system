"""Detail-chart preferences and shared MA parameter validation."""
from typing import Annotated, Literal
from pydantic import BaseModel, ConfigDict, Field, StrictBool, field_validator, model_validator

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

class PanelOptions(BaseModel):
    model_config = ConfigDict(extra='forbid')
    params: dict = Field(default_factory=dict)

class ChartSettings(BaseModel):
    model_config = ConfigDict(extra='forbid')
    ma: MaSettings = Field(default_factory=MaSettings)
    version: Literal[2] | None = None
    panel_options: dict[str, PanelOptions] | None = None
    overlays: list[str] | None = None
    overlay_options: dict[str, PanelOptions] | None = None
    panels: list[str] = Field(default_factory=lambda: ['volume','macd'], max_length=3)

    @field_validator('panels')
    @classmethod
    def unique_panels(cls, panels):
        if len(set(panels)) != len(panels):
            raise ValueError('副图不可重复')
        from app.services.indicator_registry import REGISTRY
        if any(p not in REGISTRY or REGISTRY[p]['placement'] != 'panel' for p in panels):
            raise ValueError('unsupported panel')
        return panels

    @field_validator('overlays')
    @classmethod
    def valid_overlays(cls, overlays):
        from app.services.indicator_registry import REGISTRY
        if overlays is not None and (len(set(overlays)) != len(overlays) or any(k == 'ma' or k not in REGISTRY or REGISTRY[k]['placement'] != 'main' for k in overlays)):
            raise ValueError('unsupported or duplicate main overlay')
        return overlays

    @model_validator(mode='after')
    def validate_options(self):
        from app.services.indicator_registry import REGISTRY, validate_parameters
        for name, option in (self.panel_options or {}).items():
            if name not in REGISTRY or REGISTRY[name]['placement'] != 'panel':
                raise ValueError('unsupported panel')
            validate_parameters(name, option.params)
        for name, option in (self.overlay_options or {}).items():
            if name == 'ma' or name not in REGISTRY or REGISTRY[name]['placement'] != 'main':
                raise ValueError('unsupported main overlay')
            validate_parameters(name, option.params)
        return self

class MaParameters(BaseModel):
    model_config = ConfigDict(extra='forbid')
    periods: list[Period] = Field(default_factory=lambda: [5,10,20,30], min_length=1, max_length=6)

    @field_validator('periods')
    @classmethod
    def unique_periods(cls, periods):
        if len(set(periods)) != len(periods):
            raise ValueError('MA周期不可重复')
        return periods
