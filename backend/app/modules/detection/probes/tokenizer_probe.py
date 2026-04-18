from __future__ import annotations

from statistics import mean
from typing import Any

import httpx

from app.modules.detection.probes.base import DetectionProbe, ProbeRuntime
from app.modules.detection.probes.helpers import build_response_metadata, classify_status_code
from app.modules.detection.probes.token_reference import (
    OpenAITiktokenReferenceProvider,
    AnthropicReferenceProvider,
    GeminiReferenceProvider,
    ReferenceProvider,
    ReferenceProviderError,
    is_claude_model,
    is_gemini_model,
)
from app.modules.detection.schemas import ProbeFinding


TOKENIZER_SAMPLES: tuple[dict[str, str], ...] = (
    {
        "name": "plain_english",
        "text": "Answer with exactly one word: yes.",
    },
    {
        "name": "mixed_language",
        "text": "请只回复 yes，并保留这个 JSON key: result。",
    },
    {
        "name": "emoji_and_symbol",
        "text": "Return yes for this marker set: ✅🤖✨ /dev/null",
    },
    {
        "name": "json_like_payload",
        "text": '{"user":"alice","tags":["qa","tokenizer"],"active":true}',
    },
    {
        "name": "whitespace_and_url",
        "text": "Line1\\n\\nLine2    https://example.com/a?b=1&c=two",
    },
)

OPENAI_STYLE_MODEL_PREFIXES = (
    "gpt-",
    "chatgpt-",
    "o1",
    "o3",
    "o4",
)


class TokenizerProbe(DetectionProbe):
    name = "tokenizer_probe"

    async def run(self, runtime: ProbeRuntime) -> ProbeFinding:
        provider_result = self._resolve_reference_provider(runtime)
        if isinstance(provider_result, ProbeFinding):
            return provider_result

        provider = provider_result
        sample_results: list[dict[str, Any]] = []

        for sample in TOKENIZER_SAMPLES:
            response = await runtime.adapter.create_chat_completion(
                messages=[{"role": "user", "content": sample["text"]}],
                extra_body={"max_tokens": 1},
            )

            metadata = build_response_metadata(response, runtime.adapter.endpoint_url)
            status_group = classify_status_code(response.status_code)
            if not response.ok:
                return self._build_non_success_finding(
                    sample_name=sample["name"],
                    status_code=response.status_code,
                    status_group=status_group,
                    details=metadata,
                )

            if not isinstance(response.json_body, dict):
                return ProbeFinding(
                    probe_name=self.name,
                    status="fail",
                    score=20,
                    summary="tokenizer 探针失败，目标接口未返回可解析的成功 JSON，无法提取 usage.prompt_tokens。",
                    evidence=[f"样本 {sample['name']} 的成功响应不是 JSON 对象。"],
                    details={**metadata, "sample_name": sample["name"]},
                )

            usage = response.json_body.get("usage")
            if not isinstance(usage, dict):
                return ProbeFinding(
                    probe_name=self.name,
                    status="fail",
                    score=25,
                    summary="tokenizer 探针失败，成功响应缺少 usage 对象，无法进行 prompt token 比对。",
                    evidence=[f"样本 {sample['name']} 的响应缺少 usage 对象。"],
                    details={**metadata, "sample_name": sample["name"]},
                )

            observed_prompt_tokens = usage.get("prompt_tokens")
            if not isinstance(observed_prompt_tokens, int):
                return ProbeFinding(
                    probe_name=self.name,
                    status="fail",
                    score=30,
                    summary="tokenizer 探针失败，成功响应缺少 usage.prompt_tokens，无法进行 tokenizer 指纹比对。",
                    evidence=[f"样本 {sample['name']} 的 usage.prompt_tokens 缺失或类型错误。"],
                    details={**metadata, "sample_name": sample["name"]},
                )

            try:
                reference_result = await provider.count_tokens(
                    runtime=runtime,
                    sample_name=sample["name"],
                    sample_text=sample["text"],
                )
            except ReferenceProviderError as exc:
                return ProbeFinding(
                    probe_name=self.name,
                    status=exc.status,
                    score=exc.score,
                    summary=exc.summary,
                    evidence=exc.evidence,
                    details={**exc.details, "endpoint_url": runtime.adapter.endpoint_url, "sample_name": sample["name"]},
                )
            except httpx.HTTPError as exc:
                return ProbeFinding(
                    probe_name=self.name,
                    status="warn",
                    score=20,
                    summary="tokenizer 探针部分受阻，官方参考 token 计数请求链路异常。",
                    evidence=[f"样本 {sample['name']} 的官方参考请求失败：{str(exc) or exc.__class__.__name__}"],
                    details={"endpoint_url": runtime.adapter.endpoint_url, "sample_name": sample["name"], "reference_failure_kind": "request_error"},
                )

            sample_results.append(
                {
                    "name": sample["name"],
                    "text": sample["text"],
                    "reference_tokens": reference_result.reference_tokens,
                    "observed_prompt_tokens": observed_prompt_tokens,
                    "delta": observed_prompt_tokens - reference_result.reference_tokens,
                    "http_version": metadata.get("http_version"),
                    **reference_result.sample_metadata,
                }
            )

        return self._build_success_finding(runtime=runtime, provider=provider, sample_results=sample_results)

    def _resolve_reference_provider(self, runtime: ProbeRuntime) -> ReferenceProvider | ProbeFinding:
        model_name = runtime.request.model_name
        reference_options = runtime.request.reference_options

        if self._supports_openai_style_reference(model_name):
            try:
                return OpenAITiktokenReferenceProvider(model_name)
            except ImportError:
                return ProbeFinding(
                    probe_name=self.name,
                    status="skip",
                    score=0,
                    summary="tokenizer 探针已跳过，当前环境缺少 tiktoken，无法计算本地参考 tokenizer。",
                    evidence=["未安装 tiktoken，无法生成 OpenAI 风格 tokenizer 参考值。"],
                    details={"endpoint_url": runtime.adapter.endpoint_url, "reference_family": "openai_style_only"},
                )
            except ValueError as exc:
                return ProbeFinding(
                    probe_name=self.name,
                    status="skip",
                    score=0,
                    summary="tokenizer 探针已跳过，当前模型无法映射到可用的本地 tokenizer 参考编码。",
                    evidence=[str(exc)],
                    details={"endpoint_url": runtime.adapter.endpoint_url, "reference_family": "openai_style_only"},
                )

        if is_claude_model(model_name):
            if not reference_options.anthropic_api_key:
                return ProbeFinding(
                    probe_name=self.name,
                    status="skip",
                    score=0,
                    summary="tokenizer 探针已跳过，当前 Claude 模型未提供 Anthropic 官方 API Key，无法建立官方输入 token 基线。",
                    evidence=["未提供 anthropic_api_key，已跳过 Anthropic 官方 count_tokens 对比。"],
                    details={"endpoint_url": runtime.adapter.endpoint_url, "reference_family": "anthropic_official"},
                )
            return AnthropicReferenceProvider(reference_options.anthropic_api_key)

        if is_gemini_model(model_name):
            if not reference_options.gemini_api_key:
                return ProbeFinding(
                    probe_name=self.name,
                    status="skip",
                    score=0,
                    summary="tokenizer 探针已跳过，当前 Gemini 模型未提供 Gemini 官方 API Key，无法建立官方输入 token 基线。",
                    evidence=["未提供 gemini_api_key，已跳过 Gemini 官方 countTokens 对比。"],
                    details={"endpoint_url": runtime.adapter.endpoint_url, "reference_family": "gemini_official"},
                )
            return GeminiReferenceProvider(reference_options.gemini_api_key)

        return ProbeFinding(
            probe_name=self.name,
            status="skip",
            score=0,
            summary="tokenizer 探针已跳过，当前仅支持 OpenAI、Claude、Gemini 三类模型的输入 token 参考比对。",
            evidence=[f"当前模型名为 {model_name}，尚未实现对应厂商的参考 token 计数。"],
            details={"endpoint_url": runtime.adapter.endpoint_url, "reference_family": "unsupported"},
        )

    @staticmethod
    def _supports_openai_style_reference(model_name: str) -> bool:
        return model_name.strip().lower().startswith(OPENAI_STYLE_MODEL_PREFIXES)

    def _build_non_success_finding(
        self,
        *,
        sample_name: str,
        status_code: int,
        status_group: str,
        details: dict[str, Any],
    ) -> ProbeFinding:
        evidence = [f"样本 {sample_name} 返回 HTTP {status_code}。"]
        if status_group == "auth_error":
            evidence.append("请求未通过鉴权，无法继续做 tokenizer 指纹对比。")
            return ProbeFinding(
                probe_name=self.name,
                status="warn",
                score=35,
                summary="tokenizer 探针未完成，当前凭证无法验证 usage.prompt_tokens 与参考 tokenizer 的关系。",
                evidence=evidence,
                details={**details, "failure_kind": status_group, "sample_name": sample_name},
            )
        if status_group == "client_error":
            evidence.append("目标接口拒绝了最小 token 计数请求，无法建立 usage.prompt_tokens 基线。")
            return ProbeFinding(
                probe_name=self.name,
                status="warn",
                score=45,
                summary="tokenizer 探针部分受阻，目标接口未接受用于 token 指纹分析的最小请求。",
                evidence=evidence,
                details={**details, "failure_kind": status_group, "sample_name": sample_name},
            )
        if status_group == "server_error":
            evidence.append("目标接口在 tokenizer 指纹测试样本上触发了 5xx。")
        else:
            evidence.append("目标接口未返回可用于 token 指纹分析的成功响应。")
        return ProbeFinding(
            probe_name=self.name,
            status="fail",
            score=15,
            summary="tokenizer 探针失败，目标接口无法稳定返回用于 usage.prompt_tokens 比对的样本结果。",
            evidence=evidence,
            details={**details, "failure_kind": status_group, "sample_name": sample_name},
        )

    def _build_success_finding(
        self,
        *,
        runtime: ProbeRuntime,
        provider: ReferenceProvider,
        sample_results: list[dict[str, Any]],
    ) -> ProbeFinding:
        deltas = [int(item["delta"]) for item in sample_results]
        delta_range = max(deltas) - min(deltas)
        negative_count = sum(1 for delta in deltas if delta < 0)
        stable_sample_count = sum(1 for delta in deltas if abs(delta - round(mean(deltas))) <= 2)

        reference_encoding = None
        if isinstance(provider, OpenAITiktokenReferenceProvider):
            reference_encoding = provider.encoding_name

        evidence = [
            f"参考来源为 {provider.reference_source}，共比对 {len(sample_results)} 组样本。",
            f"observed_prompt_tokens - reference_tokens 的范围为 {delta_range}。",
            f"有 {stable_sample_count}/{len(sample_results)} 个样本与主包络偏差不超过 2。",
        ]
        if negative_count:
            evidence.append(f"有 {negative_count} 个样本的 observed_prompt_tokens 小于参考 token 数。")
        else:
            evidence.append("所有样本的 observed_prompt_tokens 都不小于参考 token 数。")

        details = {
            "endpoint_url": runtime.adapter.endpoint_url,
            "reference_family": provider.reference_family,
            "reference_source": provider.reference_source,
            "reference_model_name": runtime.request.model_name,
            "sample_count": len(sample_results),
            "delta_range": delta_range,
            "negative_delta_count": negative_count,
            "stable_sample_count": stable_sample_count,
            "samples": sample_results,
        }
        if reference_encoding:
            details["reference_encoding"] = reference_encoding

        if negative_count == 0 and delta_range <= 4:
            return ProbeFinding(
                probe_name=self.name,
                status="pass",
                score=91,
                summary="tokenizer 探针通过，目标 usage.prompt_tokens 与参考输入 token 计数呈现稳定包络关系。",
                evidence=evidence,
                details=details,
            )

        if negative_count <= 1 and delta_range <= 8:
            evidence.append("delta 虽有波动，但整体仍接近同一包装开销下的稳定分布。")
            return ProbeFinding(
                probe_name=self.name,
                status="warn",
                score=72,
                summary="tokenizer 探针出现轻度偏差，目标 usage.prompt_tokens 与参考输入 token 计数大体接近，但包络不够稳定。",
                evidence=evidence,
                details=details,
            )

        evidence.append("不同样本的 delta 波动过大，或出现 observed_prompt_tokens 低于参考 token 数的情况。")
        return ProbeFinding(
            probe_name=self.name,
            status="fail",
            score=35,
            summary="tokenizer 探针失败，目标 usage.prompt_tokens 与参考输入 token 计数的关系不稳定，存在明显可疑偏差。",
            evidence=evidence,
            details=details,
        )
