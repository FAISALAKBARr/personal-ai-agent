import time
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from ..approvals.service import create_approval, get_pending_approval, resolve_approval
from ..audit.logger import write_audit_log
from ..models.models import User
from ..permissions.firewall import Decision, evaluate
from ..tools.base import TOOL_DESCRIPTIONS, TOOL_REGISTRY
from .providers import AIProvider

SYSTEM_PROMPT = """You are a personal task and reminder assistant, reachable over WhatsApp.
Given the user's message, decide what to do and respond with ONLY a JSON object shaped like:

{
  "intent": "INFORMATION" | "SIMPLE_ACTION" | "MULTI_STEP_ACTION" | "UNKNOWN",
  "tool_name": one of [get_tasks, create_task, update_task, create_reminder, delete_task] or null,
  "tool_params": {object of named parameters for that tool},
  "reply_if_no_tool": "short reply text, used only when tool_name is null"
}

Tool reference:
- get_tasks(status?: "pending"|"done"|"cancelled")
- create_task(title, description?, due_at?: ISO8601 datetime, priority?: "low"|"normal"|"high")
- create_reminder(title, remind_at: ISO8601 datetime) — use this whenever the user says "remind me to..."
- update_task(task_id, ...fields to change)
- delete_task(task_id) — placeholder, always requires confirmation

Rules:
- If a required parameter is missing (e.g. no time given for a reminder), set tool_name to null and
  ask for exactly the missing piece in reply_if_no_tool. Do not guess a time.
- If the request doesn't need a tool (e.g. small talk, a question you can just answer), set tool_name
  to null and put the answer in reply_if_no_tool.
- Today's date/time will be given to you in the user message context — use it to resolve "tomorrow",
  "tonight", etc. into absolute ISO8601 datetimes.
"""

CONFIRM_YES = {"setuju", "approve", "ya", "yes", "iya", "ok", "oke"}
CONFIRM_NO = {"batal", "reject", "no", "tidak", "cancel"}


async def handle_message(db: AsyncSession, user: User, text: str, provider: AIProvider, now_iso: str) -> str:
    # A pending CONFIRM always takes priority over planning a new action —
    # otherwise a stray "ya" could get reinterpreted as a brand new request.
    pending = await get_pending_approval(db, user.id)
    if pending is not None:
        normalized = text.strip().lower()
        if normalized in CONFIRM_YES:
            await resolve_approval(db, pending, approved=True)
            return await _execute_tool(db, user, pending.action, pending.parameters, Decision.CONFIRM)
        if normalized in CONFIRM_NO:
            await resolve_approval(db, pending, approved=False)
            await write_audit_log(
                db, user_id=user.id, tool_name=pending.action, params=pending.parameters,
                decision=Decision.CONFIRM, result=None, error="rejected by user",
            )
            return "Oke, dibatalkan."
        return (
            f"Masih ada aksi yang nunggu persetujuan kamu:\n\n"
            f"Aksi: {pending.action}\nDetail: {pending.parameters}\n\n"
            f"Balas 'setuju' atau 'batal' dulu sebelum lanjut."
        )

    try:
        plan = await provider.complete_json(SYSTEM_PROMPT, f"[current time: {now_iso}]\n{text}")
    except Exception:
        return "Maaf, saya lagi kesulitan memproses pesan ini. Coba lagi sebentar ya."

    tool_name = plan.get("tool_name")
    if not tool_name:
        return plan.get("reply_if_no_tool") or "Bisa dijelaskan lebih detail?"

    decision = evaluate(tool_name)
    params = plan.get("tool_params") or {}

    if decision == Decision.BLOCK:
        await write_audit_log(db, user_id=user.id, tool_name=tool_name, params=params, decision=decision, result=None, error="blocked by policy")
        return f"Aksi ini ({tool_name}) diblokir oleh kebijakan sistem — nggak bisa saya jalankan."

    if decision == Decision.CONFIRM:
        await create_approval(db, user_id=user.id, action=tool_name, target=params.get("task_id"), parameters=params)
        return (
            f"Sebelum saya lanjut:\n\nAksi: {tool_name}\nDetail: {params}\n\n"
            f"Setuju? (balas 'setuju' atau 'batal', berlaku 15 menit)"
        )

    return await _execute_tool(db, user, tool_name, params, decision)


async def _execute_tool(db: AsyncSession, user: User, tool_name: str, params: dict, decision: Decision) -> str:
    tool_fn = TOOL_REGISTRY.get(tool_name)
    if tool_fn is None:
        await write_audit_log(db, user_id=user.id, tool_name=tool_name, params=params, decision=decision, result=None, error="tool not implemented")
        return f"Tool '{tool_name}' belum diimplementasikan."

    started = time.monotonic()
    result = await tool_fn(db=db, user_id=user.id, **params)
    duration_ms = int((time.monotonic() - started) * 1000)

    await write_audit_log(
        db, user_id=user.id, tool_name=tool_name, params=params, decision=decision,
        result=result.data if result.success else None, error=result.error, duration_ms=duration_ms,
    )

    if not result.success:
        return f"Gagal menjalankan {tool_name}: {result.error}"
    return _format_result(tool_name, result.data)


def _format_result(tool_name: str, data) -> str:
    if tool_name in ("create_task", "create_reminder"):
        when = f" untuk {data['due_at']}" if data.get("due_at") else ""
        return f"Done. '{data['title']}' dibuat{when}."
    if tool_name == "get_tasks":
        if not data:
            return "Nggak ada task saat ini."
        lines = [f"- {t['title']} ({t['status']}{', due ' + t['due_at'] if t['due_at'] else ''})" for t in data]
        return "Task kamu:\n" + "\n".join(lines)
    if tool_name == "update_task":
        return "Done. Task di-update."
    return "Done."
