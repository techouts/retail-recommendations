import os

import pytest


os.environ.setdefault("ES_HOST", "localhost")
os.environ.setdefault("ES_PORT", "9200")
os.environ.setdefault("ES_SCHEME", "http")

from recommendations.adapters.es import searcher


class _FakeIndicesMissingAlias:
    def exists_alias(self, name: str) -> bool:
        return False


class _FakeClientMissingAlias:
    def __init__(self):
        self.indices = _FakeIndicesMissingAlias()


class _FakeIndicesExistsAlias:
    def exists_alias(self, name: str) -> bool:
        return True


class _FakeClientSearchFails:
    def __init__(self):
        self.indices = _FakeIndicesExistsAlias()

    def search(self, index, body, from_, size):
        raise RuntimeError("es boom")


def test_search_es_raises_runtime_error_when_alias_missing(monkeypatch):
    monkeypatch.setattr(searcher, "get_es_client", lambda: _FakeClientMissingAlias())

    with pytest.raises(RuntimeError) as exc:
        searcher.search_es("tenant_missing_alias")

    assert "tenant_missing_alias" in str(exc.value)


def test_search_es_raises_runtime_error_when_es_search_fails(monkeypatch):
    monkeypatch.setattr(searcher, "get_es_client", lambda: _FakeClientSearchFails())

    with pytest.raises(RuntimeError) as exc:
        searcher.search_es("tenant_alias", query={"query": {"match_all": {}}})

    assert "tenant_alias" in str(exc.value)
