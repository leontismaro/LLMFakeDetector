from typing import Any, Literal

from pydantic import BaseModel, Field


ProbeStatus = Literal["pass", "warn", "fail", "skip"]


class DetectionRequest(BaseModel):
    base_url: str = Field(..., description="目标 API Base URL")
    api_key: str | None = Field(default=None, description="目标 API Key")
    model_name: str = Field(..., description="待检测模型名")
    enabled_probes: list[str] = Field(default_factory=list, description="启用的探针列表")


class ProbeFinding(BaseModel):
    probe_name: str
    status: ProbeStatus
    score: int = Field(ge=0, le=100)
    summary: str
    evidence: list[str] = Field(default_factory=list)
    details: dict[str, Any] = Field(default_factory=dict)


class DetectionResponse(BaseModel):
    model_name: str
    trust_score: int = Field(ge=0, le=100)
    findings: list[ProbeFinding]
