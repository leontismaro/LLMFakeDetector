from typing import Any, Literal

from pydantic import BaseModel, Field


ProbeStatus = Literal["pass", "warn", "fail", "skip"]
ContextMode = Literal["light", "standard", "heavy"]


class ReferenceOptions(BaseModel):
    anthropic_api_key: str | None = Field(default=None, description="Anthropic 官方参考 API Key，可选")
    gemini_api_key: str | None = Field(default=None, description="Gemini 官方参考 API Key，可选")


class DetectionRequest(BaseModel):
    base_url: str = Field(..., description="目标 API Base URL")
    api_key: str | None = Field(default=None, description="目标 API Key")
    model_name: str = Field(..., description="待检测模型名")
    enabled_probes: list[str] = Field(default_factory=list, description="启用的探针列表")
    context_mode: ContextMode = Field(default="standard", description="上下文探针档位，控制能力层压测强度")
    reference_options: ReferenceOptions = Field(default_factory=ReferenceOptions, description="官方参考 token 计数所需的可选凭证")


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
