
# Standard imports.
from typing import (
    Any,
    Dict,
    List,
    Set
)
from enum import Enum


# Third-party imports.
from kubernetes import client

class JobStatus(str, Enum):
    SUCCEEDED: str = "SUCCEEDED"
    FAILED:     str = "FAILED"
    PENDING:    str = "PENDING"
    RUNNING:    str = "RUNNING"
    STUCK:      str = "STUCK"
    UNKNOWN:    str = "UNKNOWN"

def _is_stuck(pods: List[client.V1Pod]) -> bool:
    STUCK_REASONS = {
        "CrashLoopBackOff",
        "ImagePullBackOff",
        "ErrImagePull",
        "InvalidImageName",
    }
    for pod in pods:
        c_statuses: List[client.V1ContainerStatus] = pod.status.container_statuses or []
        for cs in c_statuses:
            if (cs.state.waiting) and (cs.state.waiting.reason in STUCK_REASONS):
                return True
    return False

def _status_from_pods(pods: List[client.V1Pod]) -> JobStatus:
    
    if _is_stuck(pods):
        return JobStatus.STUCK
    
    phases: Set[str] = {p.status.phase for p in pods} - {"Succeeded", "Failed"}
    if ("Running" in phases):
        return JobStatus.RUNNING
    elif ("Unknown" in phases):
        return JobStatus.UNKNOWN
    else:
        return JobStatus.PENDING

def compute_status(
    job:  client.V1Job,
    pods: List[client.V1Pod],
) -> JobStatus:

    status_conditions: List[client.V1JobCondition] = (
        (job.status.conditions if job.status else None)
        or []
    )

    for condition in status_conditions:
        if (condition.status == "True"):
            if (condition.type == "Complete"):
                return JobStatus.SUCCEEDED
            elif (condition.type == "Failed"):
                return JobStatus.FAILED

    return _status_from_pods(pods)
        
