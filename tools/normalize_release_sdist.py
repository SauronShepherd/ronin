"""Normalize release sdist metadata for stable, candidate-bound digests."""

from __future__ import annotations

import argparse
import gzip
import os
import stat
import tarfile
import tempfile
import zlib
from pathlib import Path, PurePosixPath


def _validate_member(member: tarfile.TarInfo) -> None:
    name = PurePosixPath(member.name)
    if (
        not member.name
        or member.name == "."
        or "\\" in member.name
        or name.is_absolute()
        or ".." in name.parts
    ):
        raise ValueError(f"unsafe sdist member path: {member.name!r}")
    if not (member.isfile() or member.isdir()):
        raise ValueError(f"unsupported sdist member type: {member.name!r}")


def normalize_sdist(path: Path, *, source_date_epoch: int) -> None:
    """Normalize tar/gzip timestamps and ownership without extracting members."""

    candidate = path.expanduser().absolute()
    if candidate.is_symlink():
        raise ValueError("sdist must be a regular file, not a symlink")
    artifact = candidate.resolve(strict=True)
    if not artifact.is_file():
        raise ValueError("sdist must be a regular file, not a symlink")
    if artifact.suffixes[-2:] != [".tar", ".gz"]:
        raise ValueError("sdist must use the .tar.gz format")
    if not 0 <= source_date_epoch <= 0xFFFFFFFF:
        raise ValueError("source_date_epoch must fit the gzip timestamp field")

    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{artifact.name}.", suffix=".tmp", dir=artifact.parent
    )
    os.close(descriptor)
    temporary = Path(temporary_name)
    try:
        with tarfile.open(artifact, mode="r:gz") as source:
            members = source.getmembers()
            names: set[str] = set()
            for member in members:
                _validate_member(member)
                if member.name in names:
                    raise ValueError(f"duplicate sdist member path: {member.name!r}")
                names.add(member.name)

            with (
                temporary.open("wb") as raw_output,
                gzip.GzipFile(
                    filename="", mode="wb", fileobj=raw_output, mtime=source_date_epoch
                ) as compressed_output,
                tarfile.open(
                    fileobj=compressed_output, mode="w", format=tarfile.PAX_FORMAT
                ) as normalized,
            ):
                for member in members:
                    record = tarfile.TarInfo(member.name)
                    record.type = member.type
                    record.mode = member.mode
                    record.uid = 0
                    record.gid = 0
                    record.uname = ""
                    record.gname = ""
                    record.mtime = source_date_epoch
                    record.pax_headers = {}
                    record.size = member.size if member.isfile() else 0
                    content = source.extractfile(member) if member.isfile() else None
                    if member.isfile() and content is None:
                        raise ValueError(f"could not read sdist member: {member.name!r}")
                    normalized.addfile(record, content)

        temporary.chmod(stat.S_IMODE(artifact.stat().st_mode))
        temporary.replace(artifact)
    except (OSError, EOFError, zlib.error, tarfile.TarError) as exc:
        raise ValueError(f"could not normalize sdist: {exc}") from exc
    finally:
        temporary.unlink(missing_ok=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("sdist", type=Path, help="setuptools .tar.gz source distribution")
    parser.add_argument("--source-date-epoch", type=int, required=True)
    args = parser.parse_args()
    try:
        normalize_sdist(args.sdist, source_date_epoch=args.source_date_epoch)
    except (OSError, ValueError) as exc:
        parser.error(str(exc))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
