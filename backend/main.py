"""
Layer 1 — HTTP API: validation, config, and thin routes.

Chat orchestration lives in ``orchestration/chat.py``; tool allowlists in ``policy/tools.py``.
"""

from __future__ import annotations

import logging
import os
import sys
from contextlib import asynccontextmanager

from config import Settings, get_settings
from constants import (
    CHAT_MESSAGE_MAX_LEN,
    SESSION_ID_MAX_LEN,
    SESSION_ID_MIN_LEN,
    UUID_V1_TO_V5_RE,
)
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from orchestration.chat import reset_session_data, run_chat_turn
from pydantic import BaseModel, Field

from agents import set_tracing_disabled, set_tracing_export_api_key

# Safe default until lifespan configures tracing export.
set_tracing_disabled(True)


def _setup_logging() -> None:
    level_name = (os.getenv("LOG_LEVEL") or "INFO").upper()
    level = getattr(logging, level_name, logging.INFO)
    logging.basicConfig(
        level=level,
        format="%(asctime)s | %(levelname)-5s | %(name)s | %(message)s",
        stream=sys.stdout,
        force=True,
    )


_setup_logging()
log = logging.getLogger(__name__)


def _configure_tracing(st: Settings) -> None:
    key = (st.openai_api_key or "").strip()
    if key:
        set_tracing_export_api_key(key)
        set_tracing_disabled(False)
        log.info("OpenAI Agents tracing export enabled (Traces dashboard)")
    else:
        set_tracing_disabled(True)
        log.info(
            "OpenAI Agents tracing export disabled; set OPENAI_API_KEY to export traces.",
        )


@asynccontextmanager
async def lifespan(_app: FastAPI):
    _configure_tracing(get_settings())
    yield


def _norm_mcp(u: str) -> str:
    u = (u or "").strip().rstrip("/")
    if not u:
        return ""
    return u if u.endswith("/mcp") else f"{u}/mcp"


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


app = FastAPI(lifespan=lifespan)
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
        "tracing_export_configured": bool(st.openai_api_key.strip()),
    }


@app.post("/api/chat")
async def chat(body: ChatBody):
    st = get_settings()
    sid = _validate_session_id(body.session_id)
    return await run_chat_turn(
        st=st,
        session_id=sid,
        message=body.message,
    )


@app.post("/api/session/reset")
async def reset_session(body: ResetBody):
    st = get_settings()
    sid = _validate_session_id(body.session_id)
    await reset_session_data(st=st, session_id=sid)
    return {"ok": True}
