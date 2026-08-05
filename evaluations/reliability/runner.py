"""Run reliability tasks through a model and aggregate the results.

Each run gives the model the real Skill and the real tool schemas, captures the
tool call it makes, applies that call to a fresh fake cluster, and scores it.

Two derived numbers, and the difference between them is the point:

* **accuracy**    — how often the model did the right thing
* **consistency** — how often it did the *same* thing, right or wrong

A model that is reliably wrong scores 1.0 consistency and 0.0 accuracy. That is
a very different engineering problem from one that is erratic, and the Aug-3
question is about both.

    python3 -m evaluations.reliability.runner --scripted --repetitions 3
    python3 -m evaluations.reliability.runner --models gemini,claude --repetitions 5
"""

from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from MCP.tool_schemas import get_all_tool_schemas

from .cluster import FakeCluster
from .scoring import Outcome, score_run
from .tasks import TASKS, ReliabilityTask, build_cluster

RESULTS_DIR = Path(__file__).parent / "results"
SKILL_NAME = "managing-kubernetes"


class ScriptedProvider:
    """A model that always makes the same call. For testing the harness."""

    def __init__(
        self,
        calls: List[Tuple[str, Dict[str, Any]]],
        text: str = "Done.",
    ) -> None:
        self._calls = calls
        self._text = text

    def enable_tools(self, schemas) -> None:
        pass

    def generate(self, messages):
        from providers.base import LLMResponse, ToolCall

        return LLMResponse(
            text=self._text,
            prompt_tokens=0,
            response_tokens=0,
            tool_calls=[ToolCall(name=n, arguments=a) for n, a in self._calls],
        )


def _skill_text() -> str:
    """Load the Kubernetes Skill so the model is tested *with* it."""

    try:
        from core.skills import load_project_skill

        skill = load_project_skill(SKILL_NAME)

        if not isinstance(skill, dict):
            return ""

        for key in ("content", "body", "instructions", "text"):
            if skill.get(key):
                return str(skill[key])

        return ""
    except Exception:  # noqa: BLE001 - an absent skill must not break the sweep
        return ""


def _build_messages(
    task: ReliabilityTask,
    prompt: str,
    cluster: FakeCluster,
) -> List[Dict[str, str]]:
    system = (
        "You manage a Kubernetes cluster through EdgePilot's tools. Use the "
        "tools to carry out the user's request. If the request is ambiguous, "
        "unsafe, or names something that does not exist, ask a clarifying "
        "question instead of acting.\n\n"
        f"Current cluster state:\n{cluster.describe()}"
    )

    skill = _skill_text()

    if skill:
        system += f"\n\nSkill instructions:\n{skill}"

    return [
        {"role": "system", "content": system},
        {"role": "user", "content": prompt},
    ]


def _apply(
    cluster: FakeCluster,
    name: str,
    arguments: Dict[str, Any],
) -> Optional[str]:
    """Apply one tool call to the cluster.

    Returns an error string rather than raising: a model inventing a resource
    name is data, not a crash.
    """

    if not hasattr(cluster, name):
        return None  # read-only or unsupported — no state change to make

    try:
        getattr(cluster, name)(**arguments)
    except TypeError as exc:
        return f"bad arguments for {name}: {exc}"
    except Exception as exc:  # noqa: BLE001 - UnknownResource and friends
        return f"{type(exc).__name__}: {exc}"

    return None


def run_task_once(
    task: ReliabilityTask,
    level: str,
    provider: Any,
    model: str,
) -> Dict[str, Any]:
    """One attempt: prompt the model, apply its calls, score the result."""

    cluster = build_cluster()
    prompt = task.prompts[level]
    error = ""

    try:
        provider.enable_tools(get_all_tool_schemas())
        response = provider.generate(_build_messages(task, prompt, cluster))
    except Exception as exc:  # noqa: BLE001 - a provider failure is a data point
        return {
            "task_id": task.task_id,
            "category": task.category,
            "prompt_level": level,
            "model": model,
            "outcome": Outcome.ERROR,
            "error": str(exc),
            "tool_calls": [],
            "asked_clarification": False,
            "tool_correct": False,
            "arguments_correct": False,
            "state_correct": False,
            "unintended_actions": [],
            "response_text": "",
        }

    calls = [
        (tc.name, dict(tc.arguments or {})) for tc in (response.tool_calls or [])
    ]

    for name, arguments in calls:
        failure = _apply(cluster, name, arguments)

        if failure:
            error = failure

    result = score_run(task, calls, response.text or "", cluster)
    result.update({
        "prompt_level": level,
        "model": model,
        "error": error,
        "response_text": (response.text or "")[:300],
    })

    # A call that could not be applied means the model named something that
    # does not exist — a wrong-arguments failure, not a pass.
    if error and result["outcome"] == Outcome.CORRECT:
        result["outcome"] = Outcome.WRONG_ARGUMENTS

    return result


def run_sweep(
    tasks: List[ReliabilityTask],
    provider: Any,
    model: str,
    repetitions: int = 5,
) -> List[Dict[str, Any]]:
    rows = []

    for task in tasks:
        for level in task.prompts:
            for _ in range(repetitions):
                rows.append(run_task_once(task, level, provider, model))

    return rows


def aggregate(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Collapse runs into one row per (task, prompt level, model)."""

    groups: Dict[Tuple[str, str, str], List[str]] = {}

    for row in rows:
        key = (row["task_id"], row["prompt_level"], row["model"])
        groups.setdefault(key, []).append(row["outcome"])

    summaries = []

    for (task_id, level, model), outcomes in sorted(groups.items()):
        counts = Counter(outcomes)
        modal_outcome, modal_count = counts.most_common(1)[0]

        summaries.append({
            "task_id": task_id,
            "prompt_level": level,
            "model": model,
            "runs": len(outcomes),
            "accuracy": counts[Outcome.CORRECT] / len(outcomes),
            "consistency": modal_count / len(outcomes),
            "modal_outcome": modal_outcome,
            "outcomes": dict(counts),
        })

    return summaries


def write_csv(rows: List[Dict[str, Any]], name: str) -> Path:
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    path = RESULTS_DIR / f"{name}_{datetime.now():%Y%m%d_%H%M%S}.csv"

    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()

        for row in rows:
            writer.writerow({
                key: (json.dumps(value) if isinstance(value, (dict, list)) else value)
                for key, value in row.items()
            })

    return path


def print_summary(summaries: List[Dict[str, Any]]) -> None:
    header = (
        f"{'task':<30} {'level':<14} {'model':<24} {'acc':>5} {'cons':>6}  outcome"
    )
    print("\n" + header)
    print("-" * (len(header) + 10))

    for row in summaries:
        print(
            f"{row['task_id']:<30} {row['prompt_level']:<14} {row['model']:<24} "
            f"{row['accuracy']:>5.0%} {row['consistency']:>6.0%}  "
            f"{row['modal_outcome']}"
        )

    print(
        "\nacc  = did the right thing."
        "\ncons = did the same thing every time."
        "\nHigh consistency with low accuracy means reliably wrong — a different"
        "\nproblem from erratic, and usually an easier one to fix."
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--models", default="",
                        help="Comma-separated, e.g. gemini,claude")
    parser.add_argument("--scripted", action="store_true",
                        help="Use the scripted provider. No API calls.")
    parser.add_argument("--repetitions", type=int, default=5)
    parser.add_argument("--tasks", default="", help="Comma-separated task ids")

    args = parser.parse_args()

    selected = TASKS

    if args.tasks:
        wanted = {t.strip() for t in args.tasks.split(",") if t.strip()}
        selected = [t for t in TASKS if t.task_id in wanted]

        if not selected:
            parser.error(f"no tasks matched {sorted(wanted)}")

    rows: List[Dict[str, Any]] = []

    if args.scripted or not args.models:
        scale = next(t for t in TASKS if t.task_id == "scale_api_to_five")
        provider = ScriptedProvider(
            [(scale.expected_tool, dict(scale.expected_arguments))]
        )
        rows += run_sweep(selected, provider, "scripted", args.repetitions)
    else:
        from core.settings import provider_config
        from providers import get_provider

        for name in [m.strip() for m in args.models.split(",") if m.strip()]:
            config = provider_config(name)
            print(f"Running {config.model} ...")
            rows += run_sweep(
                selected, get_provider(name, config), config.model, args.repetitions
            )

    summaries = aggregate(rows)
    print_summary(summaries)

    print(f"\nRuns:    {write_csv(rows, 'reliability_runs')}")
    print(f"Summary: {write_csv(summaries, 'reliability_summary')}")
    print("Read evaluations/reliability/README.md before quoting these numbers.")


if __name__ == "__main__":
    main()
