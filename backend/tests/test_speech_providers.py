import asyncio

import pytest

from app.ai.speech.stt.factory import get_stt_provider
from app.ai.speech.tts.elevenlabs_provider import ElevenLabsTTSProvider
from app.ai.speech.tts.factory import get_tts_provider
from app.ai.speech.tts.mock_provider import MockTTSProvider
from app.core.config import Settings


def test_deepgram_unavailable_without_api_key():
    from app.ai.speech.stt.deepgram_provider import DeepgramSTTProvider

    provider = DeepgramSTTProvider(api_key="", model="nova-2")
    assert provider.is_available() is False
    with pytest.raises(RuntimeError):
        asyncio.run(provider.start_stream())


def test_deepgram_available_once_key_is_set():
    from app.ai.speech.stt.deepgram_provider import DeepgramSTTProvider

    provider = DeepgramSTTProvider(api_key="dg-fake-key", model="nova-2")
    assert provider.is_available() is True


def test_elevenlabs_unavailable_without_api_key():
    provider = ElevenLabsTTSProvider(api_key="", voice_id="voice-1")
    assert provider.is_available() is False
    with pytest.raises(RuntimeError):
        asyncio.run(provider.synthesize("hello"))


def test_elevenlabs_available_once_key_is_set():
    provider = ElevenLabsTTSProvider(api_key="el-fake-key", voice_id="voice-1")
    assert provider.is_available() is True


def test_stt_factory_falls_back_to_mock_without_deepgram_key():
    cfg = Settings(_env_file=None, stt_provider="deepgram", deepgram_api_key="")
    provider = get_stt_provider(cfg)
    assert provider.name == "mock"


def test_tts_factory_falls_back_to_mock_without_elevenlabs_key():
    cfg = Settings(_env_file=None, tts_provider="elevenlabs", elevenlabs_api_key="")
    provider = get_tts_provider(cfg)
    assert isinstance(provider, MockTTSProvider)


def test_mock_stt_session_roundtrips_text_as_transcript():
    from app.ai.speech.stt.mock_provider import MockSTTProvider

    async def run():
        provider = MockSTTProvider()
        session = await provider.start_stream()
        await session.send_audio("Hello world".encode())
        await session.finish()
        results = [r async for r in session.transcripts()]
        return results

    results = asyncio.run(run())
    assert len(results) == 1
    assert results[0].text == "Hello world"
    assert results[0].is_final is True
