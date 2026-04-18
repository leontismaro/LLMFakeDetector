import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock

from app.modules.detection.probes.base import ProbeRuntime
from app.modules.detection.probes.vision_probe import VisionProbe
from app.modules.detection.schemas import DetectionRequest


class VisionProbeTest(unittest.IsolatedAsyncioTestCase):
    async def test_should_pass_when_chart_and_watermark_are_recognized(self) -> None:
        adapter = AsyncMock()
        adapter.endpoint_url = "https://example.com/v1/chat/completions"
        adapter.create_chat_completion.side_effect = [
            self._build_response("Q4"),
            self._build_response("NOVA-42"),
        ]

        finding = await VisionProbe().run(self._build_runtime(adapter))

        self.assertEqual(finding.status, "pass")
        self.assertGreaterEqual(finding.score, 90)
        first_call_messages = adapter.create_chat_completion.call_args_list[0].kwargs["messages"]
        user_content = first_call_messages[1]["content"]
        self.assertIsInstance(user_content, list)
        self.assertEqual(user_content[1]["type"], "image_url")
        self.assertTrue(user_content[1]["image_url"]["url"].startswith("data:image/png;base64,"))

    async def test_should_warn_when_watermark_has_extra_wrapping(self) -> None:
        adapter = AsyncMock()
        adapter.endpoint_url = "https://example.com/v1/chat/completions"
        adapter.create_chat_completion.side_effect = [
            self._build_response("Q4"),
            self._build_response("The hidden code is NOVA-42."),
        ]

        finding = await VisionProbe().run(self._build_runtime(adapter))

        self.assertEqual(finding.status, "warn")
        self.assertEqual(
            finding.details["cases"]["watermark_detail_case"]["deviation_kind"],
            "extra_wrapping",
        )

    async def test_should_fail_when_chart_answer_is_wrong(self) -> None:
        adapter = AsyncMock()
        adapter.endpoint_url = "https://example.com/v1/chat/completions"
        adapter.create_chat_completion.side_effect = [
            self._build_response("Q2"),
            self._build_response("NOVA-42"),
        ]

        finding = await VisionProbe().run(self._build_runtime(adapter))

        self.assertEqual(finding.status, "fail")
        self.assertEqual(
            finding.details["cases"]["chart_reasoning_case"]["deviation_kind"],
            "vision_answer_mismatch",
        )

    @staticmethod
    def _build_runtime(adapter: AsyncMock) -> ProbeRuntime:
        return ProbeRuntime(
            request=DetectionRequest(
                base_url="https://example.com/v1",
                api_key="sk-test",
                model_name="gpt-4o",
                enabled_probes=[],
            ),
            adapter=adapter,
        )

    @staticmethod
    def _build_response(content: str) -> SimpleNamespace:
        return SimpleNamespace(
            ok=True,
            status_code=200,
            http_version="HTTP/1.1",
            response_headers={"content-type": "application/json"},
            json_body={
                "choices": [
                    {
                        "message": {
                            "role": "assistant",
                            "content": content,
                        }
                    }
                ]
            },
        )
