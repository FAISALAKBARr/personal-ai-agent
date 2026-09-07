from typing import Any, Awaitable, Callable

from pydantic import BaseModel


class ToolResult(BaseModel):
    success: bool
    data: Any = None
    error: str | None = None


TOOL_REGISTRY: dict[str, Callable[..., Awaitable[ToolResult]]] = {}
TOOL_DESCRIPTIONS: dict[str, str] = {}


def register_tool(name: str, description: str):
    """
    Decorator that registers a narrowly-scoped, strongly-typed tool.
    Deliberately the opposite of execute_sql()/execute_shell()/execute_anything() —
    every tool here does exactly one thing with named, typed parameters.
    """

    def decorator(fn):
        TOOL_REGISTRY[name] = fn
        TOOL_DESCRIPTIONS[name] = description
        return fn

    return decorator
