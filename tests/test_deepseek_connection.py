"""Integration test — verify DeepSeek API connectivity.
Requires DEEPSEEK_API_KEY in .env to be valid.
Skip if key is not set.
"""

import os
import pytest
from dotenv import load_dotenv

load_dotenv()

from src.config import DeepSeekConfig
from src.deepseek_client import DeepSeekClient

DEEPSEEK_KEY = os.getenv("DEEPSEEK_API_KEY", "")
HAS_KEY = DEEPSEEK_KEY and DEEPSEEK_KEY != "PASTE_YOUR_DEEPSEEK_KEY_HERE"


@pytest.fixture
def client():
    return DeepSeekClient(DeepSeekConfig(api_key=DEEPSEEK_KEY))


@pytest.mark.asyncio
@pytest.mark.skipif(not HAS_KEY, reason="DEEPSEEK_API_KEY not set")
async def test_deepseek_chat_ping(client):
    """Send a simple message to DeepSeek-chat and verify we get a response."""
    await client.start()
    try:
        response = await client.chat(
            messages=[{"role": "user", "content": "Reply with exactly: PING_OK"}],
            max_tokens=10,
        )
        content = client.extract_content(response)
        assert "PING_OK" in content or "error" not in response
        print(f"DeepSeek chat response: {content}")
    finally:
        await client.stop()


@pytest.mark.asyncio
@pytest.mark.skipif(not HAS_KEY, reason="DEEPSEEK_API_KEY not set")
async def test_deepseek_reasoner_ping(client):
    """Send a simple message to DeepSeek-reasoner and verify response."""
    await client.start()
    try:
        response = await client.reason(
            messages=[{"role": "user", "content": "What is 2 + 2? Reply with just the number."}],
            max_tokens=10,
        )
        content = client.extract_content(response)
        assert "4" in content or "error" not in response
        print(f"DeepSeek reasoner response: {content}")
    finally:
        await client.stop()


@pytest.mark.asyncio
@pytest.mark.skipif(not HAS_KEY, reason="DEEPSEEK_API_KEY not set")
async def test_deepseek_extract_content(client):
    """Verify content extraction from response."""
    await client.start()
    try:
        response = await client.chat(
            messages=[{"role": "user", "content": "Say hello"}],
            max_tokens=20,
        )
        content = client.extract_content(response)
        assert isinstance(content, str)
        assert len(content) > 0
        assert "[DeepSeek Error]" not in content
    finally:
        await client.stop()


@pytest.mark.asyncio
async def test_deepseek_bad_key():
    """Verify graceful handling of invalid API key."""
    client = DeepSeekClient(DeepSeekConfig(api_key="invalid_key_12345"))
    await client.start()
    try:
        response = await client.chat(
            messages=[{"role": "user", "content": "test"}],
            max_tokens=5,
        )
        # Should return error dict, not crash
        assert "error" in response
    finally:
        await client.stop()
