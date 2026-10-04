# Standard imports.
from typing import (
    Any,
    Dict,
)

# Local imports.
from app.config import (
    BACKOFF_LIMIT,
    MANAGED_BY_LABEL,
    MANAGED_BY_VALUE,
    SPEC_ANNOTATION,
)
from app.schema.job_spec import JobSpec

def build_job(spec: JobSpec) -> Dict[str, Any]:

    # Container: required fields first, optional ones only if provided.
    container: Dict[str, Any] = {
        "name":  spec.name,
        "image": spec.image,
    }
    if (spec.command is not None):
        container["command"] = spec.command
    if (spec.args is not None):
        container["args"] = spec.args
    if (spec.env is not None):
        # Kubernetes expects a list of {"name", "value"}, not a dict.
        container["env"] = [{"name": key, "value": value} for key, value in spec.env.items()]
    if (spec.resources is not None):
        # exclude_none drops unset values (e.g. memory) so they are not sent as null.
        container["resources"] = spec.resources.model_dump(exclude_none = True)

    job_dict: Dict[str, Any] = {
        "apiVersion": "batch/v1",
        "kind": "Job",
        "metadata": {
            "name": spec.name,
            "namespace": spec.namespace,
            "labels": {MANAGED_BY_LABEL: MANAGED_BY_VALUE},
            "annotations": {SPEC_ANNOTATION: spec.model_dump_json(exclude_none = True)},
        },
        "spec": {
            "completions": spec.completions,
            "parallelism": spec.parallelism,
            "backoffLimit": BACKOFF_LIMIT,
            "template": {
                "spec": {
                    "restartPolicy": "Never",
                    "containers": [container],
                },
            },
        },
    }

    return job_dict
