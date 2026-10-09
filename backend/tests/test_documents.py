import io

RESUME = (
    "Ada Lovelace. Backend engineer. Built the Acme billing API in Python and MySQL."
)


def test_paste_and_list(client, auth):
    res = client.post(
        "/api/documents", json={"kind": "resume", "text": RESUME}, headers=auth
    )
    assert res.status_code == 201
    doc = res.get_json()["document"]
    assert doc["kind"] == "resume" and doc["expires_at"]
    assert doc["title"].startswith("Résumé: Ada Lovelace")

    listed = client.get("/api/documents?kind=resume", headers=auth).get_json()
    assert [d["id"] for d in listed["documents"]] == [doc["id"]]
    full = client.get(f"/api/documents/{doc['id']}", headers=auth).get_json()
    assert full["document"]["text"] == RESUME


def test_file_upload(client, auth):
    res = client.post(
        "/api/documents",
        data={
            "kind": "job_description",
            "file": (io.BytesIO(RESUME.encode()), "jd.txt"),
        },
        headers=auth,
        content_type="multipart/form-data",
    )
    assert res.status_code == 201


def test_validation(client, auth):
    assert (
        client.post(
            "/api/documents", json={"kind": "resume", "text": "hi"}, headers=auth
        ).status_code
        == 400
    )
    assert (
        client.post(
            "/api/documents", json={"kind": "poem", "text": RESUME}, headers=auth
        ).status_code
        == 400
    )
    assert (
        client.post(
            "/api/documents", json={"kind": "resume", "text": RESUME}
        ).status_code
        == 401
    )


def test_other_users_documents_are_hidden(client, auth, signup):
    doc_id = client.post(
        "/api/documents", json={"kind": "resume", "text": RESUME}, headers=auth
    ).get_json()["document"]["id"]
    other = signup(email="bob@example.com").get_json()["access_token"]
    headers = {"Authorization": f"Bearer {other}"}
    assert client.get(f"/api/documents/{doc_id}", headers=headers).status_code == 404
    assert client.delete(f"/api/documents/{doc_id}", headers=headers).status_code == 404
    assert client.delete(f"/api/documents/{doc_id}", headers=auth).status_code == 204
