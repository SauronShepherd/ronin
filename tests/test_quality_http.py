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
from studio_quality import QualityContractDigestMismatch
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

    def put_contract(self, _workspace, contract, *, now):
        del now
        self.contract = contract
        return contract

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
    state = adapter.state(WorkspaceId("ws"), body["asset"])
    assert state["latest_status"] == "passed"
    assert state["latest_run"]["results"][0]["rule_id"] == "rows"


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
    with pytest.raises(ValueError, match="contract_digest"):
        adapter.run(
            workspace,
            {"asset": asset, "rows": [], "run_id": "r1", "contract_digest": "invalid"},
            now="2026-09-21T00:00:00Z",
        )


def test_quality_http_rejects_contract_drift_before_recording_evidence() -> None:
    store = Store()
    adapter = QualityHTTPAdapter(store)
    pinned_digest = store.contract.digest
    store.contract = DataContract(
        store.contract.asset,
        "exact",
        (QualityRule(QualityRuleId("different"), "row_count", "Rows"),),
    )

    with pytest.raises(QualityContractDigestMismatch, match="contract digest mismatch"):
        adapter.run(
            WorkspaceId("ws"),
            {
                "asset": store.contract.asset.to_payload(),
                "rows": [{"id": 1}],
                "run_id": "run-stale-contract",
                "contract_digest": pinned_digest,
            },
            now="2026-09-21T00:00:00Z",
        )

    assert store.runs == []


def test_quality_contract_digest_is_canonical_and_http_pin_accepts_current_contract() -> None:
    store = Store()
    adapter = QualityHTTPAdapter(store)
    result = adapter.run(
        WorkspaceId("ws"),
        {
            "asset": store.contract.asset.to_payload(),
            "rows": [{"id": 1}],
            "run_id": "run-pinned-contract",
            "contract_digest": store.contract.digest,
        },
        now="2026-09-21T00:00:00Z",
    )

    assert result["gate_passed"] is True
    assert DataContract.from_json(store.contract.to_json()).digest == store.contract.digest
    assert len(store.runs) == 1


def test_quality_http_persists_contract() -> None:
    store = Store()
    adapter = QualityHTTPAdapter(store)
    payload = store.contract.to_payload()
    result = adapter.put_contract(WorkspaceId("ws"), payload, now="2026-09-21T00:00:00Z")
    assert result == payload
    assert store.contract.to_payload() == payload
