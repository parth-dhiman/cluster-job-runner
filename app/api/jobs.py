# Standard imports.
from typing import (
    Any,
    Dict,
    Tuple,
)

# Third-party imports.
from requests import Response
from flask import (
    Flask,
    request,
    jsonify,
)

# Local imports.
from app.schema.job_spec import JobSpec
from app.services import jobs as jobs_service

# ===== Script-Level initilizations =====

app = Flask(__name__)

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
    return (jsonify(response), 200)