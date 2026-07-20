import logging
from typing import Dict, Any

from kubernetes import client, config
from kubernetes.client.rest import ApiException

logger = logging.getLogger(__name__)

def _get_client() -> client.AppsV1Api:
    """Load the standard kubeconfig and return the AppsV1 API client."""
    try:
        config.load_kube_config()
        return client.AppsV1Api()
    except Exception as e:
        logger.error(f"Failed to load kubeconfig: {e}")
        raise RuntimeError(f"Could not load Kubernetes configuration: {e}")

def _get_core_client() -> client.CoreV1Api:
    """Load the standard kubeconfig and return the CoreV1 API client."""
    try:
        config.load_kube_config()
        return client.CoreV1Api()
    except Exception as e:
        logger.error(f"Failed to load kubeconfig: {e}")
        raise RuntimeError(f"Could not load Kubernetes configuration: {e}")

def scale_workload(namespace: str, deployment_name: str, replicas: int) -> Dict[str, Any]:
    """Scales a deployment up or down."""
    if replicas < 0:
        return {"success": False, "error": "Replicas must be >= 0"}
    
    api = _get_client()
    try:
        # Patch the deployment spec to set the new replica count
        patch = {"spec": {"replicas": replicas}}
        api.patch_namespaced_deployment_scale(
            name=deployment_name,
            namespace=namespace,
            body=patch
        )
        msg = f"Successfully scaled deployment '{deployment_name}' in namespace '{namespace}' to {replicas} replicas."
        logger.info(msg)
        return {"success": True, "message": msg}
    except ApiException as e:
        err_msg = f"Kubernetes API error scaling deployment: {e.reason} ({e.status})"
        logger.error(err_msg)
        return {"success": False, "error": err_msg}
    except Exception as e:
        err_msg = f"Unexpected error scaling deployment: {e}"
        logger.error(err_msg)
        return {"success": False, "error": err_msg}

def restart_workload(namespace: str, deployment_name: str) -> Dict[str, Any]:
    """Performs a rolling restart of a deployment."""
    api = _get_client()
    try:
        import datetime
        # To trigger a rolling restart, we patch the pod template with a new annotation
        patch = {
            "spec": {
                "template": {
                    "metadata": {
                        "annotations": {
                            "kubectl.kubernetes.io/restartedAt": datetime.datetime.now(datetime.timezone.utc).isoformat()
                        }
                    }
                }
            }
        }
        api.patch_namespaced_deployment(
            name=deployment_name,
            namespace=namespace,
            body=patch
        )
        msg = f"Successfully triggered rolling restart for deployment '{deployment_name}' in namespace '{namespace}'."
        logger.info(msg)
        return {"success": True, "message": msg}
    except ApiException as e:
        err_msg = f"Kubernetes API error restarting deployment: {e.reason} ({e.status})"
        logger.error(err_msg)
        return {"success": False, "error": err_msg}
    except Exception as e:
        err_msg = f"Unexpected error restarting deployment: {e}"
        logger.error(err_msg)
        return {"success": False, "error": err_msg}

def cordon_node(node_name: str) -> Dict[str, Any]:
    """Marks a node as unschedulable (cordoned)."""
    api = _get_core_client()
    try:
        patch = {"spec": {"unschedulable": True}}
        api.patch_node(name=node_name, body=patch)
        msg = f"Successfully cordoned node '{node_name}'."
        logger.info(msg)
        return {"success": True, "message": msg}
    except ApiException as e:
        err_msg = f"Kubernetes API error cordoning node: {e.reason} ({e.status})"
        logger.error(err_msg)
        return {"success": False, "error": err_msg}
    except Exception as e:
        err_msg = f"Unexpected error cordoning node: {e}"
        logger.error(err_msg)
        return {"success": False, "error": err_msg}
