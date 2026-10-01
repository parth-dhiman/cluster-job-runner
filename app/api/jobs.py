# Standard imports.
from typing import (
    Any,
    Dict,
)

# Third-party imports.
from flask import (
    Flask,
    request,
    jsonify,
)
from kubernetes import client, config
from kubernetes.client.rest import ApiException

# ===== Script-Level initilizations =====

app = Flask(__name__)

config.load_kube_config()
batch_api = client.BatchV1Api()
core_api = client.CoreV1Api()

# ========== Endpoints ==========

@app.post("/api/jobs")
def create_job() -> None:

    def namespace_exists(namespace: str) -> bool:
        try:
            core_api.read_namespace(namespace)
            return True # No error raised, namespace exists.
        except ApiException as e:
            if (e.status == 404):
                return False
            else:
                raise

    try:

        # Spec JSON must exist.
        spec: Dict[str, Any] = request.get_json()
        if not spec:
            return (
                jsonify({"error": "JSON Spec is required."}),
                400
            )

        # Job Spec must exist.
        job_spec: Dict[str, Any] = spec.get("job")
        if not job_spec:
            return (
                jsonify({"error": "Job Spec is required."}),
                400
            )

        # Create namespace if it does not yet exist.
        namespace: str = spec.get("namespace", "default")
        if not namespace_exists(namespace):
            core_api.create_namespace(
                client.V1Namespace(
                    metadata = client.V1ObjectMeta(
                        name = namespace,
                    )
                )
            )

        # Define Job Object's body.
        body = client.ApiClient()._ApiClient__deserialize(
            job_spec,
            client.V1Job,
        )

        # Create the Job Object.
        created = batch_api.create_namespaced_job(
            namespace = namespace,
            body = body,
        )

        # Return UID and status.
        return (jsonify({
            "uid":       created.metadata.uid,
            "status":    "created",
        }), 201)

    except Exception as e:
        raise