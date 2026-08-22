"""Prompt construction for controlled token-usage experiments."""

from __future__ import annotations

from .conditions import ExperimentCondition


class SkillRequiredError(RuntimeError):
    """Raised when a Skill condition has no Skill instructions."""


def build_system_prompt(
    *,
    base_prompt: str,
    condition: ExperimentCondition,
    skill_text: str = "",
) -> str:
    """Build a system prompt according to an experiment condition."""

    base_prompt = base_prompt.strip()

    if not condition.include_skill:
        return base_prompt

    skill_text = skill_text.strip()
    if not skill_text:
        raise SkillRequiredError(
            f"condition {condition.name!r} requires non-empty Skill text"
        )

    return f"{base_prompt}\n\nSkill instructions:\n{skill_text}"
