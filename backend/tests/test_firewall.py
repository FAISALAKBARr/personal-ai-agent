from app.permissions.firewall import Decision, evaluate


def test_safe_tool_is_allowed():
    assert evaluate("get_tasks") == Decision.ALLOW
    assert evaluate("create_task") == Decision.ALLOW
    assert evaluate("create_reminder") == Decision.ALLOW


def test_confirm_tool_requires_confirmation():
    assert evaluate("delete_task") == Decision.CONFIRM


def test_unknown_tool_defaults_to_blocked():
    # This is the important one: fail closed. A tool the policy has never
    # heard of — e.g. something the model hallucinates — must never
    # default to ALLOW.
    assert evaluate("execute_shell") == Decision.BLOCK
    assert evaluate("send_email") == Decision.BLOCK
    assert evaluate("anything_not_in_policy_yaml") == Decision.BLOCK
