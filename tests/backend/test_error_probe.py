import unittest
from unittest.mock import AsyncMock

from app.modules.detection.probes.base import ProbeRuntime
from app.modules.detection.probes.error_probe import ErrorResponseProbe
from app.modules.detection.schemas import DetectionRequest


class ErrorResponseProbeTest(unittest.IsolatedAsyncioTestCase):
    async def test_should_pass_when_error_response_has_standard_shape(self) -> None:
        adapter = AsyncMock()
        adapter.endpoint_url = "https://example.com/v1/chat/completions"
        adapter.send_raw.return_value.ok = False
        adapter.send_raw.return_value.status_code = 400
        adapter.send_raw.return_value.http_version = "HTTP/1.1"
        adapter.send_raw.return_value.response_headers = {"content-type": "application/json"}
        adapter.send_raw.return_value.json_body = {
            "error": {
                "message": "Invalid messages field",
                "type": "invalid_request_error",
            }
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

        finding = await ErrorResponseProbe().run(runtime)

        self.assertEqual(finding.status, "pass")
        self.assertGreaterEqual(finding.score, 90)

    async def test_should_warn_when_invalid_request_returns_5xx(self) -> None:
        adapter = AsyncMock()
        adapter.endpoint_url = "https://example.com/v1/chat/completions"
        adapter.send_raw.return_value.ok = False
        adapter.send_raw.return_value.status_code = 500
        adapter.send_raw.return_value.http_version = "HTTP/1.1"
        adapter.send_raw.return_value.response_headers = {"content-type": "application/json"}
        adapter.send_raw.return_value.json_body = {
            "error": {
                "message": "Invalid messages field",
                "type": "new_api_error",
            }
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

        finding = await ErrorResponseProbe().run(runtime)

        self.assertEqual(finding.status, "warn")
        self.assertLessEqual(finding.score, 45)

    async def test_should_fail_when_invalid_request_is_accepted(self) -> None:
        adapter = AsyncMock()
        adapter.endpoint_url = "https://example.com/v1/chat/completions"
        adapter.send_raw.return_value.ok = True
        adapter.send_raw.return_value.status_code = 200
        adapter.send_raw.return_value.http_version = "HTTP/1.1"
        adapter.send_raw.return_value.response_headers = {"content-type": "application/json"}
        adapter.send_raw.return_value.json_body = {"id": "chatcmpl-test"}

        runtime = ProbeRuntime(
            request=DetectionRequest(
                base_url="https://example.com/v1",
                api_key="sk-test",
                model_name="gpt-4o",
                enabled_probes=[],
            ),
            adapter=adapter,
        )

        finding = await ErrorResponseProbe().run(runtime)

        self.assertEqual(finding.status, "fail")
        self.assertLessEqual(finding.score, 20)
