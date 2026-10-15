import pytest

from tools import ronin_postgres_backup


def test_postgres_backup_writes_atomic_dump_and_checksum(tmp_path, monkeypatch) -> None:
    output = tmp_path / "ronin.dump"

    def fake_run(command, *, check, stdout):
        assert check is True
        assert command[-1] == "ronin"
        stdout.write(b"dump-bytes")

    monkeypatch.setattr(ronin_postgres_backup.subprocess, "run", fake_run)
    ronin_postgres_backup.backup(tmp_path / "compose.yaml", output)

    assert output.read_bytes() == b"dump-bytes"
    sidecar = output.with_name("ronin.dump.sha256")
    assert sidecar.read_text(encoding="ascii").endswith("  ronin.dump\n")
    assert not list(tmp_path.glob(".ronin.dump.*.tmp"))


def test_postgres_restore_rejects_corrupt_dump_before_compose(monkeypatch, tmp_path) -> None:
    source = tmp_path / "ronin.dump"
    source.write_bytes(b"original")
    ronin_postgres_backup._checksum_path(source).write_text(
        "0" * 64 + "  ronin.dump\n", encoding="ascii"
    )
    called = False

    def fake_run(*_args, **_kwargs):
        nonlocal called
        called = True

    monkeypatch.setattr(ronin_postgres_backup.subprocess, "run", fake_run)
    with pytest.raises(ValueError, match="checksum mismatch"):
        ronin_postgres_backup.restore(tmp_path / "compose.yaml", source, force=True)
    assert called is False
