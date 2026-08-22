"""Approval handling for controlled token-usage experiments."""

from __future__ import annotations

from .conditions import ExperimentCondition


class ApprovalDecisionRequired(RuntimeError):
    """Raised when a supervised condition lacks a human decision."""


def resolve_approval(
    condition: ExperimentCondition,
    *,
    human_decision: bool | None = None,
) -> bool:
    """Return the approval decision required by the condition."""

    if condition.approval_mode == "automatic":
        return True

    if human_decision is None:
        raise ApprovalDecisionRequired(
            f"condition {condition.name!r} requires a human approval decision"
        )

    return human_decision
