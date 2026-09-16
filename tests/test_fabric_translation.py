from __future__ import annotations

from studio_migration import translate_notebook_items


def test_fabric_notebook_item_translates_and_other_items_are_reported() -> None:
    result = translate_notebook_items(
        '{"id":"fabric-1","name":"Fabric flow","items":['
        '{"id":"nb-1","type":"notebook","path":"/Workspace/nb"},'
        '{"id":"pipe-1","type":"pipeline"}]}',
        source_version="2026",
    )
    assert result.workflow.pipeline.nodes[0].operator.name == "notebook.run"
    assert {item.status for item in result.report.objects} == {"translated", "unsupported"}
