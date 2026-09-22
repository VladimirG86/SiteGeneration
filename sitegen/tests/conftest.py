"""Добавляем корень sitegen в sys.path, чтобы тесты импортировали модули напрямую."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from fastapi.testclient import TestClient
import app as appmod
import generator
import images
import llm

@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(generator, "SITES_DIR", str(tmp_path))
    monkeypatch.setattr(appmod, "_RATE", {})
    monkeypatch.setattr(llm, "API_KEY", "")
    monkeypatch.setattr(images, "API_KEY", "")
    # сбрасываем auth кэш
    monkeypatch.setattr(appmod, "_AUTH_CODES", {})
    return TestClient(appmod.app)
