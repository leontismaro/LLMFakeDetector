import unittest

from app.modules.detection.adapter import AdapterResponse
from app.modules.detection.probes.helpers import build_response_metadata, classify_status_code


class ProbeHelpersTest(unittest.TestCase):
    def test_should_classify_status_codes(self) -> None:
        self.assertEqual(classify_status_code(200), "success")
        self.assertEqual(classify_status_code(401), "auth_error")
        self.assertEqual(classify_status_code(422), "client_error")
        self.assertEqual(classify_status_code(500), "server_error")

    def test_should_extract_response_metadata(self) -> None:
        response = AdapterResponse(
            status_code=200,
            json_body={"system_fingerprint": "fp_test"},
            text_body='{"system_fingerprint":"fp_test"}',
            http_version="HTTP/1.1",
            response_headers={
                "content-type": "application/json",
                "server": "cloudflare",
                "x-request-id": "req_123",
                "set-cookie": "ignored",
            },
        )

        metadata = build_response_metadata(response, "https://example.com/v1/chat/completions")

        self.assertEqual(metadata["endpoint_url"], "https://example.com/v1/chat/completions")
        self.assertEqual(metadata["http_version"], "HTTP/1.1")
        self.assertEqual(metadata["system_fingerprint"], "fp_test")
        self.assertEqual(
            metadata["response_headers"],
            {
                "content-type": "application/json",
                "server": "cloudflare",
                "x-request-id": "req_123",
            },
        )
