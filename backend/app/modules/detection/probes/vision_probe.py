from __future__ import annotations

import base64
from typing import Any

from app.modules.detection.assets.loader import load_binary_asset
from app.modules.detection.prompts.loader import load_prompt_bundle
from app.modules.detection.probes.base import DetectionProbe, ProbeRuntime
from app.modules.detection.probes.helpers import (
    build_response_metadata,
    classify_status_code,
    extract_message,
)
from app.modules.detection.schemas import ProbeFinding


VISION_PROMPTS = load_prompt_bundle("vision_probe.json")
CHART_REASONING_CONFIG = VISION_PROMPTS["chart_reasoning_case"]
WATERMARK_DETAIL_CONFIG = VISION_PROMPTS["watermark_detail_case"]


class VisionProbe(DetectionProbe):
    name = "vision_probe"

    async def run(self, runtime: ProbeRuntime) -> ProbeFinding:
        case_findings = [
            await self._run_case(
                runtime=runtime,
                case_name="chart_reasoning_case",
                feature_label="视觉图表识别测试",
                config=CHART_REASONING_CONFIG,
            ),
            await self._run_case(
                runtime=runtime,
                case_name="watermark_detail_case",
                feature_label="视觉细节水印测试",
                config=WATERMARK_DETAIL_CONFIG,
            ),
        ]

        score = int(sum(item["score"] for item in case_findings) / len(case_findings))
        statuses = [item["status"] for item in case_findings]
        status = "pass" if all(item == "pass" for item in statuses) else "fail" if "fail" in statuses else "warn"

        return ProbeFinding(
            probe_name=self.name,
            status=status,
            score=score,
            summary=(
                f"Vision 探针完成，共检测 {len(case_findings)} 项视觉能力；"
                f"准确通过 {sum(1 for item in case_findings if item['status'] == 'pass')} 项，"
                f"存在视觉识别或细节提取风险 {sum(1 for item in case_findings if item['status'] != 'pass')} 项。"
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

    async def _run_case(
        self,
        *,
        runtime: ProbeRuntime,
        case_name: str,
        feature_label: str,
        config: dict[str, Any],
    ) -> dict[str, Any]:
        asset_path = str(config["asset_path"])
        image_data_url = self._build_png_data_url(load_binary_asset(*asset_path.split("/")))
        response = await runtime.adapter.create_chat_completion(
            messages=[
                {"role": "system", "content": config["system_prompt"]},
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": config["user_prompt"]},
                        {"type": "image_url", "image_url": {"url": image_data_url}},
                    ],
                },
            ],
            extra_body={"max_tokens": 48},
        )

        non_success_result = self._build_non_success_result(
            case_name=case_name,
            runtime=runtime,
            response=response,
            feature_label=feature_label,
            asset_path=asset_path,
        )
        if non_success_result is not None:
            return non_success_result

        content = self._extract_message_content(response.json_body)
        details = {
            **build_response_metadata(response, runtime.adapter.endpoint_url),
            "observed_content": content,
            "expected_answer": config["expected_answer"],
            "image_transport": "data_url_png",
            "image_asset_path": asset_path,
        }

        if not isinstance(content, str):
            return {
                "name": case_name,
                "status": "fail",
                "score": 18,
                "evidence": f"{feature_label}失败，响应缺少可解析的文本内容。",
                "details": {**details, "deviation_kind": "missing_text_content"},
            }

        normalized = content.strip()
        expected_answer = str(config["expected_answer"]).strip()
        if normalized == expected_answer:
            return {
                "name": case_name,
                "status": "pass",
                "score": 92,
                "evidence": f"{feature_label}通过，模型准确识别了目标视觉信息。",
                "details": details,
            }

        if expected_answer.lower() in normalized.lower():
            return {
                "name": case_name,
                "status": "warn",
                "score": 70,
                "evidence": f"{feature_label}部分通过，模型找到了目标答案，但输出带有额外包装文本。",
                "details": {**details, "deviation_kind": "extra_wrapping"},
            }

        return {
            "name": case_name,
            "status": "fail",
            "score": 28,
            "evidence": f"{feature_label}失败，模型未能正确识别目标视觉信息。",
            "details": {**details, "deviation_kind": "vision_answer_mismatch"},
        }

    @staticmethod
    def _build_non_success_result(
        *,
        case_name: str,
        runtime: ProbeRuntime,
        response: Any,
        feature_label: str,
        asset_path: str,
    ) -> dict[str, Any] | None:
        if response.ok:
            return None

        status_group = classify_status_code(response.status_code)
        details = {
            **build_response_metadata(response, runtime.adapter.endpoint_url),
            "failure_kind": status_group,
            "image_transport": "data_url_png",
            "image_asset_path": asset_path,
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
            "score": 60,
            "evidence": f"{feature_label}被显式拒绝，HTTP {response.status_code}。目标接口可能不支持当前视觉输入格式。",
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
    def _build_png_data_url(image_bytes: bytes) -> str:
        encoded = base64.b64encode(image_bytes).decode("ascii")
        return f"data:image/png;base64,{encoded}"
