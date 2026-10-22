"""Guard the artifact write paths reviewed by global retention."""

from __future__ import annotations

import ast
from collections import Counter
from pathlib import Path

_PYTHON_ROOT = Path(__file__).resolve().parents[1] / "python"
_REVIEWED_PUT_BYTES_CALLS = {
    "studio_connectors/sync.py::write": 1,
    "studio_data_engineering/evidence.py::persist_pipeline_evidence": 1,
    "studio_data_engineering/evidence.py::persist_query_engine_evidence": 1,
    "studio_data_engineering/revisions.py::_import_sdp": 3,
    "studio_ml/orchestration.py::_create": 1,
    "studio_ml/orchestration.py::_save_node_checkpoint": 1,
    "studio_ml/orchestration.py::save_plugin_stage_checkpoint": 1,
    "studio_ml/orchestration.py::_materialize_result_artifact": 1,
    "studio_ml/service.py::persist_clustering_result": 1,
    "studio_ml/service.py::register_clustering_model": 1,
    "studio_ml/service.py::train_register_tabular": 1,
    "studio_ml/registry_bundle.py::_commit_ml_registry_bundle_import": 1,
    "studio_storage/local_files.py::ingest": 1,
    "studio_synthetic_data/plugin.py::export": 1,
    "studio_worker/execution.py::_checkpoint_under_lease": 1,
    "studio_worker/execution.py::_run_scheduler_result_under_lease": 1,
}


class _PutBytesCallVisitor(ast.NodeVisitor):
    def __init__(
        self, path: Path, calls: Counter[str], pipeline_evidence_calls: Counter[str]
    ) -> None:
        self.path = path
        self.calls = calls
        self.pipeline_evidence_calls = pipeline_evidence_calls
        self.functions: list[str] = []

    def visit_FunctionDef(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        self.functions.append(node.name)
        self.generic_visit(node)
        self.functions.pop()

    visit_AsyncFunctionDef = visit_FunctionDef

    def visit_Call(self, node: ast.Call) -> None:
        function_name = (
            node.func.id
            if isinstance(node.func, ast.Name)
            else node.func.attr
            if isinstance(node.func, ast.Attribute)
            else None
        )
        if function_name == "persist_pipeline_evidence":
            self.pipeline_evidence_calls["persist_pipeline_evidence"] += 1
        if isinstance(node.func, ast.Attribute) and node.func.attr == "put_bytes":
            function = ".".join(self.functions) or "<module>"
            relative_path = self.path.relative_to(_PYTHON_ROOT).as_posix()
            self.calls[f"{relative_path}::{function}"] += 1
        self.generic_visit(node)


def test_product_artifact_writes_match_the_reviewed_retention_inventory() -> None:
    calls: Counter[str] = Counter()
    pipeline_evidence_calls: Counter[str] = Counter()
    for path in sorted(_PYTHON_ROOT.rglob("*.py")):
        visitor = _PutBytesCallVisitor(path, calls, pipeline_evidence_calls)
        visitor.visit(ast.parse(path.read_text(encoding="utf-8")))

    assert dict(calls) == _REVIEWED_PUT_BYTES_CALLS
    assert pipeline_evidence_calls == Counter()
