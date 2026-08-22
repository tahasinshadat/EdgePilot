"""Randomized run-plan generation for token-scaling experiments."""

from __future__ import annotations

import random
from dataclasses import dataclass

from .cluster_fixtures import SUPPORTED_NODE_COUNTS
from .conditions import CONDITIONS


@dataclass(frozen=True)
class PlannedRun:
    run_id: str
    repetition: int
    condition: str
    cluster_nodes: int


def build_run_plan(
    *,
    repetitions: int,
    seed: int,
) -> list[PlannedRun]:
    """Build randomized blocks containing every condition and cluster size."""

    if repetitions < 1:
        raise ValueError("repetitions must be at least 1")

    randomizer = random.Random(seed)
    plan: list[PlannedRun] = []
    run_number = 1

    for repetition in range(1, repetitions + 1):
        combinations = [
            (condition_name, cluster_nodes)
            for condition_name in sorted(CONDITIONS)
            for cluster_nodes in SUPPORTED_NODE_COUNTS
        ]
        randomizer.shuffle(combinations)

        for condition_name, cluster_nodes in combinations:
            plan.append(
                PlannedRun(
                    run_id=f"run-{run_number:03d}",
                    repetition=repetition,
                    condition=condition_name,
                    cluster_nodes=cluster_nodes,
                )
            )
            run_number += 1

    return plan
