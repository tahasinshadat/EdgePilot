import json
import sys
from pathlib import Path

from fastapi.testclient import TestClient
from typer.testing import CliRunner

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from edgepilot_cli import cli as edgepilot_cli  # noqa: E402
from main import app  # noqa: E402


runner = CliRunner()
client = TestClient(app)


def test_cli_ask_offline_answer():
    result = runner.invoke(edgepilot_cli, ["ask", "Can I schedule another job?"])
    assert result.exit_code == 0
    assert "Answer" in result.stdout


def test_cli_schedule_and_status_commands():
    schedule = runner.invoke(
        edgepilot_cli,
        ["schedule", "--action", "run_shell_commands", "--command", "echo EdgePilot CLI test"],
    )
    assert schedule.exit_code == 0
    status = runner.invoke(edgepilot_cli, ["status"])
    assert status.exit_code == 0
    assert "task_id" in status.stdout or "No tasks" in status.stdout


def test_api_ask_and_schedule_endpoints():
    ask_response = client.post("/api/ask", json={"query": "How busy is the system?"})
    assert ask_response.status_code == 200
    ask_payload = ask_response.json()
    assert "answer" in ask_payload
    schedule_response = client.post(
        "/api/schedule",
        json={"action": "run_shell_commands", "command": "echo EdgePilot API test", "delay_seconds": 0},
    )
    assert schedule_response.status_code == 200
    tasks_response = client.get("/api/tasks")
    assert tasks_response.status_code == 200
    assert isinstance(tasks_response.json(), list)
