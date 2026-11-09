from __future__ import annotations


def upload(client, name: str, text: str):
    return client.post("/api/v1/documents/upload", files={"files": (name, text.encode(), "text/markdown")})


def test_upload_retrieve_citation_and_no_evidence(client):
    response = upload(
        client,
        "workspace.md",
        "The fictional lab stores extracted document text in a local SQLite database. "
        "CSV uploads are processed in memory.",
    )
    assert response.status_code == 200
    assert response.json()["results"][0]["status"] == "indexed"
    result = client.post("/api/v1/ask", json={"question": "Where is document text stored?"})
    assert result.status_code == 200
    body = result.json()
    assert body["mode"] == "extractive"
    assert body["external_llm_used"] is False
    assert body["sources"][0]["filename"] == "workspace.md"
    assert body["sources"][0]["citation_id"] == "S1"
    assert "SQLite" in body["sources"][0]["text"]
    empty = client.post("/api/v1/ask", json={"question": "xylophonic volcano zebra"}).json()
    assert empty["sources"] == []
    assert "couldn't find" in empty["answer"]


def test_duplicate_content_is_not_indexed_twice_and_delete_clears_search(client):
    first = upload(client, "first.txt", "Only the local keeper stores this phrase in SQLite.").json()
    second = upload(client, "renamed.txt", "Only the local keeper stores this phrase in SQLite.").json()
    assert second["results"][0]["status"] == "already_exists"
    assert second["document_count"] == 1
    document_id = first["results"][0]["document"]["id"]
    assert client.delete(f"/api/v1/documents/{document_id}").json()["chunk_count"] == 0
    result = client.post("/api/v1/ask", json={"question": "local keeper SQLite"}).json()
    assert result["sources"] == []


def test_demo_library_is_explicitly_fictional(client):
    response = client.post("/api/v1/demo/load")
    assert response.status_code == 200
    assert response.json()["data_mode"] == "original fictional examples"
    assert response.json()["document_count"] == 2
    docs = client.get("/api/v1/documents").json()["documents"]
    assert all(row["source"] == "synthetic_demo" for row in docs)
