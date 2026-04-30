from __future__ import annotations

import logging
import os
import sys
import time
from contextlib import asynccontextmanager
from pathlib import Path

from agents import (
    Agent,
    OpenAIChatCompletionsModel,
    Runner,
    set_tracing_disabled,
    set_tracing_export_api_key,
    trace,
)
from agents.exceptions import AgentsException, MaxTurnsExceeded
from agents.memory import SQLiteSession
from agents.mcp import MCPServerStreamableHttp
from config import Settings, get_settings
from constants import (
    AGENT_NAME,
    CHAT_MESSAGE_MAX_LEN,
    FALLBACK_VERIFICATION_AGENT_NAME,
    MCP_SSE_READ_TIMEOUT_S,
    MCP_TIMEOUT_S,
    MAX_AGENT_TURNS,
    MAX_GUARDRAIL_TURNS,
    OPENROUTER_BASE_URL,
    SESSION_DB_FILENAME,
    SESSION_ID_MAX_LEN,
    SESSION_ID_MIN_LEN,
    TRACE_FALLBACK_SPAN,
    TRACE_SUPPORT_SPAN,
    TRACE_VERIFICATION_GUARD_SPAN,
    UUID_V1_TO_V5_RE,
    VERIFICATION_DB_FILENAME,
    VERIFICATION_GUARD_NAME,
)
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from instructions import (
    FALLBACK_VERIFICATION_CLASSIFIER,
    support_instructions_verified,
    verification_guard_instructions,
)
from openai import AsyncOpenAI
from pydantic import BaseModel, Field
from verification_signals import verification_tool_outcome
from verification_store import VerificationStore

# Safe default: OpenRouter has no OpenAI key unless we set tracing export separately.
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


def _verification_store_path(st: Settings) -> Path:
    root = Path(st.session_store_dir)
    root.mkdir(parents=True, exist_ok=True)
    return root / VERIFICATION_DB_FILENAME


def _validate_session_id(session_id: str) -> str:
    s = session_id.strip()
    if not UUID_V1_TO_V5_RE.match(s):
        raise HTTPException(status_code=400, detail="session_id must be a UUID")
    return s.lower()


async def _fallback_verification_classifier(
    *,
    user_message: str,
    assistant_reply: str,
    model: OpenAIChatCompletionsModel,
) -> bool:
    """Second pass only when MCP tool output is ambiguous. No tools."""
    agent = Agent(
        name=FALLBACK_VERIFICATION_AGENT_NAME,
        instructions=FALLBACK_VERIFICATION_CLASSIFIER,
        model=model,
    )
    payload = (
        "Evaluate this single turn.\n\n"
        f"User message:\n{user_message}\n\n"
        f"Assistant reply:\n{assistant_reply}\n"
    )
    with trace(TRACE_FALLBACK_SPAN):
        result = await Runner.run(agent, input=payload, max_turns=MAX_GUARDRAIL_TURNS)
    raw = result.final_output
    text = "" if raw is None else str(raw).strip().upper()
    token = text.split()[0] if text else ""
    return token == "VERIFIED"


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

    vstore = VerificationStore(_verification_store_path(st))
    verified_before = vstore.is_verified(sid)

    if verified_before:
        agent_name = AGENT_NAME
        instructions = support_instructions_verified()
        trace_span = TRACE_SUPPORT_SPAN
    else:
        agent_name = VERIFICATION_GUARD_NAME
        instructions = verification_guard_instructions()
        trace_span = TRACE_VERIFICATION_GUARD_SPAN

    t0 = time.perf_counter()
    log.info(
        "chat start session=%s message_len=%d verified_before=%s agent=%s",
        sid[:8],
        len(msg),
        verified_before,
        agent_name,
    )
    try:
        async with MCPServerStreamableHttp(
            params=_streamable_params(mcp_url),
            client_session_timeout_seconds=MCP_TIMEOUT_S,
            cache_tools_list=True,
        ) as mcp:
            agent = Agent(
                name=agent_name,
                instructions=instructions,
                model=model,
                mcp_servers=[mcp],
            )
            with trace(trace_span):
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
        reply = text.strip()

        verified_after = verified_before
        if not verified_before and reply:
            outcome = verification_tool_outcome(result)
            if outcome == "verified":
                vstore.set_verified(sid)
                verified_after = True
                log.info("session verified via MCP tool output session=%s", sid[:8])
            elif outcome == "unknown":
                if await _fallback_verification_classifier(
                    user_message=msg,
                    assistant_reply=reply,
                    model=model,
                ):
                    vstore.set_verified(sid)
                    verified_after = True
                    log.info("session verified via fallback classifier session=%s", sid[:8])
            elif outcome == "failed":
                log.info("PIN verification failed this turn session=%s", sid[:8])

        return {"reply": reply, "verified": verified_after}
    except MaxTurnsExceeded as e:
        log.warning("chat max_turns session=%s err=%s", sid[:8], e)
        raise HTTPException(status_code=504, detail="Too many steps—try a shorter question.") from e
    except AgentsException as e:
        log.warning(
            "chat agents_error session=%s: %s",
            sid[:8],
            getattr(e, "message", str(e))[:500],
        )
        raise HTTPException(status_code=502, detail=getattr(e, "message", str(e))) from e
    except Exception as e:  # noqa: BLE001
        log.exception("chat unexpected_error session=%s", sid[:8])
        raise HTTPException(status_code=502, detail="Support chat temporarily unavailable.") from e
    finally:
        log.info("chat end session=%s duration_ms=%d", sid[:8], int((time.perf_counter() - t0) * 1000))


@app.post("/api/session/reset")
async def reset_session(body: ResetBody):
    st = get_settings()
    sid = _validate_session_id(body.session_id)
    session = SQLiteSession(sid, db_path=str(_session_store_path(st)))
    await session.clear_session()
    VerificationStore(_verification_store_path(st)).clear(sid)
    log.info("session reset session=%s", sid[:8])
    return {"ok": True}
