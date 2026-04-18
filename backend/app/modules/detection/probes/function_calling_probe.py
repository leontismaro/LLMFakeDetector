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


FUNCTION_CALLING_PROMPTS = load_prompt_bundle("function_calling_probe.json")
COMPLEX_SCHEMA_CONFIG = FUNCTION_CALLING_PROMPTS["complex_schema_case"]
TOOL_SELECTION_CONFIG = FUNCTION_CALLING_PROMPTS["tool_selection_case"]


class FunctionCallingProbe(DetectionProbe):
    name = "function_calling_probe"

    async def run(self, runtime: ProbeRuntime) -> ProbeFinding:
        case_findings = [
            await self._run_complex_schema_case(runtime),
            await self._run_tool_selection_case(runtime),
        ]

        score = int(sum(item["score"] for item in case_findings) / len(case_findings))
        statuses = [item["status"] for item in case_findings]
        status = "pass" if all(item == "pass" for item in statuses) else "fail" if "fail" in statuses else "warn"

        return ProbeFinding(
            probe_name=self.name,
            status=status,
            score=score,
            summary=(
                f"复杂 Function Calling 探针完成，共检测 {len(case_findings)} 项场景；"
                f"严格通过 {sum(1 for item in case_findings if item['status'] == 'pass')} 项，"
                f"存在工具选择或参数结构风险 {sum(1 for item in case_findings if item['status'] != 'pass')} 项。"
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

    async def _run_complex_schema_case(self, runtime: ProbeRuntime) -> dict[str, Any]:
        response = await runtime.adapter.create_chat_completion(
            messages=[
                {"role": "system", "content": COMPLEX_SCHEMA_CONFIG["system_prompt"]},
                {"role": "user", "content": COMPLEX_SCHEMA_CONFIG["user_prompt"]},
            ],
            extra_body={
                "tools": [COMPLEX_SCHEMA_CONFIG["tool"]],
                "tool_choice": "required",
            },
        )

        return self._evaluate_tool_case(
            runtime=runtime,
            response=response,
            case_name="complex_schema_case",
            feature_label="复杂嵌套 Function Calling 测试",
            expected_tool_name=COMPLEX_SCHEMA_CONFIG["tool"]["function"]["name"],
            expected_arguments=COMPLEX_SCHEMA_CONFIG["expected_arguments"],
            success_evidence="复杂嵌套 Function Calling 测试通过，模型返回了正确工具和严格匹配的嵌套参数。",
        )

    async def _run_tool_selection_case(self, runtime: ProbeRuntime) -> dict[str, Any]:
        response = await runtime.adapter.create_chat_completion(
            messages=[
                {"role": "system", "content": TOOL_SELECTION_CONFIG["system_prompt"]},
                {"role": "user", "content": TOOL_SELECTION_CONFIG["user_prompt"]},
            ],
            extra_body={
                "tools": TOOL_SELECTION_CONFIG["tools"],
                "tool_choice": "required",
            },
        )

        return self._evaluate_tool_case(
            runtime=runtime,
            response=response,
            case_name="tool_selection_case",
            feature_label="多工具选择 Function Calling 测试",
            expected_tool_name=TOOL_SELECTION_CONFIG["expected_tool_name"],
            expected_arguments=TOOL_SELECTION_CONFIG["expected_arguments"],
            success_evidence="多工具选择 Function Calling 测试通过，模型选择了正确工具并生成了精确参数。",
        )

    def _evaluate_tool_case(
        self,
        *,
        runtime: ProbeRuntime,
        response: Any,
        case_name: str,
        feature_label: str,
        expected_tool_name: str,
        expected_arguments: dict[str, Any],
        success_evidence: str,
    ) -> dict[str, Any]:
        non_success_result = self._build_non_success_result(
            case_name=case_name,
            runtime=runtime,
            response=response,
            feature_label=feature_label,
        )
        if non_success_result is not None:
            return non_success_result

        tool_calls = self._extract_tool_calls(response.json_body)
        message = extract_message(response.json_body)
        fallback_content = message.get("content") if isinstance(message, dict) else None
        details = {
            **build_response_metadata(response, runtime.adapter.endpoint_url),
            "tool_call_count": len(tool_calls),
        }

        if not tool_calls:
            return {
                "name": case_name,
                "status": "fail",
                "score": 20,
                "evidence": f"{feature_label}失败，响应成功但没有返回任何 tool_calls。",
                "details": {
                    **details,
                    "deviation_kind": "missing_tool_calls",
                    "observed_content": fallback_content,
                },
            }

        first_tool_call = tool_calls[0]
        function_payload = first_tool_call.get("function")
        if not isinstance(function_payload, dict):
            return {
                "name": case_name,
                "status": "fail",
                "score": 18,
                "evidence": f"{feature_label}失败，tool_calls[0].function 结构不可解析。",
                "details": {
                    **details,
                    "deviation_kind": "invalid_function_payload",
                    "observed_content": json.dumps(first_tool_call, ensure_ascii=True),
                },
            }

        selected_tool_name = function_payload.get("name")
        raw_arguments = function_payload.get("arguments")
        details.update(
            {
                "selected_tool_name": selected_tool_name,
                "observed_content": raw_arguments if isinstance(raw_arguments, str) else fallback_content,
            }
        )

        if selected_tool_name != expected_tool_name:
            return {
                "name": case_name,
                "status": "fail",
                "score": 22,
                "evidence": f"{feature_label}失败，模型选择了错误工具 {selected_tool_name!r}，预期为 {expected_tool_name!r}。",
                "details": {**details, "deviation_kind": "wrong_tool_selected"},
            }

        parsed_arguments = self._parse_json_arguments(raw_arguments)
        if parsed_arguments is None:
            return {
                "name": case_name,
                "status": "fail",
                "score": 24,
                "evidence": f"{feature_label}失败，工具参数不是可解析的 JSON 字符串。",
                "details": {**details, "deviation_kind": "invalid_argument_json"},
            }

        mismatch_paths = self._collect_mismatch_paths(
            actual=parsed_arguments,
            expected=expected_arguments,
            current_path="arguments",
        )
        if mismatch_paths:
            return {
                "name": case_name,
                "status": "warn",
                "score": 64,
                "evidence": f"{feature_label}部分通过，模型选对了工具，但参数结构与预期不完全一致。",
                "details": {
                    **details,
                    "deviation_kind": "argument_contract_mismatch",
                    "mismatch_paths": mismatch_paths[:8],
                    "parsed_arguments": parsed_arguments,
                },
            }

        if len(tool_calls) > 1:
            return {
                "name": case_name,
                "status": "warn",
                "score": 78,
                "evidence": f"{feature_label}部分通过，首个工具调用正确，但返回了额外的 tool_calls。",
                "details": {
                    **details,
                    "deviation_kind": "extra_tool_calls",
                    "parsed_arguments": parsed_arguments,
                },
            }

        return {
            "name": case_name,
            "status": "pass",
            "score": 93,
            "evidence": success_evidence,
            "details": {
                **details,
                "parsed_arguments": parsed_arguments,
            },
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
                "evidence": f"{feature_label}触发了服务端异常，HTTP {response.status_code}。",
                "details": details,
            }

        if status_group == "auth_error":
            return {
                "name": case_name,
                "status": "warn",
                "score": 35,
                "evidence": f"{feature_label}未通过鉴权，HTTP {response.status_code}。",
                "details": details,
            }

        return {
            "name": case_name,
            "status": "warn",
            "score": 68,
            "evidence": f"{feature_label}被显式拒绝，HTTP {response.status_code}。",
            "details": details,
        }

    @staticmethod
    def _extract_tool_calls(body: Any) -> list[dict[str, Any]]:
        message = extract_message(body)
        if not message:
            return []
        tool_calls = message.get("tool_calls")
        if not isinstance(tool_calls, list):
            return []
        return [tool_call for tool_call in tool_calls if isinstance(tool_call, dict)]

    @staticmethod
    def _parse_json_arguments(raw_arguments: Any) -> dict[str, Any] | None:
        if not isinstance(raw_arguments, str):
            return None
        try:
            parsed = json.loads(raw_arguments)
        except json.JSONDecodeError:
            return None
        return parsed if isinstance(parsed, dict) else None

    @classmethod
    def _collect_mismatch_paths(
        cls,
        *,
        actual: Any,
        expected: Any,
        current_path: str,
    ) -> list[str]:
        if type(actual) is not type(expected):
            return [current_path]

        mismatches: list[str] = []
        if isinstance(expected, dict):
            actual_keys = set(actual.keys())
            expected_keys = set(expected.keys())

            for missing_key in sorted(expected_keys - actual_keys):
                mismatches.append(f"{current_path}.{missing_key}")
            for extra_key in sorted(actual_keys - expected_keys):
                mismatches.append(f"{current_path}.{extra_key}")
            for key in sorted(actual_keys & expected_keys):
                mismatches.extend(
                    cls._collect_mismatch_paths(
                        actual=actual[key],
                        expected=expected[key],
                        current_path=f"{current_path}.{key}",
                    )
                )
            return mismatches

        if isinstance(expected, list):
            if len(actual) != len(expected):
                mismatches.append(f"{current_path}.length")
            for index, (actual_item, expected_item) in enumerate(zip(actual, expected, strict=False)):
                mismatches.extend(
                    cls._collect_mismatch_paths(
                        actual=actual_item,
                        expected=expected_item,
                        current_path=f"{current_path}[{index}]",
                    )
                )
            return mismatches

        if actual != expected:
            return [current_path]
        return []
