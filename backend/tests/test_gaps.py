"""Résumé gap analysis: requirement by requirement, quotes verified, cached."""


def gaps(client, auth, docs, resume_id=None):
    return client.post(
        f"/api/documents/{docs['jd_id']}/gaps",
        json={"resume_id": resume_id or docs["resume_id"]},
        headers=auth,
    )


def test_gaps_keep_only_what_the_resume_shows(client, auth, docs, fire):
    r = gaps(client, auth, docs)
    assert r.status_code == 200, r.get_json()
    g = r.get_json()["gaps"]
    by = {x["requirement"]: x for x in g["requirements"]}
    assert by["API design"] == {
        "requirement": "API design",
        "status": "covered",
        "evidence": "Built the Acme billing API",
        "likely_question": "How did you version it?",
    }
    # Claimed as covered, but the quote isn't in the résumé: only partial.
    assert (
        by["MySQL tuning"]["status"] == "partial"
        and by["MySQL tuning"]["evidence"] is None
    )
    assert (
        by["Payments domain"]["status"] == "missing"
        and by["Payments domain"]["evidence"] is None
    )
    assert [x["status"] for x in g["requirements"]] == ["missing", "partial", "covered"]
    assert g["counts"] == {"missing": 1, "partial": 1, "covered": 1}
    prompt = fire.calls[-1]["prompt"]
    assert "Never infer skills the résumé doesn't state" in prompt


def test_gaps_are_cached_per_pair(client, auth, docs, fire):
    gaps(client, auth, docs)
    calls = len(fire.calls)
    gaps(client, auth, docs)
    assert len(fire.calls) == calls


def test_gaps_need_both_documents(client, auth, docs, signup):
    r = client.post(f"/api/documents/{docs['jd_id']}/gaps", json={}, headers=auth)
    assert r.status_code == 404
    token = signup("bo@example.com", "correct-horse", "Bo").get_json()["access_token"]
    other = {"Authorization": f"Bearer {token}"}
    assert gaps(client, other, docs).status_code == 404
