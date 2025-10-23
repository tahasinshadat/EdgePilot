from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import threading
import time
import uuid
from pathlib import Path
from shutil import which
from typing import Dict, List, Optional

import typer
import uvicorn
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from providers import available_providers, get_provider
from providers.base import ChatMessage, ProviderConfig
from tools.metrics import ensure_data_dir, gather_metrics
from MCP import execute_tool, format_tools_for_gemini

ROOT_DIR = Path(__file__).parent
DATA_DIR = ROOT_DIR / "data"
CHAT_FILE = DATA_DIR / "chat_history.json"
USAGE_FILE = DATA_DIR / "usage_metrics.json"
TOOL_HISTORY_FILE = DATA_DIR / "tool_call_history.json"
FRONTEND_DIR = ROOT_DIR / "frontend"

SYSTEM_PROMPT = (
    "You are EdgePilot, an on-prem AI copilot who understands real-time system capacity, bottlenecks, "
    "and scheduling needs for engineers. Provide succinct, actionable guidance grounded in the latest "
    "system context."
)

PROVIDER_ENV_SETTINGS = {
    "gemini": {
        "api_key": "GEMINI_API_KEY",
        "model": "GEMINI_MODEL",
        "default_model": "gemini-2.0-flash",
        "base_url": "GEMINI_BASE_URL",
    },
    "claude": {
        "api_key": "ANTHROPIC_API_KEY",
        "model": "CLAUDE_MODEL",
        "default_model": "claude-3-5-sonnet-20240620",
        "base_url": "CLAUDE_BASE_URL",
    },
    "gpt": {
        "api_key": "OPENAI_API_KEY",
        "model": "GPT_MODEL",
        "default_model": "gpt-4o-mini",
        "base_url": "GPT_BASE_URL",
    },
}


cli = typer.Typer(add_completion=False, help="EdgePilot backend CLI.")
tools_cli = typer.Typer(help="Utility tools.")
cli.add_typer(tools_cli, name="tools")


class ChatSummary(BaseModel):
    id: str
    title: str
    tokens_used: int = 0
    message_count: int = 0
    tool_calls_count: int = 0
    last_activity: float = Field(0.0, description="Unix timestamp")


class ChatDetail(ChatSummary):
    messages: List[Dict[str, object]] = Field(default_factory=list)


class ChatCreateRequest(BaseModel):
    title: Optional[str] = None


class SendMessageRequest(BaseModel):
    prompt: str
    provider: Optional[str] = None


class SendMessageResponse(BaseModel):
    reply: str
    tokens_used: int
    prompt_tokens: int
    response_tokens: int
    chat: ChatDetail


class ChatStore:
    """Thread-safe JSON storage for chat sessions."""

    def __init__(self, path: Path) -> None:
        self.path = path
        ensure_data_dir(self.path.parent)
        self._lock = threading.Lock()
        if not self.path.exists():
            self._write({"sessions": []})

    def _read(self) -> Dict[str, object]:
        with self.path.open("r", encoding="utf-8") as fh:
            try:
                return json.load(fh)
            except json.JSONDecodeError:
                return {"sessions": []}

    def _write(self, data: Dict[str, object]) -> None:
        tmp = self.path.with_suffix(".tmp")
        with tmp.open("w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2)
        tmp.replace(self.path)

    def list_sessions(self) -> List[Dict[str, object]]:
        with self._lock:
            data = self._read()
            return data.get("sessions", [])

    def get_session(self, chat_id: str) -> Dict[str, object]:
        with self._lock:
            data = self._read()
            for session in data.get("sessions", []):
                if session["id"] == chat_id:
                    return session
        raise KeyError(chat_id)

    def create_session(self, title: Optional[str] = None) -> Dict[str, object]:
        session = {
            "id": str(uuid.uuid4()),
            "title": title or f"Chat {time.strftime('%H:%M:%S')}",
            "messages": [],
            "tokens_used": 0,
            "tool_calls_count": 0,
            "created_at": time.time(),
            "updated_at": time.time(),
        }
        with self._lock:
            data = self._read()
            sessions = data.get("sessions", [])
            sessions.insert(0, session)
            data["sessions"] = sessions
            self._write(data)
        return session

    def append_messages(self, chat_id: str, messages: List[Dict[str, object]], token_delta: int, tool_calls_delta: int = 0) -> Dict[str, object]:
        with self._lock:
            data = self._read()
            sessions = data.get("sessions", [])
            for session in sessions:
                if session["id"] == chat_id:
                    session["messages"].extend(messages)
                    session["tokens_used"] = int(session.get("tokens_used", 0)) + max(token_delta, 0)
                    session["tool_calls_count"] = int(session.get("tool_calls_count", 0)) + max(tool_calls_delta, 0)
                    session["updated_at"] = time.time()
                    title = (session.get("title") or "").strip().lower()
                    if not title or title.startswith("new chat") or title.startswith("chat "):
                        first_user = next(
                            (m for m in session["messages"] if m.get("role") == "user" and m.get("content")), None
                        )
                        if first_user:
                            snippet = first_user["content"].strip().splitlines()[0][:50]
                            if snippet:
                                session["title"] = snippet if len(snippet) > 2 else "Conversation"
                    self._write(data)
                    return session
        raise KeyError(chat_id)

    def delete_session(self, chat_id: str) -> bool:
        """Delete a chat session by ID."""
        with self._lock:
            data = self._read()
            sessions = data.get("sessions", [])
            original_length = len(sessions)
            sessions = [s for s in sessions if s["id"] != chat_id]
            if len(sessions) < original_length:
                data["sessions"] = sessions
                self._write(data)
                return True
        return False


class UsageLogger:
    """Track usage statistics per call."""

    def __init__(self, path: Path) -> None:
        self.path = path
        ensure_data_dir(self.path.parent)
        self._lock = threading.Lock()
        if not self.path.exists():
            self._write({"records": []})

    def _read(self) -> Dict[str, object]:
        with self.path.open("r", encoding="utf-8") as fh:
            try:
                return json.load(fh)
            except json.JSONDecodeError:
                return {"records": []}

    def _write(self, data: Dict[str, object]) -> None:
        tmp = self.path.with_suffix(".tmp")
        with tmp.open("w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2)
        tmp.replace(self.path)

    def log(
        self,
        *,
        provider: str,
        model: str,
        prompt_tokens: int,
        response_tokens: int,
        latency_ms: float,
        ok: bool,
    ) -> None:
        record = {
            "ts": time.time(),
            "provider": provider,
            "model": model,
            "prompt_tokens": prompt_tokens,
            "response_tokens": response_tokens,
            "latency_ms": latency_ms,
            "ok": ok,
        }
        with self._lock:
            data = self._read()
            data.setdefault("records", []).append(record)
            self._write(data)


class ToolCallLogger:
    """Track tool calls for debugging purposes."""

    def __init__(self, path: Path) -> None:
        self.path = path
        ensure_data_dir(self.path.parent)
        self._lock = threading.Lock()
        if not self.path.exists():
            self._write({"tool_calls": []})

    def _read(self) -> Dict[str, object]:
        with self.path.open("r", encoding="utf-8") as fh:
            try:
                return json.load(fh)
            except json.JSONDecodeError:
                return {"tool_calls": []}

    def _write(self, data: Dict[str, object]) -> None:
        tmp = self.path.with_suffix(".tmp")
        with tmp.open("w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2)
        tmp.replace(self.path)

    def log(
        self,
        *,
        provider: str,
        model: str,
        tool_name: str,
        arguments: Dict[str, object],
        result: Dict[str, object],
        success: bool,
        latency_ms: float,
        chat_id: str = None,
    ) -> None:
        """Log a tool call execution."""
        record = {
            "ts": time.time(),
            "provider": provider,
            "model": model,
            "tool_name": tool_name,
            "arguments": arguments,
            "result": result,
            "success": success,
            "latency_ms": latency_ms,
            "chat_id": chat_id,
        }
        with self._lock:
            data = self._read()
            data.setdefault("tool_calls", []).append(record)
            # Keep only last 1000 tool calls to prevent file from growing too large
            if len(data["tool_calls"]) > 1000:
                data["tool_calls"] = data["tool_calls"][-1000:]
            self._write(data)


def load_env() -> None:
    env_path = Path("env") / ".env"
    if env_path.exists():
        load_dotenv(env_path, override=False)


def provider_config(name: str) -> ProviderConfig:
    key = name.lower()
    settings = PROVIDER_ENV_SETTINGS.get(key)
    if not settings:
        raise ValueError(f"Unsupported provider '{name}'")

    api_key = os.getenv(settings["api_key"], "").strip()
    model = os.getenv(settings["model"], settings["default_model"]).strip()
    base_url = os.getenv(settings["base_url"], "").strip() or None
    timeout = int(os.getenv("LLM_TIMEOUT_SEC", "60"))
    return ProviderConfig(api_key=api_key, model=model or settings["default_model"], timeout_sec=timeout, base_url=base_url)


load_env()
DEFAULT_PROVIDER = os.getenv("DEFAULT_PROVIDER", "gemini").lower()

chat_store = ChatStore(CHAT_FILE)
usage_logger = UsageLogger(USAGE_FILE)
tool_call_logger = ToolCallLogger(TOOL_HISTORY_FILE)

app = FastAPI(title="EdgePilot Backend", version="0.3.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost",
        "http://127.0.0.1",
        "http://localhost:5173",
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "null",  # Electron/file:// renderer
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

if FRONTEND_DIR.exists():
    app.mount("/app", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")


def _to_summary(session: Dict[str, object]) -> ChatSummary:
    last_msg = session["messages"][-1]["created_at"] if session.get("messages") else session.get("updated_at", 0.0)
    return ChatSummary(
        id=session["id"],
        title=session.get("title", "Chat"),
        tokens_used=int(session.get("tokens_used", 0)),
        message_count=len(session.get("messages", [])),
        tool_calls_count=int(session.get("tool_calls_count", 0)),
        last_activity=float(last_msg or 0.0),
    )


def _to_detail(session: Dict[str, object]) -> ChatDetail:
    summary = _to_summary(session)
    return ChatDetail(**summary.model_dump(), messages=session.get("messages", []))


@app.get("/", include_in_schema=False)
def root():
    if FRONTEND_DIR.exists():
        return RedirectResponse(url="/app/")
    return {"status": "ok"}


@app.get("/api/providers")
def api_providers() -> Dict[str, dict]:
    raw = available_providers()
    result: Dict[str, dict] = {}
    for name, meta in raw.items():
        entry = dict(meta)
        entry.setdefault("id", name)
        entry["preferred"] = name == DEFAULT_PROVIDER
        settings = PROVIDER_ENV_SETTINGS.get(name)
        configured = False
        note = ""
        if settings:
            configured = bool(os.getenv(settings["api_key"], "").strip())
            note = "" if configured else f"Set {settings['api_key']} in env/.env"
        entry["configured"] = configured
        entry["note"] = note
        result[name] = entry
    return result


@app.get("/api/metrics")
def api_metrics() -> Dict[str, object]:
    return gather_metrics()


@app.get("/api/chats")
def api_list_chats() -> List[ChatSummary]:
    sessions = chat_store.list_sessions()
    return [_to_summary(session) for session in sessions]


@app.post("/api/chats", status_code=201)
def api_create_chat(payload: Optional[ChatCreateRequest] = None) -> ChatDetail:
    try:
        session = chat_store.create_session(payload.title if payload else None)
        return _to_detail(session)
    except Exception as error:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"Failed to create chat: {error}") from error


@app.get("/api/chats/{chat_id}")
def api_get_chat(chat_id: str) -> ChatDetail:
    try:
        session = chat_store.get_session(chat_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="Chat not found") from None
    return _to_detail(session)


@app.delete("/api/chats/{chat_id}")
def api_delete_chat(chat_id: str) -> Dict[str, str]:
    """Delete a chat session by ID."""
    if chat_store.delete_session(chat_id):
        return {"status": "deleted", "chat_id": chat_id}
    raise HTTPException(status_code=404, detail="Chat not found")


@app.post("/api/chats/{chat_id}/messages")
def api_send_message(chat_id: str, payload: SendMessageRequest) -> SendMessageResponse:
    provider_name = (payload.provider or DEFAULT_PROVIDER).lower()
    try:
        config = provider_config(provider_name)
        provider = get_provider(provider_name, config)
    except Exception as error:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=str(error)) from error

    try:
        session = chat_store.get_session(chat_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="Chat not found") from None

    # Enable tools for providers that support them
    if hasattr(provider, 'enable_tools'):
        tool_schemas = format_tools_for_gemini()
        provider.enable_tools(tool_schemas)

    user_message: ChatMessage = {
        "role": "user",
        "content": payload.prompt.strip(),
        "created_at": time.time(),
    }
    model_messages: List[ChatMessage] = [{"role": "system", "content": SYSTEM_PROMPT}]
    model_messages.extend(session.get("messages", []))
    model_messages.append(user_message)

    # Store all messages to be saved (user + assistant messages)
    messages_to_save = [user_message]
    total_prompt_tokens = 0
    total_response_tokens = 0
    total_tool_calls = 0

    # Tool calling loop - continue until we get a final response
    max_iterations = 5  # Prevent infinite loops
    iteration = 0
    final_text = ""

    start = time.perf_counter()
    ok = True

    while iteration < max_iterations:
        iteration += 1
        
        try:
            llm_response = provider.generate(model_messages)
            total_prompt_tokens += llm_response.prompt_tokens
            total_response_tokens += llm_response.response_tokens
        except NotImplementedError as error:
            raise HTTPException(status_code=501, detail=str(error)) from error
        except Exception as error:  # noqa: BLE001
            ok = False
            latency_ms = (time.perf_counter() - start) * 1000
            usage_logger.log(
                provider=provider_name,
                model=config.model,
                prompt_tokens=total_prompt_tokens,
                response_tokens=total_response_tokens,
                latency_ms=latency_ms,
                ok=False,
            )
            raise HTTPException(status_code=500, detail=f"Provider error: {error}") from error
        
        # Check if there are tool calls
        if llm_response.has_tool_calls:
            # Execute each tool call
            tool_results = []
            total_tool_calls += len(llm_response.tool_calls)

            for tool_call in llm_response.tool_calls:
                tool_start = time.perf_counter()
                result = execute_tool(tool_call.name, tool_call.arguments)
                tool_latency = (time.perf_counter() - tool_start) * 1000

                # Log tool call
                tool_call_logger.log(
                    provider=provider_name,
                    model=config.model,
                    tool_name=tool_call.name,
                    arguments=tool_call.arguments,
                    result=result,
                    success=result.get("success", False),
                    latency_ms=tool_latency,
                    chat_id=chat_id,
                )

                tool_results.append(result)
            
            # Add assistant message with tool calls info
            tool_call_summary = f"[Called tools: {', '.join(tc.name for tc in llm_response.tool_calls)}]"
            if llm_response.text:
                tool_call_summary = llm_response.text + " " + tool_call_summary

            # Add tool results to the conversation
            tool_results_text = "\n\nTool Results:\n"
            for result in tool_results:
                if result["success"]:
                    tool_results_text += f"- {result['tool']}: {json.dumps(result['result'], indent=2)}\n"
                else:
                    tool_results_text += f"- {result['tool']} ERROR: {result['error']}\n"
            
            # Continue the conversation with tool results
            model_messages.append({
                "role": "assistant",
                "content": tool_call_summary,
            })
            model_messages.append({
                "role": "user",
                "content": tool_results_text,
            })
        else:
            # No tool calls, this is the final response
            final_text = llm_response.text
            break
    
    if not final_text:
        final_text = "I attempted to use tools but could not generate a final response."
    
    latency_ms = (time.perf_counter() - start) * 1000
    assistant_message: ChatMessage = {
        "role": "assistant",
        "content": final_text,
        "created_at": time.time(),
    }
    messages_to_save.append(assistant_message)

    updated_session = chat_store.append_messages(
        chat_id,
        messages_to_save,
        total_prompt_tokens + total_response_tokens,
        tool_calls_delta=total_tool_calls
    )
    usage_logger.log(
        provider=provider_name,
        model=config.model,
        prompt_tokens=total_prompt_tokens,
        response_tokens=total_response_tokens,
        latency_ms=latency_ms,
        ok=ok,
    )

    detail = _to_detail(updated_session)
    return SendMessageResponse(
        reply=final_text,
        tokens_used=detail.tokens_used,
        prompt_tokens=total_prompt_tokens,
        response_tokens=total_response_tokens,
        chat=detail,
    )



def run_server(host: str = "127.0.0.1", port: int = int(os.getenv("PORT", "8000")), reload: bool = False) -> None:
    """Run the API server in the foreground."""
    uvicorn.run("main:app", host=host, port=port, reload=reload)


def find_open_port(host: str, start: int, attempts: int = 10) -> int:
    """Find an available TCP port starting from `start`."""
    port = start
    for _ in range(attempts):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                sock.bind((host, port))
            except OSError:
                port += 1
                continue
        return port
    raise RuntimeError(f"Unable to bind API server near {start}")


def start_server_in_background(host: str, port: int):
    """Start the API server on a background thread."""
    config = uvicorn.Config(app=app, host=host, port=port, log_level="info")
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    while not getattr(server, "started", False) and thread.is_alive():
        time.sleep(0.1)
    if not getattr(server, "started", False):
        raise RuntimeError(f"API server failed to start on {host}:{port}")
    return server, thread


def resolve_electron_command(ui_dir: Path) -> Optional[List[str]]:
    """Return the command used to launch Electron."""
    local_paths = [
        ui_dir / "node_modules" / ".bin" / "electron.cmd",
        ui_dir / "node_modules" / ".bin" / "electron",
    ]
    for path in local_paths:
        if path.exists():
            return [str(path)]

    for candidate in ("npx.cmd", "npx"):
        cmd_path = which(candidate)
        if cmd_path:
            return [cmd_path, "electron"]
    return None


def launch_desktop_app() -> None:
    """Launch the API and Electron desktop shell."""
    host = os.getenv("HOST", "127.0.0.1")
    requested_port = int(os.getenv("PORT", "8000"))
    port = find_open_port(host, requested_port)
    try:
        server, thread = start_server_in_background(host, port)
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        sys.exit(1)
    env = os.environ.copy()
    env.setdefault("BACKEND_URL", f"http://{host}:{port}")
    ui_dir = ROOT_DIR / "ui"
    if not ui_dir.exists():
        print("Electron UI not found. Run `npm install` inside ui/ first.", file=sys.stderr)
        server.should_exit = True
        thread.join(timeout=5)
        sys.exit(1)
    cmd = resolve_electron_command(ui_dir)
    if not cmd:
        print(
            "Electron runtime missing. Install Node.js 18+, then run `npm install` inside ui/.",
            file=sys.stderr,
        )
        server.should_exit = True
        thread.join(timeout=5)
        sys.exit(1)
    cmd = cmd + ["."]
    try:
        proc = subprocess.Popen(cmd, cwd=ui_dir, env=env)
    except FileNotFoundError:
        print(
            "Electron not found on PATH. Ensure Node.js is installed and dependencies are installed in ui/.",
            file=sys.stderr,
        )
        server.should_exit = True
        thread.join(timeout=5)
        sys.exit(1)
    try:
        proc.wait()
    except KeyboardInterrupt:
        proc.terminate()
        proc.wait()
    finally:
        server.should_exit = True
        thread.join(timeout=5)
        if proc.returncode:
            sys.exit(proc.returncode)


@cli.command("serve")
def serve(
    host: str = typer.Option("127.0.0.1", "--host", "-h", help="Host interface to bind."),
    port: int = typer.Option(int(os.getenv("PORT", "8000")), "--port", "-p", help="Port to listen on."),
    reload: bool = typer.Option(False, help="Enable autoreload (development only)."),
) -> None:
    """Run the backend API server."""
    run_server(host=host, port=port, reload=reload)


@tools_cli.command("metrics")
def tool_metrics(
    top_n: int = typer.Option(10, help="Number of top processes to include."),
    pretty: bool = typer.Option(True, help="Pretty-print JSON output."),
) -> None:
    """Dump a metrics snapshot to stdout."""
    payload = gather_metrics(top_n=top_n)
    indent = 2 if pretty else None
    typer.echo(json.dumps(payload, indent=indent))


@tools_cli.command("test-tools")
def test_tools() -> None:
    """Test all tool calls and print their outputs."""
    from MCP import execute_tool

    typer.echo("=== Testing EdgePilot Tool Calls ===\n")

    # Test 1: gather_metrics
    typer.echo("1. Testing gather_metrics tool:")
    result = execute_tool("gather_metrics", {"top_n": 5})
    typer.echo(f"   Success: {result.get('success')}")
    if result.get('success'):
        metrics = result.get('result', {})
        typer.echo(f"   CPU: {metrics.get('cpu', {}).get('percent')}%")
        typer.echo(f"   Memory Used: {metrics.get('memory', {}).get('percent')}%")
        typer.echo(f"   Top Processes: {len(metrics.get('top_processes', []))}")
    else:
        typer.echo(f"   Error: {result.get('error')}")
    typer.echo()

    # Test 2: search_path
    typer.echo("2. Testing search_path tool (searching for 'notepad'):")
    result = execute_tool("search_path", {"query": "notepad", "max_results": 3})
    typer.echo(f"   Success: {result.get('success')}")
    if result.get('success'):
        search_result = result.get('result', {})
        typer.echo(f"   Found: {search_result.get('found')} paths")
        for i, path in enumerate(search_result.get('paths', []), 1):
            typer.echo(f"   {i}. {path}")
    else:
        typer.echo(f"   Error: {result.get('error')}")
    typer.echo()

    # Test 3: schedule_task (with path from search)
    typer.echo("3. Testing schedule_task tool (notepad):")
    # First get a path
    search_result = execute_tool("search_path", {"query": "notepad.exe", "max_results": 1})
    if search_result.get('success') and search_result['result']['found'] > 0:
        notepad_path = search_result['result']['paths'][0]
        result = execute_tool("schedule_task", {
            "application": notepad_path,
            "delay_seconds": 0
        })
        typer.echo(f"   Success: {result.get('success')}")
        if result.get('success'):
            task_result = result.get('result', {})
            typer.echo(f"   Status: {task_result.get('status')}")
            typer.echo(f"   PID: {task_result.get('pid')}")
            typer.echo(f"   Path: {notepad_path}")
        else:
            typer.echo(f"   Error: {result.get('error')}")
    else:
        typer.echo("   Skipped - could not find notepad.exe")
    typer.echo()

    # Test 4: end_task (test with a safe process name that likely doesn't exist)
    typer.echo("4. Testing end_task tool (safe test - non-existent process):")
    result = execute_tool("end_task", {
        "identifier": "fake_process_that_doesnt_exist_12345",
        "force": False
    })
    typer.echo(f"   Success: {result.get('success')}")
    if not result.get('success'):
        typer.echo(f"   Expected Error: {result.get('error')}")
    typer.echo()

    typer.echo("=== Tool Testing Complete ===")


if __name__ == "__main__":
    if len(sys.argv) > 1:
        cli()
    else:
        launch_desktop_app()
