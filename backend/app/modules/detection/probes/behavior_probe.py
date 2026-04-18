from __future__ import annotations

import json
from typing import Any

from app.modules.detection.prompts.loader import load_prompt_bundle
from app.modules.detection.probes.base import DetectionProbe, ProbeRuntime
from app.modules.detection.probes.helpers import (
    build_response_metadata,
    classify_status_code,
    extract_message,
)
from app.modules.detection.schemas import ProbeFinding


BEHAVIOR_PROMPTS = load_prompt_bundle("behavior_probe.json")
STRICT_JSON_CONFIG = BEHAVIOR_PROMPTS["strict_json_compliance"]
IDENTITY_CONFLICT_CONFIG = BEHAVIOR_PROMPTS["identity_conflict_probe"]
PROMPT_ECHO_CONFIG = BEHAVIOR_PROMPTS["prompt_echo_probe"]
STRICT_JSON_TARGET = STRICT_JSON_CONFIG["expected_json"]
IDENTITY_LOCKWORD = IDENTITY_CONFLICT_CONFIG["lockword"]
SUSPICIOUS_IDENTITY_MARKERS = tuple(BEHAVIOR_PROMPTS["suspicious_identity_markers"])


class BehaviorProbe(DetectionProbe):
    name = "behavior_probe"

    async def run(self, runtime: ProbeRuntime) -> ProbeFinding:
        case_findings = [
            await self._run_strict_json_case(runtime),
            await self._run_identity_conflict_case(runtime),
            await self._run_prompt_echo_case(runtime),
        ]

        score = int(sum(item["score"] for item in case_findings) / len(case_findings))
        statuses = [item["status"] for item in case_findings]
        status = "pass" if all(item == "pass" for item in statuses) else "fail" if "fail" in statuses else "warn"

        return ProbeFinding(
            probe_name=self.name,
            status=status,
            score=score,
            summary=(
                f"行为探针完成，共检测 {len(case_findings)} 项行为约束；"
                f"严格依从 {sum(1 for item in case_findings if item['status'] == 'pass')} 项，"
                f"存在偏离或注入风险 {sum(1 for item in case_findings if item['status'] != 'pass')} 项。"
            ),
            evidence=[item["evidence"] for item in case_findings],
            details={
                "endpoint_url": runtime.adapter.endpoint_url,
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

    async def _run_strict_json_case(self, runtime: ProbeRuntime) -> dict[str, Any]:
        response = await runtime.adapter.create_chat_completion(
            messages=[
                {
                    "role": "system",
                    "content": STRICT_JSON_CONFIG["system_prompt"],
                },
                {
                    "role": "user",
                    "content": STRICT_JSON_CONFIG["user_prompt"],
                },
            ]
        )

        non_success_result = self._build_non_success_result(
            case_name="strict_json_compliance",
            runtime=runtime,
            response=response,
            feature_label="严格 JSON 依从性测试",
        )
        if non_success_result is not None:
            return non_success_result

        content = self._extract_message_content(response.json_body)
        details = {
            **build_response_metadata(response, runtime.adapter.endpoint_url),
            "observed_content": content,
        }

        if not isinstance(content, str):
            return {
                "name": "strict_json_compliance",
                "status": "fail",
                "score": 20,
                "evidence": "严格 JSON 依从性测试失败，响应缺少可解析的文本内容。",
                "details": {**details, "deviation_kind": "missing_text_content"},
            }

        if content != json.dumps(STRICT_JSON_TARGET, separators=(",", ":"), ensure_ascii=True):
            parsed = self._try_parse_json(content)
            if parsed == STRICT_JSON_TARGET:
                return {
                    "name": "strict_json_compliance",
                    "status": "warn",
                    "score": 70,
                    "evidence": "严格 JSON 依从性测试出现轻度偏离，主体 JSON 正确，但输出不是要求的唯一最小化 JSON 文本。",
                    "details": {**details, "deviation_kind": "non_minified_or_extra_wrapping"},
                }

            return {
                "name": "strict_json_compliance",
                "status": "fail",
                "score": 28,
                "evidence": "严格 JSON 依从性测试失败，响应未严格遵守指定 JSON 结构。",
                "details": {**details, "deviation_kind": "json_contract_mismatch"},
            }

        return {
            "name": "strict_json_compliance",
            "status": "pass",
            "score": 94,
            "evidence": "严格 JSON 依从性测试通过，响应完全符合指定的唯一最小化 JSON。",
            "details": details,
        }

    async def _run_identity_conflict_case(self, runtime: ProbeRuntime) -> dict[str, Any]:
        response = await runtime.adapter.create_chat_completion(
            messages=[
                {
                    "role": "system",
                    "content": IDENTITY_CONFLICT_CONFIG["system_prompt_template"].format(lockword=IDENTITY_LOCKWORD),
                },
                {
                    "role": "user",
                    "content": IDENTITY_CONFLICT_CONFIG["user_prompt"],
                },
            ]
        )

        non_success_result = self._build_non_success_result(
            case_name="identity_conflict_probe",
            runtime=runtime,
            response=response,
            feature_label="身份冲突与伪装注入测试",
        )
        if non_success_result is not None:
            return non_success_result

        content = self._extract_message_content(response.json_body)
        details = {
            **build_response_metadata(response, runtime.adapter.endpoint_url),
            "observed_content": content,
        }

        if not isinstance(content, str):
            return {
                "name": "identity_conflict_probe",
                "status": "fail",
                "score": 18,
                "evidence": "身份冲突测试失败，响应缺少可解析的文本内容。",
                "details": {**details, "deviation_kind": "missing_text_content"},
            }

        normalized = content.strip()
        lowered = normalized.lower()
        leaked_system_prompt = "system prompt" in lowered or "word for word" in lowered
        suspicious_markers = [marker for marker in SUSPICIOUS_IDENTITY_MARKERS if marker in lowered]

        if suspicious_markers or leaked_system_prompt:
            return {
                "name": "identity_conflict_probe",
                "status": "fail",
                "score": 8,
                "evidence": "身份冲突测试失败，响应出现了可疑身份词或系统提示痕迹，疑似存在额外伪装注入。",
                "details": {
                    **details,
                    "deviation_kind": "identity_injection_suspected",
                    "suspicious_identity_markers": suspicious_markers,
                    "leaked_system_prompt": leaked_system_prompt,
                },
            }

        if normalized == IDENTITY_LOCKWORD:
            return {
                "name": "identity_conflict_probe",
                "status": "pass",
                "score": 92,
                "evidence": "身份冲突测试通过，响应遵守了固定口令约束，未暴露可疑厂商身份词。",
                "details": details,
            }

        return {
            "name": "identity_conflict_probe",
            "status": "warn",
            "score": 68,
            "evidence": "身份冲突测试部分通过，未发现明确伪装身份词，但输出没有严格遵守固定口令约束。",
            "details": {**details, "deviation_kind": "lockword_not_preserved"},
        }

    async def _run_prompt_echo_case(self, runtime: ProbeRuntime) -> dict[str, Any]:
        response = await runtime.adapter.create_chat_completion(
            messages=[
                {
                    "role": "user",
                    "content": PROMPT_ECHO_CONFIG["user_prompt"],
                }
            ]
        )

        non_success_result = self._build_non_success_result(
            case_name="prompt_echo_probe",
            runtime=runtime,
            response=response,
            feature_label="纯 user 提示词回显测试",
        )
        if non_success_result is not None:
            return non_success_result

        content = self._extract_message_content(response.json_body)
        details = {
            **build_response_metadata(response, runtime.adapter.endpoint_url),
            "observed_content": content,
        }

        if not isinstance(content, str):
            return {
                "name": "prompt_echo_probe",
                "status": "fail",
                "score": 18,
                "evidence": "纯 user 提示词回显测试失败，响应缺少可解析的文本内容。",
                "details": {**details, "deviation_kind": "missing_text_content"},
            }

        normalized = content.strip()
        lowered = normalized.lower()
        suspicious_markers = [marker for marker in SUSPICIOUS_IDENTITY_MARKERS if marker in lowered]
        leaked_system_prompt = "you are " in lowered or "system prompt" in lowered or "created by" in lowered

        if suspicious_markers:
            return {
                "name": "prompt_echo_probe",
                "status": "fail",
                "score": 10,
                "evidence": "纯 user 提示词回显测试失败，响应出现了疑似后台注入的身份提示或系统提示回显。",
                "details": {
                    **details,
                    "deviation_kind": "prompt_echo_suspected",
                    "suspicious_identity_markers": suspicious_markers,
                    "leaked_system_prompt": leaked_system_prompt,
                },
            }

        if leaked_system_prompt:
            return {
                "name": "prompt_echo_probe",
                "status": "warn",
                "score": 56,
                "evidence": "纯 user 提示词回显测试出现可疑回显，响应包含泛化的 system prompt 或身份说明，但未出现明确厂商身份词，建议人工复核。",
                "details": {
                    **details,
                    "deviation_kind": "generic_prompt_echo",
                    "suspicious_identity_markers": suspicious_markers,
                    "leaked_system_prompt": leaked_system_prompt,
                },
            }

        if len(normalized) <= 48:
            return {
                "name": "prompt_echo_probe",
                "status": "pass",
                "score": 88,
                "evidence": "纯 user 提示词回显测试通过，未观察到可疑身份注入提示回显。",
                "details": details,
            }

        return {
            "name": "prompt_echo_probe",
            "status": "warn",
            "score": 64,
            "evidence": "纯 user 提示词回显测试部分通过，未发现明确身份注入词，但回显内容较长，建议人工复核。",
            "details": {**details, "deviation_kind": "verbose_refusal"},
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
    def _try_parse_json(content: str) -> Any:
        try:
            return json.loads(content)
        except json.JSONDecodeError:
            return None
