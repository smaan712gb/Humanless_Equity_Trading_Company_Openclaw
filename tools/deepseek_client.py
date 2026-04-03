"""DeepSeek API client — the brain of every agent.
Uses the OpenAI SDK as recommended by DeepSeek's official docs.
"""

from __future__ import annotations

import logging
from typing import Any

from openai import AsyncOpenAI

from tools.config import DeepSeekConfig

logger = logging.getLogger(__name__)


class DeepSeekClient:
    """Async client for DeepSeek chat and reasoner models via OpenAI SDK."""

    def __init__(self, config: DeepSeekConfig):
        self.config = config
        self._client: AsyncOpenAI | None = None

    async def start(self):
        self._client = AsyncOpenAI(
            api_key=self.config.api_key,
            base_url="https://api.deepseek.com",
            timeout=self.config.timeout,
        )
        logger.info("DeepSeek client initialized (OpenAI SDK, base_url=https://api.deepseek.com)")

    async def stop(self):
        if self._client:
            await self._client.close()
            self._client = None

    async def chat(
        self,
        messages: list[dict[str, str]],
        model: str | None = None,
        temperature: float = 0.3,
        max_tokens: int | None = None,
        tools: list[dict] | None = None,
    ) -> dict[str, Any]:
        """Send a chat completion request to DeepSeek."""
        if not self._client:
            await self.start()

        model = model or self.config.chat_model
        max_tokens = max_tokens or self.config.max_tokens

        kwargs: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if tools:
            kwargs["tools"] = tools

        try:
            response = await self._client.chat.completions.create(**kwargs)
            # Convert to dict format for compatibility
            return {
                "choices": [
                    {
                        "message": {
                            "content": response.choices[0].message.content,
                            "role": response.choices[0].message.role,
                            "tool_calls": [
                                tc.model_dump() for tc in (response.choices[0].message.tool_calls or [])
                            ],
                        }
                    }
                ],
                "usage": {
                    "prompt_tokens": response.usage.prompt_tokens if response.usage else 0,
                    "completion_tokens": response.usage.completion_tokens if response.usage else 0,
                    "total_tokens": response.usage.total_tokens if response.usage else 0,
                },
                "model": response.model,
            }
        except Exception as e:
            logger.error("DeepSeek API error: %s", e)
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
