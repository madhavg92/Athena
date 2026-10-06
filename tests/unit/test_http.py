import httpx
import pytest

from athena.connectors.http import ReadOnlyClient, WriteRefused, post_allowed


def make(handler, **kw):
    sleeps: list[float] = []
    client = ReadOnlyClient(transport=httpx.MockTransport(handler), sleep=sleeps.append, **kw)
    return client, sleeps


def test_get_ok() -> None:
    client, _ = make(lambda r: httpx.Response(200, json={"ok": True}))
    assert client.get("https://api.example.test/x").json() == {"ok": True}


@pytest.mark.parametrize("method", ["PUT", "PATCH", "DELETE"])
def test_write_methods_refused(method: str) -> None:
    client, _ = make(lambda r: httpx.Response(200))
    with pytest.raises(WriteRefused):
        client.request(method, "https://api.example.test/x")


def test_no_write_helpers() -> None:
    client, _ = make(lambda r: httpx.Response(200))
    assert client.put is None and client.patch is None and client.delete is None


@pytest.mark.parametrize(
    "url,ok",
    [
        ("https://login.microsoftonline.com/tenant/oauth2/v2.0/token", True),
        ("https://graph.microsoft.com/v1.0/search/query", True),
        ("https://api.smartsheet.com/2.0/sheets/1/rows", False),
        ("https://graph.microsoft.com/v1.0/users", False),
        ("https://evil.example/search/query", False),
    ],
)
def test_post_allowlist(url: str, ok: bool) -> None:
    assert post_allowed(url) is ok
    client, _ = make(lambda r: httpx.Response(200, json={}))
    if ok:
        assert client.post(url, json={}).status_code == 200
    else:
        with pytest.raises(WriteRefused):
            client.post(url, json={})


def test_retries_then_succeeds() -> None:
    calls = {"n": 0}

    def handler(request):
        calls["n"] += 1
        return httpx.Response(503) if calls["n"] < 3 else httpx.Response(200)

    client, sleeps = make(handler)
    assert client.get("https://api.example.test/x").status_code == 200
    assert calls["n"] == 3 and sleeps == [0.5, 1.0]


def test_gives_up_after_three_retries() -> None:
    calls = {"n": 0}

    def handler(request):
        calls["n"] += 1
        return httpx.Response(429, headers={"Retry-After": "2"})

    client, sleeps = make(handler)
    with pytest.raises(httpx.HTTPStatusError):
        client.get("https://api.example.test/x")
    assert calls["n"] == 4 and sleeps == [2.0, 2.0, 2.0]


def test_transport_error_retried() -> None:
    calls = {"n": 0}

    def handler(request):
        calls["n"] += 1
        if calls["n"] == 1:
            raise httpx.ConnectError("boom")
        return httpx.Response(200)

    client, _ = make(handler)
    assert client.get("https://api.example.test/x").status_code == 200


def test_body_not_logged(caplog) -> None:
    client, _ = make(lambda r: httpx.Response(200, text="SECRET-BODY"))
    with caplog.at_level("DEBUG"):
        client.get("https://api.example.test/x?token=abc")
    joined = " ".join(f"{r.getMessage()} {r.__dict__}" for r in caplog.records)
    assert "SECRET-BODY" not in joined and "token=abc" not in joined
