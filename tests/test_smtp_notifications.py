import pytest
from studio_observability import NotificationIntent, SmtpNotificationError, SmtpNotificationSink


class _Client:
    def __init__(self) -> None:
        self.message = None
        self.tls = False

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def starttls(self) -> None:
        self.tls = True

    def send_message(self, message) -> None:
        self.message = message


def test_smtp_sink_is_bounded_and_sends_plain_text() -> None:
    client = _Client()
    sink = SmtpNotificationSink(
        "smtp.example.test",
        sender="ronin@example.test",
        recipients=("ops@example.test",),
        client_factory=lambda _host, _port, _timeout: client,
    )
    intent = NotificationIntent(
        "notification-1", "alert", "Alert", "Something happened", "2026-09-13T10:00:00.000000Z"
    )
    assert sink.send(intent) == intent.id
    assert client.tls
    assert client.message["Subject"] == "Alert"
    assert "Something happened" in client.message.get_content()


def test_smtp_sink_rejects_invalid_bounds_and_hides_transport_errors() -> None:
    with pytest.raises(ValueError, match="port"):
        SmtpNotificationSink("smtp.example.test", port=0, sender="a@b", recipients=("c@d",))

    def failing(_host, _port, _timeout):
        raise OSError("password=secret")

    sink = SmtpNotificationSink(
        "smtp.example.test",
        sender="a@b",
        recipients=("c@d",),
        client_factory=failing,
    )
    intent = NotificationIntent(
        "notification-2", "alert", "Alert", "Body", "2026-09-13T10:00:00.000000Z"
    )
    with pytest.raises(SmtpNotificationError, match="delivery failed") as error:
        sink.send(intent)
    assert "secret" not in str(error.value)
