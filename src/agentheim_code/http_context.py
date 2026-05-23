"""Request context propagation and size-limit enforcement."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import uuid4

REQUEST_ID_HEADER = "x-request-id"
MAX_JSON_BODY_BYTES = 262_144


@dataclass(frozen=True)
class RequestContext:
    request_id: str


def new_request_id() -> str:
    return uuid4().hex
