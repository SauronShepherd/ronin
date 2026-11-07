from __future__ import annotations

import hashlib
import json

import pytest

from tools.generate_release_provenance import build_provenance
from tools.generate_release_provenance import main as provenance_main
from tools.generate_release_sbom import build_sbom, verify_sbom
from tools.generate_release_sbom import main as sbom_main
from tools.supply_chain_evidence import SupplyChainEvidenceError, validate

_COMMIT = "a" * 40
_START = "2026-10-29T10:00:00+02:00"
_FINISH = "2026-10-29T10:01:00+02:00"
_TOOLCHAIN = {"python": "3.13.9", "docker_engine": "28.5.1"}


def _identity(tmp_path):
    artifact = tmp_path / "ronin-0.0.0-py3-none-any.whl"
    artifact.write_bytes(b"release-artifact")
    identity = tmp_path / "artifact-identity.json"
    identity.write_text(
        json.dumps(
            {
                "schema": "ronin.artifact-identity/v1",
                "commit": _COMMIT,
                "artifacts": [
                    {
                        "name": artifact.name,
                        "kind": "wheel",
                        "sha256": hashlib.sha256(artifact.read_bytes()).hexdigest(),
                        "size": artifact.stat().st_size,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    return identity


def _lock(tmp_path):
    lock = tmp_path / "requirements-dev.lock"
    lock.write_text(
        "# generated lock\n"
        "Demo_Package==1.2.3 \\\n"
        "    --hash=sha256:" + "b" * 64 + "\n"
        "another-package==4.5.6\n",
        encoding="utf-8",
    )
    return lock


def _generated_evidence(tmp_path):
    identity = _identity(tmp_path)
    lock = _lock(tmp_path)
    project = tmp_path / "pyproject.toml"
    project.write_text('[project]\nname = "ronin-studio"\nversion = "0.0.0"\n', encoding="utf-8")
    sbom = build_sbom(identity, lock, project_file=project)
    sbom_path = tmp_path / "ronin.cdx.json"
    sbom_path.write_text(json.dumps(sbom), encoding="utf-8")
    provenance = build_provenance(
        identity,
        build_command="python -m build --wheel --sdist",
        started_on=_START,
        finished_on=_FINISH,
        toolchain=_TOOLCHAIN,
    )
    provenance_path = tmp_path / "provenance.json"
    provenance_path.write_text(json.dumps(provenance), encoding="utf-8")
    return identity, lock, project, sbom_path, provenance_path, provenance


def test_release_sbom_is_cyclonedx_and_binds_artifact_and_locked_dependencies(tmp_path):
    identity, lock, project, sbom_path, _, _ = _generated_evidence(tmp_path)
    sbom = json.loads(sbom_path.read_text(encoding="utf-8"))

    assert sbom["bomFormat"] == "CycloneDX"
    assert sbom["specVersion"] == "1.6"
    assert sbom["metadata"]["component"]["properties"] == [
        {"name": "ronin:source-commit", "value": _COMMIT},
        {"name": "ronin:dependency-inventory", "value": lock.name},
    ]
    artifact = sbom["components"][0]
    identity_artifact = json.loads(identity.read_text(encoding="utf-8"))["artifacts"][0]
    assert artifact["type"] == "file"
    assert artifact["name"] == identity_artifact["name"]
    assert artifact["hashes"] == [{"alg": "SHA-256", "content": identity_artifact["sha256"]}]
    dependencies = {
        (component["name"], component["version"])
        for component in sbom["components"]
        if component["type"] == "library"
    }
    assert dependencies == {("demo-package", "1.2.3"), ("another-package", "4.5.6")}
    verify_sbom(sbom_path, identity, lock, expected_commit=_COMMIT)


def test_supply_chain_validator_accepts_generated_cyclonedx_and_slsa_provenance(tmp_path):
    identity, lock, _, sbom_path, provenance_path, provenance = _generated_evidence(tmp_path)

    result = validate(
        commit=_COMMIT,
        artifact_identity=identity,
        sboms=[sbom_path],
        provenance=provenance_path,
    )

    assert result["schema"] == "ronin.supply-chain-evidence/v1"
    assert result["commit"] == _COMMIT
    assert result["artifact_digests"] == {
        json.loads(identity.read_text(encoding="utf-8"))["artifacts"][0]["name"]: json.loads(
            identity.read_text(encoding="utf-8")
        )["artifacts"][0]["sha256"]
    }
    assert provenance["_type"] == "https://in-toto.io/Statement/v1"
    assert provenance["predicateType"] == "https://slsa.dev/provenance/v1"
    verify_sbom(sbom_path, identity, lock, expected_commit=_COMMIT)


@pytest.mark.parametrize("mutation", ["artifact-digest", "source-commit", "dependencies"])
def test_release_sbom_verification_rejects_tampering_and_drift(tmp_path, mutation):
    identity, lock, project, sbom_path, _, _ = _generated_evidence(tmp_path)
    sbom = json.loads(sbom_path.read_text(encoding="utf-8"))
    if mutation == "artifact-digest":
        sbom["components"][0]["hashes"][0]["content"] = "f" * 64
    elif mutation == "source-commit":
        sbom["metadata"]["component"]["properties"][0]["value"] = "b" * 40
    else:
        sbom["components"] = [
            component for component in sbom["components"] if component["type"] != "library"
        ]
    sbom_path.write_text(json.dumps(sbom), encoding="utf-8")

    expected_error = {
        "artifact-digest": "do not match",
        "source-commit": "does not match",
        "dependencies": "dependency inventory",
    }[mutation]
    with pytest.raises(ValueError, match=expected_error):
        verify_sbom(sbom_path, identity, lock, expected_commit=_COMMIT)
    assert project.exists()


def test_supply_chain_validator_rejects_name_only_and_wrong_digest_sboms(tmp_path):
    identity, _, _, sbom_path, provenance_path, _ = _generated_evidence(tmp_path)
    sbom = json.loads(sbom_path.read_text(encoding="utf-8"))
    sbom["components"][0]["hashes"] = []
    sbom_path.write_text(json.dumps(sbom), encoding="utf-8")
    with pytest.raises(SupplyChainEvidenceError, match="exactly one SHA-256"):
        validate(
            commit=_COMMIT,
            artifact_identity=identity,
            sboms=[sbom_path],
            provenance=provenance_path,
        )

    sbom["components"][0]["hashes"] = [{"alg": "SHA-256", "content": "f" * 64}]
    sbom_path.write_text(json.dumps(sbom), encoding="utf-8")
    with pytest.raises(SupplyChainEvidenceError, match="do not match artifact identity"):
        validate(
            commit=_COMMIT,
            artifact_identity=identity,
            sboms=[sbom_path],
            provenance=provenance_path,
        )


def test_slsa_provenance_rejects_wrong_candidate_and_identity_digest(tmp_path):
    identity, _, _, sbom_path, provenance_path, provenance = _generated_evidence(tmp_path)
    provenance["predicate"]["buildDefinition"]["externalParameters"]["candidateCommit"] = "b" * 40
    provenance_path.write_text(json.dumps(provenance), encoding="utf-8")
    with pytest.raises(SupplyChainEvidenceError, match="provenance commit"):
        validate(
            commit=_COMMIT,
            artifact_identity=identity,
            sboms=[sbom_path],
            provenance=provenance_path,
        )

    provenance["predicate"]["buildDefinition"]["externalParameters"]["candidateCommit"] = _COMMIT
    provenance["predicate"]["buildDefinition"]["externalParameters"]["artifactIdentitySha256"] = (
        "0" * 64
    )
    provenance_path.write_text(json.dumps(provenance), encoding="utf-8")
    with pytest.raises(SupplyChainEvidenceError, match="artifact identity file"):
        validate(
            commit=_COMMIT,
            artifact_identity=identity,
            sboms=[sbom_path],
            provenance=provenance_path,
        )


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("started_on", "2026-10-29T10:00:00", "UTC offset"),
        ("finished_on", "2026-10-29T07:00:00Z", "must not precede"),
        ("toolchain", {"token": "secret"}, "unsupported or potentially sensitive"),
    ],
)
def test_release_provenance_rejects_incomplete_or_sensitive_build_context(
    tmp_path, field, value, message
):
    identity = _identity(tmp_path)
    kwargs = {
        "build_command": "python -m build",
        "started_on": _START,
        "finished_on": _FINISH,
        "toolchain": _TOOLCHAIN,
    }
    kwargs[field] = value
    with pytest.raises(ValueError, match=message):
        build_provenance(identity, **kwargs)


def test_release_provenance_requires_valid_artifact_identity(tmp_path):
    identity = tmp_path / "bad-identity.json"
    identity.write_text("{}", encoding="utf-8")
    with pytest.raises(ValueError, match="schema"):
        build_provenance(
            identity,
            build_command="python -m build",
            started_on=_START,
            finished_on=_FINISH,
            toolchain=_TOOLCHAIN,
        )


@pytest.mark.parametrize(
    ("identity_value", "message"),
    [
        ("{", "cannot read artifact identity"),
        (
            {"schema": "ronin.artifact-identity/v1", "commit": "  bad", "artifacts": []},
            "commit",
        ),
        (
            {"schema": "ronin.artifact-identity/v1", "commit": _COMMIT, "artifacts": []},
            "must contain artifacts",
        ),
        (
            {"schema": "ronin.artifact-identity/v1", "commit": _COMMIT, "artifacts": [None]},
            "invalid artifact",
        ),
        (
            {
                "schema": "ronin.artifact-identity/v1",
                "commit": _COMMIT,
                "artifacts": [{"name": "../secret.whl", "sha256": "a" * 64}],
            },
            "invalid name or digest",
        ),
        (
            {
                "schema": "ronin.artifact-identity/v1",
                "commit": _COMMIT,
                "artifacts": [{"name": "pkg.whl", "sha256": "A" * 64}],
            },
            "invalid name or digest",
        ),
        (
            {
                "schema": "ronin.artifact-identity/v1",
                "commit": _COMMIT,
                "artifacts": [
                    {"name": "pkg.whl", "sha256": "a" * 64},
                    {"name": "pkg.whl", "sha256": "a" * 64},
                ],
            },
            "invalid name or digest",
        ),
    ],
)
def test_sbom_builder_rejects_malformed_artifact_identity(tmp_path, identity_value, message):
    identity = tmp_path / "identity.json"
    identity.write_text(
        identity_value if isinstance(identity_value, str) else json.dumps(identity_value),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match=message):
        build_provenance(
            identity,
            build_command="python -m build",
            started_on=_START,
            finished_on=_FINISH,
            toolchain=_TOOLCHAIN,
        )


def test_sbom_builder_reports_missing_identity_and_lock_files(tmp_path):
    with pytest.raises(ValueError, match="cannot read artifact identity"):
        build_provenance(
            tmp_path / "missing-identity.json",
            build_command="python -m build",
            started_on=_START,
            finished_on=_FINISH,
            toolchain=_TOOLCHAIN,
        )
    from tools.generate_release_sbom import _lock_components

    with pytest.raises(ValueError, match="cannot read dependency lock"):
        _lock_components(tmp_path / "missing.lock")


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        ("extra-file", "artifact subjects"),
        ("duplicate-file", "duplicate file component"),
        ("conflicting-file", "conflicting digests"),
        ("duplicate-library", "dependency inventory"),
        ("unknown-component", "unsupported component type"),
        ("unhashable-component-type", "unsupported component type"),
        ("invalid-hash-algorithm", "invalid hash algorithm"),
        ("invalid-hash-content", "invalid SHA-256 digest"),
        ("root-properties-not-list", "source commit"),
        ("unhashable-source-commit", "source commit"),
    ],
)
def test_sbom_verifier_rejects_unbound_or_malformed_components(tmp_path, mutation, message):
    identity, lock, _, sbom_path, _, _ = _generated_evidence(tmp_path)
    sbom = json.loads(sbom_path.read_text(encoding="utf-8"))
    libraries = [item for item in sbom["components"] if item["type"] == "library"]
    artifact = next(item for item in sbom["components"] if item["type"] == "file")
    if mutation == "extra-file":
        sbom["components"].append(
            {
                "type": "file",
                "name": "unidentified.whl",
                "hashes": [{"alg": "SHA-256", "content": "f" * 64}],
            }
        )
    elif mutation in {"duplicate-file", "conflicting-file"}:
        duplicate = json.loads(json.dumps(artifact))
        if mutation == "conflicting-file":
            duplicate["hashes"][0]["content"] = "f" * 64
        sbom["components"].append(duplicate)
    elif mutation == "duplicate-library":
        sbom["components"].append(libraries[0])
    elif mutation == "unknown-component":
        artifact["type"] = "container"
    elif mutation == "unhashable-component-type":
        artifact["type"] = []
    elif mutation == "invalid-hash-algorithm":
        artifact["hashes"][0]["alg"] = 1
    elif mutation == "invalid-hash-content":
        artifact["hashes"][0]["content"] = "not-a-sha256"
    elif mutation == "root-properties-not-list":
        sbom["metadata"]["component"]["properties"] = {}
    else:
        sbom["metadata"]["component"]["properties"][0]["value"] = []
    sbom_path.write_text(json.dumps(sbom), encoding="utf-8")

    with pytest.raises(ValueError, match=message):
        verify_sbom(sbom_path, identity, lock, expected_commit=_COMMIT)


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        ("not-a-document", "cannot read CycloneDX SBOM"),
        ("wrong-format", "CycloneDX 1.6"),
        ("wrong-bom-format", "CycloneDX 1.6"),
        ("bad-serial", "serialNumber"),
        ("missing-root", "root application component"),
        ("components-not-list", "components must be an array"),
        ("invalid-component", "invalid component"),
        ("invalid-name", "invalid name or hashes"),
        ("invalid-hash-entry", "invalid hash"),
        ("unbound-file", "artifact subjects"),
    ],
)
def test_sbom_verifier_rejects_invalid_document_shapes(tmp_path, mutation, message):
    identity, lock, _, sbom_path, _, _ = _generated_evidence(tmp_path)
    if mutation == "not-a-document":
        sbom_path.write_text("{", encoding="utf-8")
    else:
        sbom = json.loads(sbom_path.read_text(encoding="utf-8"))
        file_component = next(item for item in sbom["components"] if item["type"] == "file")
        if mutation == "wrong-format":
            sbom["specVersion"] = "1.5"
        elif mutation == "wrong-bom-format":
            sbom["bomFormat"] = "SPDX"
        elif mutation == "bad-serial":
            sbom["serialNumber"] = "urn:uuid:broken"
        elif mutation == "missing-root":
            sbom["metadata"] = {}
        elif mutation == "components-not-list":
            sbom["components"] = {}
        elif mutation == "invalid-component":
            sbom["components"][0] = "not-an-object"
        elif mutation == "invalid-name":
            file_component["name"] = None
        elif mutation == "invalid-hash-entry":
            file_component["hashes"] = [None]
        else:
            file_component["hashes"] = []
        sbom_path.write_text(json.dumps(sbom), encoding="utf-8")

    with pytest.raises(ValueError, match=message):
        verify_sbom(sbom_path, identity, lock)


@pytest.mark.parametrize(
    ("contents", "message"),
    [
        ("", "no exact name==version"),
        ("demo_package==1.0\nDemo-Package==2.0\n", "conflicting versions"),
    ],
)
def test_sbom_builder_rejects_empty_or_conflicting_lock_inventory(tmp_path, contents, message):
    identity = _identity(tmp_path)
    lock = tmp_path / "requirements.lock"
    lock.write_text(contents, encoding="utf-8")
    project = tmp_path / "pyproject.toml"
    project.write_text('[project]\nname = "ronin"\nversion = "1.0"\n', encoding="utf-8")

    with pytest.raises(ValueError, match=message):
        build_sbom(identity, lock, project_file=project)


def test_sbom_builder_preserves_conditional_lock_versions(tmp_path):
    identity = _identity(tmp_path)
    lock = tmp_path / "requirements.lock"
    lock.write_text(
        "\n".join(
            [
                "demo==1.0 ; python_full_version < '3.12'",
                "demo==2.0 ; python_full_version >= '3.12'",
                "",
            ]
        ),
        encoding="utf-8",
    )
    project = tmp_path / "pyproject.toml"
    project.write_text('[project]\nname = "ronin"\nversion = "1.0"\n', encoding="utf-8")

    components = build_sbom(identity, lock, project_file=project)["components"]
    library_components = [item for item in components if item["type"] == "library"]

    assert {(item["name"], item["version"]) for item in library_components} == {
        ("demo", "1.0"),
        ("demo", "2.0"),
    }
    markers = {
        item["version"]: {
            prop["value"]
            for prop in item["properties"]
            if prop["name"] == "ronin:environment-marker"
        }
        for item in library_components
    }
    assert markers == {
        "1.0": {"python_full_version < '3.12'"},
        "2.0": {"python_full_version >= '3.12'"},
    }


@pytest.mark.parametrize(
    "project_text",
    [
        "",
        "[tool]\nname='x'\n",
        '[project]\nname=3\nversion="1"\n',
        '[project]\nname="ronin"\nversion=" "\n',
        '[project]\nname=" ronin "\nversion="1"\n',
    ],
)
def test_sbom_builder_rejects_missing_or_invalid_project_metadata(tmp_path, project_text):
    identity, lock = _identity(tmp_path), _lock(tmp_path)
    project = tmp_path / "pyproject.toml"
    project.write_text(project_text, encoding="utf-8")

    with pytest.raises(ValueError, match="project name and version"):
        build_sbom(identity, lock, project_file=project)


def test_sbom_cli_generates_and_verifies_a_candidate_bound_document(tmp_path, monkeypatch):
    identity, lock, project, *_ = _generated_evidence(tmp_path)
    output = tmp_path / "cli-sbom.json"
    monkeypatch.setattr(
        "sys.argv",
        [
            "generate-release-sbom",
            "--artifact-identity",
            str(identity),
            "--requirements-lock",
            str(lock),
            "--project-file",
            str(project),
            "--output",
            str(output),
        ],
    )
    assert sbom_main() == 0
    monkeypatch.setattr(
        "sys.argv",
        [
            "generate-release-sbom",
            "--artifact-identity",
            str(identity),
            "--requirements-lock",
            str(lock),
            "--output",
            str(output),
            "--verify",
            "--expected-commit",
            _COMMIT,
        ],
    )
    assert sbom_main() == 0


def test_sbom_cli_reports_invalid_identity_as_usage_error(tmp_path, monkeypatch, capsys):
    lock = _lock(tmp_path)
    identity = tmp_path / "bad-identity.json"
    identity.write_text("{}", encoding="utf-8")
    output = tmp_path / "sbom.json"
    monkeypatch.setattr(
        "sys.argv",
        [
            "generate-release-sbom",
            "--artifact-identity",
            str(identity),
            "--requirements-lock",
            str(lock),
            "--output",
            str(output),
        ],
    )
    with pytest.raises(SystemExit, match="2"):
        sbom_main()
    assert "unsupported artifact identity schema" in capsys.readouterr().err
    assert not output.exists()


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("build_command", " build", "build_command"),
        ("build_command", "", "build_command"),
        ("source_uri", "file:///tmp/repo", "source_uri"),
        ("toolchain", {}, "non-empty object"),
        ("toolchain", {"python": "  "}, "non-empty strings"),
        ("toolchain", {1: "unknown"}, "unsupported or potentially sensitive"),
        ("started_on", "not-a-date", "ISO-8601"),
    ],
)
def test_provenance_rejects_invalid_command_source_toolchain_and_time(
    tmp_path, field, value, message
):
    identity = _identity(tmp_path)
    kwargs = {
        "build_command": "python -m build",
        "started_on": _START,
        "finished_on": _FINISH,
        "toolchain": _TOOLCHAIN,
    }
    kwargs[field] = value
    with pytest.raises(ValueError, match=message):
        build_provenance(identity, **kwargs)


def test_provenance_cli_writes_normalized_statement_and_handles_input_errors(tmp_path, monkeypatch):
    identity = _identity(tmp_path)
    toolchain = tmp_path / "toolchain.json"
    toolchain.write_text(json.dumps(_TOOLCHAIN), encoding="utf-8")
    output = tmp_path / "provenance.json"
    monkeypatch.setattr(
        "sys.argv",
        [
            "generate-release-provenance",
            "--artifact-identity",
            str(identity),
            "--build-command",
            "python -m build",
            "--started-on",
            _START,
            "--finished-on",
            _FINISH,
            "--toolchain-json",
            str(toolchain),
            "--source-uri",
            "git+https://github.com/SauronShepherd/ronin",
            "--output",
            str(output),
        ],
    )
    assert provenance_main() == 0
    assert json.loads(output.read_text(encoding="utf-8"))["predicate"]["runDetails"]["metadata"][
        "startedOn"
    ] == ("2026-10-29T08:00:00Z")

    toolchain.write_text("{", encoding="utf-8")
    with pytest.raises(SystemExit, match="2"):
        provenance_main()
