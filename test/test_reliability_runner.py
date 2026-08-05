import pytest

from evaluations.reliability.runner import (
    ScriptedProvider,
    aggregate,
    run_sweep,
    run_task_once,
)
from evaluations.reliability.tasks import TASKS


def task(task_id):
    return next(t for t in TASKS if t.task_id == task_id)


def test_a_correct_scripted_model_scores_correct():
    scale = task("scale_api_to_five")
    provider = ScriptedProvider(
        [(scale.expected_tool, dict(scale.expected_arguments))]
    )

    result = run_task_once(scale, "detailed", provider, model="scripted")

    assert result["outcome"] == "correct"
    assert result["prompt_level"] == "detailed"
    assert result["model"] == "scripted"


def test_the_cluster_is_reset_between_runs():
    """A leaked mutation would make later repetitions score differently."""
    scale = task("scale_api_to_five")
    provider = ScriptedProvider([("scale_workload", {
        "namespace": "default", "deployment_name": "api", "replicas": 99,
    })])

    first = run_task_once(scale, "detailed", provider, model="scripted")
    second = run_task_once(scale, "detailed", provider, model="scripted")

    assert first["outcome"] == second["outcome"]


def test_a_model_that_invents_a_resource_is_recorded_not_crashed():
    scale = task("scale_api_to_five")
    provider = ScriptedProvider([("scale_workload", {
        "namespace": "default", "deployment_name": "does-not-exist", "replicas": 5,
    })])

    result = run_task_once(scale, "detailed", provider, model="scripted")

    assert result["outcome"] in {"wrong_arguments", "error"}
    assert result["error"]


def test_a_provider_that_raises_is_recorded_as_an_error():
    class Broken:
        def enable_tools(self, schemas):
            pass

        def generate(self, messages):
            raise RuntimeError("api down")

    result = run_task_once(task("scale_api_to_five"), "detailed", Broken(), "broken")

    assert result["outcome"] == "error"
    assert "api down" in result["error"]


def test_sweep_covers_every_level_and_repetition():
    scale = task("scale_api_to_five")
    provider = ScriptedProvider(
        [(scale.expected_tool, dict(scale.expected_arguments))]
    )

    rows = run_sweep([scale], provider, model="scripted", repetitions=3)

    assert len(rows) == len(scale.prompts) * 3


def test_aggregate_reports_perfect_consistency_for_a_deterministic_model():
    rows = [
        {"task_id": "t", "prompt_level": "simple", "model": "m", "outcome": "correct"}
        for _ in range(5)
    ]

    summary = aggregate(rows)[0]

    assert summary["runs"] == 5
    assert summary["consistency"] == pytest.approx(1.0)
    assert summary["accuracy"] == pytest.approx(1.0)


def test_aggregate_detects_inconsistency():
    """Three correct and two wrong is 60% consistent, not 100%."""
    rows = (
        [{"task_id": "t", "prompt_level": "simple", "model": "m",
          "outcome": "correct"}] * 3
        + [{"task_id": "t", "prompt_level": "simple", "model": "m",
            "outcome": "wrong_tool"}] * 2
    )

    summary = aggregate(rows)[0]

    assert summary["consistency"] == pytest.approx(0.6)
    assert summary["accuracy"] == pytest.approx(0.6)


def test_consistency_and_accuracy_can_diverge():
    """A model that is reliably wrong is consistent but not accurate - the
    distinction the research question turns on."""
    rows = [
        {"task_id": "t", "prompt_level": "simple", "model": "m",
         "outcome": "wrong_tool"}
    ] * 5

    summary = aggregate(rows)[0]

    assert summary["consistency"] == pytest.approx(1.0)
    assert summary["accuracy"] == pytest.approx(0.0)


def test_aggregate_groups_by_task_level_and_model():
    rows = [
        {"task_id": "a", "prompt_level": "simple", "model": "m1", "outcome": "correct"},
        {"task_id": "a", "prompt_level": "vague", "model": "m1", "outcome": "no_action"},
        {"task_id": "a", "prompt_level": "simple", "model": "m2", "outcome": "correct"},
    ]

    assert len(aggregate(rows)) == 3


def test_scripted_model_fails_the_tasks_it_was_not_scripted_for():
    """A harness that passes everything measures nothing."""
    scale = task("scale_api_to_five")
    provider = ScriptedProvider(
        [(scale.expected_tool, dict(scale.expected_arguments))]
    )

    cordon = run_task_once(task("cordon_node_b"), "simple", provider, "scripted")
    unsafe = run_task_once(
        task("safety_ambiguous_namespace"), "simple", provider, "scripted"
    )

    assert cordon["outcome"] == "wrong_tool"
    assert unsafe["outcome"] == "unsafe_action"
