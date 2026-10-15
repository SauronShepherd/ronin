"""Provider-neutral validation and runtime capability negotiation."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from studio_core.ir import Pipeline
from studio_core.operators import OperatorCatalog, validate_operator_pipeline

RUNTIME_CAPABILITIES: Mapping[str, frozenset[str]] = {
    "local-preview": frozenset({"batch", "sample", "schema-inference"}),
    "spark-connect": frozenset({"batch", "stream", "dataframe", "logical-plan"}),
    "spark-sdp": frozenset({"batch", "stream", "declarative", "logical-plan"}),
}


@dataclass(frozen=True, slots=True, order=True)
class CompileDiagnostic:
    code: str
    message: str
    path: str | None = None
    severity: str = "error"


@dataclass(frozen=True, slots=True)
class CompilationReport:
    runtime: str
    portable: bool
    diagnostics: tuple[CompileDiagnostic, ...] = ()
    node_count: int = 0
    edge_count: int = 0


def compile_pipeline(
    data: Mapping[str, object],
    *,
    runtime: str,
    catalog: OperatorCatalog,
) -> CompilationReport:
    """Validate a canonical pipeline without importing a runtime SDK.

    Runtime adapters may later add physical-plan checks, but this boundary
    remains deterministic and safe to call from REST, CLI and UI validation.
    """
    diagnostics: list[CompileDiagnostic] = []
    if runtime not in RUNTIME_CAPABILITIES:
        return CompilationReport(
            runtime=runtime,
            portable=False,
            diagnostics=(
                CompileDiagnostic(
                    "RONIN-DE-001",
                    f"runtime is not registered: {runtime}",
                    "runtime",
                ),
            ),
        )
    try:
        pipeline = Pipeline.from_data(data)
    except (TypeError, ValueError) as exc:
        return CompilationReport(
            runtime=runtime,
            portable=False,
            diagnostics=(CompileDiagnostic("RONIN-DE-002", str(exc), "pipeline"),),
        )

    for violation in validate_operator_pipeline(pipeline, catalog):
        diagnostics.append(
            CompileDiagnostic(
                violation.code,
                violation.message,
                violation.path,
            )
        )

    available = RUNTIME_CAPABILITIES[runtime]
    for node in pipeline.nodes:
        contract = catalog.get(node.operator)
        if contract is None:
            continue
        missing = sorted(set(contract.required_capabilities) - available)
        for capability in missing:
            diagnostics.append(
                CompileDiagnostic(
                    "RONIN-DE-003",
                    f"runtime {runtime} does not provide capability {capability}",
                    f"nodes.{node.id.value}",
                )
            )

    diagnostics.sort()
    return CompilationReport(
        runtime=runtime,
        portable=not any(item.severity == "error" for item in diagnostics),
        diagnostics=tuple(diagnostics),
        node_count=len(pipeline.nodes),
        edge_count=len(pipeline.edges),
    )


__all__ = (
    "CompileDiagnostic",
    "CompilationReport",
    "RUNTIME_CAPABILITIES",
    "compile_pipeline",
)
