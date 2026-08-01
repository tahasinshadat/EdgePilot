import subprocess
import json
import logging
from typing import Any, Dict
import requests

try:
    from kubernetes import client, config
except ImportError:
    client = None
    config = None

logger = logging.getLogger(__name__)

# ==========================================
# SLURM, LSF, PBS Real Implementations
# ==========================================

def _run_slurm_cmd(cmd: list) -> str:
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        return result.stdout.strip()
    except subprocess.CalledProcessError as e:
        logger.error(f"Slurm command failed: {e.stderr}")
        raise RuntimeError(f"Slurm command failed: {e.stderr}")
    except FileNotFoundError:
        raise RuntimeError(f"Command not found: {cmd[0]}. Are you on a Slurm cluster?")

def query_slurm_jobstats(job_id: str) -> Dict[str, Any]:
    try:
        stdout = _run_slurm_cmd(["sstat", "-j", job_id, "--format=AveCPU,AveRSS,MaxRSS", "--noheader"])
        parts = stdout.split()
        if len(parts) >= 3:
            return {
                "job_id": job_id,
                "metrics": {
                    "AveCPU": parts[0],
                    "AveRSS": parts[1],
                    "MaxRSS": parts[2]
                }
            }
        return {"error": "Unexpected sstat output format"}
    except Exception as e:
        return {"error": str(e)}

def query_slurm_accounting(job_id: str) -> Dict[str, Any]:
    try:
        stdout = _run_slurm_cmd(["sacct", "-j", job_id, "--format=JobID,State,ExitCode,ReqTRES,AllocTRES,Submit,Start,End", "--noheader", "--parsable2"])
        lines = stdout.split('\n')
        if lines:
            parts = lines[0].split('|')
            if len(parts) >= 8:
                return {
                    "job_id": parts[0],
                    "state": parts[1],
                    "exit_code": parts[2],
                    "req_tres": parts[3],
                    "alloc_tres": parts[4],
                    "submit_time": parts[5],
                    "start_time": parts[6],
                    "end_time": parts[7]
                }
        return {"error": "No accounting records found"}
    except Exception as e:
        return {"error": str(e)}

def slurm_queue_snapshot(partition: str = "all") -> Dict[str, Any]:
    cmd = ["squeue", "-o", "%.10i %.9P %.8j %.8u %.2t %.10M"]
    if partition != "all":
        cmd.extend(["--partition", partition])
    try:
        stdout = _run_slurm_cmd(cmd)
        lines = stdout.split('\n')
        jobs = []
        for line in lines[1:]: # skip header
            parts = line.split()
            if len(parts) >= 6:
                jobs.append({
                    "job_id": parts[0],
                    "partition": parts[1],
                    "name": parts[2],
                    "user": parts[3],
                    "state": parts[4],
                    "time": parts[5]
                })
        return {
            "partition": partition,
            "jobs_count": len(jobs),
            "jobs_preview": jobs[:10]
        }
    except Exception as e:
        return {"error": str(e)}

def query_node_exporter_subset(node: str) -> Dict[str, Any]:
    return {"error": "Prometheus endpoint URL not configured. Cannot query node_exporter."}

def query_node_specs(node: str) -> Dict[str, Any]:
    try:
        stdout = _run_slurm_cmd(["sinfo", "-n", node, "-O", "NodeList,CPUsState,Memory,Gres", "--noheader", "--exact"])
        parts = stdout.split()
        if len(parts) >= 4:
            return {
                "node": parts[0],
                "cpus": parts[1],
                "memory": parts[2],
                "gres": parts[3]
            }
        return {"error": "Unexpected sinfo output"}
    except Exception as e:
        return {"error": str(e)}

def cancel_slurm_job(job_id: str) -> Dict[str, Any]:
    """(HITL REQUIRED) Cancel a Slurm job."""
    try:
        _run_slurm_cmd(["scancel", job_id])
        return {
            "success": True,
            "action": "cancel",
            "job_id": job_id,
            "message": f"Successfully cancelled Slurm job {job_id}."
        }
    except Exception as e:
         return {"success": False, "error": str(e)}

def update_slurm_job_qos(job_id: str, new_qos: str) -> Dict[str, Any]:
    """(HITL REQUIRED) Update QoS for a Slurm job."""
    try:
        _run_slurm_cmd(["scontrol", "update", f"JobId={job_id}", f"QOS={new_qos}"])
        return {
            "success": True,
            "action": "update_qos",
            "job_id": job_id,
            "new_qos": new_qos,
            "message": f"Demoted job {job_id} to {new_qos} QoS."
        }
    except Exception as e:
         return {"success": False, "error": str(e)}

def compare_job_efficiency(job_id: str) -> Dict[str, Any]:
    accounting = query_slurm_accounting(job_id)
    stats = query_slurm_jobstats(job_id)
    if "error" in accounting: return {"error": f"Failed to get accounting data: {accounting['error']}"}
    if "error" in stats: return {"error": f"Failed to get job stats: {stats['error']}"}
    
    req_tres = accounting.get("req_tres", "")
    req_mem_mb = 1024
    for item in req_tres.split(','):
        if item.startswith("mem="):
            mem_str = item.split('=')[1]
            try:
                if 'G' in mem_str: req_mem_mb = float(mem_str.replace('G','')) * 1024
                elif 'M' in mem_str: req_mem_mb = float(mem_str.replace('M',''))
                else: req_mem_mb = float(mem_str)
            except: pass
            
    max_rss_str = stats.get("metrics", {}).get("MaxRSS", "0K")
    actual_mem_mb = 0
    try:
        if 'K' in max_rss_str: actual_mem_mb = float(max_rss_str.replace('K','')) / 1024
        elif 'M' in max_rss_str: actual_mem_mb = float(max_rss_str.replace('M',''))
        elif 'G' in max_rss_str: actual_mem_mb = float(max_rss_str.replace('G','')) * 1024
        else: actual_mem_mb = float(max_rss_str) / (1024*1024)
    except: pass
        
    waste_pct = 0
    if req_mem_mb > 0: waste_pct = ((req_mem_mb - actual_mem_mb) / req_mem_mb) * 100
        
    recommendation = "Job memory allocation is efficient."
    if waste_pct > 50: recommendation = f"Job requested {req_mem_mb:.1f} MB but only used {actual_mem_mb:.1f} MB. Downsize memory request by at least 50%."
        
    return {
        "job_id": job_id,
        "requested_memory_mb": round(req_mem_mb, 2),
        "actual_memory_used_mb": round(actual_mem_mb, 2),
        "memory_waste_percentage": round(waste_pct, 2),
        "recommendation": recommendation
    }

def query_cluster_incidents(hours_back: int = 24) -> Dict[str, Any]:
    try:
        cmd = ["sacct", "-S", f"now-{hours_back}hours", "-X", "-s", "OOM,NODE_FAIL,PREEMPTED,TIMEOUT", "-o", "JobID,State,NodeList,End", "--noheader", "--parsable2"]
        stdout = _run_slurm_cmd(cmd)
        lines = stdout.split('\n')
        incidents = []
        for line in lines:
            if not line.strip(): continue
            parts = line.split('|')
            if len(parts) >= 4:
                incidents.append({"job_id": parts[0], "state": parts[1], "node": parts[2], "end_time": parts[3]})
        return {"timeframe_hours": hours_back, "incident_count": len(incidents), "incidents": incidents}
    except Exception as e:
        return {"error": str(e)}

import csv
import os

def ingest_historical_sample(csv_file_path: str) -> Dict[str, Any]:
    try:
        if not os.path.exists(csv_file_path): return {"error": f"CSV file not found: {csv_file_path}"}
        jobs = []
        with open(csv_file_path, 'r') as f:
            reader = csv.DictReader(f)
            for row in reader: jobs.append(row)
        oom_count = sum(1 for j in jobs if j.get('State') == 'OUT_OF_MEMORY')
        failed_count = sum(1 for j in jobs if j.get('State') == 'FAILED')
        return {
            "success": True,
            "jobs_ingested": len(jobs),
            "summary": {"oom_jobs": oom_count, "failed_jobs": failed_count},
            "sample_data": jobs[:5],
            "message": f"Successfully ingested {len(jobs)} jobs for simulation."
        }
    except Exception as e:
        return {"error": str(e)}

# ==========================================
# Kubernetes Batch & Cloud Real Implementations
# ==========================================

def analyze_oomkilled_pods(namespace: str = "default") -> Dict[str, Any]:
    if not client:
        return {"error": "kubernetes python client not installed"}
    try:
        config.load_kube_config()
        v1 = client.CoreV1Api()
        pods = v1.list_namespaced_pod(namespace=namespace)
        oom_pods = []
        for pod in pods.items:
            if pod.status.container_statuses:
                for container in pod.status.container_statuses:
                    if container.last_state.terminated and container.last_state.terminated.reason == "OOMKilled":
                        limits = {}
                        for c in pod.spec.containers:
                            if c.name == container.name:
                                limits = c.resources.limits if c.resources else {}
                        oom_pods.append({
                            "pod_name": pod.metadata.name,
                            "container": container.name,
                            "memory_limit": limits.get("memory", "Unknown"),
                            "recommendation": "Increase memory limit by 15%."
                        })
        return {
            "namespace": namespace,
            "oomkilled_pods": oom_pods
        }
    except Exception as e:
        return {"error": f"Failed to connect to Kubernetes: {e}"}

def drain_k8s_node(node_name: str) -> Dict[str, Any]:
    """(HITL REQUIRED) Safely evict all workloads from a dying Kubernetes node."""
    try:
        result = subprocess.run(["kubectl", "drain", node_name, "--ignore-daemonsets", "--delete-emptydir-data"], capture_output=True, text=True, check=True)
        return {
            "success": True,
            "action": "drain_node",
            "node_name": node_name,
            "message": f"Successfully drained node {node_name}.",
            "output": result.stdout
        }
    except subprocess.CalledProcessError as e:
        return {"success": False, "error": f"Failed to drain node: {e.stderr}"}
    except FileNotFoundError:
        return {"success": False, "error": "kubectl command not found"}
        
def query_ray_workers() -> Dict[str, Any]:
    try:
        resp = requests.get("http://localhost:8265/api/cluster_status", timeout=2)
        if resp.status_code == 200:
            return resp.json()
        return {"error": f"Ray API returned {resp.status_code}"}
    except Exception as e:
        return {"error": f"Failed to connect to Ray dashboard: {e}"}
