# Standard imports.
from typing import (
    Any,
    Dict,
)

# Third-party imports.
from kubernetes import client
from kubernetes.client.models.v1_job import V1Job
from kubernetes.client.rest import ApiException

# Local imports.
from app.k8s.builders import (
     init_core_api,
     init_batch_api,
)
from app.k8s.builders import (
    build_job,
)
from app.schema.job_spec import JobSpec

def _namespace_exists(namespace: str) -> bool:
    try:
        core_api = init_core_api()
        core_api.read_namespace(namespace)
        return True # No error raised, namespace exists.
    except ApiException as e:
        if (e.status == 404):
            return False
        else:
            raise

def _create_namespace(namespace: str) -> None:
    core_api = init_core_api()
    core_api.create_namespace(
        client.V1Namespace(
            metadata = client.V1ObjectMeta(
                name = namespace,
            )
        )
    )

def create_job(spec: JobSpec) -> Dict[str, str]:

    # Access the namespace, ensure it exists.
    namespace: str = spec.namespace
    if not _namespace_exists(namespace):
        _create_namespace(namespace)

    # Build the job as a Dict object.
    job: V1Job= build_job(spec)

    # Create the job.
    batch_api = init_batch_api()
    response = batch_api.create_namespaced_job(namespace="default", body=job)

    # Return job details in dict.
    return {
        "uid": response.metadata.uid,
    }
