from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import UUID

from app.modules.detection.adapter import AdapterResponse
from app.modules.detection.probes.base import DetectionProbe, ProbeRuntime
from app.modules.detection.probes.helpers import build_response_metadata
from app.modules.detection.probes.token_reference import is_claude_model, is_gemini_model
from app.modules.detection.schemas import ProbeFinding


OPENAI_STYLE_MODEL_PREFIXES = ("gpt-", "chatgpt-", "o1", "o3", "o4")
SAMPLE_PROMPTS = (
    ("sample_alpha", "Reply with exactly one token: alpha."),
    ("sample_bravo", "Reply with exactly one token: bravo."),
    ("sample_charlie", "Reply with exactly one token: charlie."),
)


@dataclass(slots=True)
class SampleObservation:
    sample_name: str
    status_code: int
    http_version: str
    family: str
    response_id: str | None
    response_headers: dict[str, str]
    system_fingerprint: str | None
    usage_snapshot: dict[str, Any] | None
    issues: list[str]
    matches: list[str]


class GatewaySignatureProbe(DetectionProbe):
    name = "gateway_signature_probe"

    async def run(self, runtime: ProbeRuntime) -> ProbeFinding:
        claimed_family = self._detect_claimed_family(runtime.request.model_name)
        observations: list[SampleObservation] = []
        evidence: list[str] = []
        score = 100
        hard_fail = False

        for sample_name, sample_prompt in SAMPLE_PROMPTS:
            response = await runtime.adapter.create_chat_completion(
                messages=[{"role": "user", "content": sample_prompt}]
            )
            observation = self._inspect_response(sample_name=sample_name, response=response)
            observations.append(observation)

            if response.status_code >= 500:
                score -= 35
                hard_fail = True
                evidence.append(f"{sample_name} 返回 5xx，无法稳定分析网关外壳信号。")
            elif response.status_code >= 400:
                score -= 18
                evidence.append(f"{sample_name} 返回 {response.status_code}，该样本无法作为稳定外壳信号。")

        if not observations:
            return ProbeFinding(
                probe_name=self.name,
                status="fail",
                score=0,
                summary="网关特征探针失败，未采集到任何响应样本。",
                evidence=["未返回可分析样本。"],
                details={"claimed_family": claimed_family, "sample_count": 0},
            )

        family_alignment_status, family_alignment_score_delta, family_alignment_message = self._evaluate_family_alignment(
            claimed_family=claimed_family,
            observations=observations,
        )
        score += family_alignment_score_delta
        evidence.append(family_alignment_message)
        if family_alignment_status == "fail":
            hard_fail = True

        id_status, id_score_delta, id_message = self._evaluate_id_signals(
            claimed_family=claimed_family,
            observations=observations,
        )
        score += id_score_delta
        evidence.append(id_message)
        if id_status == "fail":
            hard_fail = True

        fingerprint_status, fingerprint_score_delta, fingerprint_message = self._evaluate_fingerprint_signals(
            observations=observations
        )
        score += fingerprint_score_delta
        evidence.append(fingerprint_message)
        if fingerprint_status == "fail":
            hard_fail = True

        usage_status, usage_score_delta, usage_message = self._evaluate_usage_signals(observations=observations)
        score += usage_score_delta
        evidence.append(usage_message)
        if usage_status == "fail":
            hard_fail = True

        cases = {
            "family_alignment": {
                "status": family_alignment_status,
                "deviation_kind": family_alignment_status if family_alignment_status != "pass" else "aligned",
                "observed_content": family_alignment_message,
                "claimed_family": claimed_family,
                "observed_families": sorted({observation.family for observation in observations}),
            },
            "id_quality": {
                "status": id_status,
                "deviation_kind": id_status if id_status != "pass" else "id_shape_consistent",
                "observed_content": id_message,
                "duplicate_id_count": self._count_duplicate_ids(observations),
            },
            "fingerprint_signal": {
                "status": fingerprint_status,
                "deviation_kind": fingerprint_status if fingerprint_status != "pass" else "fingerprint_signal_present",
                "observed_content": fingerprint_message,
            },
            "usage_integrity": {
                "status": usage_status,
                "deviation_kind": usage_status if usage_status != "pass" else "usage_integrity_ok",
                "observed_content": usage_message,
            },
        }

        details = {
            "claimed_family": claimed_family,
            "observed_families": sorted({observation.family for observation in observations}),
            "sample_count": len(observations),
            "cases": cases,
            "samples": [self._serialize_observation(observation) for observation in observations],
        }

        if hard_fail or score < 60:
            status = "fail"
        elif score < 85 or any(case_status == "warn" for case_status in (family_alignment_status, id_status, fingerprint_status, usage_status)):
            status = "warn"
        else:
            status = "pass"

        return ProbeFinding(
            probe_name=self.name,
            status=status,
            score=max(min(score, 100), 0),
            summary="网关特征探针已按多次采样完成外壳信号比对，重点检查家族对齐、id 形态、system_fingerprint 与 usage 完整性。",
            evidence=evidence,
            details=details,
        )

    @staticmethod
    def _detect_claimed_family(model_name: str) -> str:
        normalized = model_name.strip().lower()
        if is_claude_model(normalized):
            return "anthropic"
        if is_gemini_model(normalized):
            return "gemini"
        if normalized.startswith(OPENAI_STYLE_MODEL_PREFIXES):
            return "openai"
        return "unknown"

    def _inspect_response(self, *, sample_name: str, response: AdapterResponse) -> SampleObservation:
        issues: list[str] = []
        matches: list[str] = []
        body = response.json_body if isinstance(response.json_body, dict) else {}
        family = self._detect_observed_family(body)
        metadata = build_response_metadata(response, "")
        response_id = self._extract_response_id(body)
        usage_snapshot = self._extract_usage_snapshot(body=body, family=family)

        if response.ok:
            if response_id:
                matches.append(f"提取到响应 id: {response_id}")
            else:
                issues.append("未提取到响应 id。")

            if usage_snapshot is not None:
                matches.append("提取到 usage 相关对象。")
            else:
                issues.append("未提取到 usage 相关对象。")
        else:
            issues.append(f"HTTP {response.status_code}，样本不可作为稳定外壳信号。")

        return SampleObservation(
            sample_name=sample_name,
            status_code=response.status_code,
            http_version=response.http_version,
            family=family,
            response_id=response_id,
            response_headers=metadata.get("response_headers", {}),
            system_fingerprint=metadata.get("system_fingerprint"),
            usage_snapshot=usage_snapshot,
            issues=issues,
            matches=matches,
        )

    @staticmethod
    def _detect_observed_family(body: dict[str, Any]) -> str:
        if isinstance(body.get("responseId"), str) or isinstance(body.get("usageMetadata"), dict):
            return "gemini"
        usage = body.get("usage")
        if isinstance(body.get("id"), str) and body["id"].startswith("msg_"):
            return "anthropic"
        if body.get("type") == "message":
            return "anthropic"
        if isinstance(usage, dict) and (
            isinstance(usage.get("input_tokens"), int) or isinstance(usage.get("output_tokens"), int)
        ):
            return "anthropic"
        if body.get("object") == "chat.completion":
            return "openai"
        if isinstance(body.get("id"), str) and body["id"].startswith("chatcmpl-"):
            return "openai"
        if isinstance(usage, dict) and all(field in usage for field in ("prompt_tokens", "completion_tokens", "total_tokens")):
            return "openai"
        return "unknown"

    @staticmethod
    def _extract_response_id(body: dict[str, Any]) -> str | None:
        for field_name in ("id", "responseId"):
            value = body.get(field_name)
            if isinstance(value, str) and value:
                return value
        return None

    @staticmethod
    def _extract_usage_snapshot(*, body: dict[str, Any], family: str) -> dict[str, Any] | None:
        if family == "gemini":
            usage = body.get("usageMetadata")
            return usage if isinstance(usage, dict) else None

        usage = body.get("usage")
        return usage if isinstance(usage, dict) else None

    @staticmethod
    def _evaluate_family_alignment(
        *,
        claimed_family: str,
        observations: list[SampleObservation],
    ) -> tuple[str, int, str]:
        observed_families = {observation.family for observation in observations}
        if "unknown" in observed_families:
            return (
                "warn",
                -8,
                f"部分样本无法明确识别响应外壳家族，当前观测到: {sorted(observed_families)}。",
            )

        if len(observed_families) > 1:
            return (
                "fail",
                -24,
                f"多次采样返回了不一致的外壳家族信号: {sorted(observed_families)}。",
            )

        observed_family = next(iter(observed_families))
        if claimed_family == "unknown":
            return (
                "warn",
                -4,
                f"模型名未能归类到 OpenAI / Anthropic / Gemini，当前观测外壳为 {observed_family}。",
            )

        if claimed_family == observed_family:
            return (
                "pass",
                0,
                f"声明模型族 {claimed_family} 与观测外壳信号 {observed_family} 一致。",
            )

        if observed_family == "openai" and claimed_family in {"anthropic", "gemini"}:
            return (
                "warn",
                -10,
                f"声明模型族为 {claimed_family}，但返回外壳表现为 OpenAI-compatible 风格；这更像中转网关，不直接等于模型造假。",
            )

        return (
            "fail",
            -28,
            f"声明模型族为 {claimed_family}，但返回外壳表现为 {observed_family}，存在明显家族不对齐。",
        )

    def _evaluate_id_signals(
        self,
        *,
        claimed_family: str,
        observations: list[SampleObservation],
    ) -> tuple[str, int, str]:
        score_delta = 0
        duplicate_id_count = self._count_duplicate_ids(observations)
        if duplicate_id_count > 0:
            return (
                "fail",
                -30,
                f"多次采样出现 {duplicate_id_count} 组重复响应 id，随机性与链路追踪信号异常。",
            )

        risky_samples: list[str] = []
        soft_risks: list[str] = []
        for observation in observations:
            response_id = observation.response_id
            if not response_id:
                risky_samples.append(f"{observation.sample_name} 缺少响应 id")
                continue

            if self._looks_like_uuid(response_id):
                if observation.family == "openai":
                    risky_samples.append(f"{observation.sample_name} 使用标准 UUID 作为响应 id")
                else:
                    soft_risks.append(f"{observation.sample_name} 的响应 id 形态偏 UUID 风格")
                continue

            if observation.family == "openai" and not response_id.startswith("chatcmpl-"):
                soft_risks.append(f"{observation.sample_name} 的响应 id 不是常见 chatcmpl-* 风格")
            elif observation.family == "anthropic" and not response_id.startswith("msg_"):
                soft_risks.append(f"{observation.sample_name} 的响应 id 不是常见 msg_* 风格")

        if risky_samples:
            return ("fail", -22, "；".join(risky_samples))
        if soft_risks:
            return ("warn", -8, "；".join(soft_risks))

        expected_prefix = {
            "openai": "chatcmpl-*",
            "anthropic": "msg_*",
            "gemini": "responseId",
        }.get(claimed_family, "当前观测家族")
        return ("pass", score_delta, f"多次采样的响应 id 唯一且整体符合 {expected_prefix} 的常见形态。")

    @staticmethod
    def _evaluate_fingerprint_signals(observations: list[SampleObservation]) -> tuple[str, int, str]:
        openai_like_observations = [observation for observation in observations if observation.family == "openai"]
        if not openai_like_observations:
            return (
                "pass",
                0,
                "当前样本未表现为 OpenAI 外壳，system_fingerprint 不作为主要判断项。",
            )

        fingerprint_values = [observation.system_fingerprint for observation in openai_like_observations]
        present_values = [value for value in fingerprint_values if isinstance(value, str) and value]
        if not present_values:
            return (
                "warn",
                -6,
                "OpenAI 风格样本均未返回 system_fingerprint，只能作为弱可疑信号。",
            )

        malformed = [value for value in present_values if not value.startswith("fp_")]
        if malformed:
            return (
                "warn",
                -6,
                f"检测到非常见 system_fingerprint 形态: {malformed}。",
            )

        return (
            "pass",
            0,
            "OpenAI 风格样本返回了形态合理的 system_fingerprint。",
        )

    @staticmethod
    def _evaluate_usage_signals(observations: list[SampleObservation]) -> tuple[str, int, str]:
        hard_risks: list[str] = []
        soft_risks: list[str] = []
        for observation in observations:
            usage = observation.usage_snapshot
            if not isinstance(usage, dict):
                hard_risks.append(f"{observation.sample_name} 缺少 usage/usageMetadata。")
                continue

            if observation.family == "openai":
                prompt_tokens = usage.get("prompt_tokens")
                completion_tokens = usage.get("completion_tokens")
                total_tokens = usage.get("total_tokens")
                if not all(isinstance(value, int) for value in (prompt_tokens, completion_tokens, total_tokens)):
                    hard_risks.append(f"{observation.sample_name} 的 usage 字段不完整或类型错误。")
                    continue
                if prompt_tokens + completion_tokens != total_tokens:
                    soft_risks.append(f"{observation.sample_name} 的 total_tokens 与 prompt/completion 之和不一致。")
                if prompt_tokens <= 0 or total_tokens <= 0:
                    soft_risks.append(f"{observation.sample_name} 的 usage 值异常偏小或为 0。")
            elif observation.family == "anthropic":
                input_tokens = usage.get("input_tokens")
                output_tokens = usage.get("output_tokens")
                if not isinstance(input_tokens, int) or not isinstance(output_tokens, int):
                    hard_risks.append(f"{observation.sample_name} 的 Anthropic usage 字段不完整。")
                    continue
                if input_tokens <= 0:
                    soft_risks.append(f"{observation.sample_name} 的 input_tokens 异常偏小或为 0。")
            elif observation.family == "gemini":
                prompt_tokens = usage.get("promptTokenCount")
                total_tokens = usage.get("totalTokenCount")
                if not isinstance(prompt_tokens, int) or not isinstance(total_tokens, int):
                    hard_risks.append(f"{observation.sample_name} 的 Gemini usageMetadata 字段不完整。")
                    continue
                if prompt_tokens <= 0 or total_tokens <= 0:
                    soft_risks.append(f"{observation.sample_name} 的 promptTokenCount/totalTokenCount 异常偏小或为 0。")
            else:
                soft_risks.append(f"{observation.sample_name} 的 usage 无法映射到已知家族结构。")

        if hard_risks:
            return ("fail", -24, "；".join(hard_risks))
        if soft_risks:
            return ("warn", -8, "；".join(soft_risks))
        return ("pass", 0, "多次采样的 usage 结构完整，且核心计数字段语义自洽。")

    @staticmethod
    def _count_duplicate_ids(observations: list[SampleObservation]) -> int:
        seen: set[str] = set()
        duplicate_count = 0
        for observation in observations:
            if not observation.response_id:
                continue
            if observation.response_id in seen:
                duplicate_count += 1
            else:
                seen.add(observation.response_id)
        return duplicate_count

    @staticmethod
    def _looks_like_uuid(value: str) -> bool:
        try:
            UUID(value)
        except ValueError:
            return False
        return True

    @staticmethod
    def _serialize_observation(observation: SampleObservation) -> dict[str, Any]:
        return {
            "sample_name": observation.sample_name,
            "status_code": observation.status_code,
            "http_version": observation.http_version,
            "family": observation.family,
            "response_id": observation.response_id,
            "system_fingerprint": observation.system_fingerprint,
            "usage_snapshot": observation.usage_snapshot,
            "response_headers": observation.response_headers,
            "issues": observation.issues,
            "matches": observation.matches,
        }
