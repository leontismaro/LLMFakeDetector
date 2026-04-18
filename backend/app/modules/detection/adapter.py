from __future__ import annotations

from dataclasses import dataclass
from json import JSONDecodeError
from typing import Any
from urllib.parse import urlparse, urlunparse

import httpx

from app.core.config import settings
from app.modules.detection.schemas import DetectionRequest


@dataclass(slots=True)
class AdapterResponse:
    status_code: int
    json_body: dict[str, Any] | list[Any] | None
    text_body: str
    http_version: str
    response_headers: dict[str, str]

    @property
    def ok(self) -> bool:
        return 200 <= self.status_code < 300


class OpenAICompatibleAdapter:
    def __init__(self, request: DetectionRequest, client: httpx.AsyncClient) -> None:
        self._request = request
        self._client = client
        self.endpoint_url = build_chat_completions_url(request.base_url)

    @property
    def client(self) -> httpx.AsyncClient:
        return self._client

    async def create_chat_completion(
        self,
        *,
        messages: list[dict[str, Any]] | None = None,
        extra_body: dict[str, Any] | None = None,
    ) -> AdapterResponse:
        payload = {
            "model": self._request.model_name,
            "messages": messages or self.build_default_messages(),
        }
        if extra_body:
            payload.update(extra_body)

        response = await self._client.post(
            self.endpoint_url,
            headers=self._build_headers(),
            json=payload,
        )
        return self._to_adapter_response(response)

    async def send_raw(self, payload: dict[str, Any]) -> AdapterResponse:
        response = await self._client.post(
            self.endpoint_url,
            headers=self._build_headers(),
            json=payload,
        )
        return self._to_adapter_response(response)

    @staticmethod
    def build_default_messages() -> list[dict[str, Any]]:
        return [
            {
                "role": "system",
                "content": "You are a precise API compatibility test assistant.",
            },
            {
                "role": "user",
                "content": "Reply with the single word pong.",
            },
        ]

    def _build_headers(self) -> dict[str, str]:
        headers = {
            "Content-Type": "application/json",
            "User-Agent": settings.outbound_user_agent,
        }
        if self._request.api_key:
            headers["Authorization"] = f"Bearer {self._request.api_key}"
        return headers

    @staticmethod
    def _to_adapter_response(response: httpx.Response) -> AdapterResponse:
        json_body: dict[str, Any] | list[Any] | None = None
        try:
            json_body = response.json()
        except JSONDecodeError:
            json_body = None

        return AdapterResponse(
            status_code=response.status_code,
            json_body=json_body,
            text_body=response.text,
            http_version=response.http_version,
            response_headers=dict(response.headers),
        )


def build_chat_completions_url(base_url: str) -> str:
    parsed = urlparse(base_url.rstrip("/"))
    path = parsed.path.rstrip("/")

    if path.endswith("/chat/completions"):
        normalized_path = path
    elif path.endswith("/v1/chat"):
        normalized_path = f"{path}/completions"
    elif path.endswith("/v1"):
        normalized_path = f"{path}/chat/completions"
    else:
        normalized_path = f"{path}/v1/chat/completions" if path else "/v1/chat/completions"

    return urlunparse(parsed._replace(path=normalized_path, params="", query="", fragment=""))
