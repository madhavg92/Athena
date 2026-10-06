from athena.bot.teams import TeamsBot, resolve_email

DM_ID = "00000000-0000-4000-8000-000000000003"  # dm.one in fixtures/entra/users.json


def test_resolve_by_object_id(app) -> None:
    assert resolve_email(app, DM_ID, None) == "dm.one@fixture.local"


def test_resolve_by_upn(app) -> None:
    assert resolve_email(app, None, "CSM.One@fixture.local") == "csm.one@fixture.local"


def test_unknown_user_gets_not_set_up(app) -> None:
    reply = TeamsBot(app).handle_message(
        "backlog Northwind", "ffffffff-0000-0000-0000-000000000000", None, "c1"
    )
    assert reply.text == "You are not set up for Athena yet." and reply.result is None


def test_known_user_gets_answer(app) -> None:
    reply = TeamsBot(app).handle_message(
        "What is the backlog for Northwind Orthopedics?", DM_ID, None, "c1"
    )
    assert reply.result is not None and "Sources:" in reply.text


def test_empty_message_gets_help(app) -> None:
    assert "Ask me" in TeamsBot(app).handle_message("  ", DM_ID, None, "c1").text
