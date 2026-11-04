from __future__ import annotations

import gzip
import io
import tarfile
from pathlib import Path

import pytest

from tools.normalize_release_sdist import main, normalize_sdist


def _write_sdist(path: Path, *, member_name: str, mtime: int) -> None:
    with tarfile.open(path, mode="w:gz") as archive:
        directory = tarfile.TarInfo("ronin_studio-1.2.3")
        directory.type = tarfile.DIRTYPE
        directory.mtime = mtime
        archive.addfile(directory)
        member = tarfile.TarInfo(member_name)
        member.size = 5
        member.mtime = mtime
        archive.addfile(member, io.BytesIO(b"ronin"))


def test_normalized_sdists_have_stable_bytes_and_metadata(tmp_path: Path) -> None:
    first = tmp_path / "first.tar.gz"
    second = tmp_path / "second.tar.gz"
    _write_sdist(first, member_name="ronin_studio-1.2.3/PKG-INFO", mtime=1_700_000_000)
    _write_sdist(second, member_name="ronin_studio-1.2.3/PKG-INFO", mtime=1_800_000_000)

    normalize_sdist(first, source_date_epoch=1_750_000_000)
    normalize_sdist(second, source_date_epoch=1_750_000_000)

    assert first.read_bytes() == second.read_bytes()
    with tarfile.open(first, mode="r:gz") as archive:
        members = archive.getmembers()
    assert all(member.mtime == 1_750_000_000 for member in members)
    assert all(member.uid == 0 and member.gid == 0 for member in members)
    assert all(not member.uname and not member.gname for member in members)


@pytest.mark.parametrize("member_name", ["../outside", "/absolute/path", "C:\\outside", ""])
def test_normalizer_rejects_unsafe_member_paths(tmp_path: Path, member_name: str) -> None:
    artifact = tmp_path / "unsafe.tar.gz"
    _write_sdist(artifact, member_name=member_name, mtime=1_700_000_000)
    original = artifact.read_bytes()

    with pytest.raises(ValueError, match="unsafe sdist member path"):
        normalize_sdist(artifact, source_date_epoch=1_750_000_000)

    assert artifact.read_bytes() == original
    assert not list(tmp_path.glob("*.tmp"))


def test_normalizer_rejects_dot_member_and_non_file_members(tmp_path: Path) -> None:
    dot_archive = tmp_path / "dot.tar.gz"
    with tarfile.open(dot_archive, mode="w:gz") as archive:
        archive.addfile(tarfile.TarInfo("."))
    with pytest.raises(ValueError, match="unsafe sdist member path"):
        normalize_sdist(dot_archive, source_date_epoch=1_750_000_000)

    link_archive = tmp_path / "link.tar.gz"
    with tarfile.open(link_archive, mode="w:gz") as archive:
        link = tarfile.TarInfo("ronin_studio-1.2.3/link")
        link.type = tarfile.SYMTYPE
        link.linkname = "PKG-INFO"
        archive.addfile(link)
    with pytest.raises(ValueError, match="unsupported sdist member type"):
        normalize_sdist(link_archive, source_date_epoch=1_750_000_000)


@pytest.mark.parametrize("epoch", [-1, 0x1_0000_0000])
def test_normalizer_rejects_gzip_epochs_outside_uint32(tmp_path: Path, epoch: int) -> None:
    artifact = tmp_path / "valid.tar.gz"
    _write_sdist(artifact, member_name="ronin_studio-1.2.3/PKG-INFO", mtime=1)
    with pytest.raises(ValueError, match="gzip timestamp"):
        normalize_sdist(artifact, source_date_epoch=epoch)


def test_normalizer_refuses_symlink_and_non_regular_input(tmp_path: Path, monkeypatch) -> None:
    artifact = tmp_path / "link.tar.gz"
    _write_sdist(artifact, member_name="ronin_studio-1.2.3/PKG-INFO", mtime=1)
    monkeypatch.setattr(Path, "is_symlink", lambda self: self == artifact.absolute())
    with pytest.raises(ValueError, match="not a symlink"):
        normalize_sdist(artifact, source_date_epoch=1)

    monkeypatch.setattr(Path, "is_symlink", lambda _path: False)
    with pytest.raises(ValueError, match="regular file"):
        normalize_sdist(tmp_path, source_date_epoch=1)


def test_normalizer_wraps_invalid_archive_and_cleans_temporary_file(tmp_path: Path) -> None:
    artifact = tmp_path / "invalid.tar.gz"
    artifact.write_bytes(gzip.compress(b"not a tar archive"))
    with pytest.raises(ValueError, match="could not normalize sdist"):
        normalize_sdist(artifact, source_date_epoch=1)
    assert not list(tmp_path.glob("*.tmp"))


def test_normalizer_reports_unreadable_member_without_replacing_source(
    tmp_path: Path, monkeypatch
) -> None:
    artifact = tmp_path / "unreadable.tar.gz"
    _write_sdist(artifact, member_name="ronin_studio-1.2.3/PKG-INFO", mtime=1)
    original = artifact.read_bytes()
    monkeypatch.setattr(tarfile.TarFile, "extractfile", lambda *_args: None)
    with pytest.raises(ValueError, match="could not read sdist member"):
        normalize_sdist(artifact, source_date_epoch=1)
    assert artifact.read_bytes() == original
    assert not list(tmp_path.glob("*.tmp"))


def test_normalizer_cli_normalizes_and_returns_usage_error(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    artifact = tmp_path / "cli.tar.gz"
    _write_sdist(artifact, member_name="ronin_studio-1.2.3/PKG-INFO", mtime=1)
    monkeypatch.setattr(
        "sys.argv", ["normalize-release-sdist", str(artifact), "--source-date-epoch", "10"]
    )
    assert main() == 0

    monkeypatch.setattr(
        "sys.argv", ["normalize-release-sdist", str(artifact), "--source-date-epoch", "-1"]
    )
    with pytest.raises(SystemExit, match="2"):
        main()
    assert "gzip timestamp" in capsys.readouterr().err


def test_normalizer_rejects_duplicate_member_paths(tmp_path: Path) -> None:
    artifact = tmp_path / "duplicate.tar.gz"
    with tarfile.open(artifact, mode="w:gz") as archive:
        for _ in range(2):
            member = tarfile.TarInfo("ronin_studio-1.2.3/PKG-INFO")
            member.size = 5
            archive.addfile(member, io.BytesIO(b"ronin"))

    with pytest.raises(ValueError, match="duplicate sdist member path"):
        normalize_sdist(artifact, source_date_epoch=1_750_000_000)


def test_normalizer_rejects_non_tar_gz(tmp_path: Path) -> None:
    artifact = tmp_path / "artifact.zip"
    artifact.write_bytes(gzip.compress(b"not a tar"))

    with pytest.raises(ValueError, match=".tar.gz format"):
        normalize_sdist(artifact, source_date_epoch=1_750_000_000)
