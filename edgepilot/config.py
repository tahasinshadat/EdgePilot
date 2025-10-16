# edgepilot/config.py
"""Configuration management for EdgePilot"""

import os
import shutil
import subprocess
from pathlib import Path
from typing import Optional, Literal
import yaml
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings


class LLMConfig(BaseModel):
    """LLM provider configuration"""
    provider: Literal["ollama", "anthropic", "gemini"] = "ollama"
    model: str = "llama3.2:3b"
    temperature: float = 0.7
    max_tokens: int = 4096
    num_ctx: Optional[int] = 8192  # For Ollama
    api_key: Optional[str] = None
    base_url: Optional[str] = "http://localhost:11434"  # For Ollama


class MetricsConfig(BaseModel):
    """Metrics collection configuration"""
    sample_interval: int = 5  # seconds during runs
    idle_interval: int = 60  # seconds when idle
    stream_interval: int = 2  # default streaming interval
    retain_days: int = 30  # days to keep metrics
    process_top_n: int = 15  # top N processes to track
    enable_gpu: bool = True
    enable_power: bool = True


class SchedulerConfig(BaseModel):
    """Task scheduler configuration"""
    max_parallel: int = 2
    default_policy: str = "balanced_defaults"
    queue_check_interval: int = 5  # seconds
    task_log_size_mb: int = 10  # per task log size limit
    enable_auto_start: bool = True


class StorageConfig(BaseModel):
    """Storage paths configuration"""
    base_dir: Path = Path.home() / ".edgepilot"
    db_name: str = "edgepilot.db"
    log_dir: str = "logs"
    data_dir: str = "data"

    @property
    def db_path(self) -> Path:
        return self.base_dir / self.db_name

    @property
    def log_path(self) -> Path:
        return self.base_dir / self.log_dir

    @property
    def data_path(self) -> Path:
        return self.base_dir / self.data_dir


class Config(BaseSettings):
    """Main EdgePilot configuration"""
    llm: LLMConfig = Field(default_factory=LLMConfig)
    metrics: MetricsConfig = Field(default_factory=MetricsConfig)
    scheduler: SchedulerConfig = Field(default_factory=SchedulerConfig)
    storage: StorageConfig = Field(default_factory=StorageConfig)

    # Runtime settings
    debug: bool = False
    host: str = "127.0.0.1"
    api_port: int = 8000
    ui_port: int = 8501

    # Installation flags
    is_configured: bool = False
    cluster_mode: bool = False
    has_sudo: bool = False

    class Config:
        env_file = ".env"
        env_prefix = "EDGEPILOT_"
        case_sensitive = False


_config: Optional[Config] = None


def get_config() -> Config:
    """Get or create the global config instance"""
    global _config
    if _config is None:
        _config = load_config()
    return _config


def load_config(path: Optional[Path] = None) -> Config:
    """Load configuration from YAML file"""
    if path is None:
        path = Path.home() / ".edgepilot" / "config.yaml"

    if not path.exists():
        # Return default config if file doesn't exist
        cfg = Config()
        # Ensure base directories exist on first import
        cfg.storage.base_dir.mkdir(parents=True, exist_ok=True)
        cfg.storage.log_path.mkdir(parents=True, exist_ok=True)
        cfg.storage.data_path.mkdir(parents=True, exist_ok=True)
        return cfg

    with open(path, "r") as f:
        data = yaml.safe_load(f) or {}

    # Parse nested configs
    config_data = {}
    if "llm" in data:
        config_data["llm"] = LLMConfig(**data["llm"])
    if "metrics" in data:
        config_data["metrics"] = MetricsConfig(**data["metrics"])
    if "scheduler" in data:
        config_data["scheduler"] = SchedulerConfig(**data["scheduler"])
    if "storage" in data:
        s = data["storage"]
        # restore Path
        if "base_dir" in s and not isinstance(s["base_dir"], Path):
            s["base_dir"] = Path(s["base_dir"])
        config_data["storage"] = StorageConfig(**s)

    # Add top-level fields
    for key in ["debug", "host", "api_port", "ui_port", "is_configured", "cluster_mode", "has_sudo"]:
        if key in data:
            config_data[key] = data[key]

    cfg = Config(**config_data)
    cfg.storage.base_dir.mkdir(parents=True, exist_ok=True)
    cfg.storage.log_path.mkdir(parents=True, exist_ok=True)
    cfg.storage.data_path.mkdir(parents=True, exist_ok=True)
    return cfg


def save_config(config: Config, path: Optional[Path] = None):
    """Save configuration to YAML file"""
    if path is None:
        path = Path.home() / ".edgepilot" / "config.yaml"

    # Ensure directory exists
    path.parent.mkdir(parents=True, exist_ok=True)

    # Convert to dict for YAML serialization
    data = {
        "llm": config.llm.model_dump(),
        "metrics": config.metrics.model_dump(),
        "scheduler": config.scheduler.model_dump(),
        "storage": {
            "base_dir": str(config.storage.base_dir),
            "db_name": config.storage.db_name,
            "log_dir": config.storage.log_dir,
            "data_dir": config.storage.data_dir,
        },
        "debug": config.debug,
        "host": config.host,
        "api_port": config.api_port,
        "ui_port": config.ui_port,
        "is_configured": config.is_configured,
        "cluster_mode": config.cluster_mode,
        "has_sudo": config.has_sudo,
    }

    with open(path, "w") as f:
        yaml.dump(data, f, default_flow_style=False, sort_keys=False)


def run_wizard():
    """Interactive setup wizard for first-time configuration"""
    from rich.console import Console
    from rich.prompt import Prompt, Confirm
    from rich.panel import Panel
    from rich.table import Table

    console = Console()

    console.print("\n[bold blue]🚀 Welcome to EdgePilot Setup Wizard![/bold blue]\n")
    console.print("This wizard will help you configure EdgePilot for first use.\n")

    cfg = load_config()

    # Step 1: LLM Provider Selection
    console.print(Panel("[bold]Step 1: LLM Provider Selection[/bold]\nChoose which LLM to use locally. "
                        "Ollama is recommended and requires the local Ollama daemon.",
                        title="LLM"))
    provider = Prompt.ask("Provider", choices=["ollama", "anthropic", "gemini"], default=cfg.llm.provider)

    model_default = cfg.llm.model if provider == cfg.llm.provider else (
        "llama3.2:3b" if provider == "ollama" else ("claude-3-5-sonnet-20240620" if provider == "anthropic" else "gemini-1.5-flash")
    )
    model = Prompt.ask("Model", default=model_default)

    api_key = None
    base_url = cfg.llm.base_url
    if provider == "ollama":
        # Check for binary
        has_ollama = shutil.which("ollama") is not None
        if not has_ollama:
            console.print(
                "[yellow]Ollama binary not detected. Install from https://ollama.ai and then run:[/yellow]\n"
                "  [bold]ollama pull llama3.2:3b[/bold]\n"
                "You can complete setup now and install later."
            )
        base_url = Prompt.ask("Ollama base URL", default=base_url or "http://localhost:11434")
    else:
        api_key = Prompt.ask(f"{provider} API key (enter to skip)", default=cfg.llm.api_key or "", show_default=False)

    temperature = float(Prompt.ask("Temperature", default=str(cfg.llm.temperature)))
    max_tokens = int(Prompt.ask("Max tokens", default=str(cfg.llm.max_tokens)))

    # Step 2: Mode & Privileges
    console.print(Panel("[bold]Step 2: Mode & Privileges[/bold]\nFor v0 we run on a single host. "
                        "If you expect to run powermetrics on macOS you may grant sudo later when prompted.",
                        title="Mode"))
    cluster_mode = Confirm.ask("Cluster mode (experimental, single host recommended)?", default=False)
    has_sudo = Confirm.ask("Can EdgePilot use elevated privileges for power metrics if needed?", default=False)

    # Step 3: Ports & Paths
    console.print(Panel("[bold]Step 3: Ports & Paths[/bold]", title="Ports"))
    host = Prompt.ask("API Host", default=cfg.host)
    api_port = int(Prompt.ask("API Port", default=str(cfg.api_port)))
    ui_port = int(Prompt.ask("UI Port", default=str(cfg.ui_port)))

    base_dir = Prompt.ask("Data directory", default=str(cfg.storage.base_dir))
    base_dir = Path(base_dir)

    # Set config
    cfg.llm.provider = provider
    cfg.llm.model = model
    cfg.llm.temperature = temperature
    cfg.llm.max_tokens = max_tokens
    cfg.llm.api_key = api_key or None
    cfg.llm.base_url = base_url

    cfg.cluster_mode = cluster_mode
    cfg.has_sudo = has_sudo
    cfg.host = host
    cfg.api_port = api_port
    cfg.ui_port = ui_port

    cfg.storage.base_dir = base_dir
    cfg.is_configured = True

    save_config(cfg)

    cfg.storage.base_dir.mkdir(parents=True, exist_ok=True)
    cfg.storage.log_path.mkdir(parents=True, exist_ok=True)
    cfg.storage.data_path.mkdir(parents=True, exist_ok=True)

    table = Table(title="Configuration Summary")
    table.add_column("Key")
    table.add_column("Value")
    table.add_row("Provider", cfg.llm.provider)
    table.add_row("Model", cfg.llm.model)
    table.add_row("API Host", cfg.host)
    table.add_row("API Port", str(cfg.api_port))
    table.add_row("UI Port", str(cfg.ui_port))
    table.add_row("Base Dir", str(cfg.storage.base_dir))
    console.print(table)

    console.print("\n[bold green]Setup complete![/bold green]\n"
                  "Next steps:\n"
                  "  • Start API: [bold]edgepilot api[/bold]\n"
                  "  • Launch UI: [bold]edgepilot ui[/bold]\n"
                  "  • Start MCP server: [bold]edgepilot mcp[/bold]\n")
