"""Tool schemas for MCP function calling integration."""

from __future__ import annotations

from typing import Any, Dict, List

# Tool schemas following the function calling format for LLMs
TOOL_SCHEMAS: List[Dict[str, Any]] = [
    {
        "name": "gather_metrics",
        "description": "Collect a current snapshot of system metrics (CPU, memory, disk, network, battery, processes). Use ONLY for 'right now' status; do not use for multi-hour summaries.",
        "parameters": {
            "type": "object",
            "properties": {
                "top_n": {
                    "type": "integer",
                    "description": "Number of top processes by CPU usage to include. Defaults to 10. Ignored if all_processes is True.",
                    "default": 10,
                },
                "all_processes": {
                    "type": "boolean",
                    "description": "If True, include all running processes instead of just top N. Use this when you need complete process information.",
                    "default": False,
                },
            },
        },
    },
    {
        "name": "report_edge_status",
        "description": "Summarize host utilization over a past window using Prometheus. Returns no_data when Prometheus history is unavailable.",
        "parameters": {
            "type": "object",
            "properties": {
                "window": {
                    "type": "string",
                    "description": "Prometheus time window to evaluate (e.g., '1h', '6h'). Defaults to 1h.",
                    "default": "1h",
                },
                "top_k": {
                    "type": "integer",
                    "description": "Number of top processes or rank entries to include when applicable.",
                    "default": 5,
                },
            },
        },
    },
    {
        "name": "evaluate_capacity",
        "description": "Assess whether the host (or a Prometheus instance) currently has enough headroom for a workload.",
        "parameters": {
            "type": "object",
            "properties": {
                "requirements": {
                    "type": "object",
                    "description": "Workload requirements (e.g., {'cpu_pct': 40, 'mem_bytes': 2147483648}).",
                },
                "duration": {
                    "type": "string",
                    "description": "Intended runtime duration for the workload (Prometheus reference). Defaults to '45m'.",
                    "default": "45m",
                },
                "host": {
                    "type": "string",
                    "description": "Optional Prometheus instance label to check. Leave empty to evaluate all instances.",
                },
            },
            "required": ["requirements"],
        },
    },
    {
        "name": "suggest_capacity_window",
        "description": "Suggest upcoming windows when resource headroom is likely sufficient for a workload.",
        "parameters": {
            "type": "object",
            "properties": {
                "requirements": {
                    "type": "object",
                    "description": "Workload requirements (e.g., {'cpu_pct': 30, 'mem_bytes': 1073741824}).",
                },
                "duration": {
                    "type": "string",
                    "description": "Desired runtime duration (e.g., '1h'). Defaults to '45m'.",
                    "default": "45m",
                },
                "horizon_hours": {
                    "type": "integer",
                    "description": "How far ahead to look when suggesting windows. Defaults to 24 hours.",
                    "default": 24,
                },
                "host": {
                    "type": "string",
                    "description": "Optional Prometheus instance label to focus on.",
                },
            },
            "required": ["requirements"],
        },
    },
    {
        "name": "launch",
        "description": "Launch an application by name, immediately or after a delay. Cross-platform: on Windows we search Start Menu shortcuts and Microsoft Store apps; on macOS we resolve .app bundles and fall back to 'open -a <name>'; on Linux we scan .desktop files in standard locations (including Flatpak/Snap) and fall back to $PATH. Use simple names like 'chrome', 'safari', 'calculator', 'notepad'. If you need to check if an app exists first, use the 'search' tool.",
        "parameters": {
            "type": "object",
            "properties": {
                "app_name": {
                    "type": "string",
                    "description": "Application name to launch (e.g., 'chrome', 'safari', 'calculator', 'discord'). The system searches Windows Start Menu/Store, macOS .app bundles, and Linux .desktop entries; if not found, it may try the name on $PATH.",
                },
                "delay_seconds": {
                    "type": "number",
                    "description": "Number of seconds to wait before launching. Default is 0 (launch immediately). Examples: 30 for '30 seconds', 120 for '2 minutes'.",
                    "default": 0,
                },
                "chat_id": {
                    "type": "string",
                    "description": "Optional chat session identifier so the launch can be surfaced on the jobs view.",
                },
            },
            "required": ["app_name"],
        },
    },
    {
        "name": "search",
        "description": "Search for installed applications by name. Cross-platform: searches Windows Start Menu/Microsoft Store, macOS .app bundles, and Linux .desktop entries (including Flatpak/Snap). Returns friendly application names that you can pass to 'launch'.",
        "parameters": {
            "type": "object",
            "properties": {
                "app_name": {
                    "type": "string",
                    "description": "Application name to search for (e.g., 'term', 'chrome', 'office'). Partial matches are supported.",
                },
            },
            "required": ["app_name"],
        },
    },
    {
        "name": "list_apps",
        "description": "List all installed applications, optionally filtered by a search term. Cross-platform: enumerates Windows Start Menu, macOS .app bundles, and Linux .desktop entries. Returns a sorted list of friendly application names.",
        "parameters": {
            "type": "object",
            "properties": {
                "filter_term": {
                    "type": "string",
                    "description": "Optional search term to filter results (e.g., 'term', 'microsoft'). Leave empty to get all apps.",
                    "default": "",
                },
            },
        },
    },
    {
        "name": "run_shell_commands",
        "description": "Execute a shell command on the local machine. This tool records the job so the user can view it in the Jobs tab; do not attempt to fetch or summarize the output afterward.",
        "parameters": {
            "type": "object",
            "properties": {
                "command": {
                    "type": "string",
                    "description": "Command to execute (e.g., 'ls -la', 'df -h')."
                },
                "cwd": {
                    "type": "string",
                    "description": "Optional working directory for the command."
                },
                "delay_seconds": {
                    "type": "number",
                    "description": "Number of seconds to wait before running the command. Example: 30 for '30 seconds'.",
                    "default": 0,
                },
                "seconds": {
                    "type": "number",
                    "description": "Alias for delay_seconds. Use when a model extracts 'seconds' from the request.",
                },
                "delay": {
                    "type": "string",
                    "description": "Natural language delay value (e.g., 'in 45 seconds', 'after 2 minutes').",
                },
                "chat_id": {
                    "type": "string",
                    "description": "Optional chat session identifier so the job can be associated with a conversation thread.",
                },
            },
            "required": ["command"]
        }
    },
    {
        "name": "run_python_script",
        "description": "Execute a Python script using the scheduler runtime. Provide the script path and optional arguments. The user will view results in the Jobs tab; do not follow up with extra commands to read stdout/stderr.",
        "parameters": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Absolute path to the Python script."
                },
                "args": {
                    "type": "array",
                    "items": {
                        "type": "string"
                    },
                    "description": "Optional list of command-line arguments for the script.",
                    "default": []
                },
                "cwd": {
                    "type": "string",
                    "description": "Optional working directory."
                },
                "delay_seconds": {
                    "type": "number",
                    "description": "Number of seconds to wait before running the script. Example: 30 for '30 seconds'.",
                    "default": 0,
                },
                "seconds": {
                    "type": "number",
                    "description": "Alias for delay_seconds. Use when a model extracts 'seconds' from input.",
                },
                "delay": {
                    "type": "string",
                    "description": "Natural language delay value (e.g., 'after 2 minutes').",
                },
                "chat_id": {
                    "type": "string",
                    "description": "Optional chat session identifier so the job can be associated with a conversation thread.",
                },
            },
            "required": ["path"]
        }
    },
    {
        "name": "end_task",
        "description": "Terminate running processes matching the identifier. The identifier can be part of the process name, executable path, or command line. Use this to stop applications, kill hung processes, or clean up resources.",
        "parameters": {
            "type": "object",
            "properties": {
                "identifier": {
                    "type": "string",
                    "description": "Process identifier to match. Can be part of the process name (e.g., 'notepad'), executable path (e.g., 'C:\\Program Files\\App\\'), or command line arguments. Matching is case-insensitive.",
                },
                "force": {
                    "type": "boolean",
                    "description": "If True, forcefully kill processes (SIGKILL). If False, gracefully terminate (SIGTERM). Default is False.",
                    "default": False,
                },
            },
            "required": ["identifier"],
        },
    },
    {
        "name": "scale_workload",
        "description": "Scales a Kubernetes deployment up or down. Requires human approval.",
        "parameters": {
            "type": "object",
            "properties": {
                "namespace": {
                    "type": "string",
                    "description": "The Kubernetes namespace.",
                    "default": "default"
                },
                "deployment_name": {
                    "type": "string",
                    "description": "The name of the deployment to scale."
                },
                "replicas": {
                    "type": "number",
                    "description": "The target number of replicas."
                }
            },
            "required": ["deployment_name", "replicas"]
        }
    },
    {
        "name": "restart_workload",
        "description": "Performs a rolling restart of a Kubernetes deployment. Requires human approval.",
        "parameters": {
            "type": "object",
            "properties": {
                "namespace": {
                    "type": "string",
                    "description": "The Kubernetes namespace.",
                    "default": "default"
                },
                "deployment_name": {
                    "type": "string",
                    "description": "The name of the deployment to restart."
                }
            },
            "required": ["deployment_name"]
        }
    },
    {
        "name": "cordon_node",
        "description": "Marks a Kubernetes node as unschedulable. Requires human approval.",
        "parameters": {
            "type": "object",
            "properties": {
                "node_name": {
                    "type": "string",
                    "description": "The name of the node to cordon."
                }
            },
            "required": ["node_name"]
        }
    },
    {
        "name": "recommend_rightsizing",
        "description": (
            "Compare what each workload requests against what it actually "
            "consumes, and recommend corrected CPU, memory and GPU sizing. "
            "Works over Slurm job accounting, an exported accounting CSV, or "
            "Kubernetes. Flags over-requested, under-requested, OOM-killed, "
            "idle-GPU and no-requests-set workloads, and reports total "
            "reclaimable resources. Read-only."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "source": {
                    "type": "string",
                    "description": (
                        "Which scheduler to read: 'slurm', 'kubernetes', "
                        "'csv' for an exported accounting file, or 'auto' to "
                        "use whichever is reachable."
                    ),
                    "default": "auto"
                },
                "namespace": {
                    "type": "string",
                    "description": "Kubernetes namespace to restrict analysis to."
                },
                "csv_path": {
                    "type": "string",
                    "description": (
                        "Path to a sacct-shaped CSV export. Required when "
                        "source is 'csv'."
                    )
                },
                "node_csv_path": {
                    "type": "string",
                    "description": (
                        "Optional path to a node-specification CSV, enabling "
                        "node-class fit analysis."
                    )
                },
                "jobstats_path": {
                    "type": "string",
                    "description": (
                        "Optional path to a Jobstats time-series JSON export, "
                        "which yields more accurate usage than accounting "
                        "summaries alone."
                    )
                },
                "days_back": {
                    "type": "integer",
                    "description": "How many days of Slurm accounting to analyze.",
                    "default": 7
                },
                "cpu_target_utilization": {
                    "type": "number",
                    "description": "Target CPU utilization ratio. Defaults to 0.7.",
                    "default": 0.7
                },
                "memory_target_utilization": {
                    "type": "number",
                    "description": "Target memory utilization ratio. Defaults to 0.8.",
                    "default": 0.8
                },
                "gpu_target_utilization": {
                    "type": "number",
                    "description": "Target GPU utilization ratio. Defaults to 0.7.",
                    "default": 0.7
                }
            },
            "required": []
        }
    },
    {
        "name": "analyze_bottlenecks",
        "description": (
            "Identify which resource actually limits each workload - CPU, "
            "memory, GPU, or none - and roll the findings up by partition. "
            "Answers 'where are the bottlenecks in this cluster', as distinct "
            "from recommend_rightsizing's 'is this workload the right size'. "
            "Read-only."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "source": {
                    "type": "string",
                    "description": (
                        "Which scheduler to read: 'slurm', 'kubernetes', "
                        "'csv', or 'auto'."
                    ),
                    "default": "auto"
                },
                "namespace": {
                    "type": "string",
                    "description": "Kubernetes namespace to restrict analysis to."
                },
                "csv_path": {
                    "type": "string",
                    "description": "Path to a sacct-shaped CSV export."
                },
                "node_csv_path": {
                    "type": "string",
                    "description": "Optional path to a node-specification CSV."
                },
                "jobstats_path": {
                    "type": "string",
                    "description": (
                        "Optional path to a Jobstats time-series JSON export."
                    )
                },
                "days_back": {
                    "type": "integer",
                    "description": "How many days of Slurm accounting to analyze.",
                    "default": 7
                }
            },
            "required": []
        }
    },
    {
        "name": "analyze_workload_families",
        "description": (
            "Group jobs into families of similar workloads using a local "
            "embedding model, then flag the runs that deviate from their own "
            "family - e.g. 'this run used a twentieth of the memory of the "
            "other 37 jobs like it'. Peer-relative counterpart to "
            "recommend_rightsizing: judges a job against its peers rather "
            "than a fixed utilization target, so it needs no arbitrary "
            "threshold. Falls back to grouping by job name when the local "
            "model is unavailable, and says so in the 'degraded' field. "
            "Read-only."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "source": {
                    "type": "string",
                    "description": (
                        "Which scheduler to read: 'slurm', 'kubernetes', "
                        "'csv', or 'auto'."
                    ),
                    "default": "auto"
                },
                "namespace": {
                    "type": "string",
                    "description": "Kubernetes namespace to restrict analysis to."
                },
                "csv_path": {
                    "type": "string",
                    "description": "Path to a sacct-shaped CSV export."
                },
                "node_csv_path": {
                    "type": "string",
                    "description": "Optional path to a node-specification CSV."
                },
                "jobstats_path": {
                    "type": "string",
                    "description": (
                        "Optional path to a Jobstats time-series JSON export."
                    )
                },
                "days_back": {
                    "type": "integer",
                    "description": "How many days of Slurm accounting to analyze.",
                    "default": 7
                },
                "similarity_threshold": {
                    "type": "number",
                    "description": (
                        "How alike two jobs must be to share a family, "
                        "0 to 1. Higher means tighter families."
                    ),
                    "default": 0.75
                },
                "anomaly_threshold": {
                    "type": "number",
                    "description": (
                        "Robust outlier score above which a run is flagged. "
                        "Defaults to 3.5."
                    ),
                    "default": 3.5
                },
                "min_family_size": {
                    "type": "integer",
                    "description": (
                        "Smallest family that can produce outliers; below "
                        "this a median is not meaningful."
                    ),
                    "default": 4
                }
            },
            "required": []
        }
    },
    {
        "name": "inspect_cluster_resources",
        "description": (
            "Read the Kubernetes cluster's node and cluster-wide resource "
            "picture: allocatable, requested and available CPU/memory per "
            "node, pod slots, node readiness and taints. Read-only."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "node": {
                    "type": "string",
                    "description": (
                        "Optional node name. Omit for the whole cluster."
                    )
                }
            },
            "required": []
        }
    },
    {
        "name": "apply_resource_requests",
        "description": (
            "Update the CPU/memory requests and limits of a container in a "
            "Kubernetes deployment. Use the quantity strings returned by "
            "recommend_rightsizing. Requires human approval."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "namespace": {
                    "type": "string",
                    "description": "The Kubernetes namespace.",
                    "default": "default"
                },
                "deployment_name": {
                    "type": "string",
                    "description": "The deployment to update."
                },
                "container_name": {
                    "type": "string",
                    "description": "The container within the pod template."
                },
                "cpu_request": {
                    "type": "string",
                    "description": "CPU request quantity, e.g. '500m'."
                },
                "memory_request": {
                    "type": "string",
                    "description": "Memory request quantity, e.g. '512Mi'."
                },
                "cpu_limit": {
                    "type": "string",
                    "description": "CPU limit quantity, e.g. '1'."
                },
                "memory_limit": {
                    "type": "string",
                    "description": "Memory limit quantity, e.g. '1Gi'."
                }
            },
            "required": ["deployment_name", "container_name"]
        }
    }
]


def get_tool_schema(tool_name: str) -> Dict[str, Any] | None:
    """Get schema for a specific tool by name."""
    for schema in TOOL_SCHEMAS:
        if schema["name"] == tool_name:
            return schema
    return None


def get_all_tool_schemas() -> List[Dict[str, Any]]:
    """Get all available tool schemas."""
    return TOOL_SCHEMAS.copy()


def format_tools_for_gemini() -> List[Dict[str, Any]]:
    """
    Format tool schemas for Gemini function calling API.

    Gemini expects a different format than the standard function calling schema.
    """
    gemini_tools = []
    for schema in TOOL_SCHEMAS:
        gemini_tool = {
            "name": schema["name"],
            "description": schema["description"],
            "parameters": schema["parameters"],
        }
        gemini_tools.append(gemini_tool)
    return gemini_tools


def format_tools_for_claude() -> List[Dict[str, Any]]:
    """
    Format tool schemas for Claude function calling API.

    Claude uses a specific tool format.
    """
    claude_tools = []
    for schema in TOOL_SCHEMAS:
        claude_tool = {
            "name": schema["name"],
            "description": schema["description"],
            "input_schema": schema["parameters"],
        }
        claude_tools.append(claude_tool)
    return claude_tools
