from __future__ import annotations

import json
from types import SimpleNamespace

import pytest
from studio_cli import main
from studio_cli.retention import _RetentionStores, _unreviewed_plugins, run_artifact_retention


def test_artifact_retention_preview_is_read_only_and_reports_snapshot_quality(
    monkeypatch, tmp_path, capsys
) -> None:
    monkeypatch.setenv("RONIN_DB", str(tmp_path / "ronin.sqlite3"))
    monkeypatch.setenv("RONIN_STORAGE_BACKEND", "sqlite")
    monkeypatch.setattr("studio_cli.retention._unreviewed_plugins", lambda _host: ())

    assert main(["artifacts", "retention", "preview"]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result == {
        "backend": "sqlite",
        "candidate_digests": [],
        "collection_ready": False,
        "inventory_truncated": False,
        "live_reference_count": 0,
        "missing_sources": [],
        "mode": "preview",
        "schema": "ronin.artifact-retention-result/v1",
        "snapshot_consistent": False,
        "unreviewed_plugins": [],
    }


def test_unreviewed_plugin_inventory_is_sorted_and_fails_closed() -> None:
    host = SimpleNamespace(
        plan=SimpleNamespace(
            records=[
                SimpleNamespace(manifest=SimpleNamespace(id="z.third-party")),
                SimpleNamespace(manifest=SimpleNamespace(id="com.sauronshepherd.ronin.ml-studio")),
                SimpleNamespace(manifest=SimpleNamespace(id="a.third-party")),
            ]
        )
    )

    assert _unreviewed_plugins(host) == ("a.third-party", "z.third-party")


def test_missing_plugin_inventory_fails_closed() -> None:
    assert _unreviewed_plugins(SimpleNamespace(plan=None)) == ("plugin-inventory-unavailable",)


def test_collection_refuses_unreviewed_plugins_and_closes_plugin_host(monkeypatch) -> None:
    monkeypatch.setenv("RONIN_STORAGE_BACKEND", "postgres")
    closed = False

    class PluginHostStub:
        def stop(self) -> None:
            nonlocal closed
            closed = True

    stores = _RetentionStores(
        artifact_store=None,
        workspaces=None,
        catalog=None,
        ml_registry=None,
        jobs=None,
        connector_checkpoints=None,
        data_engineering_revisions=None,
        query_evidence=None,
        synthetic_exports=None,
        barrier=object(),
        plugin_host=PluginHostStub(),
        unreviewed_plugins=("example.unknown-plugin",),
    )
    monkeypatch.setattr(
        "studio_cli.retention._stores_from_environment", lambda: (stores, "postgres")
    )

    with pytest.raises(ValueError, match="unreviewed plugins: example.unknown-plugin"):
        run_artifact_retention("collect", confirmed=True)
    assert closed


def test_artifact_retention_collection_requires_explicit_confirmation(monkeypatch, capsys) -> None:
    monkeypatch.setenv("RONIN_STORAGE_BACKEND", "sqlite")

    assert main(["artifacts", "retention", "collect"]) == 2
    assert "requires the explicit --confirm flag" in capsys.readouterr().err


def test_artifact_retention_collection_requires_postgres_coordination(
    monkeypatch, tmp_path, capsys
) -> None:
    monkeypatch.setenv("RONIN_DB", str(tmp_path / "ronin.sqlite3"))
    monkeypatch.setenv("RONIN_STORAGE_BACKEND", "sqlite")

    assert main(["artifacts", "retention", "collect", "--confirm"]) == 2
    assert "requires RONIN_STORAGE_BACKEND=postgres" in capsys.readouterr().err


def test_artifact_retention_empty_live_set_opt_in_is_collect_only(monkeypatch, capsys) -> None:
    monkeypatch.setenv("RONIN_STORAGE_BACKEND", "sqlite")

    assert main(["artifacts", "retention", "preview", "--allow-empty-live-set"]) == 2
    assert "only valid with collect" in capsys.readouterr().err


def test_artifact_retention_bounds_are_validated(monkeypatch, tmp_path, capsys) -> None:
    monkeypatch.setenv("RONIN_DB", str(tmp_path / "ronin.sqlite3"))
    monkeypatch.setenv("RONIN_STORAGE_BACKEND", "sqlite")

    assert main(["artifacts", "retention", "preview", "--page-size", "0"]) == 2
    assert "page_size must be between" in capsys.readouterr().err
