from typing import Any

from app.modules.detection.probes.base import DetectionProbe, ProbeRuntime
from app.modules.detection.probes.helpers import build_response_metadata, classify_status_code
from app.modules.detection.schemas import ProbeFinding


class ResponseProbe(DetectionProbe):
    name = "response_probe"

    async def run(self, runtime: ProbeRuntime) -> ProbeFinding:
        response = await runtime.adapter.create_chat_completion()
        evidence = [f"HTTP 状态码: {response.status_code}"]
        details = build_response_metadata(response, runtime.adapter.endpoint_url)

        if not response.ok:
            score, summary, failure_kind, extra_evidence = self._build_non_success_outcome(response.status_code)
            evidence.append(extra_evidence)
            return ProbeFinding(
                probe_name=self.name,
                status="fail",
                score=score,
                summary=summary,
                evidence=evidence,
                details={**details, "failure_kind": failure_kind},
            )

        if not isinstance(response.json_body, dict):
            evidence.append("响应体不是 JSON 对象。")
            return ProbeFinding(
                probe_name=self.name,
                status="fail",
                score=15,
                summary="响应结构探针失败，返回体不是标准 JSON 对象。",
                evidence=evidence,
                details=details,
            )

        score = 100
        issues: list[str] = []
        baseline_matches: list[str] = []
        baseline_risks: list[str] = []
        baseline_checks: dict[str, str] = {}
        body = response.json_body

        score, issues, baseline_matches, baseline_risks, baseline_checks = self._validate_top_level_fields(
            body=body,
            score=score,
            issues=issues,
            baseline_matches=baseline_matches,
            baseline_risks=baseline_risks,
            baseline_checks=baseline_checks,
            requested_model=runtime.request.model_name,
        )
        score, issues, baseline_matches, baseline_risks, baseline_checks = self._validate_choice_fields(
            body=body,
            score=score,
            issues=issues,
            baseline_matches=baseline_matches,
            baseline_risks=baseline_risks,
            baseline_checks=baseline_checks,
        )
        score, issues, baseline_matches, baseline_risks, baseline_checks = self._validate_usage_fields(
            body=body,
            score=score,
            issues=issues,
            baseline_matches=baseline_matches,
            baseline_risks=baseline_risks,
            baseline_checks=baseline_checks,
        )
        score, baseline_matches, baseline_risks, baseline_checks = self._validate_header_and_fingerprint_signals(
            body=body,
            details=details,
            score=score,
            baseline_matches=baseline_matches,
            baseline_risks=baseline_risks,
            baseline_checks=baseline_checks,
        )

        if issues:
            evidence.extend(issues)
        else:
            evidence.append("成功响应与 OpenAI-compatible 常见成功结构基线基本一致。")
        evidence.extend(baseline_risks)
        status = self._determine_status(score=score, baseline_checks=baseline_checks)

        return ProbeFinding(
            probe_name=self.name,
            status=status,
            score=max(score, 0),
            summary="响应结构探针已按 OpenAI-compatible 常见成功响应基线完成比对，重点检查了顶层字段、choice 语义、usage 一致性与指纹信号。",
            evidence=evidence,
            details={
                **details,
                "baseline_checks": baseline_checks,
                "baseline_matches": baseline_matches,
                "baseline_risks": baseline_risks,
            },
        )

    @staticmethod
    def _validate_top_level_fields(
        *,
        body: dict[str, Any],
        score: int,
        issues: list[str],
        baseline_matches: list[str],
        baseline_risks: list[str],
        baseline_checks: dict[str, str],
        requested_model: str,
    ) -> tuple[int, list[str], list[str], list[str], dict[str, str]]:
        expected_fields = {
            "id": str,
            "object": str,
            "created": int,
            "model": str,
            "choices": list,
        }
        has_schema_error = False
        for field_name, field_type in expected_fields.items():
            value = body.get(field_name)
            if not isinstance(value, field_type):
                score -= 15
                issues.append(f"字段 {field_name} 缺失或类型不正确。")
                has_schema_error = True

        response_id = body.get("id")
        if isinstance(response_id, str) and response_id.startswith("chatcmpl"):
            baseline_matches.append("id 前缀符合 OpenAI chat completion 常见风格。")
        elif isinstance(response_id, str):
            score -= 4
            baseline_risks.append("id 前缀不是常见的 chatcmpl-* 风格。")

        object_name = body.get("object")
        if object_name == "chat.completion":
            baseline_matches.append("object=chat.completion，符合常见成功响应类型。")
        elif isinstance(object_name, str):
            score -= 8
            issues.append(f"object={object_name}，与 chat.completion 基线不一致。")

        created = body.get("created")
        if isinstance(created, int) and created > 0:
            baseline_matches.append("created 字段为有效时间戳。")
        elif created is not None:
            score -= 6
            baseline_risks.append("created 不是有效正整数时间戳。")

        model_name = body.get("model")
        if isinstance(model_name, str):
            if model_name == requested_model:
                baseline_matches.append("响应 model 与请求模型一致。")
            elif model_name.startswith(f"{requested_model}-"):
                baseline_matches.append(f"响应 model={model_name}，表现为别名解析到具体版本。")
            else:
                score -= 10
                issues.append(f"响应 model={model_name} 与请求模型 {requested_model} 不一致。")

        baseline_checks["top_level_fields"] = "fail" if has_schema_error else "pass"
        return score, issues, baseline_matches, baseline_risks, baseline_checks

    @staticmethod
    def _validate_choice_fields(
        *,
        body: dict[str, Any],
        score: int,
        issues: list[str],
        baseline_matches: list[str],
        baseline_risks: list[str],
        baseline_checks: dict[str, str],
    ) -> tuple[int, list[str], list[str], list[str], dict[str, str]]:
        choices = body.get("choices")
        if not isinstance(choices, list) or not choices:
            score -= 25
            issues.append("choices 为空或类型错误。")
            baseline_checks["choice_shape"] = "fail"
            return score, issues, baseline_matches, baseline_risks, baseline_checks

        first_choice = choices[0]
        if not isinstance(first_choice, dict):
            score -= 20
            issues.append("首个 choice 不是对象。")
            baseline_checks["choice_shape"] = "fail"
            return score, issues, baseline_matches, baseline_risks, baseline_checks

        message = first_choice.get("message")
        if not isinstance(message, dict):
            score -= 20
            issues.append("首个 choice.message 缺失或类型错误。")
            baseline_checks["choice_shape"] = "fail"
            return score, issues, baseline_matches, baseline_risks, baseline_checks

        check_status = "pass"
        choice_index = first_choice.get("index")
        if isinstance(choice_index, int):
            baseline_matches.append("首个 choice.index 类型正确。")
        else:
            score -= 6
            check_status = "warn"
            baseline_risks.append("首个 choice.index 缺失或类型错误。")

        finish_reason = first_choice.get("finish_reason")
        if isinstance(finish_reason, str) or finish_reason is None:
            baseline_matches.append("finish_reason 字段存在且类型合理。")
        else:
            score -= 6
            check_status = "warn"
            baseline_risks.append("finish_reason 类型异常。")

        role = message.get("role")
        content = message.get("content")
        tool_calls = message.get("tool_calls")
        if role == "assistant":
            baseline_matches.append("首个 message.role=assistant，符合常见成功响应。")
        elif isinstance(role, str):
            score -= 4
            check_status = "warn"
            baseline_risks.append(f"首个 message.role={role}，不是常见的 assistant。")
        else:
            score -= 10
            check_status = "fail"
            issues.append("message.role 缺失或类型错误。")

        has_valid_tool_calls = isinstance(tool_calls, list)
        if isinstance(content, str):
            baseline_matches.append("首个 message.content 为字符串。")
        elif content is None and has_valid_tool_calls:
            baseline_matches.append("首个 message.content 为空，但 tool_calls 存在，符合工具调用场景。")
        else:
            score -= 15
            check_status = "fail"
            issues.append("message.content 与 message.tool_calls 至少应有一项可用。")

        baseline_checks["choice_shape"] = check_status
        return score, issues, baseline_matches, baseline_risks, baseline_checks

    @staticmethod
    def _validate_usage_fields(
        *,
        body: dict[str, Any],
        score: int,
        issues: list[str],
        baseline_matches: list[str],
        baseline_risks: list[str],
        baseline_checks: dict[str, str],
    ) -> tuple[int, list[str], list[str], list[str], dict[str, str]]:
        usage = body.get("usage")
        if usage is None:
            score -= 8
            issues.append("usage 缺失。")
            baseline_checks["usage_shape"] = "fail"
            baseline_checks["usage_consistency"] = "fail"
            return score, issues, baseline_matches, baseline_risks, baseline_checks

        if not isinstance(usage, dict):
            score -= 12
            issues.append("usage 类型错误。")
            baseline_checks["usage_shape"] = "fail"
            baseline_checks["usage_consistency"] = "fail"
            return score, issues, baseline_matches, baseline_risks, baseline_checks

        check_status = "pass"
        numeric_usage: dict[str, int] = {}
        for field_name in ("prompt_tokens", "completion_tokens", "total_tokens"):
            value = usage.get(field_name)
            if not isinstance(value, int):
                score -= 6
                issues.append(f"usage.{field_name} 缺失或类型错误。")
                check_status = "warn"
            else:
                numeric_usage[field_name] = value

        baseline_checks["usage_shape"] = "pass" if check_status == "pass" else "warn"
        if len(numeric_usage) != 3:
            baseline_checks["usage_consistency"] = "fail"
            return score, issues, baseline_matches, baseline_risks, baseline_checks

        if numeric_usage["prompt_tokens"] + numeric_usage["completion_tokens"] == numeric_usage["total_tokens"]:
            baseline_matches.append("usage.total_tokens 与 prompt/completion_tokens 求和一致。")
            baseline_checks["usage_consistency"] = "pass"
        else:
            score -= 10
            baseline_risks.append("usage.total_tokens 与 prompt_tokens + completion_tokens 不一致。")
            baseline_checks["usage_consistency"] = "warn"

        for field_name in ("prompt_tokens_details", "completion_tokens_details"):
            value = usage.get(field_name)
            if value is not None and not isinstance(value, dict):
                score -= 4
                baseline_risks.append(f"usage.{field_name} 存在但不是对象。")

        return score, issues, baseline_matches, baseline_risks, baseline_checks

    @staticmethod
    def _validate_header_and_fingerprint_signals(
        *,
        body: dict[str, Any],
        details: dict[str, Any],
        score: int,
        baseline_matches: list[str],
        baseline_risks: list[str],
        baseline_checks: dict[str, str],
    ) -> tuple[int, list[str], list[str], dict[str, str]]:
        check_status = "pass"
        headers = details.get("response_headers", {})
        if not isinstance(headers, dict):
            baseline_checks["response_headers"] = "fail"
            baseline_checks["system_fingerprint"] = "warn"
            return score, baseline_matches, baseline_risks, baseline_checks

        content_type = headers.get("content-type")
        if isinstance(content_type, str) and "application/json" in content_type.lower():
            baseline_matches.append("响应 Content-Type 表现为 application/json。")
        else:
            score -= 8
            check_status = "warn"
            baseline_risks.append("响应 Content-Type 不是标准 application/json。")

        request_id = headers.get("x-request-id") or headers.get("request-id")
        if isinstance(request_id, str) and request_id:
            baseline_matches.append("响应头包含 request id，可用于链路追踪。")
        else:
            score -= 4
            check_status = "warn"
            baseline_risks.append("响应头缺少 request id，不利于与官方链路风格对比。")

        if isinstance(headers.get("openai-version"), str):
            baseline_matches.append("响应头包含 openai-version。")
        if isinstance(headers.get("openai-processing-ms"), str):
            baseline_matches.append("响应头包含 openai-processing-ms。")

        baseline_checks["response_headers"] = check_status

        system_fingerprint = body.get("system_fingerprint")
        if isinstance(system_fingerprint, str) and system_fingerprint:
            baseline_matches.append("响应体包含 system_fingerprint。")
            baseline_checks["system_fingerprint"] = "pass"
        else:
            score -= 3
            baseline_risks.append("响应体未返回 system_fingerprint，无法利用系统指纹辅助判断。")
            baseline_checks["system_fingerprint"] = "warn"

        return score, baseline_matches, baseline_risks, baseline_checks

    @staticmethod
    def _build_non_success_outcome(status_code: int) -> tuple[int, str, str, str]:
        status_group = classify_status_code(status_code)

        if status_group == "server_error":
            return 5, "响应结构探针失败，基础请求触发了 5xx 服务端异常。", status_group, "基础请求触发服务端异常，无法完成结构体校验。"
        if status_group == "auth_error":
            return 20, "响应结构探针未完成，基础请求未通过鉴权。", status_group, "基础请求未通过鉴权，无法完成结构体校验。"
        if status_group == "client_error":
            return 15, "响应结构探针失败，基础请求被 4xx 拒绝。", status_group, "基础请求被客户端错误拒绝，无法完成结构体校验。"
        return 10, "响应结构探针失败，基础请求未成功。", status_group, "基础请求未成功返回，无法完成结构体校验。"

    @staticmethod
    def _determine_status(*, score: int, baseline_checks: dict[str, str]) -> str:
        structural_checks = ("top_level_fields", "choice_shape", "usage_shape")
        if any(baseline_checks.get(name) == "fail" for name in structural_checks):
            return "fail"
        if score >= 85:
            return "pass"
        if score >= 60:
            return "warn"
        return "fail"
