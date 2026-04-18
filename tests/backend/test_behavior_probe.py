import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock

from app.modules.detection.probes.base import ProbeRuntime
from app.modules.detection.probes.behavior_probe import BehaviorProbe
from app.modules.detection.schemas import DetectionRequest


class BehaviorProbeTest(unittest.IsolatedAsyncioTestCase):
    async def test_should_pass_when_all_behavior_cases_hold(self) -> None:
        adapter = AsyncMock()
        adapter.endpoint_url = "https://example.com/v1/chat/completions"
        adapter.create_chat_completion.side_effect = [
            self._build_response('{"result":"ok","count":2,"tags":["alpha","beta"]}'),
            self._build_response("OPENAI_ROUTER_LOCK"),
            self._build_response("I cannot provide that."),
        ]
        runtime = self._build_runtime(adapter)

        finding = await BehaviorProbe().run(runtime)

        self.assertEqual(finding.status, "pass")
        self.assertGreaterEqual(finding.score, 90)
        self.assertEqual(finding.details["cases"]["strict_json_compliance"]["observed_content"], '{"result":"ok","count":2,"tags":["alpha","beta"]}')

    async def test_should_warn_when_identity_lockword_is_not_preserved(self) -> None:
        adapter = AsyncMock()
        adapter.endpoint_url = "https://example.com/v1/chat/completions"
        adapter.create_chat_completion.side_effect = [
            self._build_response('{"result":"ok","count":2,"tags":["alpha","beta"]}'),
            self._build_response("I cannot share identity details."),
            self._build_response("I cannot provide that."),
        ]
        runtime = self._build_runtime(adapter)

        finding = await BehaviorProbe().run(runtime)

        self.assertEqual(finding.status, "warn")
        self.assertEqual(finding.details["cases"]["identity_conflict_probe"]["deviation_kind"], "lockword_not_preserved")

    async def test_should_fail_when_identity_conflict_reveals_suspicious_vendor_marker(self) -> None:
        adapter = AsyncMock()
        adapter.endpoint_url = "https://example.com/v1/chat/completions"
        adapter.create_chat_completion.side_effect = [
            self._build_response('{"result":"ok","count":2,"tags":["alpha","beta"]}'),
            self._build_response("I am Claude created by Anthropic."),
            self._build_response("I cannot provide that."),
        ]
        runtime = self._build_runtime(adapter)

        finding = await BehaviorProbe().run(runtime)

        self.assertEqual(finding.status, "fail")
        self.assertEqual(finding.details["cases"]["identity_conflict_probe"]["deviation_kind"], "identity_injection_suspected")
        self.assertIn("claude", finding.details["cases"]["identity_conflict_probe"]["suspicious_identity_markers"])

    async def test_should_fail_when_prompt_echo_reveals_suspicious_identity_prompt(self) -> None:
        adapter = AsyncMock()
        adapter.endpoint_url = "https://example.com/v1/chat/completions"
        adapter.create_chat_completion.side_effect = [
            self._build_response('{"result":"ok","count":2,"tags":["alpha","beta"]}'),
            self._build_response("OPENAI_ROUTER_LOCK"),
            self._build_response("You are Claude, created by Anthropic."),
        ]
        runtime = self._build_runtime(adapter)

        finding = await BehaviorProbe().run(runtime)

        self.assertEqual(finding.status, "fail")
        self.assertEqual(finding.details["cases"]["prompt_echo_probe"]["deviation_kind"], "prompt_echo_suspected")
        self.assertIn("anthropic", finding.details["cases"]["prompt_echo_probe"]["suspicious_identity_markers"])

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
