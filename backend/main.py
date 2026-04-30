from __future__ import annotations

import json
import logging
from functools import lru_cache
from typing import Any, Literal

from agents import set_tracing_disabled
from agents.exceptions import UserError
from agents.mcp import MCPServerSse, MCPServerStreamableHttp
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from openai import AsyncOpenAI
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

set_tracing_disabled(True)

logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)

MCP_TIMEOUT_S = 120.0


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    openrouter_api_key: str = Field(default="", description="OpenRouter API key")
    openrouter_model: str = "openai/gpt-4o"
    openrouter_referer: str = "https://localhost"
    openrouter_title: str = "Tim Frontiers"


@lru_cache
def get_settings() -> Settings:
    return Settings()


def openrouter_client(settings: Settings) -> AsyncOpenAI:
    headers: dict[str, str] = {}
    if settings.openrouter_referer:
        headers["HTTP-Referer"] = settings.openrouter_referer
    if settings.openrouter_title:
        headers["X-Title"] = settings.openrouter_title
    return AsyncOpenAI(
        base_url="https://openrouter.ai/api/v1",
        api_key=settings.openrouter_api_key,
        default_headers=headers or None,
    )


def _norm_mcp(u: str) -> str:
    u = u.rstrip("/")
    return u if u.endswith("/mcp") else f"{u}/mcp"


def _streamable_params(url: str, hdrs: dict[str, str]) -> dict[str, Any]:
    p: dict[str, Any] = {
        "url": url,
        "timeout": MCP_TIMEOUT_S,
        "sse_read_timeout": 300.0,
    }
    if hdrs:
        p["headers"] = hdrs
    return p


def _sse_params(url: str, hdrs: dict[str, str]) -> dict[str, Any]:
    p: dict[str, Any] = {
        "url": url,
        "timeout": MCP_TIMEOUT_S,
        "sse_read_timeout": 300.0,
    }
    if hdrs:
        p["headers"] = hdrs
    return p


def _dump_tool(t: Any) -> dict[str, Any]:
    if hasattr(t, "model_dump"):
        return t.model_dump(mode="json")
    return {"name": getattr(t, "name", str(t))}


def _dump_resource(r: Any) -> dict[str, Any]:
    if hasattr(r, "model_dump"):
        return r.model_dump(mode="json")
    return {"uri": str(getattr(r, "uri", r))}


async def _listing_from_server(mcp: Any, transport: str, url_used: str) -> dict[str, Any]:
    tools_raw = await mcp.list_tools()
    tools = [_dump_tool(t) for t in tools_raw]
    resources: list[dict[str, Any]] = []
    try:
        lr = await mcp.list_resources()
        resources = [_dump_resource(r) for r in lr.resources]
    except Exception as e:  # noqa: BLE001
        log.debug("list_resources: %s", e)
    return {
        "tools": tools,
        "resources": resources,
        "transport": transport,
        "mcp_url_used": url_used,
    }


async def _inspect_streamable(url: str, hdrs: dict[str, str]) -> dict[str, Any]:
    async with MCPServerStreamableHttp(
        params=_streamable_params(url, hdrs),
        client_session_timeout_seconds=MCP_TIMEOUT_S,
        cache_tools_list=False,
    ) as mcp:
        return await _listing_from_server(mcp, "streamable_http", url)


async def _inspect_sse(url: str, hdrs: dict[str, str]) -> dict[str, Any]:
    async with MCPServerSse(
        params=_sse_params(url, hdrs),
        client_session_timeout_seconds=MCP_TIMEOUT_S,
        cache_tools_list=False,
    ) as mcp:
        return await _listing_from_server(mcp, "sse", url)


async def _try_streamable(url: str, hdrs: dict[str, str]) -> dict[str, Any] | None:
    try:
        return await _inspect_streamable(url, hdrs)
    except UserError as e:
        log.info("streamable_http %s: %s", url, e.message)
        return None
    except Exception as e:  # noqa: BLE001
        log.info("streamable_http %s: %s", url, e)
        return None


async def _try_sse(url: str, hdrs: dict[str, str]) -> dict[str, Any] | None:
    try:
        return await _inspect_sse(url, hdrs)
    except UserError as e:
        log.info("sse %s: %s", url, e.message)
        return None
    except Exception as e:  # noqa: BLE001
        log.info("sse %s: %s", url, e)
        return None


async def run_inspect(
    mcp_url: str,
    transport: Literal["auto", "sse", "streamable_http"] = "auto",
    headers: dict[str, str] | None = None,
) -> dict[str, Any]:
    url = mcp_url.strip()
    if not url:
        raise ValueError("mcp_url is empty")
    hdrs = dict(headers) if headers else {}

    if transport == "streamable_http":
        su = _norm_mcp(url)
        r = await _try_streamable(su, hdrs)
        if r:
            return r
        raise RuntimeError(f"streamable_http failed: {su}")

    if transport == "sse":
        cands = [url]
        if not url.rstrip("/").endswith("sse"):
            cands.append(f"{url.rstrip('/')}/sse")
        seen: set[str] = set()
        for u in cands:
            if u in seen:
                continue
            seen.add(u)
            r = await _try_sse(u, hdrs)
            if r:
                return r
        raise RuntimeError(f"sse failed: {cands!r}")

    su = _norm_mcp(url)
    r = await _try_streamable(su, hdrs)
    if r:
        return r
    for u in [url] + ([] if url.rstrip("/").endswith("sse") else [f"{url.rstrip('/')}/sse"]):
        r = await _try_sse(u, hdrs)
        if r:
            return r
    raise RuntimeError("auto: streamable_http and sse both failed")


async def summarize(data: dict[str, Any], s: Settings) -> str:
    if not (s.openrouter_api_key or "").strip():
        return ""
    client = openrouter_client(s)
    payload = json.dumps(data, indent=2)[:14_000]
    msg = (
        "Briefly summarize (3-6 sentences) what this MCP server exposes for a developer.\n\n" + payload
    )
    resp = await client.chat.completions.create(
        model=s.openrouter_model,
        messages=[{"role": "user", "content": msg}],
        max_tokens=600,
    )
    return (resp.choices[0].message.content or "").strip()


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


@app.get("/api/hello")
def hello():
    return {"message": "tim-frontiers-assessment"}


class McpBody(BaseModel):
    mcp_url: str = Field(..., min_length=1)
    transport: Literal["auto", "sse", "streamable_http"] = "auto"
    headers: dict[str, str] = Field(default_factory=dict)


@app.post("/api/mcp/inspect")
async def mcp_inspect(body: McpBody):
    st = get_settings()
    try:
        listing = await run_inspect(body.mcp_url, body.transport, body.headers)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except RuntimeError as e:
        raise HTTPException(status_code=502, detail=str(e)) from e
    summary = ""
    if (st.openrouter_api_key or "").strip():
        try:
            summary = await summarize(listing, st)
        except Exception as e:  # noqa: BLE001
            log.exception("openrouter")
            summary = f"(failed: {e!s})"
    return {
        **listing,
        "openrouter_summary": summary,
        "openrouter_configured": bool((st.openrouter_api_key or "").strip()),
    }


@app.get("/api/config")
def api_config():
    s = get_settings()
    return {
        "openrouter_configured": bool((s.openrouter_api_key or "").strip()),
        "openrouter_model": s.openrouter_model,
    }
