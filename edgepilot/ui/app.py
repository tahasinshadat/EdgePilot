# edgepilot/ui/app.py

import json
from pathlib import Path
import requests
import streamlit as st
from importlib.resources import files  # add this

# CHANGE THESE THREE LINES ↓↓↓
from edgepilot.config import get_config
from edgepilot.llm.ollama import OllamaProvider
from edgepilot.usage import record_usage

cfg = get_config()
API = f"http://{cfg.host}:{cfg.api_port}"


st.set_page_config(page_title="EdgePilot", layout="wide")
st.title("EdgePilot — System Health, Scheduling, and Optimization")


def api_get(path: str, **params):
    r = requests.get(f"{API}{path}", params=params, timeout=30)
    r.raise_for_status()
    return r.json()


def api_post(path: str, json_body: dict):
    r = requests.post(f"{API}{path}", json=json_body, timeout=30)
    r.raise_for_status()
    return r.json()


# --- Run controls ---
st.subheader("Run")
col1, col2, col3 = st.columns([2, 1, 1])
with col1:
    note = st.text_input("Run note", value="interactive run")
with col2:
    sampling = st.number_input("Sampling (sec)", min_value=1, max_value=30, value=cfg.metrics.sample_interval)
with col3:
    if st.button("Start Run"):
        res = api_post("/runs/start", {"user_note": note, "sampling_sec": int(sampling)})
        st.session_state["run_id"] = res["run_id"]
if st.button("End Run"):
    rid = st.session_state.get("run_id")
    if rid:
        res = api_post("/runs/end", {"run_id": rid})
        st.success(res.get("report_text", "Run ended."))
        st.json(res.get("summary", {}))
    else:
        st.info("No active run_id in session.")

# --- Live metrics ---
st.subheader("Live Metrics")
snap = api_get("/metrics/snapshot", include_processes=True, top_n=cfg.metrics.process_top_n)
colA, colB, colC, colD = st.columns(4)
colA.metric("CPU %", f"{snap['cpu_total_pct']:.1f}")
colB.metric("Mem Used (GB)", f"{snap['mem_used_bytes']/ (1024**3):.1f}")
colC.metric("Net RX/TX (MB)", f"{snap['net']['rx_bytes']/1e6:.1f} / {snap['net']['tx_bytes']/1e6:.1f}")
colD.metric("Disk R/W (MB)", f"{snap['disk']['read_bytes']/1e6:.1f} / {snap['disk']['write_bytes']/1e6:.1f}")

if snap.get("gpu", {}).get("available"):
    colA.metric("GPU Util %", f"{snap['gpu']['util_pct']:.0f}")
else:
    colA.write("GPU: unavailable")

if snap.get("power", {}).get("available"):
    b = snap["power"].get("battery_pct")
    if b is not None:
        colB.metric("Battery %", f"{b:.0f}")
else:
    colB.write("Power: unavailable")

st.write("Top processes")
st.table(snap.get("processes", []))

# --- Scheduler ---
st.subheader("Scheduler")
with st.form("enqueue"):
    cname = st.text_input("Task name", value="train-small")
    ccmd = st.text_input("Command", value="python -c 'print(42)'")
    requires_gpu = st.checkbox("Requires GPU", value=False)
    est = st.number_input("Est. runtime (sec)", value=30, min_value=0)
    priority = st.number_input("Priority (lower is higher)", value=5, min_value=0, max_value=10)
    max_cpu = st.number_input("Max CPU %", value=90, min_value=10, max_value=100)
    max_mem = st.number_input("Max memory MB (0 for none)", value=0, min_value=0, max_value=262144)
    min_vram = st.number_input("Min VRAM MB (if GPU)", value=0, min_value=0, max_value=131072)
    if st.form_submit_button("Enqueue Task"):
        res = api_post("/tasks/enqueue",
                       {"name": cname, "command": ccmd, "requires_gpu": requires_gpu,
                        "est_runtime_sec": int(est), "priority": int(priority),
                        "max_cpu_pct": int(max_cpu), "max_mem_mb": int(max_mem), "min_vram_mb": int(min_vram)})
        st.success(f"Enqueued {res['task_id']}")
rows = api_get("/tasks/list", state="any")
st.write(rows)

# --- Policy presets (balanced defaults default) ---
st.subheader("Policy")
preset = st.selectbox("Preset", ["balanced_defaults", "performance", "sip-battery"], index=0)
if st.button("Apply Policy Preset"):
    from edgepilot.scheduler.policies import PRESETS
    rules = PRESETS[preset].rules
    res = api_post("/policies/set", {"name": preset, "rules": rules})
    st.success(f"Active: {res['active']}")
st.caption("Use CLI or MCP to fine-tune policies further.")

# --- Ask LLM (local call; uses snapshot) ---
st.subheader("LLM Advisor")
with st.form("qa"):
    q = st.text_input("Ask a question (e.g., 'Can I run a 12 GB VRAM model now?')", value="")
    if st.form_submit_button("Ask"):
        if cfg.llm.provider != "ollama":
            st.warning("The UI uses the local Ollama provider for now. Configure via `edgepilot wizard` if needed.")
        provider = OllamaProvider()
        prompt = files("edgepilot.llm.prompts").joinpath("bottleneck.md").read_text(encoding="utf-8")
        prompt = prompt.replace("{{ question }}", q or "What should I do now?")
        prompt = prompt.replace("{{ snapshot_json }}", json.dumps(snap)[:8000])
        import asyncio
        res = asyncio.run(provider.complete(prompt))
        st.write(res.text)

# --- Usage ---
st.subheader("Usage")
ust = api_get("/usage/stats")
st.json(ust)

# --- Footer ---
st.caption(f"Provider: {cfg.llm.provider} • Model: {cfg.llm.model} • DB: {cfg.storage.db_path}")
