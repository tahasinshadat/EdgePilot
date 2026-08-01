from typing import Any, Dict

from core.skills import list_project_skills, load_project_skill


def list_skills() -> Dict[str, Any]:
    skills = list_project_skills()
    return {
        "skills": skills,
        "count": len(skills),
    }


def load_skill(name: str) -> Dict[str, Any]:
    return load_project_skill(name)