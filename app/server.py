from __future__ import annotations

import asyncio
import hmac
import json
import os
from collections import OrderedDict, defaultdict
from pathlib import Path

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, Header, HTTPException, Query
from fastapi.responses import Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .context import (
    build_character_messages,
    get_max_tokens,
    stable_prefix_fingerprint,
)
from .memory import LocalHistoryIndex
from .providers import call_character, synthesize_tts
from .storage import ConversationStore, RequestConflict
from .usage import parse_provider_usage


ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")


def configured_path(name: str, fallback: str) -> Path:
    candidate = ROOT / os.getenv(name, "")
    return candidate if candidate.is_file() else ROOT / fallback


def load_text(path: Path) -> str:
    return path.read_text("utf-8") if path.is_file() else ""


def load_json(path: Path, fallback):
    if not path.is_file():
        return fallback
    return json.loads(path.read_text("utf-8"))


role_setting = load_text(
    configured_path("ROLE_SETTING_FILE", "examples/role-setting.example.txt")
)
memories = load_json(
    configured_path("MEMORIES_FILE", "examples/memories.example.json"),
    {},
)
history_payload = load_json(
    configured_path("HISTORY_FILE", "examples/history.example.json"),
    {"messages": []},
)
base_history = (
    history_payload.get("messages", [])
    if isinstance(history_payload, dict)
    else history_payload
)
base_history = list(base_history) if isinstance(base_history, list) else []

database_path = ROOT / os.getenv(
    "CONVERSATION_DB",
    "private/conversations.sqlite3",
)
store = ConversationStore(database_path)

app = FastAPI(title="Return Home Character reference server")
session_locks: defaultdict[str, asyncio.Lock] = defaultdict(asyncio.Lock)
chat_inflight: dict[tuple[str, str], tuple[str, asyncio.Task[dict]]] = {}
tts_inflight: dict[tuple[str, str], tuple[str, asyncio.Task[bytes]]] = {}
tts_completed: OrderedDict[tuple[str, str], tuple[str, bytes]] = OrderedDict()
flight_lock = asyncio.Lock()


def configured_access_token() -> str:
    token = os.getenv("APP_ACCESS_TOKEN", "").strip()
    if len(token) < 24 or token.lower().startswith("change-me"):
        raise HTTPException(
            status_code=503,
            detail="APP_ACCESS_TOKEN 尚未配置为至少 24 位的随机字符串",
        )
    return token


async def require_app_token(
    x_app_token: str | None = Header(default=None),
) -> None:
    expected = configured_access_token()
    supplied = str(x_app_token or "")
    if not hmac.compare_digest(supplied, expected):
        raise HTTPException(status_code=401, detail="App 访问令牌无效")


class ChatRequest(BaseModel):
    text: str = Field(min_length=1, max_length=20_000)
    request_id: str = Field(pattern=r"^[A-Za-z0-9._-]{8,128}$")
    session_id: str = Field(pattern=r"^[A-Za-z0-9._-]{8,128}$")


class TtsRequest(BaseModel):
    text: str = Field(min_length=1, max_length=20_000)
    request_id: str = Field(pattern=r"^[A-Za-z0-9._-]{8,128}$")
    session_id: str = Field(pattern=r"^[A-Za-z0-9._-]{8,128}$")


def current_context_history(session_id: str, request_id: str) -> list[dict]:
    current_user_id = f"chat:{session_id}:{request_id}:user"
    session_messages = [
        message
        for message in store.messages(session_id)
        if message["id"] != current_user_id
    ]
    return [*base_history, *session_messages]


async def process_chat(request: ChatRequest) -> dict:
    text = request.text.strip()
    async with session_locks[request.session_id]:
        state = store.begin_chat(
            request.session_id,
            request.request_id,
            text,
        )
        if state["status"] == "completed":
            return {"reply": state["response_text"], "deduplicated": True}

        conversation = current_context_history(
            request.session_id,
            request.request_id,
        )
        history_index = LocalHistoryIndex(conversation)
        selection = history_index.select_context(text)
        model_messages = build_character_messages(
            role_setting=role_setting,
            memories=memories,
            retrieved_turns=[
                list(turn) for turn in selection.retrieved_turns
            ],
            recent_messages=list(selection.recent_messages),
            user_text=text,
        )
        character = await call_character(
            api_key=os.getenv("ARK_API_KEY", ""),
            model=os.getenv("ARK_MODEL", "doubao-seed-character-260628"),
            url=os.getenv(
                "ARK_CHAT_URL",
                "https://ark.cn-beijing.volces.com/api/v3/chat/completions",
            ),
            messages=model_messages,
            max_tokens=get_max_tokens(text),
        )
        reply = character.reply
        store.complete_chat(
            request.session_id,
            request.request_id,
            text,
            reply,
        )
        system_prefix = [
            message for message in model_messages
            if message["role"] == "system"
            and not message["content"].startswith("【当前设备时间】")
            and "检索历史引用" not in message["content"]
        ]
        return {
            "reply": reply,
            "deduplicated": False,
            "context": selection.stats,
            "usage": parse_provider_usage(character.usage),
            "stablePrefixFingerprint": stable_prefix_fingerprint(system_prefix),
        }


async def process_tts(request: TtsRequest) -> bytes:
    return await synthesize_tts(
        api_key=os.getenv("VOLCANO_TTS_API_KEY", ""),
        voice_id=os.getenv("VOLCANO_VOICE_ID", ""),
        url=os.getenv(
            "VOLCANO_TTS_URL",
            "https://openspeech.bytedance.com/api/v3/tts/unidirectional",
        ),
        resource_id=os.getenv("VOLCANO_TTS_RESOURCE_ID", "seed-icl-2.0"),
        text=request.text,
    )


@app.get("/api/health", dependencies=[Depends(require_app_token)])
async def health():
    return {
        "ok": True,
        "characterConfigured": bool(os.getenv("ARK_API_KEY")),
        "ttsConfigured": bool(os.getenv("VOLCANO_TTS_API_KEY"))
        and bool(os.getenv("VOLCANO_VOICE_ID")),
        "baseHistoryMessages": len(base_history),
    }


@app.get("/api/history", dependencies=[Depends(require_app_token)])
async def conversation_history(
    session_id: str = Query(pattern=r"^[A-Za-z0-9._-]{8,128}$"),
):
    return {"messages": store.messages(session_id)}


@app.post("/api/chat", dependencies=[Depends(require_app_token)])
async def chat(request: ChatRequest):
    key = (request.session_id, request.request_id)
    text = request.text.strip()
    async with flight_lock:
        existing = chat_inflight.get(key)
        if existing and existing[0] != text:
            raise HTTPException(
                status_code=409,
                detail="同一会话中的 request_id 正在处理不同文本",
            )
        if existing:
            task = existing[1]
        else:
            task = asyncio.create_task(process_chat(request))
            chat_inflight[key] = (text, task)
    try:
        return await task
    except RequestConflict as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    except HTTPException:
        raise
    except Exception as error:
        raise HTTPException(status_code=502, detail=str(error)) from error
    finally:
        async with flight_lock:
            current = chat_inflight.get(key)
            if current and current[1] is task:
                chat_inflight.pop(key, None)


@app.post("/api/tts", dependencies=[Depends(require_app_token)])
async def tts(request: TtsRequest):
    key = (request.session_id, request.request_id)
    text = request.text
    async with flight_lock:
        completed = tts_completed.get(key)
        if completed and completed[0] != text:
            raise HTTPException(
                status_code=409,
                detail="同一会话中的 TTS request_id 已用于不同文本",
            )
        if completed:
            tts_completed.move_to_end(key)
            return Response(completed[1], media_type="audio/mpeg")

        existing = tts_inflight.get(key)
        if existing and existing[0] != text:
            raise HTTPException(
                status_code=409,
                detail="同一会话中的 TTS request_id 正在处理不同文本",
            )
        if existing:
            task = existing[1]
        else:
            task = asyncio.create_task(process_tts(request))
            tts_inflight[key] = (text, task)
    try:
        audio = await task
        async with flight_lock:
            tts_completed[key] = (text, audio)
            tts_completed.move_to_end(key)
            while len(tts_completed) > 8:
                tts_completed.popitem(last=False)
        return Response(audio, media_type="audio/mpeg")
    except HTTPException:
        raise
    except Exception as error:
        raise HTTPException(status_code=502, detail=str(error)) from error
    finally:
        async with flight_lock:
            current = tts_inflight.get(key)
            if current and current[1] is task:
                tts_inflight.pop(key, None)


app.mount(
    "/",
    StaticFiles(directory=ROOT / "app" / "static", html=True),
    name="static",
)
