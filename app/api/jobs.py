# Standard imports.
from typing import (
    Any,
    Dict,
    List,
    Tuple,
)

# Third-party imports.
from flask import (
    Flask,
    request,
    jsonify,
    Response,
)

# Local imports.
from app.schema.jobs import (
    JobSpec,
    JobListQuery,
    JobRef,
)
from app.services import jobs as jobs_service
from app.api.errors import register_error_handlers

# ===== Script-Level initilizations =====

app = Flask(
    __name__,
    static_folder   = "../ui",
    static_url_path = "/ui",
)
register_error_handlers(app)

# ========== UI ==========

@app.get("/")
def index() -> Response:
    return app.send_static_file("index.html")

# ========== Endpoints ==========

@app.post("/api/jobs")
def create_job() -> Tuple[Response, int]:

    # Validate input payload.
    job_spec: JobSpec = JobSpec.model_validate(
        request.get_json(
            silent = True,
        )
    )

    # Create the job.
    response: Dict[str, Any] = jobs_service.create_job(job_spec)

    # Return response info and status.
    return (jsonify(response), 201)

@app.get("/api/jobs")
def list_jobs() -> Tuple[Response, int]:
    namespace: str = request.args.get("namespace", None)
    job_list_query: JobListQuery = JobListQuery.model_validate({
        "namespace": namespace,
    })
    response: List[Dict[str, Any]] = jobs_service.list_jobs(
        namespace = job_list_query.namespace,
    )
    return (jsonify(response), 200)

@app.get("/api/jobs/<name>")
def fetch_job(name: str) -> Tuple[Response, int]:
    namespace: str = request.args.get("namespace", "default")
    job_ref: JobRef = JobRef.model_validate(
        {
            "name": name,
            "namespace": namespace,
        }
    )
    response: Dict[str, Any] = jobs_service.fetch_job(
        name      = job_ref.name,
        namespace = job_ref.namespace,
    )
    return (jsonify(response), 200)

@app.delete("/api/jobs/<name>")
def delete_job(name: str) -> Tuple[Response, int]:
    namespace: str = request.args.get("namespace", "default")
    job_ref: JobRef = JobRef.model_validate(
        {
            "name": name,
            "namespace": namespace,
        }
    )
    jobs_service.delete_job(
        name = job_ref.name,
        namespace = job_ref.namespace,
    )
    return Response(
        status = 204,
    )

@app.post("/api/jobs/<name>/rerun")
def rerun_job(name: str) -> Tuple[Response, int]:
    namespace: str = request.args.get("namespace", "default")
    job_ref: JobRef = JobRef.model_validate(
        {
            "name": name,
            "namespace": namespace,
        }
    )

    response: Dict[str, Any] = jobs_service.rerun_job(
        name      = job_ref.name,
        namespace = job_ref.namespace,
    )

    return (jsonify(response), 201)