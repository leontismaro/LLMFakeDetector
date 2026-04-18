from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol
from urllib.parse import quote

from app.modules.detection.probes.base import ProbeRuntime
from app.modules.detection.probes.helpers import classify_status_code


CLAUDE_MODEL_PREFIXES = ("claude-", "claude")
GEMINI_MODEL_PREFIXES = ("gemini-", "models/gemini")


class EncodingProtocol(Protocol):
    name: str

    def encode(self, text: str) -> list[int]:
        ...


@dataclass(slots=True)
class ReferenceCountResult:
    reference_tokens: int
    reference_family: str
    reference_source: str
    sample_metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class ReferenceProviderError(Exception):
    status: str
    score: int
    summary: str
    evidence: list[str]
    details: dict[str, Any] = field(default_factory=dict)


class ReferenceProvider(Protocol):
    reference_family: str
    reference_source: str

    async def count_tokens(self, runtime: ProbeRuntime, sample_name: str, sample_text: str) -> ReferenceCountResult:
        ...


class OpenAITiktokenReferenceProvider:
    reference_family = "openai_tiktoken"
    reference_source = "local_tiktoken"

    def __init__(self, model_name: str) -> None:
        self._encoding = self._resolve_reference_encoding(model_name)

    @property
    def encoding_name(self) -> str:
        return self._encoding.name

    async def count_tokens(self, runtime: ProbeRuntime, sample_name: str, sample_text: str) -> ReferenceCountResult:
        del runtime, sample_name
        return ReferenceCountResult(
            reference_tokens=len(self._encoding.encode(sample_text)),
            reference_family=self.reference_family,
            reference_source=self.reference_source,
            sample_metadata={"reference_encoding": self._encoding.name},
        )

    @staticmethod
    def _resolve_reference_encoding(model_name: str) -> EncodingProtocol:
        import tiktoken

        normalized_model_name = model_name.strip().lower()

        try:
            return tiktoken.encoding_for_model(normalized_model_name)
        except KeyError:
            fallback_name = "o200k_base" if normalized_model_name.startswith(("gpt-4o", "gpt-5", "o1", "o3", "o4")) else "cl100k_base"
            try:
                return tiktoken.get_encoding(fallback_name)
            except ValueError as exc:  # pragma: no cover
                raise ValueError(f"无法为模型 {model_name} 解析本地参考编码。") from exc


class AnthropicReferenceProvider:
    reference_family = "anthropic_official"
    reference_source = "anthropic_count_tokens_api"
    endpoint_url = "https://api.anthropic.com/v1/messages/count_tokens"

    def __init__(self, api_key: str) -> None:
        self._api_key = api_key

    async def count_tokens(self, runtime: ProbeRuntime, sample_name: str, sample_text: str) -> ReferenceCountResult:
        response = await runtime.adapter.client.post(
            self.endpoint_url,
            headers={
                "content-type": "application/json",
                "x-api-key": self._api_key,
                "anthropic-version": "2023-06-01",
            },
            json={
                "model": runtime.request.model_name,
                "messages": [
                    {
                        "role": "user",
                        "content": sample_text,
                    }
                ],
            },
        )
        metadata = {
            "reference_endpoint_url": self.endpoint_url,
            "reference_status_code": response.status_code,
            "reference_http_version": response.http_version,
        }
        if response.status_code < 200 or response.status_code >= 300:
            status_group = classify_status_code(response.status_code)
            raise self._build_error(sample_name=sample_name, status_code=response.status_code, status_group=status_group, details=metadata)

        body = response.json()
        input_tokens = body.get("input_tokens") if isinstance(body, dict) else None
        if not isinstance(input_tokens, int):
            raise ReferenceProviderError(
                status="fail",
                score=20,
                summary="tokenizer 探针失败，Anthropic 官方参考未返回可解析的 input_tokens。",
                evidence=[f"样本 {sample_name} 的 Anthropic 参考响应缺少 input_tokens。"],
                details=metadata,
            )

        return ReferenceCountResult(
            reference_tokens=input_tokens,
            reference_family=self.reference_family,
            reference_source=self.reference_source,
            sample_metadata=metadata,
        )

    def _build_error(self, *, sample_name: str, status_code: int, status_group: str, details: dict[str, Any]) -> ReferenceProviderError:
        evidence = [f"样本 {sample_name} 的 Anthropic 官方参考返回 HTTP {status_code}。"]
        if status_group == "auth_error":
            evidence.append("Anthropic 官方 API Key 无法完成输入 token 基线计数。")
            return ReferenceProviderError(
                status="warn",
                score=35,
                summary="tokenizer 探针未完成，Anthropic 官方参考鉴权失败。",
                evidence=evidence,
                details={**details, "reference_failure_kind": status_group},
            )
        if status_group == "client_error":
            evidence.append("Anthropic 官方参考拒绝了当前模型名或输入格式。")
            return ReferenceProviderError(
                status="warn",
                score=45,
                summary="tokenizer 探针部分受阻，Anthropic 官方参考未接受当前计数请求。",
                evidence=evidence,
                details={**details, "reference_failure_kind": status_group},
            )
        evidence.append("Anthropic 官方参考暂时不可用，无法建立输入 token 基线。")
        return ReferenceProviderError(
            status="fail",
            score=15,
            summary="tokenizer 探针失败，Anthropic 官方参考请求异常，无法完成输入 token 对比。",
            evidence=evidence,
            details={**details, "reference_failure_kind": status_group},
        )


class GeminiReferenceProvider:
    reference_family = "gemini_official"
    reference_source = "gemini_count_tokens_api"

    def __init__(self, api_key: str) -> None:
        self._api_key = api_key

    async def count_tokens(self, runtime: ProbeRuntime, sample_name: str, sample_text: str) -> ReferenceCountResult:
        model_resource = runtime.request.model_name if runtime.request.model_name.startswith("models/") else f"models/{runtime.request.model_name}"
        endpoint_url = f"https://generativelanguage.googleapis.com/v1beta/{quote(model_resource, safe='/')}:countTokens"
        response = await runtime.adapter.client.post(
            endpoint_url,
            params={"key": self._api_key},
            headers={"content-type": "application/json"},
            json={
                "contents": [
                    {
                        "role": "user",
                        "parts": [{"text": sample_text}],
                    }
                ]
            },
        )
        metadata = {
            "reference_endpoint_url": endpoint_url,
            "reference_status_code": response.status_code,
            "reference_http_version": response.http_version,
        }
        if response.status_code < 200 or response.status_code >= 300:
            status_group = classify_status_code(response.status_code)
            raise self._build_error(sample_name=sample_name, status_code=response.status_code, status_group=status_group, details=metadata)

        body = response.json()
        total_tokens = None
        if isinstance(body, dict):
            raw_total_tokens = body.get("totalTokens", body.get("total_tokens"))
            if isinstance(raw_total_tokens, int):
                total_tokens = raw_total_tokens

        if not isinstance(total_tokens, int):
            raise ReferenceProviderError(
                status="fail",
                score=20,
                summary="tokenizer 探针失败，Gemini 官方参考未返回可解析的 totalTokens。",
                evidence=[f"样本 {sample_name} 的 Gemini 参考响应缺少 totalTokens。"],
                details=metadata,
            )

        return ReferenceCountResult(
            reference_tokens=total_tokens,
            reference_family=self.reference_family,
            reference_source=self.reference_source,
            sample_metadata=metadata,
        )

    def _build_error(self, *, sample_name: str, status_code: int, status_group: str, details: dict[str, Any]) -> ReferenceProviderError:
        evidence = [f"样本 {sample_name} 的 Gemini 官方参考返回 HTTP {status_code}。"]
        if status_group == "auth_error":
            evidence.append("Gemini 官方 API Key 无法完成输入 token 基线计数。")
            return ReferenceProviderError(
                status="warn",
                score=35,
                summary="tokenizer 探针未完成，Gemini 官方参考鉴权失败。",
                evidence=evidence,
                details={**details, "reference_failure_kind": status_group},
            )
        if status_group == "client_error":
            evidence.append("Gemini 官方参考拒绝了当前模型名或输入格式。")
            return ReferenceProviderError(
                status="warn",
                score=45,
                summary="tokenizer 探针部分受阻，Gemini 官方参考未接受当前计数请求。",
                evidence=evidence,
                details={**details, "reference_failure_kind": status_group},
            )
        evidence.append("Gemini 官方参考暂时不可用，无法建立输入 token 基线。")
        return ReferenceProviderError(
            status="fail",
            score=15,
            summary="tokenizer 探针失败，Gemini 官方参考请求异常，无法完成输入 token 对比。",
            evidence=evidence,
            details={**details, "reference_failure_kind": status_group},
        )


def is_claude_model(model_name: str) -> bool:
    normalized = model_name.strip().lower()
    return normalized.startswith(CLAUDE_MODEL_PREFIXES)


def is_gemini_model(model_name: str) -> bool:
    normalized = model_name.strip().lower()
    return normalized.startswith(GEMINI_MODEL_PREFIXES)
