# edgepilot/cli.py
from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Optional

import typer
from rich import print as rprint

from edgepilot.config import run_wizard, get_config
from edgepilot.mcp.server import run_mcp
from edgepilot.metrics import get_metrics_service
from edgepilot.scheduler import get_scheduler
from edgepilot.llm.ollama import OllamaProvider
from edgepilot.usage import usage_stats

# Root app
app = typer.Typer(add_completion=False, help="EdgePilot CLI")

# --------------------------- Top-level commands ---------------------------

@app.command()
def wizard():
    """Run first-time setup wizard."""
    run_wizard()


@app.command()
def api(host: Optional[str] = None, port: Optional[int] = None):
    """Launch FastAPI."""
    cfg = get_config()
    h = host or cfg.host
    p = port or cfg.api_port
    import uvicorn
    uvicorn.run("edgepilot.api.main:app", host=h, port=p, reload=False)


@app.command()
def ui(port: Optional[int] = None):
    """Launch Streamlit UI."""
    cfg = get_config()
    p = port or cfg.ui_port
    import subprocess, shutil
    app_py = Path(__file__).resolve().parent / "ui" / "app.py"
    cmd = [shutil.which("streamlit") or "streamlit", "run", str(app_py), "--server.port", str(p)]
    subprocess.check_call(cmd)


@app.command()
def mcp():
    """Start the MCP server on stdio transport."""
    run_mcp()

# --------------------------- Sub-apps (Typer way) ---------------------------

run_app = typer.Typer(help="Manage Runs.")
metrics_app = typer.Typer(help="Metrics commands.")
task_app = typer.Typer(help="Scheduler task commands.")
policy_app = typer.Typer(help="Policy commands.")

# ---- run ----
@run_app.command("start")
def run_start(
    user_note: str = typer.Option("", help="Note for the run"),
    sampling_sec: Optional[int] = typer.Option(None, help="Sampling seconds"),
):
    svc = get_metrics_service()
    res = svc.start_run(user_note=user_note, sampling_sec=sampling_sec)
    rprint(res)


@run_app.command("end")
def run_end(run_id: str):
    svc = get_metrics_service()
    res = asyncio.run(svc.end_run(run_id))
    rprint(res)

# ---- metrics ----
@metrics_app.command("snapshot")
def metrics_snapshot(include_processes: bool = False, top_n: int = 15):
    svc = get_metrics_service()
    rprint(svc.snapshot(include_processes=include_processes, top_n=top_n))


@metrics_app.command("stream")
def metrics_stream(interval_sec: float = 2.0):
    svc = get_metrics_service()
    sid = svc.start_stream(interval=interval_sec)
    rprint({"stream_id": sid, "note": "Press Ctrl+C to stop"})
    try:
        while True:
            import time
            time.sleep(1)
    except KeyboardInterrupt:
        svc.stop_stream(sid)
        rprint({"stopped": True})

# ---- task ----
@task_app.command("enqueue")
def task_enqueue(
    name: str,
    command: str,
    requires_gpu: bool = False,
    est_runtime_sec: int = 0,
    priority: int = 5,
    max_cpu_pct: int = 90,
    max_mem_mb: int = 0,
    min_vram_mb: int = 0,
):
    sch = get_scheduler()
    t = sch.enqueue(
        name=name,
        command=command,
        requires_gpu=requires_gpu,
        est_runtime_sec=est_runtime_sec,
        priority=priority,
        max_cpu_pct=max_cpu_pct,
        max_mem_mb=max_mem_mb,
        min_vram_mb=min_vram_mb,
    )
    rprint({"task_id": t.id, "state": t.state})


@task_app.command("list")
def task_list(state: str = "any"):
    sch = get_scheduler()
    rows = sch.list(state=state)
    rprint(
        [
            {"id": r.id, "name": r.name, "state": r.state, "priority": r.priority, "command": r.command}
            for r in rows
        ]
    )


@task_app.command("cancel")
def task_cancel(task_id: str):
    sch = get_scheduler()
    rprint({"canceled": sch.cancel(task_id)})

# ---- policy ----
@policy_app.command("set")
def policy_set(preset: str = typer.Argument("balanced_defaults")):
    from edgepilot.scheduler.policies import PRESETS

    if preset not in PRESETS:
        rprint(f"[red]Unknown preset[/red]: {preset}")
        raise typer.Exit(1)
    sch = get_scheduler()
    r = sch.policy_set(preset, PRESETS[preset].rules)
    rprint({"active": r})


@policy_app.command("show")
def policy_show():
    sch = get_scheduler()
    rprint(sch.simulate())

# Attach sub-apps
app.add_typer(run_app, name="run")
app.add_typer(metrics_app, name="metrics")
app.add_typer(task_app, name="task")
app.add_typer(policy_app, name="policy")

# ---- advisor (top-level command) ----
@app.command()
def advise(question: str = typer.Argument(..., help="Ask a quick question; uses snapshot + local LLM")):
    svc = get_metrics_service()
    snap = svc.snapshot(include_processes=True)
    provider = OllamaProvider()
    prompt_path = Path(__file__).resolve().parent / "llm" / "prompts" / "bottleneck.md"
    prompt = prompt_path.read_text()
    prompt = prompt.replace("{{ question }}", question)
    prompt = prompt.replace("{{ snapshot_json }}", json.dumps(snap)[:8000])
    res = asyncio.run(provider.complete(prompt))
    rprint(res.text)
    rprint(usage_stats())
