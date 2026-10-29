"""V2.1.1 policy evaluation — allow | deny | requires_approval (default deny)."""

from __future__ import annotations

from typing import Any, Literal

from app.agent_models import AiAgentCapability
from app.agent_tools import FORBIDDEN_AUTONOMOUS, PROPOSAL_TOOLS, READ_TOOLS
from app.models import TenantMembership

POLICY_VERSION = "2.1.1"
Decision = Literal["allow", "deny", "requires_approval"]


def evaluate_policy(
    *,
    membership: TenantMembership,
    capability: AiAgentCapability | None,
    tool_code: str | None = None,
    action_type: str = "agent_step",
) -> dict[str, Any]:
    if tool_code and tool_code in FORBIDDEN_AUTONOMOUS:
        return {
            "decision": "deny",
            "policy_version": POLICY_VERSION,
            "reason_code": "FORBIDDEN_AUTONOMOUS_TOOL",
            "required_approver_role": None,
        }

    if capability is None:
        return {
            "decision": "deny",
            "policy_version": POLICY_VERSION,
            "reason_code": "CAPABILITY_MISSING",
            "required_approver_role": None,
        }

    if capability.status not in {"enabled", "monitored"}:
        return {
            "decision": "deny",
            "policy_version": POLICY_VERSION,
            "reason_code": "CAPABILITY_NOT_ENABLED",
            "required_approver_role": None,
        }

    if tool_code:
        meta = READ_TOOLS.get(tool_code) or PROPOSAL_TOOLS.get(tool_code)
        if meta is None:
            return {
                "decision": "deny",
                "policy_version": POLICY_VERSION,
                "reason_code": "UNKNOWN_TOOL",
                "required_approver_role": None,
            }
        roles = meta.get("roles") or ()
        if membership.role not in roles:
            return {
                "decision": "deny",
                "policy_version": POLICY_VERSION,
                "reason_code": "TOOL_ROLE_DENIED",
                "required_approver_role": None,
            }
        if meta.get("approval_required") or capability.requires_human_approval:
            return {
                "decision": "requires_approval",
                "policy_version": POLICY_VERSION,
                "reason_code": "CLINICAL_ACTION_REVIEW"
                if capability.domain == "clinical"
                else "ACTION_REVIEW",
                "required_approver_role": meta.get("required_role") or "provider",
            }
        return {
            "decision": "allow",
            "policy_version": POLICY_VERSION,
            "reason_code": "READ_AUTHORIZED",
            "required_approver_role": None,
        }

    if capability.requires_human_approval or capability.risk_level in {"high", "restricted"}:
        return {
            "decision": "requires_approval",
            "policy_version": POLICY_VERSION,
            "reason_code": "CLINICAL_ACTION_REVIEW"
            if capability.domain == "clinical"
            else "HIGH_RISK_ACTION",
            "required_approver_role": "provider"
            if capability.domain == "clinical"
            else "staff",
        }

    if action_type and not capability:
        return {
            "decision": "deny",
            "policy_version": POLICY_VERSION,
            "reason_code": "POLICY_INCOMPLETE",
            "required_approver_role": None,
        }

    return {
        "decision": "allow",
        "policy_version": POLICY_VERSION,
        "reason_code": "LOW_RISK_AUTHORIZED",
        "required_approver_role": None,
    }
