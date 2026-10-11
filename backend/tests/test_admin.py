"""Admin usage page: daily usage and Fire spend, admins only."""

from app.services.limits import record_fire_call, today


def test_only_admins_see_usage(client, auth):
    assert client.get("/api/admin/usage", headers=auth).status_code == 404
    assert (
        client.get("/api/auth/me", headers=auth).get_json()["user"]["is_admin"] is False
    )


def test_usage_shows_daily_spend_top_users_and_budget(app, client, auth, signup):
    token = signup(email="Admin@example.com", name="Admin").get_json()["access_token"]
    admin = {"Authorization": f"Bearer {token}"}
    assert client.get("/api/auth/me", headers=admin).get_json()["user"]["is_admin"]
    record_fire_call(1, 0.01)  # Ada
    record_fire_call(1, 0.02)
    record_fire_call(None, 0.005)  # signed-out decoder

    u = client.get("/api/admin/usage", headers=admin).get_json()["usage"]
    assert u["budget_usd"] == 1
    assert abs(u["month_spend_usd"] - 0.035) < 1e-9
    assert not u["paused"]
    assert u["users_total"] == 2
    assert len(u["days"]) == 30
    day = u["days"][0]
    assert day["date"] == today().isoformat()
    assert day["fire_calls"] == 3 and abs(day["spend_usd"] - 0.035) < 1e-9
    assert day["users"] == 1
    assert u["top_users"][0]["email"] == "ada@example.com"
    assert abs(u["top_users"][0]["spend_usd"] - 0.03) < 1e-9
