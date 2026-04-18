from __future__ import annotations

import json
from typing import Any

from app.modules.detection.probes.base import DetectionProbe, ProbeRuntime
from app.modules.detection.probes.helpers import (
    build_response_metadata,
    classify_status_code,
    extract_message,
)
from app.modules.detection.schemas import ProbeFinding


class ParameterProbe(DetectionProbe):
    name = "parameter_probe"

    async def run(self, runtime: ProbeRuntime) -> ProbeFinding:
        case_findings = []
        case_findings.append(await self._run_json_schema_case(runtime))
        case_findings.append(await self._run_tool_call_case(runtime))

        score = int(sum(item["score"] for item in case_findings) / len(case_findings))
        statuses = [item["status"] for item in case_findings]
        status = "pass" if all(item == "pass" for item in statuses) else "fail" if "fail" in statuses else "warn"

        supported_count = sum(1 for item in case_findings if item["status"] == "pass")
        ignored_count = sum(1 for item in case_findings if item["ignored"])
        evidence = [item["evidence"] for item in case_findings]

        return ProbeFinding(
            probe_name=self.name,
            status=status,
            score=score,
            summary=(
                f"参数探针完成，共检测 {len(case_findings)} 项特性；"
                f"明确支持 {supported_count} 项，疑似静默忽略 {ignored_count} 项。"
            ),
            evidence=evidence,
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

    async def _run_json_schema_case(self, runtime: ProbeRuntime) -> dict[str, Any]:
        response = await runtime.adapter.create_chat_completion(
            messages=[
                {
                    "role": "user",
                    "content": "Return a JSON object with only one field named answer and value ok.",
                }
            ],
            extra_body={
                "response_format": {
                    "type": "json_schema",
                    "json_schema": {
                        "name": "compatibility_contract",
                        "schema": {
                            "type": "object",
                            "properties": {
                                "answer": {"type": "string"},
                            },
                            "required": ["answer"],
                            "additionalProperties": False,
                        },
                        "strict": True,
                    },
                }
            },
        )

        non_success_result = self._build_non_success_result(
            case_name="response_format_json_schema",
            feature_label="response_format=json_schema",
            runtime=runtime,
            response=response,
        )
        if non_success_result is not None:
            return non_success_result

        content = self._extract_message_content(response.json_body)
        if isinstance(content, str):
            try:
                parsed = json.loads(content)
            except json.JSONDecodeError:
                parsed = None
            if isinstance(parsed, dict) and parsed.get("answer") == "ok":
                return {
                    "name": "response_format_json_schema",
                    "status": "pass",
                    "score": 95,
                    "ignored": False,
                    "evidence": "response_format=json_schema 生效，返回内容符合约束。",
                    "details": build_response_metadata(response, runtime.adapter.endpoint_url),
                }

        return {
            "name": "response_format_json_schema",
            "status": "fail",
            "score": 25,
            "ignored": True,
            "evidence": "response_format=json_schema 请求成功但未返回受约束 JSON，疑似参数被忽略。",
            "details": build_response_metadata(response, runtime.adapter.endpoint_url),
        }

    async def _run_tool_call_case(self, runtime: ProbeRuntime) -> dict[str, Any]:
        response = await runtime.adapter.create_chat_completion(
            messages=[
                {
                    "role": "user",
                    "content": "Call the inspect_target tool with provider=openai-compatible and confidence=0.9.",
                }
            ],
            extra_body={
                "tools": [
                    {
                        "type": "function",
                        "function": {
                            "name": "inspect_target",
                            "description": "Return the provider name and confidence.",
                            "parameters": {
                                "type": "object",
                                "properties": {
                                    "provider": {"type": "string"},
                                    "confidence": {"type": "number"},
                                },
                                "required": ["provider", "confidence"],
                                "additionalProperties": False,
                            },
                        },
                    }
                ],
                "tool_choice": "required",
            },
        )

        non_success_result = self._build_non_success_result(
            case_name="tools_and_tool_choice",
            feature_label="tools/tool_choice",
            runtime=runtime,
            response=response,
        )
        if non_success_result is not None:
            return non_success_result

        tool_calls = self._extract_tool_calls(response.json_body)
        if tool_calls:
            return {
                "name": "tools_and_tool_choice",
                "status": "pass",
                "score": 92,
                "ignored": False,
                "evidence": "tools/tool_choice 生效，响应返回了 tool_calls。",
                "details": {
                    **build_response_metadata(response, runtime.adapter.endpoint_url),
                    "tool_call_count": len(tool_calls),
                },
            }

        return {
            "name": "tools_and_tool_choice",
            "status": "fail",
            "score": 20,
            "ignored": True,
            "evidence": "tools/tool_choice 请求成功但没有返回 tool_calls，疑似参数被忽略。",
            "details": build_response_metadata(response, runtime.adapter.endpoint_url),
        }

    @staticmethod
    def _extract_message_content(body: Any) -> str | None:
        message = extract_message(body)
        if not message:
            return None
        content = message.get("content")
        return content if isinstance(content, str) else None

    @staticmethod
    def _extract_tool_calls(body: Any) -> list[dict[str, Any]]:
        if not isinstance(body, dict):
            return []
        choices = body.get("choices")
        if not isinstance(choices, list) or not choices:
            return []
        first_choice = choices[0]
        if not isinstance(first_choice, dict):
            return []
        message = first_choice.get("message")
        if not isinstance(message, dict):
            return []
        tool_calls = message.get("tool_calls")
        if not isinstance(tool_calls, list):
            return []
        return [item for item in tool_calls if isinstance(item, dict)]

    @staticmethod
    def _build_non_success_result(
        *,
        case_name: str,
        feature_label: str,
        runtime: ProbeRuntime,
        response: Any,
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
                "ignored": False,
                "evidence": f"{feature_label} 触发了服务端异常，HTTP {response.status_code}。",
                "details": details,
            }

        if status_group == "auth_error":
            return {
                "name": case_name,
                "status": "warn",
                "score": 35,
                "ignored": False,
                "evidence": f"{feature_label} 请求未通过鉴权，HTTP {response.status_code}。",
                "details": details,
            }

        return {
            "name": case_name,
            "status": "warn",
            "score": 68,
            "ignored": False,
            "evidence": f"{feature_label} 被显式拒绝，HTTP {response.status_code}。",
            "details": details,
        }
