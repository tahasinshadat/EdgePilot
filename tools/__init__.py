"""Tools exposed to providers and UI."""

from .metrics import (
    gather_metrics,
    report_edge_status,
    evaluate_capacity,
    suggest_capacity_window,
)
from .end_task import end_task
from .scheduler import (
    get_latest_task,
    get_latest_task_any,
    get_latest_task_by_metadata,
    get_task,
    launch,
    list_apps,
    list_recent_tasks,
    list_tasks,
    list_tasks_by_metadata,
    run_python,
    run_shell,
    search,
)

# Backwards-compatible aliases expected by other modules
get_task_record = get_task
get_latest_task_record = get_latest_task
get_latest_task_any_record = get_latest_task_any
list_task_records = list_tasks
list_recent_task_records = list_recent_tasks
get_latest_task_by_metadata_record = get_latest_task_by_metadata
list_tasks_by_metadata_record = list_tasks_by_metadata
