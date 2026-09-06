from services.file_service import read_json, write_json


def test_m015_removes_ntfy_fields_from_every_user(brain):
    from migrations.runner import m015_remove_ntfy_fields

    auth_file = brain / "_system" / "auth.json"
    write_json(
        auth_file,
        {
            "users": [
                {
                    "id": "u1",
                    "name": "Alice",
                    "notification_channel": "lc-abc123",
                    "channel_rotated_at": "2026-08-01T00:00:00+00:00",
                    "channel_reminder_at": "2026-08-15T00:00:00+00:00",
                },
                {"id": "u2", "name": "Bob"},  # never had the fields — no-op
            ]
        },
    )

    m015_remove_ntfy_fields(brain)

    data = read_json(auth_file, default={"users": []})
    alice, bob = data["users"]
    assert "notification_channel" not in alice
    assert "channel_rotated_at" not in alice
    assert "channel_reminder_at" not in alice
    assert alice["id"] == "u1"  # untouched fields survive
    assert bob == {"id": "u2", "name": "Bob"}


def test_m015_no_auth_file_is_a_no_op(brain):
    from migrations.runner import m015_remove_ntfy_fields

    m015_remove_ntfy_fields(brain)  # must not raise


def test_m015_is_idempotent(brain):
    from migrations.runner import m015_remove_ntfy_fields

    auth_file = brain / "_system" / "auth.json"
    write_json(auth_file, {"users": [{"id": "u1", "notification_channel": "lc-abc123"}]})

    m015_remove_ntfy_fields(brain)
    m015_remove_ntfy_fields(brain)  # second run: nothing left to strip

    data = read_json(auth_file, default={"users": []})
    assert data["users"] == [{"id": "u1"}]
