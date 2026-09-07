import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from ..models.models import AuditLog
from ..permissions.firewall import Decision

# Blocklist redaction: safe for now because no Phase 1 tool ever touches a
# credential. It's a safety net, not the primary control. Once you add tools
# that DO touch secrets (email tokens, API keys — Phase 5+), switch this to
# an explicit per-tool allowlist of loggable fields instead of a blocklist —
# a blocklist only catches key names you thought to list.
_REDACT_KEYS = {"password", "token", "api_key", "apikey", "secret", "authorization", "credential", "access_token"}


def redact(params: dict) -> dict:
    return {k: ("***REDACTED***" if k.lower() in _REDACT_KEYS else v) for k, v in (params or {}).items()}


async def write_audit_log(
    db: AsyncSession,
    *,
    user_id: uuid.UUID | None,
    tool_name: str,
    params: dict | None,
    decision: Decision,
    result,
    error: str | None,
    duration_ms: int | None = None,
    agent_run_id: uuid.UUID | None = None,
) -> None:
    entry = AuditLog(
        id=uuid.uuid4(),
        user_id=user_id,
        agent_run_id=agent_run_id,
        tool_name=tool_name,
        parameters=redact(params),
        permission_decision=decision.value,
        result=result,
        error=error,
        duration_ms=duration_ms,
    )
    db.add(entry)
    await db.commit()
