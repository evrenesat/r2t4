from __future__ import annotations

import asyncio
import base64
import json
import socket
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from json_repair import repair_json

from context_strategies import PromptContext

CONTENT_TYPE_HEADER = "application/json"
DEFAULT_REQUEST_TIMEOUT_SEC = 180
DEFAULT_TEMPERATURE = 0.0
DEFAULT_MAX_RETRIES = 1


@dataclass(frozen=True)
class CompletionSuccess:
    parsed_json: dict[str, Any]
    raw_text: str
    repaired_json: bool
    retry_count: int

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class CompletionFailure:
    error_type: str
    message: str
    raw_text: str | None
    repaired_json: bool
    retry_count: int

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


class OpenAICompatibleClient:
    def __init__(
        self,
        chat_completions_url: str,
        timeout_sec: int = DEFAULT_REQUEST_TIMEOUT_SEC,
    ) -> None:
        self._chat_completions_url = chat_completions_url
        self._timeout_sec = timeout_sec

    async def analyze(
        self,
        model: str,
        prompt_context: PromptContext,
    ) -> CompletionSuccess | CompletionFailure:
        return await self.generate_json(
            model=model,
            system_prompt=prompt_context.system_prompt,
            user_text=prompt_context.user_text,
            image_path=Path(prompt_context.image_path),
        )

    async def generate_json(
        self,
        model: str,
        system_prompt: str,
        user_text: str,
        image_path: Path | None = None,
    ) -> CompletionSuccess | CompletionFailure:
        retry_count = 0
        while True:
            try:
                payload = self._build_payload(
                    model=model,
                    system_prompt=system_prompt,
                    user_text=user_text,
                    image_path=image_path,
                )
                response = await asyncio.to_thread(self._post_payload, payload)
                raw_text = extract_message_text(response)
            except urllib.error.HTTPError as error:
                body = error.read().decode("utf-8", errors="replace")
                return CompletionFailure(
                    error_type="http_error",
                    message=f"{error.code} {error.reason}",
                    raw_text=body,
                    repaired_json=False,
                    retry_count=retry_count,
                )
            except (urllib.error.URLError, TimeoutError, socket.timeout) as error:
                return CompletionFailure(
                    error_type="transport_error",
                    message=str(error),
                    raw_text=None,
                    repaired_json=False,
                    retry_count=retry_count,
                )

            parse_result = parse_model_json(raw_text)
            if parse_result["ok"]:
                return CompletionSuccess(
                    parsed_json=parse_result["parsed_json"],
                    raw_text=raw_text,
                    repaired_json=parse_result["repaired_json"],
                    retry_count=retry_count,
                )

            if retry_count >= DEFAULT_MAX_RETRIES:
                return CompletionFailure(
                    error_type="invalid_json",
                    message=parse_result["message"],
                    raw_text=raw_text,
                    repaired_json=parse_result["repaired_json"],
                    retry_count=retry_count,
                )
            retry_count += 1

    def _build_payload(
        self,
        model: str,
        system_prompt: str,
        user_text: str,
        image_path: Path | None = None,
    ) -> dict[str, object]:
        user_content: list[dict[str, Any]] = [
            {
                "type": "text",
                "text": user_text,
            }
        ]
        if image_path is not None:
            user_content.append(
                {
                    "type": "image_url",
                    "image_url": {
                        "url": image_path_to_data_uri(image_path),
                    },
                }
            )
        return {
            "model": model,
            "temperature": DEFAULT_TEMPERATURE,
            "messages": [
                {
                    "role": "system",
                    "content": system_prompt,
                },
                {
                    "role": "user",
                    "content": user_content,
                },
            ],
        }

    def _post_payload(self, payload: dict[str, object]) -> dict[str, Any]:
        request = urllib.request.Request(
            self._chat_completions_url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": CONTENT_TYPE_HEADER},
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=self._timeout_sec) as response:
            return json.loads(response.read().decode("utf-8"))


def image_path_to_data_uri(path: Path) -> str:
    suffix = path.suffix.lower()
    mime_type = "image/jpeg" if suffix in {".jpg", ".jpeg"} else "image/png"
    encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:{mime_type};base64,{encoded}"


def extract_message_text(response_payload: dict[str, Any]) -> str:
    try:
        content = response_payload["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as error:
        raise ValueError(f"Unexpected chat completion response: {response_payload}") from error

    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n".join(
            part.get("text", "")
            for part in content
            if isinstance(part, dict)
        )
    raise ValueError(f"Unsupported message content type: {type(content)!r}")


def parse_model_json(raw_text: str) -> dict[str, object]:
    try:
        parsed = json.loads(raw_text)
        if isinstance(parsed, dict):
            return {"ok": True, "parsed_json": parsed, "repaired_json": False}
        raise ValueError("Model response JSON must be an object.")
    except (json.JSONDecodeError, ValueError):
        repaired = repair_json(raw_text, return_objects=True)
        if isinstance(repaired, tuple):
            repaired = repaired[0]
        if isinstance(repaired, dict):
            return {"ok": True, "parsed_json": repaired, "repaired_json": True}
        return {
            "ok": False,
            "message": "Model response could not be repaired into a JSON object.",
            "repaired_json": False,
        }
