from enum import Enum
from pathlib import Path

import yaml

_POLICY_PATH = Path(__file__).parent / "policy.yaml"


class Decision(str, Enum):
    ALLOW = "ALLOW"
    CONFIRM = "CONFIRM"
    BLOCK = "BLOCK"


# Mapping from the human-friendly labels in policy.yaml (SAFE/CONFIRM/BLOCKED)
# to the Decision the firewall actually returns.
_LEVEL_TO_DECISION = {
    "SAFE": Decision.ALLOW,
    "CONFIRM": Decision.CONFIRM,
    "BLOCKED": Decision.BLOCK,
}


def _load_policy() -> dict:
    with open(_POLICY_PATH) as f:
        return yaml.safe_load(f)


_policy = _load_policy()


def reload_policy() -> None:
    """Call after editing policy.yaml without restarting the process (tests use this too)."""
    global _policy
    _policy = _load_policy()


def evaluate(tool_name: str) -> Decision:
    """
    The ONLY function that decides whether a tool call may run.
    Deliberately dumb: a dict lookup, nothing the model said gets consulted.
    Unknown tool name -> whatever `default` says in policy.yaml (BLOCKED).
    """
    level = _policy.get("tools", {}).get(tool_name, _policy.get("default", "BLOCKED"))
    return _LEVEL_TO_DECISION.get(level, Decision.BLOCK)
