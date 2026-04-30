"""Application-wide constants (timeouts, limits, compiled patterns)."""

import re


MCP_TIMEOUT_S = 120.0
MCP_SSE_READ_TIMEOUT_S = 300.0


MAX_AGENT_TURNS = 24
MAX_GUARDRAIL_TURNS = 6
AGENT_NAME = "SupportAgent"
VERIFICATION_GUARD_NAME = "VerificationGuard"
FALLBACK_VERIFICATION_AGENT_NAME = "VerificationFallback"
TRACE_SUPPORT_SPAN = "support_chat"
TRACE_VERIFICATION_GUARD_SPAN = "verification_guard"
TRACE_FALLBACK_SPAN = "verification_fallback"

OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"

SESSION_DB_FILENAME = "conversations.sqlite"
VERIFICATION_DB_FILENAME = "verification.sqlite"

CHAT_MESSAGE_MAX_LEN = 16_000


SESSION_ID_MIN_LEN = 36
SESSION_ID_MAX_LEN = 36

# RFC 4122 UUID: version nibble in group 3, variant 8/9/a/b in group 4.
# Used so session keys are well-formed UUIDs, not arbitrary strings, before
# using them with SQLiteSession and file paths.
UUID_V1_TO_V5_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$",
    re.I,
)
