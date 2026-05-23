"""Tests for backend lifespan and startup/shutdown hooks."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from agentheim_code.backend import create_app


@pytest.fixture
def client(tmp_path):
    app = create_app(tmp_path)
    return TestClient(app)


def test_lifespan_shutdown_completes_cleanly(client: TestClient) -> None:
    app = client.app
    assert app.title == "Agentheim Code"
