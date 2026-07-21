from __future__ import annotations

import asyncio
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
from typing import Any, Dict, List, Optional

import typer
import uvicorn
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Query, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from providers import available_providers, get_provider
from providers.base import ChatMessage, ProviderConfig
from tools.metrics import gather_metrics
from tools.scheduler import _REGISTRY
from MCP import (
    execute_tool,
    format_tools_for_gemini,
    format_tools_for_claude,
    get_all_tool_schemas,
)
from core.interface import ask_question, schedule_operation, summarize_tasks
from core.settings import (
    DEFAULT_PROVIDER,
    PROVIDER_ENV_SETTINGS,
    SYSTEM_PROMPT,
    load_env,
    provider_config,
)

'''
what is the command to make the installer for Mac?

pyinstaller --onefile --windowed --icon=assets/logo.ico --name=EdgePilot-Installer-Windows installer/install.py

is for windows
'''

ROOT_DIR = Path(__file__).parent
DATA_DIR = ROOT_DIR / "data"
CHAT_FILE = DATA_DIR / "chat_history.json"
USAGE_FILE = DATA_DIR / "usage_metrics.json"
TOOL_HISTORY_FILE = DATA_DIR / "tool_call_history.json"
FRONTEND_DIR = ROOT_DIR / "frontend"


def ensure_data_dir(path: Path) -> None:
    """Create directory if it does not exist."""
    path.mkdir(parents=True, exist_ok=True)



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


class AskRequest(BaseModel):
    query: str
    provider: Optional[str] = None
    response_format: str = Field("text", description="Either 'text' or 'json'.")
    context: Optional[Dict[str, Any]] = None
    system_prompt: Optional[str] = None
    context_window: int = Field(5, ge=1, le=50)


class AskResponse(BaseModel):
    question: str
    answer: str
    provider: str
    used_remote_provider: bool
    metrics: Dict[str, Any]
    recent_tasks: List[Dict[str, Any]]
    tokens: Dict[str, Any]
    response_format: str


class ScheduleRequest(BaseModel):
    action: str
    command: Optional[str] = None
    application: Optional[str] = None
    script_path: Optional[str] = None
    args: Optional[List[str]] = None
    cwd: Optional[str] = None
    delay_seconds: int = Field(0, ge=0)


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


load_env()

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

@app.websocket("/api/metrics/stream")
async def api_metrics_stream(websocket: WebSocket):
    await websocket.accept()
    try:
        while True:
            try:
                data = gather_metrics()
                await websocket.send_json(data)
            except Exception as e:
                # If we fail to send (e.g. client disconnected), break the loop
                break
            await asyncio.sleep(1.0)
    except WebSocketDisconnect:
        pass



@app.post("/api/ask", response_model=AskResponse)
def api_ask(payload: AskRequest) -> AskResponse:
    fmt = (payload.response_format or "text").lower()
    if fmt not in {"text", "json"}:
        raise HTTPException(status_code=400, detail="response_format must be 'text' or 'json'")
    result = ask_question(
        payload.query,
        provider=payload.provider,
        response_format=fmt,
        context=payload.context,
        system_prompt=payload.system_prompt,
        context_window=payload.context_window,
    )
    return AskResponse(**result)


@app.post("/api/schedule")
def api_schedule(payload: ScheduleRequest) -> Dict[str, Any]:
    try:
        return schedule_operation(payload.action, payload.model_dump())
    except ValueError as error:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=str(error)) from error


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
    if hasattr(provider, "enable_tools"):
        provider_id = ""
        try:
            provider_id = (type(provider).describe() or {}).get("id", "")
        except Exception:
            provider_id = ""

        if provider_id == "claude":
            tool_schemas = format_tools_for_claude()
        elif provider_id == "gemini":
            tool_schemas = format_tools_for_gemini()
        else:
            tool_schemas = get_all_tool_schemas()
        provider.enable_tools(tool_schemas)

    user_message: ChatMessage = {
        "role": "user",
        "content": payload.prompt.strip(),
        "created_at": time.time(),
    }
    model_messages: List[ChatMessage] = [{"role": "system", "content": SYSTEM_PROMPT}]

    # Context Pruning: keep only the last 10 messages
    history = session.get("messages", [])
    if len(history) > 10:
        model_messages.append({"role": "system", "content": "[Note: Older conversation context has been pruned for performance]"})
        model_messages.extend(history[-10:])
    else:
        model_messages.extend(history)

    model_messages.append(user_message)

    # Store all messages to be saved (user + assistant messages)
    messages_to_save = [user_message]

    total_prompt_tokens = 0
    total_response_tokens = 0
    total_tool_calls = 0

    # Tool calling loop - continue until we get a final response
    max_iterations = 15  # Allow more iterations for complex multi-step tasks
    iteration = 0
    final_text = ""

    start = time.perf_counter()
    ok = True

    from core.cache import check_cache, store_in_cache

    # Check if the exact prompt has been answered before (static knowledge only)
    cached = check_cache(payload.prompt)
    if cached:
        final_text = cached
        iteration = max_iterations  # skip loop

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

            import concurrent.futures

            def execute_single_tool(tc):
                tool_start = time.perf_counter()
                args = dict(tc.arguments or {})
                if tc.name in {"run_python_script", "run_shell_commands", "launch"}:
                    args.setdefault("chat_id", chat_id)
                res = execute_tool(tc.name, args)
                tool_latency = (time.perf_counter() - tool_start) * 1000

                # Log tool call
                tool_call_logger.log(
                    provider=provider_name,
                    model=config.model,
                    tool_name=tc.name,
                    arguments=tc.arguments,
                    result=res,
                    success=res.get("success", False),
                    latency_ms=tool_latency,
                    chat_id=chat_id,
                )
                return res

            with concurrent.futures.ThreadPoolExecutor() as executor:
                futures = [executor.submit(execute_single_tool, tc) for tc in llm_response.tool_calls]
                for future in futures:
                    tool_results.append(future.result())

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
        if iteration >= max_iterations:
            final_text = f"I reached the maximum number of tool iterations ({max_iterations}). The task may be too complex or requires manual intervention."
        else:
            final_text = "I attempted to use tools but could not generate a final response."

    # Save to cache if it's a general knowledge question (used NO tools = static answer)
    if ok and total_tool_calls == 0 and final_text:
        store_in_cache(payload.prompt, final_text)

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


@app.get("/api/tasks")
def api_list_tasks(
    limit: int = Query(100, ge=1, le=500),
    action: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    chat_id: Optional[str] = Query(None),
) -> Dict[str, object]:
    tasks = _REGISTRY.list_all()
    if action:
        tasks = [rec for rec in tasks if rec.get("action") == action]
    if status:
        tasks = [rec for rec in tasks if str(rec.get("status", "")).lower() == status.lower()]
    if chat_id:
        tasks = [rec for rec in tasks if rec.get("metadata", {}).get("chat_id") == chat_id]
    tasks.sort(key=lambda rec: rec.get("created_at", 0), reverse=True)
    tasks = tasks[:limit] if limit > 0 else tasks
    return {"tasks": tasks, "count": len(tasks)}


# Settings endpoints
SETTINGS_FILE = DATA_DIR / "settings.json"


def load_settings() -> Dict[str, object]:
    """Load settings from settings.json."""
    # Load default SMTP credentials from environment variables (sender credentials)
    # Users must provide their own email_address (recipient)
    defaults = {
        "usage_alerts_enabled": False,
        "alert_thresholds": {
            "cpu_percent": 85.0,
            "memory_percent": 85.0,
            "disk_percent": 90.0,
        },
        "check_interval_seconds": 30,
        "email_alerts_enabled": False,
        "email_address": "",  # User must provide recipient email
        "smtp_server": os.getenv("DEFAULT_SMTP_SERVER", "smtp.gmail.com"),
        "smtp_port": int(os.getenv("DEFAULT_SMTP_PORT", "587")),
        "smtp_username": os.getenv("DEFAULT_SMTP_USERNAME", ""),
        "smtp_password": os.getenv("DEFAULT_SMTP_PASSWORD", ""),
        "smtp_use_tls": os.getenv("DEFAULT_SMTP_USE_TLS", "true").lower() == "true",
    }
    if not SETTINGS_FILE.exists():
        return defaults
    try:
        with open(SETTINGS_FILE, "r") as f:
            loaded = json.load(f)
            # Merge with defaults to ensure new fields exist
            for key, value in defaults.items():
                if key not in loaded:
                    loaded[key] = value
            return loaded
    except Exception:
        return defaults


def save_settings(settings: Dict[str, object]) -> None:
    """Save settings to settings.json."""
    ensure_data_dir(DATA_DIR)
    with open(SETTINGS_FILE, "w") as f:
        json.dump(settings, f, indent=2)


@app.get("/api/settings")
def api_get_settings() -> Dict[str, object]:
    """Get current settings."""
    return load_settings()


class SettingsUpdateRequest(BaseModel):
    usage_alerts_enabled: Optional[bool] = None
    alert_thresholds: Optional[Dict[str, float]] = None
    check_interval_seconds: Optional[int] = None
    email_alerts_enabled: Optional[bool] = None
    email_address: Optional[str] = None
    smtp_server: Optional[str] = None
    smtp_port: Optional[int] = None
    smtp_username: Optional[str] = None
    smtp_password: Optional[str] = None
    smtp_use_tls: Optional[bool] = None


@app.post("/api/settings")
def api_update_settings(payload: SettingsUpdateRequest) -> Dict[str, object]:
    """Update settings and manage the usage monitor process."""
    settings = load_settings()

    # Track if usage_alerts_enabled changed
    old_enabled = settings.get("usage_alerts_enabled", False)

    # Update settings
    if payload.usage_alerts_enabled is not None:
        settings["usage_alerts_enabled"] = payload.usage_alerts_enabled
    if payload.alert_thresholds is not None:
        settings["alert_thresholds"] = payload.alert_thresholds
    if payload.check_interval_seconds is not None:
        settings["check_interval_seconds"] = payload.check_interval_seconds
    if payload.email_alerts_enabled is not None:
        settings["email_alerts_enabled"] = payload.email_alerts_enabled
    if payload.email_address is not None:
        settings["email_address"] = payload.email_address
    if payload.smtp_server is not None:
        settings["smtp_server"] = payload.smtp_server
    if payload.smtp_port is not None:
        settings["smtp_port"] = payload.smtp_port
    if payload.smtp_username is not None:
        settings["smtp_username"] = payload.smtp_username
    if payload.smtp_password is not None:
        settings["smtp_password"] = payload.smtp_password
    if payload.smtp_use_tls is not None:
        settings["smtp_use_tls"] = payload.smtp_use_tls

    # Validate: If email alerts enabled, email address must be provided
    if settings.get("email_alerts_enabled", False):
        email_address = settings.get("email_address", "").strip()
        if not email_address:
            raise HTTPException(
                status_code=400,
                detail="Email address is required when email alerts are enabled. Please provide your email address or disable email alerts."
            )

    # Save settings
    save_settings(settings)

    # Manage the usage monitor process
    new_enabled = settings.get("usage_alerts_enabled", False)

    if old_enabled != new_enabled:
        if new_enabled:
            # Start the monitor
            start_usage_monitor()
        else:
            # Stop the monitor
            stop_usage_monitor()

    return settings


def start_usage_monitor():
    """Start the usage monitor process in the background."""
    import sys
    from pathlib import Path

    monitor_script = ROOT_DIR / "tools" / "usage_monitor.py"

    # Check if already running
    from tools.usage_monitor import is_monitor_running
    if is_monitor_running():
        print("Usage monitor is already running")
        return

    # Start the monitor process
    try:
        if sys.platform == "win32":
            # Windows: use pythonw to avoid console window
            python_exe = sys.executable.replace("python.exe", "pythonw.exe")
            if not Path(python_exe).exists():
                python_exe = sys.executable

            subprocess.Popen(
                [python_exe, str(monitor_script), "start"],
                creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, 'CREATE_NO_WINDOW') else 0,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        else:
            # Unix-like: use nohup
            subprocess.Popen(
                [sys.executable, str(monitor_script), "start"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                preexec_fn=os.setpgrp if hasattr(os, 'setpgrp') else None,
            )

        print("Usage monitor started")
    except Exception as e:
        print(f"Error starting usage monitor: {e}")


def stop_usage_monitor():
    """Stop the usage monitor process."""
    try:
        from tools.usage_monitor import stop_monitor
        stop_monitor()
        print("Usage monitor stopped")
    except Exception as e:
        print(f"Error stopping usage monitor: {e}")


@app.get("/api/settings/monitor-status")
def api_monitor_status() -> Dict[str, object]:
    """Get the status of the usage monitor process."""
    try:
        from tools.usage_monitor import is_monitor_running
        pid = is_monitor_running()
        return {
            "running": pid is not None,
            "pid": pid,
        }
    except Exception as e:
        return {
            "running": False,
            "error": str(e),
        }


@app.get("/api/settings/auto-start/status")
def api_auto_start_status() -> Dict[str, object]:
    """Check if auto-start is installed."""
    try:
        # Import the status function from manage_startup
        manage_startup_path = ROOT_DIR / "scripts" / "manage_startup.py"

        # Use subprocess to run the status command
        result = subprocess.run(
            [sys.executable, str(manage_startup_path), "status"],
            capture_output=True,
            text=True,
            timeout=10
        )

        return {
            "installed": result.returncode == 0,
            "message": result.stdout.strip()
        }
    except subprocess.TimeoutExpired:
        return {
            "installed": False,
            "error": "Status check timed out"
        }
    except Exception as e:
        return {
            "installed": False,
            "error": str(e)
        }


@app.post("/api/settings/auto-start/install")
def api_auto_start_install() -> Dict[str, object]:
    """Install auto-start configuration."""
    try:
        manage_startup_path = ROOT_DIR / "scripts" / "manage_startup.py"

        # Run the install command in background thread to not block
        def install_async():
            subprocess.run(
                [sys.executable, str(manage_startup_path), "install"],
                capture_output=True,
                text=True,
                timeout=30
            )

        thread = threading.Thread(target=install_async, daemon=True)
        thread.start()
        thread.join(timeout=30)

        # Check status after install
        result = subprocess.run(
            [sys.executable, str(manage_startup_path), "status"],
            capture_output=True,
            text=True,
            timeout=10
        )

        return {
            "success": result.returncode == 0,
            "message": "Auto-start installed successfully" if result.returncode == 0 else "Failed to install auto-start"
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e)
        }


@app.post("/api/settings/auto-start/uninstall")
def api_auto_start_uninstall() -> Dict[str, object]:
    """Uninstall auto-start configuration."""
    try:
        manage_startup_path = ROOT_DIR / "scripts" / "manage_startup.py"

        result = subprocess.run(
            [sys.executable, str(manage_startup_path), "uninstall"],
            capture_output=True,
            text=True,
            timeout=30
        )

        return {
            "success": result.returncode == 0,
            "message": "Auto-start removed successfully" if result.returncode == 0 else "Failed to remove auto-start"
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e)
        }


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
def test_tools(
    actually_launch: bool = typer.Option(False, "--launch", help="If set, attempt a real launch of a found app.")
) -> None:
    """Test core MCP tool calls and print their outputs (cross-platform)."""
    typer.echo("=== Testing EdgePilot Tool Calls ===\n")

    # Test 1: gather_metrics
    typer.echo("1. Testing gather_metrics tool:")
    result = execute_tool("gather_metrics", {"top_n": 5})
    typer.echo(f"   Success: {result.get('success')}")
    if result.get("success"):
        metrics = result.get("result", {})
        typer.echo(f"   CPU: {metrics.get('cpu', {}).get('percent')}%")
        typer.echo(f"   Memory Used: {metrics.get('memory', {}).get('percent')}%")
        typer.echo(f"   Top Processes: {len(metrics.get('top_processes', []))}")
    else:
        typer.echo(f"   Error: {result.get('error')}")
    typer.echo()

    # Test 2: search (platform-friendly query)
    query = "term"
    typer.echo(f"2. Testing search tool (searching for '{query}'):")
    result = execute_tool("search", {"app_name": query})
    typer.echo(f"   Success: {result.get('success')}")
    if result.get("success"):
        payload = result.get("result") or {}
        matches = payload.get("matches") or payload.get("apps") or payload
        if isinstance(matches, list):
            typer.echo(f"   Found {len(matches)} matches")
            for i, name in enumerate(matches[:5], 1):
                typer.echo(f"   {i}. {name}")
        else:
            typer.echo("   (No list returned)")
    else:
        typer.echo(f"   Error: {result.get('error')}")
    typer.echo()

    # Test 3: list_apps
    typer.echo("3. Testing list_apps tool (filter 'term'):")
    result = execute_tool("list_apps", {"filter_term": "term"})
    typer.echo(f"   Success: {result.get('success')}")
    if result.get("success"):
        payload = result.get("result") or {}
        apps = payload.get("apps") or payload.get("matches") or payload
        if isinstance(apps, list):
            typer.echo(f"   Returned {len(apps)} app(s). Sample:")
            for i, name in enumerate(apps[:5], 1):
                typer.echo(f"   {i}. {name}")
        else:
            typer.echo("   (No list returned)")
    else:
        typer.echo(f"   Error: {result.get('error')}")
    typer.echo()

    # Test 4: optional launch
    candidates_by_platform = {
        "win": ["notepad", "wordpad", "paint", "windows terminal", "calc"],
        "darwin": ["Safari", "TextEdit", "Notes", "Terminal", "Calculator"],
        "linux": ["Calculator", "Firefox", "Files", "Terminal", "Chromium"],
    }
    plat = "win" if os.name == "nt" else "darwin" if sys.platform == "darwin" else "linux"
    candidates = candidates_by_platform.get(plat, [])
    chosen: Optional[str] = None
    for candidate in candidates:
        res = execute_tool("search", {"app_name": candidate})
        if res.get("success"):
            payload = res.get("result") or {}
            matches = payload.get("apps") or payload.get("matches") or payload
            if isinstance(matches, list) and matches:
                chosen = matches[0]
                break
    typer.echo("4. Testing launch tool:")
    if chosen and actually_launch:
        typer.echo(f"   Attempting to launch '{chosen}'...")
        res = execute_tool("launch", {"app_name": chosen, "delay_seconds": 0})
        typer.echo(f"   Success: {res.get('success')}")
        if not res.get("success"):
            typer.echo(f"   Error: {res.get('error')}")
    else:
        note = "(set --launch to actually launch)" if chosen else "(no candidate found; skipping)"
        typer.echo(f"   Skipping real launch {note}")
    typer.echo()

    # Test 5: end_task (safe failure expected)
    typer.echo("5. Testing end_task tool (safe test - non-existent process):")
    result = execute_tool(
        "end_task",
        {
            "identifier": "fake_process_that_doesnt_exist_12345",
            "force": False,
        },
    )
    typer.echo(f"   Success: {result.get('success')}")
    if not result.get("success"):
        typer.echo(f"   Expected Error: {result.get('error')}")
    typer.echo()

    typer.echo("=== Tool Testing Complete ===")


if __name__ == "__main__":
    if len(sys.argv) > 1:
        cli()
    else:
        launch_desktop_app()
def ensure_data_dir(path: Path) -> None:
    """Create directory if it does not exist."""
    path.mkdir(parents=True, exist_ok=True)
