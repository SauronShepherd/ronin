from __future__ import annotations

from collections.abc import Callable
from time import perf_counter

from studio_core import Edge, Node, OperatorCatalog, OperatorContract, OperatorRef, Pipeline, Port


def _elapsed(operation: Callable[[], object], iterations: int) -> float:
    started = perf_counter()
    for _ in range(iterations):
        operation()
    return perf_counter() - started


def test_node_param_lookup_budget() -> None:
    node = Node.create(
        operator=OperatorRef("transform.identity"),
        instance_key="param-budget",
        params={f"p{i:03d}": i for i in range(100)},
    )
    elapsed = _elapsed(lambda: node.param("p099"), 100_000)
    assert elapsed < 0.5


def test_operator_catalog_lookup_budget() -> None:
    catalog = OperatorCatalog(
        tuple(
            OperatorContract(OperatorRef(f"op.{i:04d}"), f"Operator {i}", "test")
            for i in range(1_000)
        )
    )
    target = OperatorRef("op.0999")
    elapsed = _elapsed(lambda: catalog.get(target), 20_000)
    assert elapsed < 0.5


def test_pipeline_fanin_construction_budget() -> None:
    source_nodes = tuple(
        Node.create(
            operator=OperatorRef("source.test"),
            instance_key=f"source-{i:04d}",
            outputs=(Port("out"),),
        )
        for i in range(800)
    )
    sink = Node.create(
        operator=OperatorRef("sink.test"),
        instance_key="sink",
        inputs=(Port("in"),),
    )
    edges = tuple(Edge(node.id, "out", sink.id, "in") for node in source_nodes)
    started = perf_counter()
    pipeline = Pipeline((*source_nodes, sink), edges)
    elapsed = perf_counter() - started
    assert len(pipeline.nodes) == 801
    assert elapsed < 0.5
