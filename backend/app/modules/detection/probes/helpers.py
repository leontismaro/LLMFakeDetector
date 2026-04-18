from typing import Any

from app.modules.detection.adapter import AdapterResponse


INTERESTING_RESPONSE_HEADERS = (
    "content-type",
    "server",
    "via",
    "x-request-id",
    "request-id",
    "cf-ray",
    "openai-processing-ms",
    "openai-version",
)


def classify_status_code(status_code: int) -> str:
    if 200 <= status_code < 300:
        return "success"
    if status_code in {401, 403}:
        return "auth_error"
    if 400 <= status_code < 500:
        return "client_error"
    if 500 <= status_code < 600:
        return "server_error"
    return "unexpected_error"


def build_response_metadata(response: AdapterResponse, endpoint_url: str) -> dict[str, Any]:
    metadata: dict[str, Any] = {
        "endpoint_url": endpoint_url,
        "status_code": response.status_code,
        "http_version": response.http_version,
        "response_headers": extract_interesting_headers(response.response_headers),
    }

    if isinstance(response.json_body, dict):
        system_fingerprint = response.json_body.get("system_fingerprint")
        if isinstance(system_fingerprint, str):
            metadata["system_fingerprint"] = system_fingerprint

    return metadata


def extract_interesting_headers(headers: dict[str, str]) -> dict[str, str]:
    return {
        name: value
        for name, value in headers.items()
        if name.lower() in INTERESTING_RESPONSE_HEADERS
    }


def extract_first_choice(body: Any) -> dict[str, Any] | None:
    if not isinstance(body, dict):
        return None
    choices = body.get("choices")
    if not isinstance(choices, list) or not choices:
        return None
    first_choice = choices[0]
    return first_choice if isinstance(first_choice, dict) else None


def extract_message(body: Any) -> dict[str, Any] | None:
    first_choice = extract_first_choice(body)
    if not first_choice:
        return None
    message = first_choice.get("message")
    return message if isinstance(message, dict) else None
