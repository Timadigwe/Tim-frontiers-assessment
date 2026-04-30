"""
Layer 2 — Orchestration: one chat turn.

Loads session verification state, applies policy (tool allowlist on MCP), runs the right agent,
updates verification from tool output / fallback classifier.
"""

from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Any

from agents import Agent, OpenAIChatCompletionsModel, Runner, trace
from agents.exceptions import AgentsException, MaxTurnsExceeded
from agents.memory import SQLiteSession
from agents.mcp import MCPServerStreamableHttp
from config import Settings
from constants import (
    AGENT_NAME,
    FALLBACK_VERIFICATION_AGENT_NAME,
    MCP_SSE_READ_TIMEOUT_S,
    MCP_TIMEOUT_S,
    MAX_AGENT_TURNS,
    MAX_GUARDRAIL_TURNS,
    OPENROUTER_BASE_URL,
    SESSION_DB_FILENAME,
    TRACE_FALLBACK_SPAN,
    TRACE_SUPPORT_SPAN,
    TRACE_VERIFICATION_GUARD_SPAN,
    VERIFICATION_DB_FILENAME,
    VERIFICATION_GUARD_NAME,
)
from fastapi import HTTPException
from instructions import (
    FALLBACK_VERIFICATION_CLASSIFIER,
    support_instructions_verified,
    verification_guard_instructions,
)
from openai import AsyncOpenAI
from policy.tools import mcp_tool_filter
from verification_signals import verification_tool_outcome
from verification_store import VerificationStore

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


def _streamable_params(url: str) -> dict[str, Any]:
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


async def _fallback_verification_classifier(
    *,
    user_message: str,
    assistant_reply: str,
    model: OpenAIChatCompletionsModel,
) -> bool:
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


async def run_chat_turn(
    *,
    st: Settings,
    session_id: str,
    message: str,
) -> dict[str, Any]:
    """
    Execute one user message: MCP (with policy filter) + optional verification update.

    Returns: ``{"reply": str, "verified": bool}``
    """
    if not st.openrouter_api_key.strip():
        raise HTTPException(status_code=503, detail="OPENROUTER_API_KEY is not set")
    mcp_url = _norm_mcp(st.mcp_server_url)
    if not mcp_url:
        raise HTTPException(status_code=503, detail="MCP_SERVER_URL is not set")

    sid = session_id.strip().lower()
    msg = message.strip()

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

    tool_filter = mcp_tool_filter(session_verified=verified_before)

    t0 = time.perf_counter()
    log.info(
        "chat start session=%s message_len=%d verified_before=%s agent=%s tools=%s",
        sid[:8],
        len(msg),
        verified_before,
        agent_name,
        tool_filter.get("allowed_tool_names"),
    )
    try:
        async with MCPServerStreamableHttp(
            params=_streamable_params(mcp_url),
            client_session_timeout_seconds=MCP_TIMEOUT_S,
            cache_tools_list=True,
            tool_filter=tool_filter,
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


async def reset_session_data(*, st: Settings, session_id: str) -> None:
    """Clear agent conversation + verification row for a session."""
    sid = session_id.strip().lower()
    db_path = _session_store_path(st)
    session = SQLiteSession(sid, db_path=str(db_path))
    await session.clear_session()
    VerificationStore(_verification_store_path(st)).clear(sid)
    log.info("session reset session=%s", sid[:8])
