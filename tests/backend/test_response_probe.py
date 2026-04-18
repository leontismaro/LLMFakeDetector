import unittest
from unittest.mock import AsyncMock

from app.modules.detection.probes.base import ProbeRuntime
from app.modules.detection.probes.response_probe import ResponseProbe
from app.modules.detection.schemas import DetectionRequest


class ResponseProbeTest(unittest.IsolatedAsyncioTestCase):
    async def test_should_pass_when_success_response_matches_openai_like_baseline(self) -> None:
        adapter = AsyncMock()
        adapter.endpoint_url = "https://example.com/v1/chat/completions"
        adapter.create_chat_completion.return_value.ok = True
        adapter.create_chat_completion.return_value.status_code = 200
        adapter.create_chat_completion.return_value.http_version = "HTTP/1.1"
        adapter.create_chat_completion.return_value.response_headers = {
            "content-type": "application/json",
            "x-request-id": "req_123",
            "openai-version": "2020-10-01",
            "openai-processing-ms": "123",
        }
        adapter.create_chat_completion.return_value.json_body = {
            "id": "chatcmpl-123",
            "object": "chat.completion",
            "created": 1710000000,
            "model": "gpt-4o",
            "system_fingerprint": "fp_test",
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
                "prompt_tokens": 8,
                "completion_tokens": 2,
                "total_tokens": 10,
            },
        }

        runtime = ProbeRuntime(
            request=DetectionRequest(
                base_url="https://example.com/v1",
                api_key="sk-test",
                model_name="gpt-4o",
                enabled_probes=[],
            ),
            adapter=adapter,
        )

        finding = await ResponseProbe().run(runtime)

        self.assertEqual(finding.status, "pass")
        self.assertGreaterEqual(finding.score, 85)
        self.assertEqual(finding.details["baseline_checks"]["usage_consistency"], "pass")
        self.assertIn("响应体包含 system_fingerprint。", finding.details["baseline_matches"])

    async def test_should_warn_when_success_response_deviates_from_openai_like_baseline(self) -> None:
        adapter = AsyncMock()
        adapter.endpoint_url = "https://example.com/v1/chat/completions"
        adapter.create_chat_completion.return_value.ok = True
        adapter.create_chat_completion.return_value.status_code = 200
        adapter.create_chat_completion.return_value.http_version = "HTTP/1.1"
        adapter.create_chat_completion.return_value.response_headers = {
            "content-type": "application/json",
            "server": "custom-gateway",
        }
        adapter.create_chat_completion.return_value.json_body = {
            "id": "resp_123",
            "object": "chat.completion",
            "created": 1710000000,
            "model": "gpt-4o-2026-01-01",
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
                "prompt_tokens": 8,
                "completion_tokens": 2,
                "total_tokens": 99,
            },
        }

        runtime = ProbeRuntime(
            request=DetectionRequest(
                base_url="https://example.com/v1",
                api_key="sk-test",
                model_name="gpt-4o",
                enabled_probes=[],
            ),
            adapter=adapter,
        )

        finding = await ResponseProbe().run(runtime)

        self.assertEqual(finding.status, "warn")
        self.assertLess(finding.score, 85)
        self.assertEqual(finding.details["baseline_checks"]["response_headers"], "warn")
        self.assertIn("响应体未返回 system_fingerprint，无法利用系统指纹辅助判断。", finding.details["baseline_risks"])

    async def test_should_fail_when_success_response_lacks_required_structures(self) -> None:
        adapter = AsyncMock()
        adapter.endpoint_url = "https://example.com/v1/chat/completions"
        adapter.create_chat_completion.return_value.ok = True
        adapter.create_chat_completion.return_value.status_code = 200
        adapter.create_chat_completion.return_value.http_version = "HTTP/1.1"
        adapter.create_chat_completion.return_value.response_headers = {
            "content-type": "application/json",
        }
        adapter.create_chat_completion.return_value.json_body = {
            "id": "chatcmpl-123",
            "object": "chat.completion",
            "created": 1710000000,
            "model": "gpt-4o",
            "choices": [],
        }

        runtime = ProbeRuntime(
            request=DetectionRequest(
                base_url="https://example.com/v1",
                api_key="sk-test",
                model_name="gpt-4o",
                enabled_probes=[],
            ),
            adapter=adapter,
        )

        finding = await ResponseProbe().run(runtime)

        self.assertEqual(finding.status, "fail")
        self.assertEqual(finding.details["baseline_checks"]["choice_shape"], "fail")
        self.assertEqual(finding.details["baseline_checks"]["usage_shape"], "fail")
