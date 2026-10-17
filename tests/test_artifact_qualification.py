from __future__ import annotations

import hashlib
import json
import zipfile
from pathlib import Path
from types import SimpleNamespace

import pytest

from tools import artifact_qualification as module


def _wheel(path: Path, *, record: bytes | None = None) -> None:
    record_name = "pyronin-0.1.0a2.dist-info/RECORD"
    payload = record or f"pyronin/__init__.py,,\n{record_name},,\n".encode()
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("pyronin/__init__.py", "__version__='0.1.0a2'\n")
        archive.writestr(record_name, payload)


def _wheel_with_record(path: Path, record_name: str, record: bytes) -> None:
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr(record_name, record)


def test_artifact_record_binds_exact_bytes_and_record(tmp_path: Path) -> None:
    wheel = tmp_path / "pyronin-0.1.0a2-py3-none-any.whl"
    sdist = tmp_path / "pyronin-0.1.0a2.tar.gz"
    _wheel(wheel)
    sdist.write_bytes(b"sdist")
    result = module.artifact_record(wheel, sdist)
    assert result["package"] == "pyronin"
    assert result["version"] == "0.1.0a2"
    assert result["wheel"]["sha256"] == hashlib.sha256(wheel.read_bytes()).hexdigest()
    assert result["sdist"]["sha256"] == hashlib.sha256(b"sdist").hexdigest()
    assert len(result["wheel_record_sha256"]) == 64
    assert json.loads(module._canonical_json(result)) == result


def test_origin_must_be_site_packages_and_outside_checkout(tmp_path: Path) -> None:
    checkout = tmp_path / "repo"
    site = tmp_path / "isolated" / "site-packages"
    checkout.mkdir()
    site.mkdir(parents=True)
    good = site / "pyronin.py"
    good.write_text("x=1")
    resolved = module.assert_installed_origin(good, checkout=checkout, site_packages=site)
    assert resolved == good.resolve()
    leaked = checkout / "pyronin.py"
    leaked.write_text("x=1")
    with pytest.raises(module.ArtifactQualificationError, match="leaked"):
        module.assert_installed_origin(leaked, checkout=checkout, site_packages=site)
    alien = tmp_path / "alien.py"
    alien.write_text("x=1")
    with pytest.raises(module.ArtifactQualificationError, match="outside isolated"):
        module.assert_installed_origin(alien, checkout=checkout, site_packages=site)


def test_qualification_record_is_machine_path_independent(tmp_path: Path) -> None:
    candidate = {"schema": "ronin.python-artifact-candidate/v1", "package": "pyronin"}
    results: list[dict[str, object]] = []
    for root_name in ("runner-a", "different-host-root"):
        site = tmp_path / root_name / "site-packages"
        module_path = site / "pyronin" / "__init__.py"
        module_path.parent.mkdir(parents=True)
        module_path.write_text("__version__='0.1.0a2'\n")
        results.append(
            module._record_qualification(
                candidate,
                imported_module=module_path.resolve(),
                site_packages=site,
            )
        )
    assert results[0] == results[1]
    assert results[0]["qualification"] == {
        "contract_tests": "passed",
        "import_origin": "isolated-site-packages",
        "module_path": "pyronin/__init__.py",
    }
    assert str(tmp_path) not in module._canonical_json(results[0])


def test_license_binding_uses_artifact_digest_not_installed_metadata(tmp_path: Path) -> None:
    artifact = tmp_path / "dep.whl"
    artifact.write_bytes(b"candidate")
    digest = module.sha256_file(artifact)
    inventory = {
        "schema_version": 1,
        "packages": [
            {
                "package": "Demo_Pkg",
                "version": "2.0",
                "evidence_sha256": "a" * 64,
            }
        ],
    }
    result = module.bind_license_evidence(
        package="demo-pkg", version="2.0", artifact_sha256=digest, inventory=inventory
    )
    assert result == {
        "package": "demo-pkg",
        "version": "2.0",
        "artifact_sha256": digest,
        "license_evidence_sha256": "a" * 64,
    }


def test_license_binding_fails_closed_on_missing_or_bad_evidence() -> None:
    with pytest.raises(module.ArtifactQualificationError, match="found 0"):
        module.bind_license_evidence(
            package="x",
            version="1",
            artifact_sha256="b" * 64,
            inventory={"schema_version": 1, "packages": []},
        )
    with pytest.raises(module.ArtifactQualificationError, match="invalid evidence"):
        module.bind_license_evidence(
            package="x",
            version="1",
            artifact_sha256="b" * 64,
            inventory={
                "schema_version": 1,
                "packages": [{"package": "x", "version": "1", "evidence_sha256": "bad"}],
            },
        )


def test_work_root_inside_checkout_is_rejected(tmp_path: Path) -> None:
    checkout = tmp_path / "repo"
    checkout.mkdir()
    inside = checkout / "work"
    inside.mkdir()
    with pytest.raises(module.ArtifactQualificationError, match="outside checkout"):
        module.qualify_pyronin(checkout, inside)


def test_single_artifact_rejects_zero_and_multiple_matches(tmp_path: Path) -> None:
    with pytest.raises(module.ArtifactQualificationError, match="found 0"):
        module._single_artifact(tmp_path, ".whl")

    (tmp_path / "a.whl").write_bytes(b"a")
    (tmp_path / "b.whl").write_bytes(b"b")
    with pytest.raises(module.ArtifactQualificationError, match="found 2"):
        module._single_artifact(tmp_path, ".whl")


@pytest.mark.parametrize(
    ("record_name", "record", "message"),
    [
        ("pyronin-1.dist-info/RECORD", b"", "malformed"),
        ("pyronin-1.dist-info/RECORD", b"\xff", "not UTF-8"),
    ],
)
def test_wheel_metadata_rejects_malformed_record_identity(
    tmp_path: Path, record_name: str, record: bytes, message: str
) -> None:
    wheel = tmp_path / "candidate.whl"
    _wheel_with_record(wheel, record_name, record)

    with pytest.raises(module.ArtifactQualificationError, match=message):
        module._wheel_metadata(wheel)


def test_wheel_metadata_requires_one_record(tmp_path: Path) -> None:
    wheel = tmp_path / "candidate.whl"
    _wheel_with_record(wheel, "pyronin-1.dist-info/not-record", b"ignored")

    with pytest.raises(module.ArtifactQualificationError, match="exactly one wheel RECORD"):
        module._wheel_metadata(wheel)


def test_license_binding_rejects_invalid_inventory_shapes_and_ambiguity() -> None:
    digest = "b" * 64
    with pytest.raises(module.ArtifactQualificationError, match="artifact_sha256"):
        module.bind_license_evidence(
            package="x", version="1", artifact_sha256="B" * 64, inventory={}
        )
    with pytest.raises(module.ArtifactQualificationError, match="schema_version"):
        module.bind_license_evidence(package="x", version="1", artifact_sha256=digest, inventory=[])
    with pytest.raises(module.ArtifactQualificationError, match="packages must be a list"):
        module.bind_license_evidence(
            package="x",
            version="1",
            artifact_sha256=digest,
            inventory={"schema_version": 1, "packages": {}},
        )
    with pytest.raises(module.ArtifactQualificationError, match="entry must be an object"):
        module.bind_license_evidence(
            package="x",
            version="1",
            artifact_sha256=digest,
            inventory={"schema_version": 1, "packages": [None]},
        )
    entry = {"package": "x", "version": "1", "evidence_sha256": "a" * 64}
    with pytest.raises(module.ArtifactQualificationError, match="found 2"):
        module.bind_license_evidence(
            package="x",
            version="1",
            artifact_sha256=digest,
            inventory={"schema_version": 1, "packages": [entry, entry]},
        )


def test_qualification_record_rejects_module_outside_site_packages(tmp_path: Path) -> None:
    site = tmp_path / "site-packages"
    site.mkdir()
    outside = tmp_path / "pyronin.py"
    outside.write_text("x=1", encoding="utf-8")

    with pytest.raises(module.ArtifactQualificationError, match="outside isolated"):
        module._record_qualification({}, imported_module=outside, site_packages=site)


def test_run_raises_with_command_and_exit_code(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(
        module.subprocess,
        "run",
        lambda *_args, **_kwargs: SimpleNamespace(returncode=7),
    )

    with pytest.raises(module.ArtifactQualificationError, match="exit code 7"):
        module._run(["build"], cwd=tmp_path)


def _mock_successful_qualification(
    monkeypatch: pytest.MonkeyPatch, checkout: Path
) -> list[list[str]]:
    package_root = checkout / "packages" / "pyronin"
    (package_root / "tests").mkdir(parents=True)
    (package_root / "tests" / "test_contract.py").write_text("def test_contract(): pass\n")
    commands: list[list[str]] = []

    def fake_run(argv: list[str], *, _cwd: Path | None = None) -> None:
        commands.append(argv)
        if "build" in argv:
            outdir = Path(argv[argv.index("--outdir") + 1])
            _wheel(outdir / "pyronin-0.1.0a2-py3-none-any.whl")
            (outdir / "pyronin-0.1.0a2.tar.gz").write_bytes(b"sdist")

    monkeypatch.setattr(module, "_run", fake_run)

    def fake_subprocess_run(_argv: list[str], **kwargs: object) -> SimpleNamespace:
        if kwargs.get("capture_output"):
            target = Path(str(kwargs["env"]["PYTHONPATH"]))
            imported = target / "pyronin" / "__init__.py"
            imported.parent.mkdir(parents=True)
            imported.write_text("__version__='0.1.0a2'\n", encoding="utf-8")
            return SimpleNamespace(returncode=0, stdout=str(imported), stderr="")
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(module.subprocess, "run", fake_subprocess_run)
    return commands


def test_qualify_pyronin_builds_installs_and_runs_isolated_contract_tests(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    checkout = tmp_path / "checkout"
    checkout.mkdir()
    work_root = tmp_path / "qualification"
    work_root.mkdir()
    commands = _mock_successful_qualification(monkeypatch, checkout)

    result = module.qualify_pyronin(checkout, work_root)

    assert result["package"] == "pyronin"
    assert result["qualification"]["module_path"] == "pyronin/__init__.py"
    assert len(commands) == 2
    assert "--no-index" in commands[1]
    assert "--no-deps" in commands[1]
    assert (work_root / "contract-tests" / "test_contract.py").is_file()


def test_qualify_pyronin_fails_closed_when_installed_import_probe_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    checkout = tmp_path / "checkout"
    checkout.mkdir()
    work_root = tmp_path / "qualification"
    work_root.mkdir()
    _mock_successful_qualification(monkeypatch, checkout)
    monkeypatch.setattr(
        module.subprocess,
        "run",
        lambda *_args, **_kwargs: SimpleNamespace(returncode=1, stdout="", stderr="import failed"),
    )

    with pytest.raises(module.ArtifactQualificationError, match="import probe failed"):
        module.qualify_pyronin(checkout, work_root)


def test_qualify_pyronin_fails_when_installed_contract_tests_fail(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    checkout = tmp_path / "checkout"
    checkout.mkdir()
    work_root = tmp_path / "qualification"
    work_root.mkdir()
    _mock_successful_qualification(monkeypatch, checkout)
    calls = 0

    def fail_contract_tests(_argv: list[str], **kwargs: object) -> SimpleNamespace:
        nonlocal calls
        calls += 1
        if kwargs.get("capture_output"):
            target = Path(str(kwargs["env"]["PYTHONPATH"]))
            imported = target / "pyronin" / "__init__.py"
            imported.parent.mkdir(parents=True)
            imported.write_text("__version__='0.1.0a2'\n", encoding="utf-8")
            return SimpleNamespace(returncode=0, stdout=str(imported), stderr="")
        return SimpleNamespace(returncode=2)

    monkeypatch.setattr(module.subprocess, "run", fail_contract_tests)

    with pytest.raises(module.ArtifactQualificationError, match="contract tests failed"):
        module.qualify_pyronin(checkout, work_root)


def test_cli_writes_json_to_requested_output(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    checkout = tmp_path / "checkout"
    checkout.mkdir()
    output = tmp_path / "qualification.json"
    work_root = tmp_path / "work"
    expected = {"schema": "ronin.python-artifact-candidate/v1", "package": "pyronin"}
    monkeypatch.setattr(module, "qualify_pyronin", lambda *_args: expected)

    assert (
        module.main(
            ["--checkout", str(checkout), "--work-root", str(work_root), "--output", str(output)]
        )
        == 0
    )

    assert json.loads(output.read_text(encoding="utf-8")) == expected
    assert work_root.is_dir()


def test_cli_uses_temporary_work_root_and_writes_stdout(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    checkout = tmp_path / "checkout"
    checkout.mkdir()
    expected = {"package": "pyronin"}
    monkeypatch.setattr(module, "qualify_pyronin", lambda *_args: expected)

    assert module.main(["--checkout", str(checkout)]) == 0

    assert json.loads(capsys.readouterr().out) == expected
