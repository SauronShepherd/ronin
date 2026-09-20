import pytest
from studio_ai_studio.streaming import (
    BoundedEventQueue,
    StreamLimitExceeded,
    StreamLimits,
    StreamProtocolError,
    parse_sse,
)


def test_parser_handles_fragmented_events():
    result = list(parse_sse([b"data: {\"a\"", b":1}\n", b"\ndata: [DONE]\n\n"]))
    assert result == [b'data: {"a":1}\n\n', b"data: [DONE]\n\n"]


def test_parser_rejects_incomplete_and_oversized_streams():
    with pytest.raises(StreamProtocolError, match="incomplete"):
        list(parse_sse([b"data: incomplete\n"]))
    with pytest.raises(StreamLimitExceeded, match="event"):
        list(
            parse_sse(
                [b"data: xxxxxxxxx\n\n"],
                limits=StreamLimits(max_event_bytes=5, max_stream_bytes=100),
            )
        )


def test_queue_is_bounded_and_fifo():
    queue = BoundedEventQueue(2)
    queue.put(b"a")
    queue.put(b"b")
    assert queue.get() == b"a"
    queue.put(b"c")
    assert queue.get() == b"b"
    queue.put(b"d")
    with pytest.raises(StreamLimitExceeded):
        queue.put(b"e")
