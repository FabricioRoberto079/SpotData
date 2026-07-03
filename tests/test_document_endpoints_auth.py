"""Auth guards on the /documents router.

Regression test for the finding that list/search/metadata/download/delete were
reachable without a JWT. Every request here carries no Authorization header, so
`authenticate_request` must reject it before any service or DB access — the
assertions never depend on a database being available.
"""
from fastapi.testclient import TestClient

from main import app

client = TestClient(app)


def test_list_documents_requires_auth():
    assert client.get("/documents").status_code == 401


def test_search_documents_requires_auth():
    assert client.get("/documents/search", params={"q": "anything"}).status_code == 401


def test_get_document_metadata_requires_auth():
    assert client.get("/documents/some-id").status_code == 401


def test_download_latest_requires_auth():
    assert client.get("/documents/some-id/download").status_code == 401


def test_download_version_requires_auth():
    assert client.get("/documents/some-id/versions/1/download").status_code == 401


def test_delete_document_requires_auth():
    assert client.delete("/documents/some-id").status_code == 401


def test_upload_requires_auth():
    assert client.post("/documents/upload", data={"kind": "text"}).status_code == 401
