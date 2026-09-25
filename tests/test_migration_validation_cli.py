import json

from studio_cli import main


def test_migrate_validate_writes_full_report(tmp_path, capsys) -> None:
    expected = tmp_path / "expected.json"
    actual = tmp_path / "actual.json"
    output = tmp_path / "report.json"
    expected.write_text(json.dumps([{"id": "a", "amount": 10.0}]), encoding="utf-8")
    actual.write_text(json.dumps([{"id": "a", "amount": 10.005}]), encoding="utf-8")
    code = main(
        [
            "migrate",
            "validate",
            "orders",
            str(expected),
            str(actual),
            "--level",
            "full",
            "--mode",
            "keyed",
            "--key",
            "id",
            "--tolerance",
            "amount=0.01",
            "--output",
            str(output),
        ]
    )
    assert code == 0
    assert "validation report written" in capsys.readouterr().out
    report = json.loads(output.read_text(encoding="utf-8"))
    assert report["status"] == "pass"


def test_migrate_export_writes_portable_script(tmp_path, capsys) -> None:
    inventory = tmp_path / "inventory.json"
    generated = tmp_path / "generated"
    exported = tmp_path / "ronin_migration.py"
    inventory.write_text(
        json.dumps(
            {
                "adapter_id": "iics",
                "adapter_version": "test",
                "artifacts": [],
                "units": [
                    {
                        "key": "iics:process:orders",
                        "kind": "process",
                        "name": "orders",
                        "state": "ready",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    assert main(["migrate", "generate", str(inventory), str(generated)]) == 0
    assert main(["migrate", "export", str(generated), "--output", str(exported)]) == 0
    assert "--source" in exported.read_text(encoding="utf-8")
    assert "portable migration script written" in capsys.readouterr().out


def test_migrate_validate_returns_nonzero_for_different_results(tmp_path) -> None:
    expected = tmp_path / "expected.json"
    actual = tmp_path / "actual.json"
    expected.write_text('[{"id": "a"}]', encoding="utf-8")
    actual.write_text('[{"id": "b"}]', encoding="utf-8")
    assert main(["migrate", "validate", "orders", str(expected), str(actual)]) == 1


def test_migrate_validate_renders_markdown_and_html(tmp_path) -> None:
    expected = tmp_path / "expected.json"
    actual = tmp_path / "actual.json"
    markdown = tmp_path / "report.md"
    html = tmp_path / "report.html"
    expected.write_text('[{"id": "a"}]', encoding="utf-8")
    actual.write_text('[{"id": "a"}]', encoding="utf-8")
    assert (
        main(
            [
                "migrate",
                "validate",
                "orders",
                str(expected),
                str(actual),
                "--format",
                "markdown",
                "--output",
                str(markdown),
            ]
        )
        == 0
    )
    assert "# Migration validation: `orders`" in markdown.read_text(encoding="utf-8")
    assert (
        main(
            [
                "migrate",
                "validate",
                "orders",
                str(expected),
                str(actual),
                "--format",
                "html",
                "--output",
                str(html),
            ]
        )
        == 0
    )
    assert "<!doctype html>" in html.read_text(encoding="utf-8")


def test_migrate_generate_and_qualify_candidate_project(tmp_path, capsys) -> None:
    inventory = tmp_path / "inventory.json"
    output = tmp_path / "generated"
    inventory.write_text(
        json.dumps(
            {
                "adapter_id": "iics",
                "adapter_version": "test",
                "artifacts": [],
                "units": [
                    {
                        "key": "iics:process:p1",
                        "kind": "process",
                        "name": "orders-process",
                        "state": "ready",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    assert main(["migrate", "generate", str(inventory), str(output)]) == 0
    assert (output / "manifest.json").is_file()
    assert main(["migrate", "qualify", str(output)]) == 0
    assert '"status":"passed"' in capsys.readouterr().out
    evidence = tmp_path / "import-evidence.json"
    assert (
        main(
            [
                "migrate",
                "import",
                str(output),
                "--target",
                "project-catalog",
                "--output",
                str(evidence),
            ]
        )
        == 0
    )
    payload = json.loads(evidence.read_text(encoding="utf-8"))
    assert payload["status"] == "importable"
    assert payload["target"] == "project-catalog"
    assert len(payload["project_digest"]) == 64


def test_migrate_promote_emits_auditable_evidence(tmp_path) -> None:
    benchmark = {
        "name": "orders",
        "warmup_runs": 1,
        "measured_runs": 3,
        "durations_ms": [10, 9, 11],
        "median_ms": 10,
        "fingerprint": "same",
    }
    baseline = tmp_path / "baseline.json"
    candidate = tmp_path / "candidate.json"
    output = tmp_path / "promotion.json"
    baseline.write_text(json.dumps(benchmark), encoding="utf-8")
    candidate.write_text(json.dumps({**benchmark, "median_ms": 9}), encoding="utf-8")
    assert (
        main(
            [
                "migrate",
                "promote",
                "candidate-1",
                str(baseline),
                str(candidate),
                "--semantic-passed",
                "--quality-passed",
                "--output",
                str(output),
            ]
        )
        == 0
    )
    report = json.loads(output.read_text(encoding="utf-8"))
    assert report["decision"]["promoted"] is True
    assert report["schema"] == "ronin.migration.optimization-evidence/v1"


def test_migrate_adapters_lists_supported_adapters(capsys) -> None:
    assert main(["migrate", "adapters"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["items"][0]["adapter_id"] == "iics"


def test_migrate_artifact_emits_safe_descriptor(tmp_path, capsys) -> None:
    source = tmp_path / "export.zip"
    source.write_bytes(b"fixture")
    assert (
        main(["migrate", "artifact", "export.zip", str(source), "--media-type", "application/zip"])
        == 0
    )
    payload = json.loads(capsys.readouterr().out)
    assert payload["name"] == "export.zip"
    assert payload["size_bytes"] == 7
    assert payload["execution"] == "not_run"
