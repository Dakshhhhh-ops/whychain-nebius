"""Tests never call a model or an embedding API: memory recall falls back to keyword overlap."""
import pytest


@pytest.fixture(autouse=True)
def _no_cloud_embeddings(monkeypatch):
    monkeypatch.setenv("WHYCHAIN_EMBED_MODEL", "off")
