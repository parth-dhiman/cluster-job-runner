# Standard imports.
from typing import (
    Dict,
    List,
    Self,
)
import re
from decimal import Decimal

# Third-party imports.
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)
from kubernetes.utils import parse_quantity

# Script-Level Constants.
_NAMECHECK_RE = re.compile(r"[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?")

# Image reference grammar (same rules Docker and the kubelet use to parse image names).
_IMAGE_PATH_COMPONENT = r"[a-z0-9]+(?:(?:[._]|__|-+)[a-z0-9]+)*"
_IMAGE_REGISTRY = (
    r"[a-zA-Z0-9](?:[a-zA-Z0-9-]*[a-zA-Z0-9])?"
    r"(?:\.[a-zA-Z0-9](?:[a-zA-Z0-9-]*[a-zA-Z0-9])?)*"
    r"(?::[0-9]+)?"
)
_IMAGE_TAG = r"[A-Za-z0-9_][A-Za-z0-9_.-]{0,127}"
_IMAGE_DIGEST = r"[A-Za-z][A-Za-z0-9]*(?:[-_+.][A-Za-z][A-Za-z0-9]*)*:[0-9a-fA-F]{32,}"

_IMAGE_RE = re.compile(
    rf"(?:{_IMAGE_REGISTRY}/)?"                                 # optional registry + "/"
    rf"{_IMAGE_PATH_COMPONENT}(?:/{_IMAGE_PATH_COMPONENT})*"    # path: one or more components
    rf"(?::{_IMAGE_TAG})?"                                      # optional ":tag"
    rf"(?:@{_IMAGE_DIGEST})?"                                   # optional "@digest"
)


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid") 

class ResourceObject(Strict):
    cpu:    str | None = None
    memory: str | None = None

    @field_validator("cpu", "memory")
    @classmethod
    def value_check(cls, v: str | None) -> str | None:

        # If resource value was not provided, let it be.
        if (v is None):
            return v

        # If it was provided, try to parse it as quantity.
        try:
            parsed_v: Decimal = parse_quantity(v)
        except ValueError:
            raise ValueError(
                "Must be a valid Kubernetes string quantity, "
                "like '100m', '0.5', or '64Mi'."
            )

        # Parsed value cannot be negative and must be finite.
        if (not parsed_v.is_finite()) or (parsed_v < 0):
            raise ValueError("Must be a finite, non-negative quantity.")

        # If we did not get halted by any of these conditionals, just return value as is.
        return v

class Resources(Strict):
    requests: ResourceObject | None = None
    limits:   ResourceObject | None = None

    @model_validator(mode="after")
    def requests_within_limits(self) -> Self:

        # Cannot do this check unless BOTH are available.
        if (self.requests is None) or (self.limits is None):
            return self

        for field in ("cpu", "memory"):
            request = getattr(self.requests, field)
            limit = getattr(self.limits, field)
            if (request is not None) and (limit is not None):
                if (parse_quantity(request) > parse_quantity(limit)):
                    raise ValueError(
                        f"requests.{field} ({request}) must not exceed limits.{field} ({limit})"
                    )
        return self

class JobSpec(Strict):

    # Required.
    name:  str
    image: str

    # Optional, defaults needed.
    namespace:   str = "default"
    completions: int = Field(default=1, ge=1)
    parallelism: int = Field(default=1, ge=1)

    # Optional, no defaults needed.
    command:   List[str] | None = None
    args:      List[str] | None = None
    env:       Dict[str, str] | None = None
    resources: Resources | None = None

    @field_validator("name", "namespace")
    @classmethod
    def name_check(cls, v: str) -> str:  
        if not _NAMECHECK_RE.fullmatch(v):
            raise ValueError(
                "Must be lowercase letters, digits, or '-', "
                "start and end with a letter or digit, max 63 characters."
            )
        return v

    @field_validator("image")
    @classmethod
    def image_check(cls, v: str) -> str:
        if not _IMAGE_RE.fullmatch(v):
            raise ValueError(
                "Must be a valid image reference, "
                "like 'busybox', 'busybox:1.36', or 'ghcr.io/org/app:v1'."
            )
        return v
