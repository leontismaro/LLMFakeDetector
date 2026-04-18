from typing import Any

from app.modules.detection.probes.base import DetectionProbe, ProbeRuntime
from app.modules.detection.probes.helpers import (
    build_response_metadata,
    classify_status_code,
    extract_first_choice,
)
from app.modules.detection.schemas import ProbeFinding


class LogprobsProbe(DetectionProbe):
    name = "logprobs_probe"

    async def run(self, runtime: ProbeRuntime) -> ProbeFinding:
        response = await runtime.adapter.create_chat_completion(
            messages=[
                {
                    "role": "user",
                    "content": "Reply with exactly one short token: yes",
                }
            ],
            extra_body={
                "logprobs": True,
                "top_logprobs": 2,
                "max_tokens": 4,
            },
        )

        details = build_response_metadata(response, runtime.adapter.endpoint_url)
        evidence = [f"HTTP 状态码: {response.status_code}"]
        status_group = classify_status_code(response.status_code)

        if status_group == "server_error":
            evidence.append("logprobs 请求触发了服务端异常。")
            return ProbeFinding(
                probe_name=self.name,
                status="fail",
                score=10,
                summary="logprobs 探针失败，接口在处理 logprobs 参数时返回了 5xx。",
                evidence=evidence,
                details={**details, "failure_kind": status_group},
            )

        if status_group == "auth_error":
            evidence.append("请求未通过鉴权，无法判断 logprobs 是否受支持。")
            return ProbeFinding(
                probe_name=self.name,
                status="warn",
                score=35,
                summary="logprobs 探针未完成，当前凭证无法验证该能力。",
                evidence=evidence,
                details={**details, "failure_kind": status_group},
            )

        if status_group == "client_error":
            evidence.append("logprobs 参数被显式拒绝。")
            return ProbeFinding(
                probe_name=self.name,
                status="warn",
                score=65,
                summary="logprobs 探针部分通过，接口明确拒绝了该参数组合。",
                evidence=evidence,
                details={**details, "failure_kind": status_group},
            )

        if not response.ok or not isinstance(response.json_body, dict):
            evidence.append("响应体不是可解析的成功 JSON。")
            return ProbeFinding(
                probe_name=self.name,
                status="fail",
                score=20,
                summary="logprobs 探针失败，接口未返回可验证的成功响应。",
                evidence=evidence,
                details={**details, "failure_kind": status_group},
            )

        logprobs = self._extract_logprobs(response.json_body)
        if logprobs is None:
            evidence.append("请求成功，但响应中缺少 choices[0].logprobs。")
            return ProbeFinding(
                probe_name=self.name,
                status="fail",
                score=25,
                summary="logprobs 探针失败，请求成功但响应缺少 logprobs 结果，疑似参数被忽略。",
                evidence=evidence,
                details=details,
            )

        token_count = self._estimate_logprob_token_count(logprobs)
        evidence.append(f"logprobs 结构存在，检测到约 {token_count} 个候选条目。")
        return ProbeFinding(
            probe_name=self.name,
            status="pass",
            score=92,
            summary="logprobs 探针通过，接口返回了结构化 logprobs 结果。",
            evidence=evidence,
            details={**details, "logprobs_token_count": token_count},
        )

    @staticmethod
    def _extract_logprobs(body: dict[str, Any]) -> Any:
        first_choice = extract_first_choice(body)
        if not first_choice:
            return None
        return first_choice.get("logprobs")

    @staticmethod
    def _estimate_logprob_token_count(logprobs: Any) -> int:
        if not isinstance(logprobs, dict):
            return 0
        content = logprobs.get("content")
        if isinstance(content, list):
            return len(content)
        return 0
