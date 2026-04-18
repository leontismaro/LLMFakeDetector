import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from app.modules.detection.probes.base import ProbeRuntime
from app.modules.detection.probes.token_reference import OpenAITiktokenReferenceProvider
from app.modules.detection.probes.tokenizer_probe import TOKENIZER_SAMPLES, TokenizerProbe
from app.modules.detection.schemas import DetectionRequest, ReferenceOptions


class FakeEncoding:
    def __init__(self, token_lengths: dict[str, int], name: str = "fake_o200k_base") -> None:
        self._token_lengths = token_lengths
        self.name = name

    def encode(self, text: str) -> list[int]:
        return [0] * self._token_lengths[text]


class TokenizerProbeTest(unittest.IsolatedAsyncioTestCase):
    async def test_should_pass_when_openai_prompt_token_delta_is_stable(self) -> None:
        token_lengths = {
            sample["text"]: index + 10
            for index, sample in enumerate(TOKENIZER_SAMPLES)
        }
        adapter = AsyncMock()
        adapter.endpoint_url = "https://example.com/v1/chat/completions"
        adapter.create_chat_completion.side_effect = [
            self._build_target_response(prompt_tokens=token_lengths[sample["text"]] + 6)
            for sample in TOKENIZER_SAMPLES
        ]

        runtime = ProbeRuntime(
            request=DetectionRequest(
                base_url="https://example.com/v1",
                api_key="sk-test",
                model_name="gpt-5-nano",
                enabled_probes=[],
            ),
            adapter=adapter,
        )

        with patch.object(OpenAITiktokenReferenceProvider, "_resolve_reference_encoding", return_value=FakeEncoding(token_lengths)):
            finding = await TokenizerProbe().run(runtime)

        self.assertEqual(finding.status, "pass")
        self.assertGreaterEqual(finding.score, 90)
        self.assertEqual(finding.details["reference_family"], "openai_tiktoken")
        self.assertEqual(finding.details["delta_range"], 0)
        self.assertEqual(finding.details["stable_sample_count"], len(TOKENIZER_SAMPLES))

    async def test_should_fail_when_openai_prompt_token_delta_is_unstable(self) -> None:
        token_lengths = {
            sample["text"]: index + 12
            for index, sample in enumerate(TOKENIZER_SAMPLES)
        }
        deltas = [2, 8, -1, 11, 5]
        adapter = AsyncMock()
        adapter.endpoint_url = "https://example.com/v1/chat/completions"
        adapter.create_chat_completion.side_effect = [
            self._build_target_response(prompt_tokens=token_lengths[sample["text"]] + delta)
            for sample, delta in zip(TOKENIZER_SAMPLES, deltas, strict=True)
        ]

        runtime = ProbeRuntime(
            request=DetectionRequest(
                base_url="https://example.com/v1",
                api_key="sk-test",
                model_name="gpt-5-nano",
                enabled_probes=[],
            ),
            adapter=adapter,
        )

        with patch.object(OpenAITiktokenReferenceProvider, "_resolve_reference_encoding", return_value=FakeEncoding(token_lengths)):
            finding = await TokenizerProbe().run(runtime)

        self.assertEqual(finding.status, "fail")
        self.assertLessEqual(finding.score, 35)
        self.assertEqual(finding.details["negative_delta_count"], 1)

    async def test_should_skip_claude_when_official_key_missing(self) -> None:
        runtime = ProbeRuntime(
            request=DetectionRequest(
                base_url="https://example.com/v1",
                api_key="sk-test",
                model_name="claude-3-5-sonnet",
                enabled_probes=[],
            ),
            adapter=AsyncMock(endpoint_url="https://example.com/v1/chat/completions"),
        )

        finding = await TokenizerProbe().run(runtime)

        self.assertEqual(finding.status, "skip")
        self.assertEqual(finding.details["reference_family"], "anthropic_official")

    async def test_should_skip_gemini_when_official_key_missing(self) -> None:
        runtime = ProbeRuntime(
            request=DetectionRequest(
                base_url="https://example.com/v1",
                api_key="sk-test",
                model_name="gemini-2.5-pro",
                enabled_probes=[],
            ),
            adapter=AsyncMock(endpoint_url="https://example.com/v1/chat/completions"),
        )

        finding = await TokenizerProbe().run(runtime)

        self.assertEqual(finding.status, "skip")
        self.assertEqual(finding.details["reference_family"], "gemini_official")

    async def test_should_treat_openai_style_model_name_case_insensitively(self) -> None:
        token_lengths = {
            sample["text"]: index + 10
            for index, sample in enumerate(TOKENIZER_SAMPLES)
        }
        adapter = AsyncMock()
        adapter.endpoint_url = "https://example.com/v1/chat/completions"
        adapter.create_chat_completion.side_effect = [
            self._build_target_response(prompt_tokens=token_lengths[sample["text"]] + 5)
            for sample in TOKENIZER_SAMPLES
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

        with patch.object(OpenAITiktokenReferenceProvider, "_resolve_reference_encoding", return_value=FakeEncoding(token_lengths)):
            finding = await TokenizerProbe().run(runtime)

        self.assertEqual(finding.status, "pass")
        self.assertEqual(finding.details["reference_family"], "openai_tiktoken")

    async def test_should_pass_when_claude_official_reference_matches(self) -> None:
        adapter = AsyncMock()
        adapter.endpoint_url = "https://example.com/v1/chat/completions"
        adapter.create_chat_completion.side_effect = [
            self._build_target_response(prompt_tokens=40 + index)
            for index, _ in enumerate(TOKENIZER_SAMPLES)
        ]
        adapter.client = AsyncMock()
        adapter.client.post.side_effect = [
            self._build_reference_response(status_code=200, json_body={"input_tokens": 40 + index})
            for index, _ in enumerate(TOKENIZER_SAMPLES)
        ]

        runtime = ProbeRuntime(
            request=DetectionRequest(
                base_url="https://example.com/v1",
                api_key="sk-test",
                model_name="claude-3-5-sonnet",
                enabled_probes=[],
                reference_options=ReferenceOptions(anthropic_api_key="sk-ant-test"),
            ),
            adapter=adapter,
        )

        finding = await TokenizerProbe().run(runtime)

        self.assertEqual(finding.status, "pass")
        self.assertEqual(finding.details["reference_family"], "anthropic_official")
        self.assertEqual(finding.details["reference_source"], "anthropic_count_tokens_api")
        self.assertEqual(finding.details["delta_range"], 0)
        self.assertTrue(all(sample["reference_status_code"] == 200 for sample in finding.details["samples"]))

    @staticmethod
    def _build_target_response(prompt_tokens: int) -> SimpleNamespace:
        return SimpleNamespace(
            ok=True,
            status_code=200,
            http_version="HTTP/1.1",
            response_headers={"content-type": "application/json"},
            json_body={
                "usage": {
                    "prompt_tokens": prompt_tokens,
                    "completion_tokens": 1,
                    "total_tokens": prompt_tokens + 1,
                }
            },
        )

    @staticmethod
    def _build_reference_response(status_code: int, json_body: dict[str, int]) -> SimpleNamespace:
        return SimpleNamespace(
            status_code=status_code,
            http_version="HTTP/2",
            json=lambda: json_body,
        )
