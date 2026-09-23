import pytest
from studio_core import (
    AssetId,
    AssetRef,
    AssetVersion,
    DataContract,
    QualityRule,
    QualityRuleId,
    WorkspaceId,
)
from studio_quality.http import QualityHTTPAdapter


class Store:
    def __init__(self):
        self.contract = DataContract(
            AssetRef(AssetId("customers"), AssetVersion("v1")),
            "exact",
            (
                QualityRule(
                    QualityRuleId("rows"),
                    "row_count",
                    "Rows",
                    parameters=(("min", "1"),),
                ),
            ),
        )
        self.runs = []

    def get_contract(self, _workspace, _asset):
        return self.contract

    def record_run(self, _workspace, run, *, now):
        del now
        self.runs.append(run)
        return run

    def list_runs(self, _workspace, _asset):
        return tuple(self.runs)


def test_quality_http_runs_and_lists_evidence() -> None:
    adapter = QualityHTTPAdapter(Store())
    body = {
        "asset": {"asset_id": "customers", "version": "v1"},
        "rows": [{"id": 1}],
        "run_id": "run-1",
    }
    result = adapter.run(WorkspaceId("ws"), body, now="2026-09-21T00:00:00Z")
    assert result["gate_passed"] is True
    assert len(adapter.history(WorkspaceId("ws"), body["asset"])) == 1
    assert adapter.state(WorkspaceId("ws"), body["asset"])["latest_status"] == "passed"


def test_quality_http_rejects_ambiguous_boolean_and_identifiers() -> None:
    store = Store()
    adapter = QualityHTTPAdapter(store)
    asset = store.contract.asset.to_payload()
    workspace = WorkspaceId("ws")
    with pytest.raises(ValueError, match="enforce_blocking"):
        adapter.run(
            workspace,
            {"asset": asset, "rows": [], "run_id": "r1", "enforce_blocking": "false"},
            now="2026-09-21T00:00:00Z",
        )
    with pytest.raises(ValueError, match="run_id"):
        adapter.run(
            workspace,
            {"asset": asset, "rows": [], "run_id": 1},
            now="2026-09-21T00:00:00Z",
        )
