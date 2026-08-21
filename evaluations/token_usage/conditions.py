"""Experimental conditions for the token-usage study."""

from dataclasses import dataclass
from typing import Literal


ApprovalMode = Literal["human", "automatic"]


@dataclass(frozen=True)
class ExperimentCondition:
    name: str
    include_skill: bool
    approval_mode: ApprovalMode


CONDITIONS = {
    "no_skill": ExperimentCondition(
        name="no_skill",
        include_skill=False,
        approval_mode="human",
    ),
    "skill_with_approval": ExperimentCondition(
        name="skill_with_approval",
        include_skill=True,
        approval_mode="human",
    ),
    "fully_agentic": ExperimentCondition(
        name="fully_agentic",
        include_skill=True,
        approval_mode="automatic",
    ),
}
