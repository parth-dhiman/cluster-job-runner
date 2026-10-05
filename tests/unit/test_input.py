# Standard imports.
from typing import (
    Any,
    Dict,
    List,
    Set,
)

# Third-party imports.
import pytest
from pydantic import ValidationError
from app.schema.jobs import JobSpec

_BASE_INPUT: Dict[str, Any] = {
    "name":  "hello",
    "image": "busybox",
}

def _input(**overrides):
    return {
        **_BASE_INPUT,
        **overrides,
    }

def _error_fields(exc_info) -> Set[str]:
    return {
        ".".join(str(p) for p in e["loc"])
        for e in exc_info.value.errors()
    }

def test_base_input():
    spec: JobSpec = JobSpec.model_validate(_input())
    assert (spec.name  == _BASE_INPUT["name"])
    assert (spec.image == _BASE_INPUT["image"])

def test_full_input():
    JobSpec.model_validate(
        _input(
            namespace   = "default",
            completions = 3,
            parallelism = 3,
            command     = ["echo", "hello"],
            env         = {"secret_key": "secret_value"},
            args        = [],
            resources   = {
                "requests": {
                    "cpu"   : "100m",
                    "memory": "1Gi",
                },
                "limits": {
                    "cpu"   : "200m",
                    "memory": "2Gi",
                }
            }
        )
    )

def test_name_is_required():
    with pytest.raises(ValidationError) as exc_info:
        JobSpec.model_validate({
            "image" : "busybox",
        })
    assert (_error_fields(exc_info) == {"name"})

def test_image_is_required():
    with pytest.raises(ValidationError) as exc_info:
        JobSpec.model_validate({
            "name" : "hello",
        })
    assert (_error_fields(exc_info) == {"image"})

@pytest.mark.parametrize("field", ["name", "namespace"])
@pytest.mark.parametrize("value", ["a", "job-1", "123-abc", "a" * 63])
def test_valid_dns_labels(field: str, value: str):
    spec: JobSpec = JobSpec.model_validate(_input(**{
        field: value,
    }))
    assert (getattr(spec, field) == value)

@pytest.mark.parametrize("field", ["name", "namespace"])
@pytest.mark.parametrize("value", ["Hello", "job_1", "-job", "job-", "job.1", "", "a" * 64])
def test_invalid_dns_labels(field: str, value: str):
    with pytest.raises(ValidationError) as exc_info:
        JobSpec.model_validate(_input(**{
            field: value,
        }))
    assert (_error_fields(exc_info) == {field})

@pytest.mark.parametrize("image", [
    "busybox",
    "busybox:1.36",
    "library/busybox",
    "ghcr.io/org/app:v1",
    "localhost:5000/app",
    "busybox@sha256:" + "a" * 64,
    "doesnotexist/nope:1.0",  # well-formed but missing: a runtime STUCK, not a 400
])
def test_valid_images(image: str):
    spec: JobSpec = JobSpec.model_validate(_input(**{
        "image": image,
    }))
    assert (getattr(spec, "image") == image)

@pytest.mark.parametrize("image", ["", "BusyBox", "busy box", "busybox:", ":latest", "a//b", "app/", "busybox\n"])
def test_invalid_images(image: str):
    with pytest.raises(ValidationError) as exc_info:
        JobSpec.model_validate(_input(**{
            "image": image,
        }))
    assert (_error_fields(exc_info) == {"image"})

@pytest.mark.parametrize("field", ["completions", "parallelism"])
@pytest.mark.parametrize("value", [1, 5])
def test_valid_counts(field: str, value: Any):
    spec: JobSpec = JobSpec.model_validate(_input(**{
        field: value,
    }))
    assert (getattr(spec, field) == value)

@pytest.mark.parametrize("field", ["completions", "parallelism"])
@pytest.mark.parametrize("value", [0, -1])
def test_invalid_counts(field: str, value: Any):
    with pytest.raises(ValidationError) as exc_info:
        JobSpec.model_validate(_input(**{
            field: value,
        }))
    assert (_error_fields(exc_info) == {field})

@pytest.mark.parametrize("section",  ["requests", "limits"])
@pytest.mark.parametrize("resource", ["cpu", "memory"])
@pytest.mark.parametrize("value",    ["100m", "0.5", "1", "64Mi", "1Gi"])
def test_valid_resources(section: str, resource: int, value: Any):
    spec: JobSpec = JobSpec.model_validate(_input(
        resources = {
            section: {
                resource: value,
            }
        }
    ))
    assert (getattr(getattr(spec.resources, section), resource) == value)

@pytest.mark.parametrize("section",  ["requests", "limits"])
@pytest.mark.parametrize("resource", ["cpu", "memory"])
@pytest.mark.parametrize("value",     ["lots", "-1", "NaN", "Infinity", "Mi", ""])
def test_invalid_resources(section: str, resource: str, value: Any):
    with pytest.raises(ValidationError) as exc_info:
        JobSpec.model_validate(_input(
            resources = {
                section: {
                    resource: value,
            }
        }
        ))
    assert (_error_fields(exc_info) == {f"resources.{section}.{resource}"})

@pytest.mark.parametrize(
    ("resource", "requested", "limit"),
    [
        ("cpu", "1", "1"),       # equal is allowed
        ("cpu", "500m", "1"),    # proves quantities are compared numerically, not as text
        ("memory", "512Mi", "1Gi"),
    ],
)
def test_requests_under_limits(
    resource: str,
    requested: Any,
    limit: Any,
) -> None:
    spec: JobSpec = JobSpec.model_validate(
        _input(
            resources={
                "requests": {resource: requested},
                "limits":   {resource: limit},
            }
        )
    )

    assert (getattr(spec.resources.requests, resource) == requested)
    assert (getattr(spec.resources.limits, resource) == limit)

@pytest.mark.parametrize(
    ("resource", "requested", "limit"),
    [
        ("cpu", "2", "1"),
        ("memory", "1Gi", "512Mi"),
    ],
)
def test_requests_exceeds_limit(
    resource: str,
    requested: Any,
    limit: Any,
) -> None:
    with pytest.raises(ValidationError) as exc_info:
        JobSpec.model_validate(
            _input(
                resources = {
                    "requests": {resource: requested},
                    "limits":   {resource: limit},
                }
            )
        )
    assert (_error_fields(exc_info) == {"resources"})

@pytest.mark.parametrize("command", [
    ["echo", "hello"],
    ["sh", "-c", "echo hi"],
    [],
    None,
])
def test_valid_command(command: Any):
    spec: JobSpec = JobSpec.model_validate(_input(
        command = command,
    ))
    assert (spec.command == command)

@pytest.mark.parametrize("command", [
    "echo hi",               # a string, not a list
    42,
    {"run": "echo hi"},
])
def test_invalid_command(command: Any):
    with pytest.raises(ValidationError) as exc_info:
        JobSpec.model_validate(_input(
            command = command,
        ))
    assert (_error_fields(exc_info) == {"command"})

@pytest.mark.parametrize("args", [
    ["hello"],
    ["-c", "echo hi"],
    [],
    None,
])
def test_valid_args(args: Any):
    spec: JobSpec = JobSpec.model_validate(_input(
        args = args,
    ))
    assert (spec.args == args)

@pytest.mark.parametrize("args", [
    "hello",                 # a string, not a list
    42,
    {"arg": "hello"},
])
def test_invalid_args(args: Any):
    with pytest.raises(ValidationError) as exc_info:
        JobSpec.model_validate(_input(
            args = args,
        ))
    assert (_error_fields(exc_info) == {"args"})

@pytest.mark.parametrize("env", [
    {"GREETING": "hi"},
    {"A": ""},               # an empty value is allowed
    {},
    None,
])
def test_valid_env(env: Any):
    spec: JobSpec = JobSpec.model_validate(_input(
        env = env,
    ))
    assert (spec.env == env)

@pytest.mark.parametrize("env", [
    ["A=1"],                 # a list, not an object
    "A=1",
    42,
])
def test_invalid_env(env: Any):
    with pytest.raises(ValidationError) as exc_info:
        JobSpec.model_validate(_input(
            env = env,
        ))
    assert (_error_fields(exc_info) == {"env"})
