# Standard imports.
from typing import (
    Any,
    Dict,
    List,
    Optional,
)
from datetime import datetime
import secrets

# Third-party imports.
from kubernetes import client
from kubernetes.client.rest import ApiException
from app.exceptions import NotFoundError

# Local imports.
from app.k8s.client import (
     init_core_api,
     init_batch_api,
)
from app.k8s.builders import (
    build_job,
)
from app.config import (
    MANAGED_BY_LABEL,
    MANAGED_BY_VALUE,
    SPEC_ANNOTATION,
)
from app.schema.jobs import JobSpec

def _iso(dt: datetime) -> Optional[str]:
    if dt:
        return dt.isoformat()
    else:
        return None
    
def _namespace_exists(namespace: str) -> bool:
    try:
        core_api: client.CoreV1Api = init_core_api()
        core_api.read_namespace(namespace)
        return True # No error raised, namespace exists.
    except ApiException as e:
        if (e.status == 404):
            return False
        else:
            raise

def _create_namespace(namespace: str) -> None:
    core_api: client.CoreV1Api = init_core_api()
    core_api.create_namespace(
        client.V1Namespace(
            metadata = client.V1ObjectMeta(
                name = namespace,
            )
        )
    )

def _read_managed_job(
    name: str,
    namespace: str,
) -> client.V1Job:
    
    batch_api: client.BatchV1Api = init_batch_api()

    job: client.V1Job = batch_api.read_namespaced_job(
        name=name,
        namespace=namespace,
    )

    # Verify that the job is managed by this service.
    labels = job.metadata.labels or {}
    if (labels.get(MANAGED_BY_LABEL) != MANAGED_BY_VALUE):
        raise NotFoundError(
            name      = name,
            namespace = namespace,
        )

    return job

def _get_job_info(job) -> Dict[str, Any]:

    name:      str = job.metadata.name
    namespace: str = job.metadata.namespace
    uid:       str = job.metadata.uid

    succeeded: int = job.status.succeeded or 0
    active:    int = job.status.active or 0
    failed:    int = job.status.failed or 0

    if job.status.conditions:
        conditions: List[Dict[str, Any]] = [
            {
                "type"   : condition.type,
                "status" : condition.status,    
                "reason" : condition.reason,
                "message": condition.message,
                "last_transition_time": _iso(condition.last_transition_time),  
            }
            for condition in job.status.conditions
        ]
    else:
        conditions: List[Dict[str, Any]] = []

    start_time:      str = _iso(job.status.start_time)
    completion_time: str = _iso(job.status.completion_time)

    labels:   Dict[str, str] = job.spec.selector.match_labels
    selector: str = ",".join(f"{k}={v}" for k, v in labels.items())

    core_api: client.CoreV1Api = init_core_api()
    pods: client.V1PodList = core_api.list_namespaced_pod(
        namespace      = namespace,
        label_selector = selector,
    )

    per_pod_data: List[Dict[str, Any]] = [
        {
            "name":  pod.metadata.name,
            "phase": pod.status.phase,
            "node":  pod.spec.node_name,
            "restart_count": sum([
                cs.restart_count
                for cs in (pod.status.container_statuses or [])
            ]),
            "container_states": [
                {
                    "name":     cs.name,
                    "ready":    cs.ready,
                    "state":    cs.state.to_dict(),
                    "started":  cs.started,
                    "image":    cs.image,
                    "image_id": cs.image_id,
                    "restart_count": cs.restart_count,
                    "container_id":  cs.container_id,
                }
                for cs in (pod.status.container_statuses or [])
            ]
        }
        for pod in pods.items
    ]

    return {
        "name":            name,
        "namespace":       namespace,
        "uid":             uid,
        "succeeded":       succeeded,
        "active":          active,
        "failed":          failed,
        "conditions":      conditions,
        "start_time":      start_time,
        "completion_time": completion_time,
        "pods":            per_pod_data,
    }

def create_job(spec: JobSpec) -> Dict[str, Any]:

    # Access the namespace, ensure it exists.
    namespace: str = spec.namespace
    if not _namespace_exists(namespace):
        _create_namespace(namespace)

    # Build the job as a Dict object.
    job_dict: Dict[str, Any] = build_job(spec)

    # Create the job.
    batch_api: client.BatchV1Api = init_batch_api()
    response = batch_api.create_namespaced_job(
        namespace = namespace,
        body = job_dict,
    )

    # Return job details in dict.
    return {
        "name":      response.metadata.name,
        "namespace": response.metadata.namespace,
        "uid":       response.metadata.uid,
    }

def list_jobs(namespace: str) -> List[Dict[str, Any]]:

    batch_api: client.BatchV1Api = init_batch_api()
    
    jobs: client.V1JobList

    if namespace:
        jobs = batch_api.list_namespaced_job(
            namespace = namespace,
            label_selector = f"{MANAGED_BY_LABEL}={MANAGED_BY_VALUE}",
        )
    else:
        jobs = batch_api.list_job_for_all_namespaces(
            label_selector = f"{MANAGED_BY_LABEL}={MANAGED_BY_VALUE}",
        )

    return [
        _get_job_info(job)
        for job in jobs.items
    ]

def fetch_job(
    name:      str,
    namespace: str,
) -> Dict[str, Any]:
    job: client.V1Job = _read_managed_job(name, namespace)
    return _get_job_info(job)

def delete_job(
    name:      str,
    namespace: str,
) -> None:

    # Make sure the job is managed by our script.
    _read_managed_job(name, namespace)

    delete_options: client.V1DeleteOptions = client.V1DeleteOptions(
        propagation_policy = "Background",
        # Cascades deletion to the job's Pods
    )

    batch_api: client.BatchV1Api = init_batch_api()
    batch_api.delete_namespaced_job(
        name      = name, 
        namespace = namespace, 
        body      = delete_options,
    )

def rerun_job(
    name:      str,
    namespace: str, 
) -> Dict[str, Any]:
    
    # Makes sure the job is managed by our script.
    job: client.V1Job = _read_managed_job(name, namespace)

    original_spec: JobSpec = JobSpec.model_validate_json(job.metadata.annotations[SPEC_ANNOTATION]) 
    new_spec: JobSpec = original_spec.model_copy(
        update = {
            "name": f"{original_spec.name[:56]}-{secrets.token_hex(3)}",
    })

    return create_job(new_spec)

    
    