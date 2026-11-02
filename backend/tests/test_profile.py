API = "/api/v1"


def test_get_and_update_profile(client, verified):
    h, _ = verified
    me = client.get(f"{API}/me", headers=h).json()
    assert me["timezone"] == "Africa/Johannesburg" and me["units"] == "metric"
    res = client.patch(f"{API}/me", headers=h, json={"first_name": " Grace ", "units": "imperial", "timezone": "Europe/London"})
    assert res.status_code == 200
    body = res.json()
    assert (body["first_name"], body["units"], body["timezone"]) == ("Grace", "imperial", "Europe/London")


def test_profile_rejects_invalid_values_and_ignores_privileged_fields(client, verified):
    h, _ = verified
    assert client.patch(f"{API}/me", headers=h, json={"timezone": "Nowhere/Land"}).status_code == 422
    assert client.patch(f"{API}/me", headers=h, json={"units": "furlongs"}).status_code == 422
    res = client.patch(f"{API}/me", headers=h, json={"email": "evil@example.com", "plan": "premium",
                                                     "email_verified": False})
    assert res.status_code == 200
    assert res.json()["email"] == "ada@example.com" and res.json()["plan"] == "free"


def test_notification_preferences(client, verified):
    h, _ = verified
    prefs = client.get(f"{API}/me/notification-preferences", headers=h).json()
    assert prefs["hydration_reminders_enabled"] is False
    assert prefs["hydration_reminder_interval_minutes"] == 90
    assert prefs["quiet_hours_start"] == "22:00:00" and prefs["quiet_hours_end"] == "07:00:00"
    assert client.patch(f"{API}/me/notification-preferences", headers=h, json={
        "quiet_hours_start": "22:00:00", "quiet_hours_end": "22:00:00",
    }).status_code == 422
    res = client.patch(f"{API}/me/notification-preferences", headers=h, json={
        "hydration_reminders_enabled": True, "hydration_reminder_interval_minutes": 90,
        "quiet_hours_start": "22:00:00", "quiet_hours_end": "07:00:00",
    })
    assert res.status_code == 200 and res.json()["hydration_reminder_interval_minutes"] == 90
    assert client.patch(f"{API}/me/notification-preferences", headers=h,
                        json={"quiet_hours_start": "22:00:00"}).status_code == 422
    assert client.patch(f"{API}/me/notification-preferences", headers=h,
                        json={"hydration_reminder_interval_minutes": 5}).status_code == 422
