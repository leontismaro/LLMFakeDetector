from typing import Any

from app.modules.detection.probes.base import DetectionProbe, ProbeRuntime
from app.modules.detection.probes.helpers import build_response_metadata, classify_status_code
from app.modules.detection.schemas import ProbeFinding


class ErrorResponseProbe(DetectionProbe):
    name = "error_probe"

    async def run(self, runtime: ProbeRuntime) -> ProbeFinding:
        response = await runtime.adapter.send_raw(
            {
                "model": runtime.request.model_name,
                "messages": "invalid-messages-type",
            }
        )

        evidence = [f"HTTP 状态码: {response.status_code}"]
        details = build_response_metadata(response, runtime.adapter.endpoint_url)
        status_group = classify_status_code(response.status_code)

        if response.ok:
            evidence.append("非法请求未被拒绝，服务端直接返回成功。")
            return ProbeFinding(
                probe_name=self.name,
                status="fail",
                score=20,
                summary="错误响应探针失败，接口没有对非法请求进行有效校验。",
                evidence=evidence,
                details=details,
            )

        if not isinstance(response.json_body, dict):
            evidence.append("错误响应不是 JSON 结构。")
            return ProbeFinding(
                probe_name=self.name,
                status="fail",
                score=25,
                summary="错误响应探针失败，错误返回不符合 OpenAI-compatible 常见风格。",
                evidence=evidence,
                details=details,
            )

        error = response.json_body.get("error")
        if not isinstance(error, dict):
            evidence.append("缺少顶层 error 对象。")
            return ProbeFinding(
                probe_name=self.name,
                status="fail",
                score=30,
                summary="错误响应探针失败，未返回标准错误对象。",
                evidence=evidence,
                details=details,
            )

        message = error.get("message")
        error_type = error.get("type")
        if isinstance(message, str):
            evidence.append(f"error.message 存在: {message[:120]}")
        else:
            evidence.append("error.message 缺失或类型错误。")

        if isinstance(error_type, str):
            evidence.append(f"error.type 存在: {error_type}")
        else:
            evidence.append("error.type 缺失或类型错误。")

        if status_group == "server_error" and isinstance(message, str) and isinstance(error_type, str):
            evidence.append("错误请求虽然被结构化处理，但服务端返回了 5xx，不符合规范错误语义。")
            return ProbeFinding(
                probe_name=self.name,
                status="warn",
                score=45,
                summary="错误响应探针部分通过，接口返回了结构化错误，但状态码为 5xx。",
                evidence=evidence,
                details={**details, "failure_kind": status_group},
            )

        if isinstance(message, str) and isinstance(error_type, str):
            return ProbeFinding(
                probe_name=self.name,
                status="pass",
                score=90,
                summary="错误响应探针通过，接口能够对非法请求返回结构化错误。",
                evidence=evidence,
                details={**details, "failure_kind": status_group},
            )

        return ProbeFinding(
            probe_name=self.name,
            status="warn",
            score=60,
            summary="错误响应探针部分通过，接口会拒绝非法请求，但错误结构不够完整。",
            evidence=evidence,
            details={**details, "failure_kind": status_group},
        )
