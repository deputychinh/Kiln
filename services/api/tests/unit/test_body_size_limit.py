import asyncio

from starlette.types import Message, Receive, Scope, Send

from kiln_api.problems import BodySizeLimit


def _run(messages: list[Message]) -> tuple[list[Message], list[Message]]:
    """Feed `messages` to the middleware; return what the app received and what was sent."""
    received: list[Message] = []
    sent: list[Message] = []
    queue = list(messages)

    async def receive() -> Message:
        return queue.pop(0) if queue else {"type": "http.disconnect"}

    async def send(message: Message) -> None:
        sent.append(message)

    async def app(_scope: Scope, inner_receive: Receive, _send: Send) -> None:
        received.append(await inner_receive())
        received.append(await inner_receive())

    scope: Scope = {
        "type": "http",
        "method": "POST",
        "path": "/",
        "headers": [],
        "query_string": b"",
    }
    asyncio.run(BodySizeLimit(app)(scope, receive, send))
    return received, sent


def test_a_small_chunked_body_is_replayed_once_then_the_real_stream_continues() -> None:
    received, sent = _run(
        [
            {"type": "http.request", "body": b"ab", "more_body": True},
            {"type": "http.request", "body": b"cd", "more_body": False},
        ]
    )

    assert received[0] == {"type": "http.request", "body": b"abcd", "more_body": False}
    assert received[1] == {"type": "http.disconnect"}
    assert sent == []


def test_a_client_that_disconnects_mid_body_reaches_the_app_with_what_arrived() -> None:
    received, _ = _run([{"type": "http.request", "body": b"ab", "more_body": True}])

    assert received[0]["body"] == b"ab"


def test_non_http_scopes_pass_through() -> None:
    seen: list[str] = []

    async def app(scope: Scope, _receive: Receive, _send: Send) -> None:
        seen.append(scope["type"])

    async def noop_receive() -> Message:
        return {"type": "lifespan.startup"}

    async def noop_send(_message: Message) -> None:
        return None

    asyncio.run(BodySizeLimit(app)({"type": "lifespan"}, noop_receive, noop_send))

    assert seen == ["lifespan"]
