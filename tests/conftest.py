from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from skyle_ai.api import create_app
from skyle_ai.config import Settings


@pytest.fixture
def client(tmp_path: Path):
    settings = Settings(data_dir=tmp_path / "state")
    with TestClient(create_app(settings)) as test_client:
        yield test_client
