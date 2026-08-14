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

def apply_resource_requests(
    namespace: str,
    deployment_name: str,
    container_name: str,
    cpu_request: str | None = None,
    memory_request: str | None = None,
    cpu_limit: str | None = None,
    memory_limit: str | None = None,
) -> Dict[str, Any]:
    """Patch a deployment container's resource requests and/or limits.

    Quantities are Kubernetes strings such as ``500m`` or ``512Mi`` —
    exactly what ``tools.rightsizing`` emits in its recommendations.
    """

    requests: Dict[str, str] = {}
    limits: Dict[str, str] = {}

    if cpu_request:
        requests["cpu"] = cpu_request
    if memory_request:
        requests["memory"] = memory_request
    if cpu_limit:
        limits["cpu"] = cpu_limit
    if memory_limit:
        limits["memory"] = memory_limit

    if not requests and not limits:
        return {
            "success": False,
            "error": (
                "At least one of cpu_request, memory_request, cpu_limit "
                "or memory_limit must be provided."
            ),
        }

    resources: Dict[str, Any] = {}

    if requests:
        resources["requests"] = requests
    if limits:
        resources["limits"] = limits

    api = _get_client()

    try:
        # A strategic merge patch keys the container list by name, so
        # sibling containers are left untouched.
        patch = {
            "spec": {
                "template": {
                    "spec": {
                        "containers": [
                            {"name": container_name, "resources": resources}
                        ]
                    }
                }
            }
        }
        api.patch_namespaced_deployment(
            name=deployment_name,
            namespace=namespace,
            body=patch,
        )
        msg = (
            f"Updated resources for container '{container_name}' in "
            f"deployment '{deployment_name}' (namespace '{namespace}'): "
            f"{resources}."
        )
        logger.info(msg)
        return {"success": True, "message": msg}
    except ApiException as e:
        err_msg = (
            f"Kubernetes API error updating deployment resources: "
            f"{e.reason} ({e.status})"
        )
        logger.error(err_msg)
        return {"success": False, "error": err_msg}
    except Exception as e:
        err_msg = f"Unexpected error updating deployment resources: {e}"
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

def migrate_workload(namespace: str, deployment_name: str, target_node: str) -> Dict[str, Any]:
    """Migrates a deployment to a specific node by patching its nodeSelector."""
    api = _get_client()
    try:
        patch = {
            "spec": {
                "template": {
                    "spec": {
                        "nodeSelector": {
                            "kubernetes.io/hostname": target_node
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
        msg = f"Successfully migrated deployment '{deployment_name}' in namespace '{namespace}' to node '{target_node}'."
        logger.info(msg)
        return {"success": True, "message": msg}
    except ApiException as e:
        err_msg = f"Kubernetes API error migrating deployment: {e.reason} ({e.status})"
        logger.error(err_msg)
        return {"success": False, "error": err_msg}
    except Exception as e:
        err_msg = f"Unexpected error migrating deployment: {e}"
        logger.error(err_msg)
        return {"success": False, "error": err_msg}
