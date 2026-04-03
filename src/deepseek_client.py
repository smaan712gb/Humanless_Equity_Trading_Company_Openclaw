"""DeepSeek API client — the brain of every agent."""

from __future__ import annotations

import json
import logging
from typing import Any

import aiohttp

from .config import DeepSeekConfig

logger = logging.getLogger(__name__)


class DeepSeekClient:
    """Async client for DeepSeek chat and reasoner models."""

    def __init__(self, config: DeepSeekConfig):
        self.config = config
        self._session: aiohttp.ClientSession | None = None

    async def start(self):
        self._session = aiohttp.ClientSession(
            headers={
                "Authorization": f"Bearer {self.config.api_key}",
                "Content-Type": "application/json",
            },
            timeout=aiohttp.ClientTimeout(total=self.config.timeout),
        )

    async def stop(self):
        if self._session:
            await self._session.close()
            self._session = None

    async def chat(
        self,
        messages: list[dict[str, str]],
        model: str | None = None,
        temperature: float = 0.3,
        max_tokens: int | None = None,
        tools: list[dict] | None = None,
    ) -> dict[str, Any]:
        """Send a chat completion request to DeepSeek."""
        if not self._session:
            await self.start()

        model = model or self.config.chat_model
        max_tokens = max_tokens or self.config.max_tokens

        payload: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if tools:
            payload["tools"] = tools

        url = f"{self.config.api_base}/chat/completions"

        try:
            async with self._session.post(url, json=payload) as resp:
                if resp.status != 200:
                    error_text = await resp.text()
                    logger.error("DeepSeek API error %d: %s", resp.status, error_text)
                    return {"error": error_text, "status": resp.status}

                data = await resp.json()
                return data
        except aiohttp.ClientError as e:
            logger.error("DeepSeek request failed: %s", e)
            return {"error": str(e)}

    async def reason(
        self,
        messages: list[dict[str, str]],
        temperature: float = 0.1,
        max_tokens: int = 16384,
        tools: list[dict] | None = None,
    ) -> dict[str, Any]:
        """Use the reasoner model for complex decisions."""
        return await self.chat(
            messages=messages,
            model=self.config.reasoner_model,
            temperature=temperature,
            max_tokens=max_tokens,
            tools=tools,
        )

    def extract_content(self, response: dict) -> str:
        """Extract the text content from a DeepSeek response."""
        if "error" in response:
            return f"[DeepSeek Error] {response['error']}"
        try:
            return response["choices"][0]["message"]["content"]
        except (KeyError, IndexError):
            return "[DeepSeek Error] Unexpected response format"

    def extract_tool_calls(self, response: dict) -> list[dict]:
        """Extract tool calls from a DeepSeek response."""
        try:
            msg = response["choices"][0]["message"]
            return msg.get("tool_calls", [])
        except (KeyError, IndexError):
            return []
