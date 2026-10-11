import json
import os
from abc import ABC, abstractmethod
from typing import Any, Dict

import requests

from .config import MISTRAL_API_KEY, MISTRAL_MODEL


class MistralProvider(ABC):
    def __init__(
        self,
        api_key: str | None = None,
        model: str = MISTRAL_MODEL,
        session: Any = None,
    ):
        self.api_key = api_key if api_key is not None else MISTRAL_API_KEY
        self.model = model
        self.session = session or requests.Session()

    def _request(self, messages):
        if not self.api_key:
            raise RuntimeError(
                "Mistral is not configured; set MISTRAL_API_KEY for LLM features"
            )
        response = self.session.post(
            "https://api.mistral.ai/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": self.model,
                "messages": messages,
                "temperature": 0,
                "response_format": {"type": "json_object"},
            },
            timeout=60,
        )
        if response.status_code >= 400:
            raise RuntimeError(f"Mistral request failed with status {response.status_code}")
        try:
            payload = response.json()
            content = payload["choices"][0]["message"]["content"]
        except (ValueError, KeyError, IndexError, TypeError) as exc:
            raise RuntimeError("Mistral returned an invalid response") from exc
        if isinstance(content, list):
            content = "".join(
                part.get("text", "") if isinstance(part, dict) else str(part)
                for part in content
            )
        return self._parse_json(str(content))

    @staticmethod
    def _parse_json(content: str) -> Dict[str, Any]:
        cleaned = content.strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.split("\n", 1)[1] if "\n" in cleaned else cleaned
            if cleaned.endswith("```"):
                cleaned = cleaned[:-3].rstrip()
        decoder = json.JSONDecoder()
        try:
            value, _ = decoder.raw_decode(cleaned)
        except json.JSONDecodeError:
            value = None
            for index, character in enumerate(cleaned):
                if character == "{":
                    try:
                        value, _ = decoder.raw_decode(cleaned[index:])
                        break
                    except json.JSONDecodeError:
                        continue
            if value is None:
                raise RuntimeError("Mistral returned malformed JSON")
        if not isinstance(value, dict):
            raise RuntimeError("Mistral structured output must be a JSON object")
        return value

    @abstractmethod
    def complete_json(self, system: str, user: str) -> Dict[str, Any]:
        raise NotImplementedError


class MistralLLMProvider(MistralProvider):
    def complete_json(self, system: str, user: str) -> Dict[str, Any]:
        return self._request([
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ])
