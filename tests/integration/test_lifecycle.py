
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

def _list_job(
    client:    FlaskClient,
    namespace: str,
):
    response: TestResponse = client.get(
        _BASE_API_URL,
        query_string = {
            "namespace": namespace,
        }
    )
    assert (response.status_code == 200)

def _fetch_job(
    client:    FlaskClient,
    namespace: str,
):
    response: TestResponse = client.get(
        f"{_BASE_API_URL}/{_BASE_SPEC['name']}",
        query_string = {
            "namespace": namespace,
        }
    )
    assert (response.status_code == 200)

def _rerun_job(
    client:    FlaskClient,
    namespace: str,
):
    response: TestResponse = client.post(
        f"{_BASE_API_URL}/{_BASE_SPEC['name']}/rerun",
        query_string = {
            "namespace": namespace,
        }
    )
    assert (response.status_code == 201)
    
def _delete_job(
    client:    FlaskClient,
    namespace: str,
):
    response: TestResponse = client.delete(
        f"{_BASE_API_URL}/{_BASE_SPEC['name']}",
        query_string = {
            "namespace": namespace,
        },
    )
    assert (response.status_code == 204)

def test_lifecycle(
    client: FlaskClient,
    namespace: str,
):    
    _create_job(client, namespace)
    _list_job(  client, namespace)
    _fetch_job( client, namespace)
    _rerun_job( client, namespace)
    _delete_job(client, namespace)
    

