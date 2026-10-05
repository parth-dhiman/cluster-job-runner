
# Standard imports.
import logging
from typing import (
    Any,
    Dict,
)

# Third-party imports.
from flask.testing import FlaskClient
from werkzeug.test import TestResponse

# Script-Level Constants.
_BASE_API_URL: str = "/api/jobs"
_BASE_SPEC: Dict[str, Any] = {
    "name":  "hello",
    "image": "busybox",
}

def _create_job(
    client:    FlaskClient,
    namespace: str,
):
    payload: Dict[str, Any] = {
        **_BASE_SPEC,
        "namespace": namespace,
    }
    response: TestResponse = client.post(
        _BASE_API_URL,
        json = payload,
    )
    assert (response.status_code == 201)

def _create_duplicate(
    client:    FlaskClient,
    namespace: str,
):
    payload: Dict[str, Any] = {
        **_BASE_SPEC,
        "namespace": namespace,
    }
    response: TestResponse = client.post(
        _BASE_API_URL,
        json = payload,
    )
    assert (response.status_code == 409)
    assert (response.get_json()["error"]["code"] == "CONFLICT")

def test_duplicate(
    client:    FlaskClient,
    namespace: str,
):    
    _create_job(client, namespace)
    _create_duplicate(client, namespace)
    

