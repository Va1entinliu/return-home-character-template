from __future__ import annotations

import base64
import json
import re
import uuid
from dataclasses import dataclass


@dataclass(frozen=True)
class CharacterResponse:
    reply: str
    usage: dict


def speech_text(text: str) -> str:
    without_actions = re.sub(r"\([^)]*\)|（[^）]*）", "", str(text or ""))
    return re.sub(r"\s+", " ", without_actions).strip()


async def call_character(
    *,
    api_key: str,
    model: str,
    url: str,
    messages: list[dict],
    max_tokens: int,
) -> CharacterResponse:
    import httpx

    if not api_key:
        raise RuntimeError("ARK_API_KEY 尚未配置")
    async with httpx.AsyncClient(timeout=90) as client:
        response = await client.post(
            url,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": model,
                "messages": messages,
                "max_tokens": max_tokens,
            },
        )
    response.raise_for_status()
    payload = response.json()
    return CharacterResponse(
        reply=str(payload["choices"][0]["message"]["content"]).strip(),
        usage=payload.get("usage") if isinstance(payload.get("usage"), dict) else {},
    )


def _decode_tts_payload(content: bytes, content_type: str) -> bytes:
    if "audio/" in content_type or content.startswith(b"ID3"):
        return content

    audio_parts: list[bytes] = []
    for raw_line in content.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        encoded = event.get("data") or event.get("audio")
        if isinstance(encoded, str) and encoded:
            audio_parts.append(base64.b64decode(encoded))
    if not audio_parts:
        raise RuntimeError("TTS 返回中没有可播放的 MP3 数据")
    return b"".join(audio_parts)


async def synthesize_tts(
    *,
    api_key: str,
    voice_id: str,
    url: str,
    resource_id: str,
    text: str,
) -> bytes:
    import httpx

    spoken = speech_text(text)
    if not spoken:
        raise RuntimeError("消息只有动作描写，没有需要朗读的文字")
    if not api_key or not voice_id or voice_id == "S_xxxx":
        raise RuntimeError("语音 API Key 或私有音色 ID 尚未配置")

    async with httpx.AsyncClient(timeout=90) as client:
        response = await client.post(
            url,
            headers={
                "X-Api-Key": api_key,
                "X-Api-Resource-Id": resource_id,
                "X-Api-Request-Id": str(uuid.uuid4()),
                "Content-Type": "application/json",
                "Connection": "keep-alive",
            },
            json={
                "req_params": {
                    "text": spoken,
                    "speaker": voice_id,
                    "audio_params": {"format": "mp3", "sample_rate": 24000},
                }
            },
        )
    response.raise_for_status()
    return _decode_tts_payload(
        response.content,
        response.headers.get("content-type", "").lower(),
    )
