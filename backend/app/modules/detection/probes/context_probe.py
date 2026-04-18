from __future__ import annotations

import re
from typing import Any, Protocol

from app.modules.detection.prompts.loader import load_prompt_bundle
from app.modules.detection.probes.base import DetectionProbe, ProbeRuntime
from app.modules.detection.probes.helpers import (
    build_response_metadata,
    classify_status_code,
    extract_message,
)
from app.modules.detection.schemas import ProbeFinding


CONTEXT_PROMPTS = load_prompt_bundle("context_probe.json")
NEEDLE_CONFIG = CONTEXT_PROMPTS["needle_in_haystack"]
LONG_OUTPUT_CONFIG = CONTEXT_PROMPTS["long_output_probe"]
ROW_PATTERN = re.compile(r"^row-(\d{2}): value-(\d{2})$")
OPENAI_STYLE_MODEL_PREFIXES = (
    "gpt-",
    "chatgpt-",
    "o1",
    "o3",
    "o4",
)
CONTEXT_MODE_PROFILE_MAP = {
    "light": ("small",),
    "standard": ("small", "medium"),
    "heavy": ("small", "medium", "large"),
}


class EncodingProtocol(Protocol):
    name: str

    def encode(self, text: str) -> list[int]:
        ...


class ContextProbe(DetectionProbe):
    name = "context_probe"

    async def run(self, runtime: ProbeRuntime) -> ProbeFinding:
        encoding = self._resolve_context_encoding(runtime.request.model_name)
        selected_profiles = CONTEXT_MODE_PROFILE_MAP[runtime.request.context_mode]
        case_findings = [
            await self._run_needle_case(runtime, profile_name, NEEDLE_CONFIG["profiles"][profile_name], encoding)
            for profile_name in selected_profiles
        ]
        case_findings.append(await self._run_long_output_case(runtime))

        score = int(sum(item["score"] for item in case_findings) / len(case_findings))
        statuses = [item["status"] for item in case_findings]
        status = "pass" if all(item == "pass" for item in statuses) else "fail" if "fail" in statuses else "warn"

        return ProbeFinding(
            probe_name=self.name,
            status=status,
            score=score,
            summary=(
                f"上下文能力探针完成，共检测 {len(case_findings)} 项能力约束；"
                f"通过 {sum(1 for item in case_findings if item['status'] == 'pass')} 项，"
                f"存在容量或稳定性风险 {sum(1 for item in case_findings if item['status'] != 'pass')} 项。"
            ),
            evidence=[item["evidence"] for item in case_findings],
            details={
                "endpoint_url": runtime.adapter.endpoint_url,
                "context_mode": runtime.request.context_mode,
                "selected_profiles": list(selected_profiles),
                "context_reference_encoding": encoding.name,
                "cases": {
                    item["name"]: {
                        "status": item["status"],
                        "evidence": item["evidence"],
                        **item["details"],
                    }
                    for item in case_findings
                },
            },
        )

    async def _run_needle_case(
        self,
        runtime: ProbeRuntime,
        profile_name: str,
        profile_config: dict[str, Any],
        encoding: EncodingProtocol,
    ) -> dict[str, Any]:
        context, context_stats = self._build_needle_context(encoding, int(profile_config["target_context_tokens"]))
        response = await runtime.adapter.create_chat_completion(
            messages=[
                {
                    "role": "system",
                    "content": NEEDLE_CONFIG["system_prompt"],
                },
                {
                    "role": "user",
                    "content": NEEDLE_CONFIG["user_prompt_template"].format(context=context),
                },
            ],
            extra_body={"max_tokens": int(profile_config.get("max_tokens", 32))},
        )

        case_name = f"needle_in_haystack_{profile_name}"
        non_success_result = self._build_non_success_result(
            case_name=case_name,
            runtime=runtime,
            response=response,
            feature_label=f"大海捞针测试（{profile_name}）",
        )
        if non_success_result is not None:
            return non_success_result

        content = self._extract_message_content(response.json_body)
        details = {
            **build_response_metadata(response, runtime.adapter.endpoint_url),
            "observed_content": content,
            "target_profile": profile_name,
            "target_context_tokens": int(profile_config["target_context_tokens"]),
            "expected_answer": NEEDLE_CONFIG["expected_answer"],
            **context_stats,
        }

        if not isinstance(content, str):
            return {
                "name": case_name,
                "status": "fail",
                "score": 20,
                "evidence": f"大海捞针测试（{profile_name}）失败，响应缺少可解析的文本内容。",
                "details": {**details, "deviation_kind": "missing_text_content"},
            }

        normalized = content.strip()
        if normalized == NEEDLE_CONFIG["expected_answer"]:
            return {
                "name": case_name,
                "status": "pass",
                "score": 92,
                "evidence": f"大海捞针测试（{profile_name}）通过，模型成功从长上下文中准确提取出验证口令。",
                "details": details,
            }

        if NEEDLE_CONFIG["expected_answer"].lower() in normalized.lower():
            return {
                "name": case_name,
                "status": "warn",
                "score": 72,
                "evidence": f"大海捞针测试（{profile_name}）部分通过，模型找到了目标口令，但输出不够干净，存在额外文本。",
                "details": {**details, "deviation_kind": "extra_wrapping"},
            }

        return {
            "name": case_name,
            "status": "fail",
            "score": 30,
            "evidence": f"大海捞针测试（{profile_name}）失败，模型未能从长上下文中稳定找回目标口令。",
            "details": {**details, "deviation_kind": "needle_not_found"},
        }

    async def _run_long_output_case(self, runtime: ProbeRuntime) -> dict[str, Any]:
        response = await runtime.adapter.create_chat_completion(
            messages=[
                {
                    "role": "system",
                    "content": LONG_OUTPUT_CONFIG["system_prompt"],
                },
                {
                    "role": "user",
                    "content": LONG_OUTPUT_CONFIG["user_prompt"],
                },
            ],
            extra_body={"max_tokens": 700},
        )

        non_success_result = self._build_non_success_result(
            case_name="long_output_probe",
            runtime=runtime,
            response=response,
            feature_label="长输出格式稳定性测试",
        )
        if non_success_result is not None:
            return non_success_result

        content = self._extract_message_content(response.json_body)
        details = {
            **build_response_metadata(response, runtime.adapter.endpoint_url),
            "observed_content": content,
            "expected_line_count": LONG_OUTPUT_CONFIG["expected_line_count"],
        }

        if not isinstance(content, str):
            return {
                "name": "long_output_probe",
                "status": "fail",
                "score": 18,
                "evidence": "长输出格式稳定性测试失败，响应缺少可解析的文本内容。",
                "details": {**details, "deviation_kind": "missing_text_content"},
            }

        lines = [line for line in content.splitlines() if line.strip()]
        valid_line_count = 0
        sequential_match_count = 0

        for index, line in enumerate(lines, start=1):
            match = ROW_PATTERN.fullmatch(line.strip())
            if not match:
                continue
            valid_line_count += 1
            left_value, right_value = match.groups()
            expected_value = f"{index:02d}"
            if left_value == expected_value and right_value == expected_value:
                sequential_match_count += 1

        details.update(
            {
                "observed_line_count": len(lines),
                "valid_line_count": valid_line_count,
                "sequential_match_count": sequential_match_count,
            }
        )

        expected_line_count = int(LONG_OUTPUT_CONFIG["expected_line_count"])
        if valid_line_count == expected_line_count and sequential_match_count == expected_line_count:
            return {
                "name": "long_output_probe",
                "status": "pass",
                "score": 90,
                "evidence": "长输出格式稳定性测试通过，模型完整输出了要求的 40 行结构化内容。",
                "details": details,
            }

        if valid_line_count >= expected_line_count * 0.8 and sequential_match_count >= expected_line_count * 0.7:
            return {
                "name": "long_output_probe",
                "status": "warn",
                "score": 68,
                "evidence": "长输出格式稳定性测试出现轻度退化，主体结构仍可辨认，但存在截断或格式漂移。",
                "details": {**details, "deviation_kind": "partial_truncation_or_format_drift"},
            }

        return {
            "name": "long_output_probe",
            "status": "fail",
            "score": 28,
            "evidence": "长输出格式稳定性测试失败，输出明显截断或结构约束大面积失效。",
            "details": {**details, "deviation_kind": "severe_truncation_or_format_failure"},
        }

    @staticmethod
    def _build_non_success_result(
        *,
        case_name: str,
        runtime: ProbeRuntime,
        response: Any,
        feature_label: str,
    ) -> dict[str, Any] | None:
        if response.ok:
            return None

        status_group = classify_status_code(response.status_code)
        details = {
            **build_response_metadata(response, runtime.adapter.endpoint_url),
            "failure_kind": status_group,
        }

        if status_group == "server_error":
            return {
                "name": case_name,
                "status": "fail",
                "score": 10,
                "evidence": f"{feature_label} 触发了服务端异常，HTTP {response.status_code}。",
                "details": details,
            }

        if status_group == "auth_error":
            return {
                "name": case_name,
                "status": "warn",
                "score": 35,
                "evidence": f"{feature_label} 未通过鉴权，HTTP {response.status_code}。",
                "details": details,
            }

        return {
            "name": case_name,
            "status": "warn",
            "score": 55,
            "evidence": f"{feature_label} 被接口显式拒绝，HTTP {response.status_code}。",
            "details": details,
        }

    @staticmethod
    def _extract_message_content(body: Any) -> str | None:
        message = extract_message(body)
        if not message:
            return None
        content = message.get("content")
        return content if isinstance(content, str) else None

    @staticmethod
    def _resolve_context_encoding(model_name: str) -> EncodingProtocol:
        import tiktoken

        try:
            return tiktoken.encoding_for_model(model_name)
        except KeyError:
            fallback_name = "o200k_base" if model_name.startswith(OPENAI_STYLE_MODEL_PREFIXES) else "cl100k_base"
            return tiktoken.get_encoding(fallback_name)

    @staticmethod
    def _build_needle_context(encoding: EncodingProtocol, target_context_tokens: int) -> tuple[str, dict[str, int | str]]:
        filler_sections: list[str] = []
        canary_text = NEEDLE_CONFIG["canary_text"]
        cumulative_tokens = 0
        inserted = False
        section_index = 1
        half_budget = max(target_context_tokens // 2, 1)

        while cumulative_tokens < target_context_tokens:
            filler_text = NEEDLE_CONFIG["filler_unit"].format(index=f"{section_index:04d}")
            filler_sections.append(filler_text)
            cumulative_tokens += len(encoding.encode(filler_text))

            if not inserted and cumulative_tokens >= half_budget:
                filler_sections.append(canary_text)
                cumulative_tokens += len(encoding.encode(canary_text))
                inserted = True

            section_index += 1

        if not inserted:
            insert_at = max(len(filler_sections) // 2, 0)
            filler_sections.insert(insert_at, canary_text)

        context = "\n".join(filler_sections)
        estimated_context_tokens = len(encoding.encode(context))
        needle_insert_index = filler_sections.index(canary_text) + 1
        return (
            context,
            {
                "context_character_count": len(context),
                "estimated_context_tokens": estimated_context_tokens,
                "context_section_count": len(filler_sections),
                "needle_insert_index": needle_insert_index,
                "context_reference_encoding": encoding.name,
            },
        )
