"""Project-local Agent Skill discovery and loading."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict


SKILLS_DIR = Path(__file__).resolve().parents[1] / "skills"
VALID_SKILL_NAME = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


def _parse_skill(path: Path) -> Dict[str, Any]:
    text = path.read_text(encoding="utf-8")

    if not text.startswith("---\n"):
        raise ValueError(f"{path} must start with YAML frontmatter")

    try:
        frontmatter, body = text[4:].split("\n---\n", 1)
    except ValueError as exc:
        raise ValueError(f"{path} has invalid YAML frontmatter") from exc

    metadata = {}

    for line in frontmatter.splitlines():
        key, separator, value = line.partition(":")
        if separator:
            metadata[key.strip()] = value.strip()

    name = metadata.get("name", "")
    description = metadata.get("description", "")

    if not VALID_SKILL_NAME.fullmatch(name):
        raise ValueError(f"Invalid skill name: {name}")

    if not description:
        raise ValueError("Skill description is required")

    if path.parent.name != name:
        raise ValueError(
            f"Skill directory '{path.parent.name}' must match '{name}'"
        )

    return {
        "name": name,
        "description": description,
        "instructions": body.strip(),
    }


def list_project_skills() -> list[Dict[str, str]]:
    if not SKILLS_DIR.exists():
        return []

    results = []

    for path in sorted(SKILLS_DIR.glob("*/SKILL.md")):
        skill = _parse_skill(path)
        results.append({
            "name": skill["name"],
            "description": skill["description"],
        })

    return results


def load_project_skill(name: str) -> Dict[str, Any]:
    normalized = str(name or "").strip().lower()

    if not VALID_SKILL_NAME.fullmatch(normalized):
        raise ValueError(
            "Skill name must use lowercase letters, digits, and hyphens"
        )

    path = SKILLS_DIR / normalized / "SKILL.md"

    if not path.is_file():
        available = [
            skill["name"]
            for skill in list_project_skills()
        ]
        raise ValueError(
            f"Unknown skill '{normalized}'. Available: {available}"
        )

    return _parse_skill(path)