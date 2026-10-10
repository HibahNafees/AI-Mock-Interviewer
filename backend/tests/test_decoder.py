"""Job description decoder: works signed out, quotes the posting, caches, caps."""

from app.extensions import db
from app.models import AnonSpend, JdDecode, UsageLimit
from app.services.limits import month_spend_usd

POSTING = (
    "Backend Engineer. You will work closely with stakeholders across product and sales, "
    "and ship features every week. Stakeholders expect clear updates. You'll get "
    "mentoring from senior engineers. Keep stakeholders informed about trade-offs and "
    "present plans to stakeholders monthly. Experience with Python and MySQL required."
)


def decode(client, text=POSTING, headers=None, ip="10.0.0.1"):
    return client.post(
        "/api/decoder",
        json={"text": text},
        headers=headers or {},
        environ_base={"REMOTE_ADDR": ip},
    )


def test_decodes_without_signing_in_and_keeps_only_real_quotes(client, fire):
    r = decode(client)
    assert r.status_code == 200, r.get_json()
    d = r.get_json()["decode"]
    assert d["pace"]["evidence"] == "ship features every week"
    assert d["team_size"]["evidence"] is None  # not in the posting
    assert [p["point"] for p in d["priorities"]] == ["Keeping stakeholders aligned"]
    assert d["red_flags"] == []  # "around the clock" isn't in the posting
    assert d["green_flags"][0]["evidence"] == "mentoring from senior engineers"
    assert {"word": "stakeholders", "count": 4} in d["signals"]
    prompt = fire.calls[-1]["prompt"]
    assert '"word": "stakeholders", "count": 4' in prompt
    assert "interpretation, not fact" in prompt


def test_shared_link_and_cache(client, fire):
    token = decode(client).get_json()["decode"]["share_token"]
    calls = len(fire.calls)
    again = decode(client, POSTING.upper()).get_json()["decode"]  # same posting
    assert again["share_token"] == token and len(fire.calls) == calls
    shared = client.get(f"/api/decoder/{token}")
    assert shared.status_code == 200 and shared.get_json()["decode"]["summary"]
    assert client.get("/api/decoder/nope").status_code == 404
    # The posting itself isn't stored, only its hash and the interpretation.
    row = db.session.scalar(db.select(JdDecode))
    assert "Backend Engineer. You will work" not in str(row.result_json)


def test_signed_out_spend_counts_toward_the_budget(app, client, fire):
    decode(client)
    assert float(db.session.scalar(db.select(AnonSpend.fire_spend_usd))) > 0
    assert month_spend_usd() > 0
    app.config["FIRE_MONTHLY_BUDGET_USD"] = 0
    r = decode(client, POSTING + " A different posting entirely.")
    assert r.status_code == 429


def test_signed_out_caps_per_visitor_and_overall(app, client, fire):
    app.config["ANON_DECODER_RUNS"] = 1
    assert decode(client).status_code == 200
    r = decode(client, POSTING + " Another one.")
    assert r.status_code == 429 and "Sign up" in r.get_json()["error"]
    assert decode(client, POSTING + " Another one.", ip="10.0.0.2").status_code == 200
    app.config["ANON_DECODER_DAILY"] = 2
    assert decode(client, POSTING + " Third.", ip="10.0.0.3").status_code == 429


def test_signed_in_runs_count_and_can_use_a_saved_jd(app, client, auth, docs, fire):
    app.config["DAILY_DECODER_RUNS"] = 1
    r = client.post("/api/decoder", json={"jd_id": docs["jd_id"]}, headers=auth)
    assert r.status_code == 400  # the fixture JD is one sentence: too short to decode
    assert decode(client, headers=auth).status_code == 200
    assert db.session.scalar(db.select(UsageLimit.decoder_runs)) == 1
    assert decode(client, POSTING + " More.", headers=auth).status_code == 429


def test_too_short_is_explained(client):
    r = decode(client, "Backend engineer wanted.")
    assert r.status_code == 400 and "full job description" in r.get_json()["error"]
