"""Infer PIN verification outcome from an Agents RunResult (MCP tool outputs)."""

from __future__ import annotations

import json
import logging
from typing import Literal

from agents import RunResult

log = logging.getLogger(__name__)

VerificationOutcome = Literal["verified", "failed", "unknown"]


def _run_blob(result: RunResult) -> str:
    try:
        items = result.to_input_list()
        return json.dumps(items, default=str)
    except Exception as e:  # noqa: BLE001
        log.debug("verification_signals: could not serialize run: %s", e)
        return ""


def verification_tool_outcome(result: RunResult) -> VerificationOutcome:
    """Parse MCP turn for verify_customer_pin result.

    Returns **verified** when tool output clearly includes a customer id (assessment MCP shape).
    Returns **failed** when the verify step clearly failed (without a customer id).
    Returns **unknown** when the tool was not invoked or output is ambiguous.
    """
    blob = _run_blob(result)
    low = blob.lower()
    if "verify_customer_pin" not in low:
        return "unknown"

    if "customer_id" in low:
        return "verified"

    failure_tokens = (
        "invalid",
        "incorrect",
        "wrong",
        "not found",
        "verification failed",
        "unable to verify",
        "no matching",
        "denied",
        "error",
    )
    if any(tok in low for tok in failure_tokens):
        return "failed"

    return "unknown"
