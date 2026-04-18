import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from app.modules.detection.probes.base import ProbeRuntime
from app.modules.detection.probes.context_probe import ContextProbe
from app.modules.detection.schemas import DetectionRequest


class FakeEncoding:
    name = "fake_context_encoding"

    def encode(self, text: str) -> list[int]:
        return text.split()


class ContextProbeTest(unittest.IsolatedAsyncioTestCase):
    async def test_should_pass_when_all_needle_profiles_and_long_output_are_stable(self) -> None:
        adapter = AsyncMock()
        adapter.endpoint_url = "https://example.com/v1/chat/completions"
        adapter.create_chat_completion.side_effect = [
            self._build_response("Pineapple2024"),
            self._build_response("Pineapple2024"),
            self._build_response("Pineapple2024"),
            self._build_response(self._build_rows(40)),
        ]

        with patch.object(ContextProbe, "_resolve_context_encoding", return_value=FakeEncoding()):
            finding = await ContextProbe().run(self._build_runtime(adapter, context_mode="heavy"))

        self.assertEqual(finding.status, "pass")
        self.assertGreaterEqual(finding.score, 88)
        self.assertEqual(finding.details["context_reference_encoding"], "fake_context_encoding")
        self.assertEqual(finding.details["cases"]["needle_in_haystack_small"]["target_profile"], "small")
        self.assertEqual(finding.details["cases"]["needle_in_haystack_large"]["expected_answer"], "Pineapple2024")
        self.assertEqual(finding.details["cases"]["long_output_probe"]["valid_line_count"], 40)

    async def test_should_warn_when_medium_profiles_are_noisy_and_output_is_partially_truncated(self) -> None:
        adapter = AsyncMock()
        adapter.endpoint_url = "https://example.com/v1/chat/completions"
        adapter.create_chat_completion.side_effect = [
            self._build_response("Pineapple2024"),
            self._build_response("The passphrase is Pineapple2024."),
            self._build_response(self._build_rows(32)),
        ]

        with patch.object(ContextProbe, "_resolve_context_encoding", return_value=FakeEncoding()):
            finding = await ContextProbe().run(self._build_runtime(adapter))

        self.assertEqual(finding.status, "warn")
        self.assertEqual(finding.details["context_mode"], "standard")
        self.assertEqual(finding.details["selected_profiles"], ["small", "medium"])
        self.assertEqual(
            finding.details["cases"]["needle_in_haystack_medium"]["deviation_kind"],
            "extra_wrapping",
        )
        self.assertEqual(
            finding.details["cases"]["long_output_probe"]["deviation_kind"],
            "partial_truncation_or_format_drift",
        )

    async def test_should_fail_when_large_profile_and_long_output_break_down(self) -> None:
        adapter = AsyncMock()
        adapter.endpoint_url = "https://example.com/v1/chat/completions"
        adapter.create_chat_completion.side_effect = [
            self._build_response("Pineapple2024"),
            self._build_response("Pineapple2024"),
            self._build_response("Orange2024"),
            self._build_response("row-01: value-01\nrow-02: wrong-02\nfinal answer"),
        ]

        with patch.object(ContextProbe, "_resolve_context_encoding", return_value=FakeEncoding()):
            finding = await ContextProbe().run(self._build_runtime(adapter, context_mode="heavy"))

        self.assertEqual(finding.status, "fail")
        self.assertEqual(
            finding.details["cases"]["needle_in_haystack_large"]["deviation_kind"],
            "needle_not_found",
        )
        self.assertEqual(
            finding.details["cases"]["long_output_probe"]["deviation_kind"],
            "severe_truncation_or_format_failure",
        )

    @staticmethod
    def _build_runtime(adapter: AsyncMock, context_mode: str = "standard") -> ProbeRuntime:
        return ProbeRuntime(
            request=DetectionRequest(
                base_url="https://example.com/v1",
                api_key="sk-test",
                model_name="gpt-4o",
                enabled_probes=[],
                context_mode=context_mode,
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

    @staticmethod
    def _build_rows(count: int) -> str:
        return "\n".join(f"row-{index:02d}: value-{index:02d}" for index in range(1, count + 1))
