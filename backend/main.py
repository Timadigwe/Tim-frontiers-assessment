from __future__ import annotations

import logging
from pathlib import Path

from agents import Agent, OpenAIChatCompletionsModel, Runner, set_tracing_disabled, trace
from agents.exceptions import AgentsException, MaxTurnsExceeded
from agents.memory import SQLiteSession
from agents.mcp import MCPServerStreamableHttp
from config import Settings, get_settings
from constants import (
    AGENT_NAME,
    CHAT_MESSAGE_MAX_LEN,
    MCP_SSE_READ_TIMEOUT_S,
    MCP_TIMEOUT_S,
    MAX_AGENT_TURNS,
    OPENROUTER_BASE_URL,
    SESSION_DB_FILENAME,
    SESSION_ID_MAX_LEN,
    SESSION_ID_MIN_LEN,
    TRACE_SPAN_NAME,
    UUID_V1_TO_V5_RE,
)
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from instructions import SUPPORT_AGENT
from openai import AsyncOpenAI
from pydantic import BaseModel, Field

set_tracing_disabled(True)

logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)


def openrouter_client(settings: Settings) -> AsyncOpenAI:
    headers: dict[str, str] = {}
    if settings.openrouter_referer:
        headers["HTTP-Referer"] = settings.openrouter_referer
    if settings.openrouter_title:
        headers["X-Title"] = settings.openrouter_title
    return AsyncOpenAI(
        base_url=OPENROUTER_BASE_URL,
        api_key=settings.openrouter_api_key,
        default_headers=headers or None,
    )


def _norm_mcp(u: str) -> str:
    u = (u or "").strip().rstrip("/")
    if not u:
        return ""
    return u if u.endswith("/mcp") else f"{u}/mcp"


def _streamable_params(url: str) -> dict:
    return {
        "url": url,
        "timeout": MCP_TIMEOUT_S,
        "sse_read_timeout": MCP_SSE_READ_TIMEOUT_S,
    }


def _session_store_path(st: Settings) -> Path:
    root = Path(st.session_store_dir)
    root.mkdir(parents=True, exist_ok=True)
    return root / SESSION_DB_FILENAME


def _validate_session_id(session_id: str) -> str:
    s = session_id.strip()
    if not UUID_V1_TO_V5_RE.match(s):
        raise HTTPException(status_code=400, detail="session_id must be a UUID")
    return s.lower()


class ChatBody(BaseModel):
    session_id: str = Field(..., min_length=SESSION_ID_MIN_LEN, max_length=SESSION_ID_MAX_LEN)
    message: str = Field(..., min_length=1, max_length=CHAT_MESSAGE_MAX_LEN)


class ResetBody(BaseModel):
    session_id: str = Field(..., min_length=SESSION_ID_MIN_LEN, max_length=SESSION_ID_MAX_LEN)


app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
def health():
    return {"ok": True}


@app.get("/api/config")
def api_config():
    st = get_settings()
    return {
        "model": st.openrouter_model,
        "llm_configured": bool(st.openrouter_api_key.strip()),
        "mcp_configured": bool(_norm_mcp(st.mcp_server_url)),
    }


@app.post("/api/chat")
async def chat(body: ChatBody):
    st = get_settings()
    if not st.openrouter_api_key.strip():
        raise HTTPException(status_code=503, detail="OPENROUTER_API_KEY is not set")
    mcp_url = _norm_mcp(st.mcp_server_url)
    if not mcp_url:
        raise HTTPException(status_code=503, detail="MCP_SERVER_URL is not set")

    sid = _validate_session_id(body.session_id)
    msg = body.message.strip()
    db_path = _session_store_path(st)
    session = SQLiteSession(sid, db_path=str(db_path))
    model = OpenAIChatCompletionsModel(model=st.openrouter_model, openai_client=openrouter_client(st))
    try:
        async with MCPServerStreamableHttp(
            params=_streamable_params(mcp_url),
            client_session_timeout_seconds=MCP_TIMEOUT_S,
            cache_tools_list=True,
        ) as mcp:
            agent = Agent(
                name=AGENT_NAME,
                instructions=SUPPORT_AGENT,
                model=model,
                mcp_servers=[mcp],
            )
            with trace(TRACE_SPAN_NAME):
                result = await Runner.run(
                    agent,
                    input=msg,
                    session=session,
                    max_turns=MAX_AGENT_TURNS,
                )
        text = result.final_output
        if text is None:
            text = ""
        elif not isinstance(text, str):
            text = str(text)
        return {"reply": text.strip()}
    except MaxTurnsExceeded as e:
        log.warning("max turns: %s", e)
        raise HTTPException(status_code=504, detail="Too many steps—try a shorter question.") from e
    except AgentsException as e:
        log.exception("agents")
        raise HTTPException(status_code=502, detail=getattr(e, "message", str(e))) from e
    except Exception as e:  # noqa: BLE001
        log.exception("chat")
        raise HTTPException(status_code=502, detail="Support chat temporarily unavailable.") from e


@app.post("/api/session/reset")
async def reset_session(body: ResetBody):
    st = get_settings()
    sid = _validate_session_id(body.session_id)
    session = SQLiteSession(sid, db_path=str(_session_store_path(st)))
    await session.clear_session()
    return {"ok": True}
