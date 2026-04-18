from __future__ import annotations

from statistics import mean
from typing import Any, Protocol

from app.modules.detection.probes.base import DetectionProbe, ProbeRuntime
from app.modules.detection.probes.helpers import build_response_metadata, classify_status_code
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


class EncodingProtocol(Protocol):
    name: str

    def encode(self, text: str) -> list[int]:
        ...


class TokenizerProbe(DetectionProbe):
    name = "tokenizer_probe"

    async def run(self, runtime: ProbeRuntime) -> ProbeFinding:
        model_name = runtime.request.model_name
        if not self._supports_openai_style_reference(model_name):
            return ProbeFinding(
                probe_name=self.name,
                status="skip",
                score=0,
                summary="tokenizer 探针已跳过，当前仅对 OpenAI 风格模型名提供本地 tokenizer 参考比对。",
                evidence=[f"当前模型名为 {model_name}，不在 OpenAI 风格参考范围内。"],
                details={"endpoint_url": runtime.adapter.endpoint_url, "reference_family": "openai_style_only"},
            )

        try:
            encoding = self._resolve_reference_encoding(model_name)
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

            reference_tokens = len(encoding.encode(sample["text"]))
            sample_results.append(
                {
                    "name": sample["name"],
                    "text": sample["text"],
                    "reference_tokens": reference_tokens,
                    "observed_prompt_tokens": observed_prompt_tokens,
                    "delta": observed_prompt_tokens - reference_tokens,
                    "http_version": metadata.get("http_version"),
                }
            )

        return self._build_success_finding(
            runtime=runtime,
            encoding=encoding,
            sample_results=sample_results,
        )

    @staticmethod
    def _supports_openai_style_reference(model_name: str) -> bool:
        return model_name.startswith(OPENAI_STYLE_MODEL_PREFIXES)

    @staticmethod
    def _resolve_reference_encoding(model_name: str) -> EncodingProtocol:
        import tiktoken

        try:
            return tiktoken.encoding_for_model(model_name)
        except KeyError:
            fallback_name = "o200k_base" if model_name.startswith(("gpt-4o", "gpt-5", "o1", "o3", "o4")) else "cl100k_base"
            try:
                return tiktoken.get_encoding(fallback_name)
            except ValueError as exc:  # pragma: no cover
                raise ValueError(f"无法为模型 {model_name} 解析本地参考编码。") from exc

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
                summary="tokenizer 探针未完成，当前凭证无法验证 usage.prompt_tokens 与本地参考 tokenizer 的关系。",
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
        encoding: EncodingProtocol,
        sample_results: list[dict[str, Any]],
    ) -> ProbeFinding:
        deltas = [int(item["delta"]) for item in sample_results]
        delta_range = max(deltas) - min(deltas)
        negative_count = sum(1 for delta in deltas if delta < 0)
        stable_sample_count = sum(1 for delta in deltas if abs(delta - round(mean(deltas))) <= 2)

        evidence = [
            f"本地参考编码为 {encoding.name}，共比对 {len(sample_results)} 组样本。",
            f"observed_prompt_tokens - reference_tokens 的范围为 {delta_range}。",
            f"有 {stable_sample_count}/{len(sample_results)} 个样本与主包络偏差不超过 2。",
        ]
        if negative_count:
            evidence.append(f"有 {negative_count} 个样本的 observed_prompt_tokens 小于本地参考 token 数。")
        else:
            evidence.append("所有样本的 observed_prompt_tokens 都不小于本地参考 token 数。")

        details = {
            "endpoint_url": runtime.adapter.endpoint_url,
            "reference_family": "openai_tiktoken",
            "reference_encoding": encoding.name,
            "sample_count": len(sample_results),
            "delta_range": delta_range,
            "negative_delta_count": negative_count,
            "stable_sample_count": stable_sample_count,
            "samples": sample_results,
        }

        if negative_count == 0 and delta_range <= 4:
            return ProbeFinding(
                probe_name=self.name,
                status="pass",
                score=91,
                summary="tokenizer 探针通过，usage.prompt_tokens 与 OpenAI 风格本地 tokenizer 参考呈现稳定包络关系。",
                evidence=evidence,
                details=details,
            )

        if negative_count <= 1 and delta_range <= 8:
            evidence.append("delta 虽有波动，但整体仍接近同一包装开销下的稳定分布。")
            return ProbeFinding(
                probe_name=self.name,
                status="warn",
                score=72,
                summary="tokenizer 探针出现轻度偏差，usage.prompt_tokens 与 OpenAI 风格本地参考大体接近，但包络不够稳定。",
                evidence=evidence,
                details=details,
            )

        evidence.append("不同样本的 delta 波动过大，或出现 observed_prompt_tokens 低于参考 token 数的情况。")
        return ProbeFinding(
            probe_name=self.name,
            status="fail",
            score=35,
            summary="tokenizer 探针失败，usage.prompt_tokens 与 OpenAI 风格 tokenizer 参考的关系不稳定，存在明显可疑偏差。",
            evidence=evidence,
            details=details,
        )
