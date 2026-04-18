import json
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock

from app.modules.detection.probes.base import ProbeRuntime
from app.modules.detection.probes.function_calling_probe import FunctionCallingProbe
from app.modules.detection.schemas import DetectionRequest


class FunctionCallingProbeTest(unittest.IsolatedAsyncioTestCase):
    async def test_should_pass_when_complex_schema_and_tool_selection_are_correct(self) -> None:
        adapter = AsyncMock()
        adapter.endpoint_url = "https://example.com/v1/chat/completions"
        adapter.create_chat_completion.side_effect = [
            self._build_tool_call_response(
                "schedule_incident_response",
                {
                    "severity": "sev1",
                    "region": "emea",
                    "contacts": [
                        {"name": "Ava", "role": "lead"},
                        {"name": "Noah", "role": "sre"},
                    ],
                    "mitigation": {
                        "notify_customer": True,
                        "eta_minutes": 15,
                    },
                    "tags": ["payments", "rollback"],
                },
            ),
            self._build_tool_call_response(
                "open_billing_case",
                {
                    "invoice_id": "INV-8842",
                    "issue_type": "duplicate_charge",
                    "priority": "high",
                },
            ),
        ]

        finding = await FunctionCallingProbe().run(self._build_runtime(adapter))

        self.assertEqual(finding.status, "pass")
        self.assertGreaterEqual(finding.score, 90)
        self.assertEqual(finding.details["cases"]["complex_schema_case"]["selected_tool_name"], "schedule_incident_response")

    async def test_should_warn_when_tool_arguments_partially_drift(self) -> None:
        adapter = AsyncMock()
        adapter.endpoint_url = "https://example.com/v1/chat/completions"
        adapter.create_chat_completion.side_effect = [
            self._build_tool_call_response(
                "schedule_incident_response",
                {
                    "severity": "sev1",
                    "region": "emea",
                    "contacts": [
                        {"name": "Ava", "role": "lead"},
                        {"name": "Noah", "role": "sre"},
                    ],
                    "mitigation": {
                        "notify_customer": True,
                        "eta_minutes": 30,
                    },
                    "tags": ["payments", "rollback"],
                },
            ),
            self._build_tool_call_response(
                "open_billing_case",
                {
                    "invoice_id": "INV-8842",
                    "issue_type": "duplicate_charge",
                    "priority": "high",
                },
            ),
        ]

        finding = await FunctionCallingProbe().run(self._build_runtime(adapter))

        self.assertEqual(finding.status, "warn")
        self.assertEqual(
            finding.details["cases"]["complex_schema_case"]["deviation_kind"],
            "argument_contract_mismatch",
        )
        self.assertIn(
            "arguments.mitigation.eta_minutes",
            finding.details["cases"]["complex_schema_case"]["mismatch_paths"],
        )

    async def test_should_fail_when_wrong_tool_is_selected(self) -> None:
        adapter = AsyncMock()
        adapter.endpoint_url = "https://example.com/v1/chat/completions"
        adapter.create_chat_completion.side_effect = [
            self._build_tool_call_response(
                "schedule_incident_response",
                {
                    "severity": "sev1",
                    "region": "emea",
                    "contacts": [
                        {"name": "Ava", "role": "lead"},
                        {"name": "Noah", "role": "sre"},
                    ],
                    "mitigation": {
                        "notify_customer": True,
                        "eta_minutes": 15,
                    },
                    "tags": ["payments", "rollback"],
                },
            ),
            self._build_tool_call_response(
                "summarize_incident_timeline",
                {
                    "incident_id": "INC-42",
                    "audience": "internal",
                },
            ),
        ]

        finding = await FunctionCallingProbe().run(self._build_runtime(adapter))

        self.assertEqual(finding.status, "fail")
        self.assertEqual(
            finding.details["cases"]["tool_selection_case"]["deviation_kind"],
            "wrong_tool_selected",
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
    def _build_tool_call_response(tool_name: str, arguments: dict[str, object]) -> SimpleNamespace:
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
                            "content": None,
                            "tool_calls": [
                                {
                                    "id": "call_1",
                                    "type": "function",
                                    "function": {
                                        "name": tool_name,
                                        "arguments": json.dumps(arguments, ensure_ascii=True),
                                    },
                                }
                            ],
                        }
                    }
                ]
            },
        )
