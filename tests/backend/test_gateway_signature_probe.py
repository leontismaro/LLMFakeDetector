import unittest
from unittest.mock import AsyncMock

from app.modules.detection.adapter import AdapterResponse
from app.modules.detection.probes.base import ProbeRuntime
from app.modules.detection.probes.gateway_signature_probe import GatewaySignatureProbe
from app.modules.detection.schemas import DetectionRequest


class GatewaySignatureProbeTest(unittest.IsolatedAsyncioTestCase):
    async def test_should_pass_for_consistent_openai_like_shell(self) -> None:
        adapter = AsyncMock()
        adapter.create_chat_completion.side_effect = [
            self._build_openai_response("chatcmpl-a1", prompt_tokens=11, total_tokens=13),
            self._build_openai_response("chatcmpl-a2", prompt_tokens=12, total_tokens=14),
            self._build_openai_response("chatcmpl-a3", prompt_tokens=13, total_tokens=15),
        ]

        runtime = ProbeRuntime(
            request=DetectionRequest(
                base_url="https://example.com/v1",
                api_key="sk-test",
                model_name="GPT-5-NANO",
                enabled_probes=[],
            ),
            adapter=adapter,
        )

        finding = await GatewaySignatureProbe().run(runtime)

        self.assertEqual(finding.status, "pass")
        self.assertEqual(finding.details["claimed_family"], "openai")
        self.assertEqual(finding.details["cases"]["family_alignment"]["status"], "pass")
        self.assertEqual(finding.details["cases"]["id_quality"]["status"], "pass")
        self.assertEqual(finding.details["cases"]["usage_integrity"]["status"], "pass")

    async def test_should_warn_when_claude_model_is_wrapped_in_openai_shell(self) -> None:
        adapter = AsyncMock()
        adapter.create_chat_completion.side_effect = [
            self._build_openai_response("chatcmpl-b1", prompt_tokens=10, total_tokens=12),
            self._build_openai_response("chatcmpl-b2", prompt_tokens=11, total_tokens=13),
            self._build_openai_response("chatcmpl-b3", prompt_tokens=12, total_tokens=14),
        ]

        runtime = ProbeRuntime(
            request=DetectionRequest(
                base_url="https://example.com/v1",
                api_key="sk-test",
                model_name="Claude-3-7-Sonnet",
                enabled_probes=[],
            ),
            adapter=adapter,
        )

        finding = await GatewaySignatureProbe().run(runtime)

        self.assertEqual(finding.status, "warn")
        self.assertEqual(finding.details["claimed_family"], "anthropic")
        self.assertEqual(finding.details["cases"]["family_alignment"]["status"], "warn")
        self.assertIn("OpenAI-compatible 风格", finding.details["cases"]["family_alignment"]["observed_content"])

    async def test_should_fail_for_duplicate_uuid_ids_and_broken_usage(self) -> None:
        adapter = AsyncMock()
        adapter.create_chat_completion.side_effect = [
            self._build_openai_response(
                "123e4567-e89b-12d3-a456-426614174000",
                prompt_tokens=0,
                completion_tokens=0,
                total_tokens=0,
                system_fingerprint=None,
            ),
            self._build_openai_response(
                "123e4567-e89b-12d3-a456-426614174000",
                prompt_tokens=0,
                completion_tokens=0,
                total_tokens=0,
                system_fingerprint=None,
            ),
            self._build_openai_response(
                "123e4567-e89b-12d3-a456-426614174001",
                prompt_tokens=0,
                completion_tokens=0,
                total_tokens=0,
                system_fingerprint=None,
            ),
        ]

        runtime = ProbeRuntime(
            request=DetectionRequest(
                base_url="https://example.com/v1",
                api_key="sk-test",
                model_name="gpt-4o",
                enabled_probes=[],
            ),
            adapter=adapter,
        )

        finding = await GatewaySignatureProbe().run(runtime)

        self.assertEqual(finding.status, "fail")
        self.assertEqual(finding.details["cases"]["id_quality"]["status"], "fail")
        self.assertEqual(finding.details["cases"]["usage_integrity"]["status"], "warn")
        self.assertIn("重复响应 id", finding.details["cases"]["id_quality"]["observed_content"])

    @staticmethod
    def _build_openai_response(
        response_id: str,
        *,
        prompt_tokens: int,
        completion_tokens: int = 2,
        total_tokens: int = 13,
        system_fingerprint: str | None = "fp_test",
    ) -> AdapterResponse:
        body = {
            "id": response_id,
            "object": "chat.completion",
            "created": 1710000000,
            "model": "gpt-4o",
            "choices": [
                {
                    "index": 0,
                    "finish_reason": "stop",
                    "message": {
                        "role": "assistant",
                        "content": "pong",
                    },
                }
            ],
            "usage": {
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "total_tokens": total_tokens,
            },
        }
        if system_fingerprint is not None:
            body["system_fingerprint"] = system_fingerprint

        return AdapterResponse(
            status_code=200,
            json_body=body,
            text_body="{}",
            http_version="HTTP/1.1",
            response_headers={"content-type": "application/json"},
        )
