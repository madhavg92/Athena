import httpx

from athena.connectors.entra import EntraConnector
from athena.connectors.http import ReadOnlyClient


def test_fixture_users(cfg) -> None:
    users = EntraConnector(cfg, run_mode="fixture").read("users")
    assert {u.get("email") for u in users} >= {"dm.one@fixture.local", "hl.key@fixture.local"}
    assert (
        next(u for u in users if u.get("email") == "dm.one@fixture.local").get("manager")
        == "hl.key@fixture.local"
    )


def test_live_pages(cfg) -> None:
    pages = {
        "first": {
            "value": [
                {
                    "mail": "A@fixture.local",
                    "displayName": "A",
                    "manager": {"mail": "B@fixture.local"},
                }
            ],
            "@odata.nextLink": "https://graph.microsoft.com/v1.0/users?page=2",
        },
        "second": {
            "value": [{"mail": "B@fixture.local", "displayName": "B"}, {"displayName": "no mail"}]
        },
    }

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, json=pages["second" if "page=2" in str(request.url) else "first"]
        )

    conn = EntraConnector(
        cfg,
        run_mode="live",
        http=ReadOnlyClient(transport=httpx.MockTransport(handler)),
        token_provider=lambda: "t",
    )
    users = conn.read("users")
    assert [u.get("email") for u in users] == ["a@fixture.local", "b@fixture.local"]
    assert users[0].get("manager") == "b@fixture.local"
